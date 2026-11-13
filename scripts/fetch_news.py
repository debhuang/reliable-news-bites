"""Fetch RSS feeds listed in feeds.json and write docs/news.json.

Groups stories by category, removes duplicates, keeps only recent stories,
and stores just the headline, a short summary and the link to the original
article (no full-text scraping).

Usage: python scripts/fetch_news.py [--feeds feeds.json] [--out docs/news.json]
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser

ROOT = Path(__file__).resolve().parent.parent
USER_AGENT = "Mozilla/5.0 (compatible; reliable-news-bites/1.0; daily RSS reader)"
TIMEOUT_SECONDS = 20
MAX_AGE_HOURS = 48          # drop stories older than this
MAX_PER_CATEGORY = 40       # cap the list length per category
MAX_PER_SOURCE = 12         # stop one busy feed from crowding out the rest
SUMMARY_CHARS = 280

TRACKING_PARAMS = re.compile(r"^(utm_|fbclid$|gclid$|mc_|ref$|cmpid$)", re.I)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def fetch_feed(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
        return resp.read()


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    return SPACE_RE.sub(" ", text).strip()


def shorten(text: str, limit: int = SUMMARY_CHARS) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0].rstrip(",.;:-–— ")
    return cut + "…"


def normalize_url(url: str) -> str:
    """Strip tracking params and fragments so the same story dedupes."""
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query) if not TRACKING_PARAMS.match(k)]
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), urlencode(query), ""))


def title_key(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc)
    return None


def parse_entries(feed_name: str, data: bytes) -> list[dict]:
    parsed = feedparser.parse(data)
    stories = []
    for entry in parsed.entries:
        title = clean_text(entry.get("title"))
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        source = feed_name
        summary = clean_text(entry.get("summary") or entry.get("description"))

        # Google News: headline is "Title - Publisher" and the summary just repeats it.
        if "news.google.com" in link:
            publisher = clean_text((entry.get("source") or {}).get("title"))
            if publisher:
                source = publisher
                suffix = f" - {publisher}"
                if title.endswith(suffix):
                    title = title[: -len(suffix)]
            summary = ""

        # Hacker News feeds only carry "Article URL / Comments URL" boilerplate.
        if summary.startswith("Article URL:"):
            summary = ""

        if summary and title_key(summary).startswith(title_key(title)):
            summary = summary[len(title):].strip(" -–—:")

        published = entry_time(entry)
        stories.append(
            {
                "title": title,
                "link": link,
                "source": source,
                "summary": shorten(summary),
                "published": published.isoformat() if published else None,
            }
        )
    return stories


def build_category(category: dict, results: dict[str, list[dict]], now: datetime) -> list[dict]:
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)
    seen_links: set[str] = set()
    seen_titles: set[str] = set()
    per_source: dict[str, int] = {}
    stories: list[dict] = []

    candidates = []
    for feed in category["feeds"]:
        candidates.extend(results.get(feed["url"], []))

    # Newest first; undated stories go last.
    candidates.sort(key=lambda s: s["published"] or "", reverse=True)

    for story in candidates:
        if story["published"] and datetime.fromisoformat(story["published"]) < cutoff:
            continue
        link_key = normalize_url(story["link"])
        t_key = title_key(story["title"])
        if link_key in seen_links or t_key in seen_titles:
            continue
        if per_source.get(story["source"], 0) >= MAX_PER_SOURCE:
            continue
        seen_links.add(link_key)
        seen_titles.add(t_key)
        per_source[story["source"]] = per_source.get(story["source"], 0) + 1
        stories.append(story)
        if len(stories) >= MAX_PER_CATEGORY:
            break
    return stories


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--feeds", type=Path, default=ROOT / "feeds.json")
    parser.add_argument("--out", type=Path, default=ROOT / "docs" / "news.json")
    args = parser.parse_args()

    config = json.loads(args.feeds.read_text(encoding="utf-8"))
    feeds = {f["url"]: f["name"] for c in config["categories"] for f in c["feeds"]}

    def load(url: str):
        try:
            return url, parse_entries(feeds[url], fetch_feed(url)), None
        except Exception as exc:  # one broken feed must not stop the rest
            return url, [], f"{type(exc).__name__}: {exc}"

    results: dict[str, list[dict]] = {}
    failed: list[dict] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for url, stories, error in pool.map(load, feeds):
            results[url] = stories
            status = f"FAILED ({error})" if error else f"{len(stories)} stories"
            print(f"  {feeds[url]:<16} {status}")
            if error:
                failed.append({"name": feeds[url], "url": url, "error": error})

    if len(failed) == len(feeds):
        print("Every feed failed; keeping the previous news.json.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    output = {
        "generated_at": now.isoformat(timespec="seconds"),
        "categories": [
            {
                "id": c["id"],
                "label": c["label"],
                "stories": build_category(c, results, now),
            }
            for c in config["categories"]
        ],
        "failed_feeds": [f["name"] for f in failed],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    total = sum(len(c["stories"]) for c in output["categories"])
    print(f"Wrote {total} stories to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
