import asyncio
from dataclasses import dataclass

import feedparser
import httpx
import trafilatura

from .config import Feed

_HEADERS = {"User-Agent": "NewsToMe/0.7 (+https://github.com/)"}
_PER_FEED_LIMIT = 12
_FEED_CONCURRENCY = 6
_ARTICLE_CONCURRENCY = 10


@dataclass
class Article:
    title: str
    url: str
    published: str
    content: str
    source: str
    category: str
    trust: float


def fetch_all(feeds: list[Feed], per_feed_limit: int = _PER_FEED_LIMIT) -> list[Article]:
    """Fetch feeds and extract articles concurrently.

    Public signature is unchanged (sync, returns list[Article]) — we run the
    async pipeline via asyncio.run() so existing callers stay untouched.
    """
    return asyncio.run(_fetch_all_async(feeds, per_feed_limit))


async def _fetch_all_async(feeds: list[Feed], per_feed_limit: int) -> list[Article]:
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=_HEADERS) as client:
        feed_sem = asyncio.Semaphore(_FEED_CONCURRENCY)
        article_sem = asyncio.Semaphore(_ARTICLE_CONCURRENCY)

        async def bounded_feed(feed: Feed) -> list[Article]:
            async with feed_sem:
                try:
                    return await _fetch_feed(client, feed, per_feed_limit, article_sem)
                except Exception as e:
                    print(f"  feed error ({feed.name}): {e}")
                    return []

        results = await asyncio.gather(*[bounded_feed(f) for f in feeds])
    return [a for batch in results for a in batch]


async def _fetch_feed(
    client: httpx.AsyncClient,
    feed: Feed,
    limit: int,
    article_sem: asyncio.Semaphore,
) -> list[Article]:
    try:
        resp = await client.get(feed.url)
        resp.raise_for_status()
    except Exception as e:
        print(f"  fetch failed ({feed.name}): {e}")
        return []

    parsed = feedparser.parse(resp.text)
    entries = [e for e in parsed.entries[:limit] if getattr(e, "link", None)]
    if not entries:
        return []

    async def build(entry) -> Article:
        async with article_sem:
            content = await _extract_async(client, entry.link) or entry.get("summary", "")
        return Article(
            title=getattr(entry, "title", "(untitled)"),
            url=entry.link,
            published=entry.get("published", ""),
            content=content,
            source=feed.name,
            category=feed.category,
            trust=feed.trust,
        )

    return list(await asyncio.gather(*[build(e) for e in entries]))


async def _extract_async(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        resp = await client.get(url)
        resp.raise_for_status()
    except Exception:
        return None
    # trafilatura.extract is CPU-bound — run in a thread so we don't block the loop.
    return await asyncio.to_thread(
        trafilatura.extract,
        resp.text,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    )
