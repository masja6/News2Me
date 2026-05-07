"""Hugging Face model releases adapter.

Polls the HF API for new models, filters by org allowlist and popularity
thresholds, collapses quantized variants, and maps to Article with
content_type="model".
"""

from __future__ import annotations

import asyncio
import re

import httpx

from ..allowlists import load_hf_orgs
from ..fetch import Article

_HEADERS = {"User-Agent": "NewsToMe/0.7 (+https://github.com/)"}
_HF_API = "https://huggingface.co/api/models"
_TRUST = 0.85
_LIMIT = 100

_QUANT_SUFFIXES = re.compile(
    r"[-_](GGUF|GPTQ|AWQ|GGML|EXL2|fp16|bf16|int[48]|Q[2-8]_[A-Z0-9_]+)$",
    re.IGNORECASE,
)

_LIKES_THRESHOLD = 50
_DOWNLOADS_24H_THRESHOLD = 5000


def _base_model_key(model_id: str) -> str:
    """Collapse quantized variants to their canonical base."""
    name = model_id.rsplit("/", 1)[-1] if "/" in model_id else model_id
    return _QUANT_SUFFIXES.sub("", name).lower()


def _org_from_id(model_id: str) -> str:
    return model_id.split("/")[0] if "/" in model_id else ""


def fetch_huggingface(
    extra_orgs: set[str] | None = None,
) -> list[Article]:
    """Synchronous entry point."""
    return asyncio.run(_fetch(extra_orgs))


async def _fetch(extra_orgs: set[str] | None) -> list[Article]:
    org_slugs = {o.slug for o in load_hf_orgs()}
    if extra_orgs:
        org_slugs |= extra_orgs

    async with httpx.AsyncClient(timeout=20, follow_redirects=True, headers=_HEADERS) as client:
        recent = await _fetch_recent(client)
        trending = await _fetch_trending(client)

    all_models = {m["id"]: m for m in recent + trending}
    filtered = _filter(list(all_models.values()), org_slugs)
    deduped = _dedupe_variants(filtered)
    return [_to_article(m) for m in deduped]


async def _fetch_recent(client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(
            _HF_API,
            params={"sort": "createdAt", "direction": "-1", "limit": _LIMIT},
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  hf recent error: {e}")
        return []


async def _fetch_trending(client: httpx.AsyncClient) -> list[dict]:
    try:
        resp = await client.get(
            _HF_API,
            params={"sort": "likes7d", "direction": "-1", "limit": _LIMIT},
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  hf trending error: {e}")
        return []


def _filter(models: list[dict], org_slugs: set[str]) -> list[dict]:
    out: list[dict] = []
    for m in models:
        model_id = m.get("id", "")
        org = _org_from_id(model_id)
        likes = m.get("likes", 0) or 0
        downloads = m.get("downloads", 0) or 0

        if org in org_slugs:
            out.append(m)
        elif likes >= _LIKES_THRESHOLD:
            out.append(m)
        elif downloads >= _DOWNLOADS_24H_THRESHOLD:
            out.append(m)
    return out


def _dedupe_variants(models: list[dict]) -> list[dict]:
    """Keep only the first (highest-signal) model per base key."""
    seen: dict[str, dict] = {}
    for m in models:
        key = _base_model_key(m.get("id", ""))
        if key not in seen:
            seen[key] = m
    return list(seen.values())


def _to_article(m: dict) -> Article:
    model_id = m.get("id", "")
    org = _org_from_id(model_id)
    likes = m.get("likes", 0) or 0
    downloads = m.get("downloads", 0) or 0
    pipeline_tag = m.get("pipeline_tag", "")
    tags = m.get("tags", []) or []

    description_parts = [model_id]
    if pipeline_tag:
        description_parts.append(f"({pipeline_tag})")

    content = f"Model: {model_id}\nOrg: {org}\nPipeline: {pipeline_tag}\nTags: {', '.join(tags[:10])}\nLikes: {likes}\nDownloads: {downloads}"

    return Article(
        title=model_id,
        url=f"https://huggingface.co/{model_id}",
        published=m.get("createdAt", ""),
        content=content,
        source="Hugging Face",
        category="ai_models",
        trust=_TRUST,
        content_type="model",
        authors=[org] if org else None,
        external_id=model_id,
        metrics={"downloads": downloads, "likes": likes, "downloads_24h": downloads},
        extra={
            "pipeline_tag": pipeline_tag,
            "tags": tags[:10],
            "gated": m.get("gated", False),
        },
    )
