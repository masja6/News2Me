"""Substack / curated blogs adapter.

Fetches long-form essays from curated publications, maps them to Article with
content_type="essay". Applies per-publication rate caps and paywall detection.
"""

from __future__ import annotations

import asyncio
import re

import feedparser
import httpx

from ..allowlists import load_publications
from ..fetch import Article

_HEADERS = {"User-Agent": "NewsToMe/0.7 (+https://github.com/)"}
_CONCURRENCY = 4
_PER_PUB_LIMIT = 1
_MIN_CONTENT_WORDS = 400
_MAX_CONTENT_CHARS = 8000

_PUB_TRUST = {
    "anthropic": 0.95,
    "openai": 0.95,
    "deepmind": 0.95,
    "meta-ai": 0.95,
    "mistral": 0.95,
}
_DEFAULT_TRUST = 0.85


def _reading_time(text: str) -> int:
    """Estimated reading time in minutes (220 wpm)."""
    return max(1, len(text.split()) // 220)


def fetch_blogs(
    per_pub_limit: int = _PER_PUB_LIMIT,
) -> list[Article]:
    """Synchronous entry point."""
    pubs = load_publications()
    if not pubs:
        return []
    return asyncio.run(_fetch_all(pubs, per_pub_limit))


async def _fetch_all(pubs, limit: int) -> list[Article]:
    all_articles: list[Article] = []
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_HEADERS) as client:
        tasks = [_fetch_pub(client, pub, limit, sem) for pub in pubs]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_articles.extend(r)
            elif isinstance(r, Exception):
                print(f"  blog error: {r}")
    return all_articles


async def _fetch_pub(client, pub, limit, sem) -> list[Article]:
    async with sem:
        try:
            resp = await client.get(pub.feed_url)
            resp.raise_for_status()
        except Exception as e:
            print(f"  blog fetch failed ({pub.slug}): {e}")
            return []

    parsed = feedparser.parse(resp.text)
    trust = _PUB_TRUST.get(pub.slug, _DEFAULT_TRUST)

    articles: list[Article] = []
    for entry in parsed.entries[:limit]:
        link = getattr(entry, "link", "")
        if not link:
            continue

        content_html = entry.get("content", [{}])
        if isinstance(content_html, list) and content_html:
            raw_html = content_html[0].get("value", "")
        else:
            raw_html = entry.get("summary", "")

        content = re.sub(r"<[^>]+>", " ", raw_html).strip()
        content = re.sub(r"\s+", " ", content)

        if not content:
            content = entry.get("summary", "")

        content = content[:_MAX_CONTENT_CHARS]

        word_count = len(content.split())
        if word_count < _MIN_CONTENT_WORDS:
            continue

        articles.append(Article(
            title=getattr(entry, "title", "(untitled)"),
            url=link,
            published=entry.get("published", ""),
            content=content,
            source=pub.slug,
            category="ai_essays",
            trust=trust,
            content_type="essay",
            authors=[pub.slug],
            external_id=pub.slug,
            metrics={"reading_time_min": _reading_time(content)},
        ))
    return articles
