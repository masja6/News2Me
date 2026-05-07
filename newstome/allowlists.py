"""Load curated allowlists from markdown files in config/allowlists/.

Each .md file uses a simple convention:
- Lines starting with ``- `` are entries.
- Everything else (headings, blank lines, blockquotes) is ignored.
- Entry format varies by file; callers parse the bullet text themselves.

This module provides both a generic loader and typed helpers for each list.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ALLOWLISTS_DIR = Path("config/allowlists")


def load_bullets(name: str) -> list[str]:
    """Return raw bullet texts from ``config/allowlists/{name}.md``."""
    path = ALLOWLISTS_DIR / f"{name}.md"
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    return [line[2:].strip() for line in lines if line.startswith("- ")]


# -- Typed helpers -----------------------------------------------------------

@dataclass
class AiCategory:
    slug: str
    emoji: str
    label: str
    description: str


def load_ai_categories() -> list[AiCategory]:
    cats: list[AiCategory] = []
    for raw in load_bullets("ai_categories"):
        m = re.match(r"^(\S+)\s+—\s+(\S+)\s+(.+?)\s+·\s+(.+)$", raw)
        if m:
            cats.append(AiCategory(
                slug=m.group(1),
                emoji=m.group(2),
                label=m.group(3),
                description=m.group(4),
            ))
    return cats


@dataclass
class Publication:
    slug: str
    feed_url: str
    note: str


def load_publications() -> list[Publication]:
    pubs: list[Publication] = []
    for raw in load_bullets("substack_publications"):
        m = re.match(r"^(\S+)\s+\|\s+(\S+)\s+—\s+(.+)$", raw)
        if m:
            pubs.append(Publication(slug=m.group(1), feed_url=m.group(2), note=m.group(3)))
    return pubs


@dataclass
class TrackedLibrary:
    name: str
    ecosystem: str  # "pypi" or "npm"
    note: str


def load_libraries() -> list[TrackedLibrary]:
    libs: list[TrackedLibrary] = []
    for raw in load_bullets("ai_libraries"):
        m = re.match(r"^(.+?)\s+\((\w+)\)\s+—\s+(.+)$", raw)
        if m:
            libs.append(TrackedLibrary(name=m.group(1), ecosystem=m.group(2), note=m.group(3)))
    return libs


@dataclass
class HfOrg:
    slug: str
    note: str


def load_hf_orgs() -> list[HfOrg]:
    orgs: list[HfOrg] = []
    for raw in load_bullets("ai_orgs"):
        m = re.match(r"^(\S+)\s+—\s+(.+)$", raw)
        if m:
            orgs.append(HfOrg(slug=m.group(1), note=m.group(2)))
    return orgs


@dataclass
class SuggestedRepo:
    full_name: str  # "owner/repo"
    note: str


def load_repos() -> list[SuggestedRepo]:
    repos: list[SuggestedRepo] = []
    for raw in load_bullets("popular_ai_repos"):
        m = re.match(r"^(\S+/\S+)\s+—\s+(.+)$", raw)
        if m:
            repos.append(SuggestedRepo(full_name=m.group(1), note=m.group(2)))
    return repos
