"""GitHub trending repos + release tracker adapter.

Two sub-features:
1. Trending repos: scrapes GitHub search API for AI-topic repos gaining stars.
   Maps to Article with content_type="news" and category="ai_tools".
2. Release tracker: polls /releases.atom feeds for repos on the curated list
   or in user trackers. Maps to Article with content_type="release".
"""

from __future__ import annotations

import asyncio
import re

import feedparser
import httpx

from ..allowlists import load_repos
from ..fetch import Article

_HEADERS = {"User-Agent": "NewsToMe/0.7 (+https://github.com/)"}
_TRUST = 0.82
_CONCURRENCY = 4

_EXCLUDE_TOPICS = {"awesome", "dotfiles", "cheatsheet", "roadmap", "interview", "list"}

_GH_SEARCH_API = "https://api.github.com/search/repositories"

_MIN_STARS_WEEK = 200


# ---------------------------------------------------------------------------
# Trending repos
# ---------------------------------------------------------------------------

def fetch_github_trending() -> list[Article]:
    """Synchronous entry point for weekly trending repos."""
    return asyncio.run(_fetch_trending())


async def _fetch_trending() -> list[Article]:
    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_HEADERS) as client:
        repos = await _search_trending(client)
    return [_repo_to_article(r) for r in repos]


async def _search_trending(client: httpx.AsyncClient) -> list[dict]:
    """Use GitHub search API to find recently-pushed AI repos sorted by stars."""
    from datetime import datetime, timedelta, timezone

    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d")
    query = f"topic:llm OR topic:ai OR topic:machine-learning pushed:>{since} stars:>{_MIN_STARS_WEEK}"

    try:
        resp = await client.get(
            _GH_SEARCH_API,
            params={"q": query, "sort": "stars", "order": "desc", "per_page": 30},
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  github trending error: {e}")
        return []

    items = data.get("items", [])
    filtered: list[dict] = []
    for repo in items:
        topics = set(repo.get("topics", []))
        if topics & _EXCLUDE_TOPICS:
            continue
        desc = (repo.get("description") or "").lower()
        if any(word in desc for word in ("awesome list", "curated list", "cheatsheet")):
            continue
        filtered.append(repo)
    return filtered[:10]


def _repo_to_article(repo: dict) -> Article:
    full_name = repo.get("full_name", "")
    desc = repo.get("description", "") or ""
    stars = repo.get("stargazers_count", 0)
    language = repo.get("language", "")

    content = f"Repository: {full_name}\nDescription: {desc}\nLanguage: {language}\nStars: {stars}"

    return Article(
        title=f"{full_name}: {desc[:100]}",
        url=repo.get("html_url", f"https://github.com/{full_name}"),
        published=repo.get("pushed_at", ""),
        content=content,
        source="GitHub",
        category="ai_tools",
        trust=_TRUST,
        content_type="news",
        external_id=full_name,
        metrics={"stars": stars, "language": language},
    )


# ---------------------------------------------------------------------------
# Release tracker
# ---------------------------------------------------------------------------

def fetch_github_releases(
    extra_repos: set[str] | None = None,
) -> list[Article]:
    """Synchronous entry point for tracked-repo releases.

    Only polls repos explicitly in extra_repos (user trackers). The suggested
    list from popular_ai_repos.md is for onboarding UI only — polling all 35
    on every tick would waste memory and API budget.
    """
    repos = extra_repos or set()
    if not repos:
        return []
    return asyncio.run(_fetch_releases(repos))


async def _fetch_releases(repos: set[str]) -> list[Article]:
    all_articles: list[Article] = []
    sem = asyncio.Semaphore(_CONCURRENCY)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=_HEADERS) as client:
        tasks = [_fetch_repo_releases(client, repo, sem) for repo in repos]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, list):
                all_articles.extend(r)
            elif isinstance(r, Exception):
                print(f"  github release error: {r}")
    return all_articles


async def _fetch_repo_releases(
    client: httpx.AsyncClient, repo: str, sem: asyncio.Semaphore
) -> list[Article]:
    async with sem:
        atom_url = f"https://github.com/{repo}/releases.atom"
        try:
            resp = await client.get(atom_url)
            resp.raise_for_status()
        except Exception as e:
            print(f"  github release fetch failed ({repo}): {e}")
            return []

    parsed = feedparser.parse(resp.text)
    articles: list[Article] = []

    for entry in parsed.entries[:1]:
        link = getattr(entry, "link", "")
        title = getattr(entry, "title", "")
        if not link or not title:
            continue

        tag = title.strip()
        content = entry.get("summary", "") or ""
        content = re.sub(r"<[^>]+>", "", content).strip()

        repo_name = repo.rsplit("/", 1)[-1] if "/" in repo else repo
        articles.append(Article(
            title=f"{repo_name} {tag}",
            url=link,
            published=entry.get("updated", entry.get("published", "")),
            content=content or f"New release: {repo_name} {tag}",
            source="GitHub",
            category="ai_libraries",
            trust=_TRUST,
            content_type="release",
            external_id=f"{repo}@{tag}",
            extra={"library": repo_name, "version": tag, "repo": repo},
        ))
    return articles
