"""iGaming news scraper: pulls RSS feeds and writes news.json/news.js."""
import json
import re
from calendar import timegm
from datetime import datetime, timezone
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser

FEEDS = {
    "SBC News": "https://sbcnews.co.uk/feed/",
    "iGaming Business": "https://www.igamingbusiness.com/feed/",
    "EGR Global": "https://egr.global/feed/",
    "Gambling Insider": "https://www.gamblinginsider.com/rss",
    "CalvinAyre": "https://calvinayre.com/feed/",
    "Gaming Intelligence": "https://www.gamingintelligence.com/feed/",
    "iGamingNext": "https://next.io/feed/",
    "Legal Sports Report": "https://www.legalsportsreport.com/feed/",
    "Covers": "https://www.covers.com/feed",
    "Gaming Today": "https://www.gamingtoday.com/feed/",
    "Casino.org": "https://www.casino.org/news/feed/",
    "Yogonet": "https://www.yogonet.com/international/rss",
    "Asia Gaming Brief": "https://agbrief.com/feed/",
    "Inside Asian Gaming": "https://www.asgam.com/index.php/feed/",
    "Gambling News": "https://www.gamblingnews.com/feed/",
    "SBC Noticias": "https://www.sbcnoticias.com/feed/",
    "iGamingToday": "https://www.igamingtoday.com/feed/",
    "InterGame Online": "https://www.intergameonline.com/rss/igaming/news",
    "iGaming Expert": "https://igamingexpert.com/feed/",
    "European Gaming": "https://europeangaming.eu/portal/feed/",
}

MAX_PER_FEED = 20
MAX_IMAGE_LOOKUPS = 120
IMAGE_WORKERS = 8

def clean(text, limit=220):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")

def valid_url(url):
    return url if urlparse(url or "").scheme in {"http", "https"} else ""

def to_iso(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return None
    return datetime.fromtimestamp(timegm(parsed), timezone.utc).isoformat()

def image_url(entry):
    for key in ("media_content", "media_thumbnail"):
        for media in entry.get(key, []) or []:
            url = valid_url(media.get("url"))
            if url:
                return url
    for enclosure in entry.get("enclosures", []) or []:
        url = valid_url(enclosure.get("href") or enclosure.get("url"))
        if url and (enclosure.get("type", "").startswith("image/") or re.search(r"\.(jpg|jpeg|png|webp)(\?|$)", url, re.I)):
            return url
    html = entry.get("summary") or entry.get("description") or ""
    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html, re.I)
    return valid_url(match.group(1)) if match else ""

def page_image(url):
    """Fallback: extract the publisher's Open Graph/Twitter image from the article page."""
    try:
        req = Request(url, headers={
            "User-Agent": "Mozilla/5.0 (compatible; iGamingNewsBot/1.0)",
            "Accept": "text/html,application/xhtml+xml",
        })
        with urlopen(req, timeout=8) as response:
            html = response.read(750_000).decode("utf-8", errors="ignore")
    except Exception as exc:
        print(f"[image-skip] {url}: {exc}")
        return ""

    patterns = [
        r'<meta[^>]+property=["\\\']og:image(?::secure_url)?["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
        r'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+property=["\\\']og:image(?::secure_url)?["\\\']',
        r'<meta[^>]+name=["\\\']twitter:image(?::src)?["\\\'][^>]+content=["\\\']([^"\\\']+)["\\\']',
        r'<meta[^>]+content=["\\\']([^"\\\']+)["\\\'][^>]+name=["\\\']twitter:image(?::src)?["\\\']',
        r'"image"\\s*:\\s*"([^"]+\\.(?:jpg|jpeg|png|webp)(?:\\?[^"]*)?)"',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, re.I)
        if match:
            image = valid_url(urljoin(url, match.group(1).replace("\\\\/", "/")))
            if image:
                return image
    return ""


def enrich_images(items):
    missing = [item for item in items if not item.get("image")][:MAX_IMAGE_LOOKUPS]
    if not missing:
        return
    print(f"[images] Looking up article images for {len(missing)} items…")
    with ThreadPoolExecutor(max_workers=IMAGE_WORKERS) as pool:
        futures = {pool.submit(page_image, item["link"]): item for item in missing}
        for future in as_completed(futures):
            item = futures[future]
            try:
                item["image"] = future.result()
            except Exception as exc:
                print(f"[image-skip] {item['link']}: {exc}")


def main():
    items, seen = [], set()
    for source, url in FEEDS.items():
        try:
            feed = feedparser.parse(url, agent="Mozilla/5.0 (compatible; iGamingNewsBot/1.0)")
        except Exception as exc:
            print(f"[skip] {source}: {exc}")
            continue
        if getattr(feed, "bozo", False) and not feed.entries:
            print(f"[skip] {source}: could not read feed")
            continue
        added = 0
        for entry in feed.entries[:MAX_PER_FEED]:
            link = valid_url(entry.get("link"))
            title = clean(entry.get("title"), 160)
            date = to_iso(entry)
            if not link or not title or not date or link in seen:
                continue
            seen.add(link)
            items.append({
                "title": title,
                "link": link,
                "summary": clean(entry.get("summary") or entry.get("description")),
                "source": source,
                "date": date,
                "image": image_url(entry),
            })
            added += 1
        print(f"[ok] {source}: added {added} entries")
    items.sort(key=lambda item: item["date"], reverse=True)
    enrich_images(items)
    data = {"updated": datetime.now(timezone.utc).isoformat(), "items": items}
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    with open("news.js", "w", encoding="utf-8") as f:
        f.write("window.NEWS = " + json.dumps(data, ensure_ascii=False) + ";\n")
    print(f"Saved {len(items)} articles to news.json and news.js")

if __name__ == "__main__":
    main()
