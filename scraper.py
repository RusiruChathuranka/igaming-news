"""iGaming news scraper: pulls RSS feeds and writes news.json.

Setup:  pip install feedparser
Run:    python scraper.py
"""
import json
import re
import time
from datetime import datetime, timezone

import feedparser

# Verify each URL in a browser; add or remove sources freely.
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
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if not t:
        return datetime.now(timezone.utc).isoformat()
    return datetime.fromtimestamp(time.mktime(t), timezone.utc).isoformat()


def main():
    items, seen = [], set()
    for source, url in FEEDS.items():
        feed = feedparser.parse(url, agent="Mozilla/5.0 (iGamingNewsBot)")
        if feed.bozo and not feed.entries:
            print(f"[skip] {source}: could not read feed")
            continue
        for e in feed.entries[:MAX_PER_FEED]:
            link = e.get("link")
            if not link or link in seen:
                continue
            seen.add(link)
            items.append({
                "title": clean(e.get("title"), 160),
                "link": link,
                "summary": clean(e.get("summary")),
                "source": source,
                "date": to_iso(e),
            })
        print(f"[ok] {source}: {len(feed.entries)} entries")

    items.sort(key=lambda x: x["date"], reverse=True)
    data = {"updated": datetime.now(timezone.utc).isoformat(), "items": items}
    with open("news.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    # news.js lets index.html show articles even when opened directly (no server)
    with open("news.js", "w", encoding="utf-8") as f:
        f.write("window.NEWS = " + json.dumps(data, ensure_ascii=False) + ";")
    print(f"Saved {len(items)} articles to news.json and news.js")


if __name__ == "__main__":
    main()
