"""iGaming news scraper: pulls RSS feeds and writes news.json/news.js.

Setup:  python -m pip install feedparser
Run:    python scraper.py
"""

import json
import re
from calendar import timegm
from datetime import datetime, timezone

import feedparser

FEEDS = {
    "iGamingBusiness": "https://www.igamingbusiness.com/feed/",
    "SBC News": "https://sbcnews.co.uk/feed/",
    "Gambling Insider": "https://www.gamblinginsider.com/rss",
    "Casino.org": "https://www.casino.org/news/feed/",
    "Legal Sports Report": "https://www.legalsportsreport.com/feed/",
}

MAX_PER_FEED = 25


def clean(text, limit=220):
    text = re.sub(r"<[^>]+>", "", text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def to_iso(entry):
    parsed = entry.get("published_parsed") or entry.get("updated_parsed")
    if not parsed:
        return datetime.now(timezone.utc).isoformat()
    # RSS parsed times are UTC-like struct_time values; timegm avoids
    # applying the GitHub runner's local timezone during conversion.
    return datetime.fromtimestamp(timegm(parsed), timezone.utc).isoformat()


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
            link = entry.get("link")
            title = clean(entry.get("title"), 160)
            if not link or not title or link in seen:
                continue

            seen.add(link)
            items.append({
                "title": title,
                "link": link,
                "summary": clean(entry.get("summary") or entry.get("description")),
                "source": source,
                "date": to_iso(entry),
            })
            added += 1

        print(f"[ok] {source}: added {added} entries")

    items.sort(key=lambda item: item["date"], reverse=True)

    data = {
        "updated": datetime.now(timezone.utc).isoformat(),
        "items": items,
    }

    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # Keep the site fully static: index.html can load news without a server.
    with open("news.js", "w", encoding="utf-8") as f:
        f.write("window.NEWS = " + json.dumps(data, ensure_ascii=False) + ";\n")

    print(f"Saved {len(items)} articles to news.json and news.js")


if __name__ == "__main__":
    main()
