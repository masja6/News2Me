"""PyPI / npm release adapter.

Polls per-package RSS feeds (PyPI) and the npm registry for new releases.
Only tracks packages on the curated allowlist. Maps to Article with
content_type="release".
"""

from __future__ import annotations

import asyncio
import re

import feedparser
import httpx

from ..allowlists import load_libraries
from ..fetch import Article

_HEADERS = {"User-Agent": "NewsToMe/0.7 (+https://github.com/)"}
_CONCURRENCY = 10
_TRUST = 0.80

_PYPI_RSS = "https://pypi.org/rss/project/{name}/releases.xml"
_NPM_REGISTRY = "https://registry.npmjs.org/{name}"

_PRE_RELEASE_RE = re.compile(r"(a|b|rc|dev|alpha|beta|preview)\d*", re.IGNORECASE)


def _is_prerelease(version: str) -> bool:
    return bool(_PRE_RELEASE_RE.search(version))


def _is_major_or_minor(version: str) -> bool:
    """True for x.y.0 or x.0 (major/minor bumps)."""
    parts = version.split(".")
    if len(parts) >= 3:
        try:
            return int(parts[2]) == 0
        except ValueError:
            return True
    return True


def fetch_pypi_npm() -> list[Article]:
    """Synchronous entry point."""
    libs = load_libraries()
    if not libs:
        return []
    return asyncio.run(_fetch_all(libs))


async def _fetch_all(libs) -> list[Article]:
    all_articles: list[Article] = []
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=_HEADERS) as client:
        tasks = []
        for lib in libs:
            if lib.ecosystem == "pypi":
                tasks.append(_fetch_pypi(client, lib, sem))
            elif lib.ecosystem == "npm":
                tasks.append(_fetch_npm(client, lib, sem))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_articles.extend(r)
            elif isinstance(r, Exception):
                print(f"  pypi/npm error: {r}")
    return all_articles


async def _fetch_pypi(client, lib, sem) -> list[Article]:
    async with sem:
        url = _PYPI_RSS.format(name=lib.name)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            print(f"  pypi fetch failed ({lib.name}): {e}")
            return []

    parsed = feedparser.parse(resp.text)
    articles: list[Article] = []

    for entry in parsed.entries[:3]:
        title = getattr(entry, "title", "")
        link = getattr(entry, "link", "")
        if not title or not link:
            continue

        version = title.strip()
        if _is_prerelease(version):
            continue
        if not _is_major_or_minor(version):
            continue

        articles.append(Article(
            title=f"{lib.name} {version}",
            url=link,
            published=entry.get("published", ""),
            content=entry.get("summary", f"New release: {lib.name} {version}"),
            source="PyPI",
            category="ai_libraries",
            trust=_TRUST,
            content_type="release",
            external_id=f"pypi:{lib.name}@{version}",
            extra={"library": lib.name, "version": version, "ecosystem": "pypi"},
        ))

    return articles[:1]


async def _fetch_npm(client, lib, sem) -> list[Article]:
    async with sem:
        url = _NPM_REGISTRY.format(name=lib.name)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            print(f"  npm fetch failed ({lib.name}): {e}")
            return []

    data = resp.json()
    time_map = data.get("time", {})
    if not time_map:
        return []

    versions = sorted(
        [(v, t) for v, t in time_map.items() if v not in ("created", "modified")],
        key=lambda x: x[1],
        reverse=True,
    )

    articles: list[Article] = []
    for version, published in versions[:3]:
        if _is_prerelease(version):
            continue
        if not _is_major_or_minor(version):
            continue

        pkg_url = f"https://www.npmjs.com/package/{lib.name}/v/{version}"
        articles.append(Article(
            title=f"{lib.name} {version}",
            url=pkg_url,
            published=published,
            content=f"New release: {lib.name} {version}",
            source="npm",
            category="ai_libraries",
            trust=_TRUST,
            content_type="release",
            external_id=f"npm:{lib.name}@{version}",
            extra={"library": lib.name, "version": version, "ecosystem": "npm"},
        ))
        break

    return articles
