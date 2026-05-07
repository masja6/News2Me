import math
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .config import Ranking
from .fetch import Article


@dataclass
class RankedCluster:
    articles: list[Article]
    score: float
    recency: float
    trust: float
    cluster_boost: float
    tracked: bool = False


def _age_hours(a: Article) -> float:
    if not a.published:
        return 24.0
    try:
        dt = parsedate_to_datetime(a.published)
        if dt is None:
            return 24.0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600.0)
    except Exception:
        return 24.0


def _content_type_bonus(article: Article) -> float:
    """Extra scoring signal derived from content-type-specific metrics."""
    m = article.metrics or {}
    ct = article.content_type or "news"
    if ct == "model":
        dl = m.get("downloads_24h", 0) or 0
        likes = m.get("likes", 0) or 0
        return min(0.3, math.log1p(dl + likes * 10) / 30)
    if ct == "release":
        if article.extra and article.extra.get("breaking_changes"):
            return 0.15
        return 0.0
    if ct in ("paper", "essay"):
        org_prior = m.get("org_prior", 0.5)
        return (org_prior - 0.5) * 0.2
    return 0.0


def rank(
    clusters: list[list[Article]],
    w: Ranking,
    category_boosts: dict[str, float] | None = None,
    tracked_ids: set[str] | None = None,
) -> list[RankedCluster]:
    ranked: list[RankedCluster] = []
    boosts = category_boosts or {}
    tracked = tracked_ids or set()
    for c in clusters:
        rep = max(c, key=lambda a: a.trust)
        age = min(_age_hours(a) for a in c)
        recency = math.exp(-age / 12.0)
        trust = max(a.trust for a in c)
        cluster_boost = min(1.0, math.log1p(len(c)) / math.log(4))

        base_score = (
            w.recency_weight * recency
            + w.trust_weight * trust
            + w.cluster_size_weight * cluster_boost
        )

        base_score += _content_type_bonus(rep)

        cat = rep.category
        personal_boost = boosts.get(cat, 0.0)
        score = base_score * (1.0 + personal_boost)

        is_tracked = any(a.external_id in tracked for a in c if a.external_id)

        ranked.append(RankedCluster(
            articles=c,
            score=score,
            recency=recency,
            trust=trust,
            cluster_boost=cluster_boost,
            tracked=is_tracked,
        ))
    ranked.sort(key=lambda r: (r.tracked, r.score), reverse=True)
    return ranked


def _region(category: str) -> str:
    if category.startswith("india"):
        return "india"
    if category.startswith("ai_"):
        return "ai"
    return "global"


def enforce_diversity(ranked: list[RankedCluster], per_category_max: int, max_items: int, per_region_max: int = 6) -> list[RankedCluster]:
    actual_region_max = max(per_region_max, max_items)
    actual_cat_max = max(per_category_max, math.ceil(max_items / 3))

    per_cat: dict[str, int] = {}
    per_reg: dict[str, int] = {}
    out: list[RankedCluster] = []
    for rc in ranked:
        if rc.tracked:
            out.append(rc)
            continue
        cat = rc.articles[0].category
        reg = _region(cat)
        if per_cat.get(cat, 0) >= actual_cat_max:
            continue
        if per_reg.get(reg, 0) >= actual_region_max:
            continue
        out.append(rc)
        per_cat[cat] = per_cat.get(cat, 0) + 1
        per_reg[reg] = per_reg.get(reg, 0) + 1
        if len(out) >= max_items:
            break
    return out
