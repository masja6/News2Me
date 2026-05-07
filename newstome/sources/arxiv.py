"""arXiv RSS adapter.

Fetches papers from arXiv RSS feeds (cs.AI, cs.CL, cs.LG, cs.CV, stat.ML),
maps them to Article with content_type="paper", and deduplicates cross-listed
papers by arxiv ID.
"""

from __future__ import annotations

import asyncio
import re

import feedparser
import httpx

from ..fetch import Article

_HEADERS = {"User-Agent": "NewsToMe/0.7 (+https://github.com/)"}

ARXIV_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.CV", "stat.ML"]

_ARXIV_FEED_URL = "https://export.arxiv.org/rss/{cat}"
_ARXIV_ID_RE = re.compile(r"abs/(\d+\.\d+)")

_TRUST = 0.85
_PER_CATEGORY_LIMIT = 10
_REQUEST_DELAY = 3.0


def _parse_authors(raw: str) -> list[str]:
    """Parse the dc:creator field into a list of author names."""
    if not raw:
        return []
    parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", raw)
    cleaned = []
    for p in parts:
        name = re.sub(r"<[^>]+>", "", p).strip()
        if name:
            cleaned.append(name)
    return cleaned


def _extract_arxiv_id(link: str) -> str | None:
    m = _ARXIV_ID_RE.search(link)
    return m.group(1) if m else None


def _clean_title(title: str) -> str:
    return re.sub(r"\s*\(arXiv:\d+\.\d+v?\d*\s*\[.*?\]\)\s*$", "", title).strip()


def fetch_arxiv(
    categories: list[str] | None = None,
    per_category_limit: int = _PER_CATEGORY_LIMIT,
) -> list[Article]:
    """Synchronous entry point — runs the async pipeline internally."""
    cats = categories or ARXIV_CATEGORIES
    return asyncio.run(_fetch_all(cats, per_category_limit))


async def _fetch_all(cats: list[str], limit: int) -> list[Article]:
    seen_ids: set[str] = set()
    all_articles: list[Article] = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_HEADERS) as client:
        for cat in cats:
            try:
                articles = await _fetch_category(client, cat, limit)
            except Exception as e:
                print(f"  arxiv error ({cat}): {e}")
                continue
            for a in articles:
                if a.external_id and a.external_id in seen_ids:
                    continue
                if a.external_id:
                    seen_ids.add(a.external_id)
                all_articles.append(a)
            if cat != cats[-1]:
                await asyncio.sleep(_REQUEST_DELAY)
    return all_articles


async def _fetch_category(
    client: httpx.AsyncClient, cat: str, limit: int
) -> list[Article]:
    url = _ARXIV_FEED_URL.format(cat=cat)
    resp = await client.get(url)
    resp.raise_for_status()
    parsed = feedparser.parse(resp.text)

    articles: list[Article] = []
    for entry in parsed.entries[:limit]:
        link = getattr(entry, "link", "")
        if not link:
            continue

        arxiv_id = _extract_arxiv_id(link)
        authors = _parse_authors(getattr(entry, "author", ""))
        abstract = getattr(entry, "summary", "") or ""
        abstract = re.sub(r"<[^>]+>", "", abstract).strip()

        articles.append(Article(
            title=_clean_title(getattr(entry, "title", "(untitled)")),
            url=link,
            published=entry.get("published", ""),
            content=abstract,
            source=f"arXiv {cat}",
            category="ai_papers",
            trust=_TRUST,
            content_type="paper",
            authors=authors or None,
            external_id=arxiv_id,
            extra={"pdf_url": link.replace("/abs/", "/pdf/"), "primary_category": cat},
        ))
    return articles
