from dataclasses import dataclass

import feedparser
import httpx
import trafilatura

from .config import Feed


@dataclass
class Article:
    title: str
    url: str
    published: str
    content: str
    source: str
    category: str
    trust: float


def fetch_all(feeds: list[Feed], per_feed_limit: int = 12) -> list[Article]:
    out: list[Article] = []
    headers = {"User-Agent": "NewsToMe/0.6 (+https://github.com/)"}
    with httpx.Client(timeout=15, follow_redirects=True, headers=headers) as client:
        for feed in feeds:
            try:
                out.extend(_fetch_one(client, feed, per_feed_limit))
            except Exception as e:
                print(f"  feed error ({feed.name}): {e}")
    return out


def _fetch_one(client: httpx.Client, feed: Feed, limit: int) -> list[Article]:
    try:
        resp = client.get(feed.url)
        resp.raise_for_status()
    except Exception as e:
        print(f"  fetch failed ({feed.name}): {e}")
        return []

    parsed = feedparser.parse(resp.text)
    articles: list[Article] = []
    for entry in parsed.entries[:limit]:
        url = getattr(entry, "link", None)
        if not url:
            continue
        content = _extract(client, url) or entry.get("summary", "")
        articles.append(Article(
            title=getattr(entry, "title", "(untitled)"),
            url=url,
            published=entry.get("published", ""),
            content=content,
            source=feed.name,
            category=feed.category,
            trust=feed.trust,
        ))
    return articles


def _extract(client: httpx.Client, url: str) -> str | None:
    try:
        resp = client.get(url)
        resp.raise_for_status()
    except Exception:
        return None
    return trafilatura.extract(
        resp.text,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
