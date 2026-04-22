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


def rank(clusters: list[list[Article]], w: Ranking) -> list[RankedCluster]:
    ranked: list[RankedCluster] = []
    for c in clusters:
        rep = max(c, key=lambda a: a.trust)
        age = min(_age_hours(a) for a in c)
        recency = math.exp(-age / 12.0)
        trust = max(a.trust for a in c)
        cluster_boost = min(1.0, math.log1p(len(c)) / math.log(4))
        score = (
            w.recency_weight * recency
            + w.trust_weight * trust
            + w.cluster_size_weight * cluster_boost
        )
        ranked.append(RankedCluster(
            articles=c,
            score=score,
            recency=recency,
            trust=trust,
            cluster_boost=cluster_boost,
        ))
    ranked.sort(key=lambda r: r.score, reverse=True)
    return ranked


def _region(category: str) -> str:
    return "india" if category.startswith("india") else "global"


def enforce_diversity(ranked: list[RankedCluster], per_category_max: int, max_items: int, per_region_max: int = 6) -> list[RankedCluster]:
    per_cat: dict[str, int] = {}
    per_reg: dict[str, int] = {}
    out: list[RankedCluster] = []
    for rc in ranked:
        cat = rc.articles[0].category
        reg = _region(cat)
        if per_cat.get(cat, 0) >= per_category_max:
            continue
        if per_reg.get(reg, 0) >= per_region_max:
            continue
        out.append(rc)
        per_cat[cat] = per_cat.get(cat, 0) + 1
        per_reg[reg] = per_reg.get(reg, 0) + 1
        if len(out) >= max_items:
            break
    return out
