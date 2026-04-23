"""
Rule-based evals for classify.py output quality.
Tests the parser and category-validation logic directly — no live API calls.
"""
import pytest

from newstome.classify import _extract_json_array
from newstome.fetch import Article
from .fixtures import ARTICLES


CATEGORIES = [
    "india_politics", "india_business", "india_markets", "india_tech",
    "india_science", "india_sports", "india_entertainment", "india_crime",
    "global_politics", "global_business", "global_markets", "global_tech",
    "global_science", "global_sports", "global_entertainment", "global_health",
    "global_climate", "other",
]


# ── Parser tests ──────────────────────────────────────────────────────────────

def test_extract_json_array_plain():
    raw = '[{"id": 0, "category": "india_markets"}, {"id": 1, "category": "global_tech"}]'
    result = _extract_json_array(raw)
    assert len(result) == 2
    assert result[0]["category"] == "india_markets"


def test_extract_json_array_strips_markdown_fences():
    raw = '```json\n[{"id": 0, "category": "india_markets"}]\n```'
    result = _extract_json_array(raw)
    assert result[0]["category"] == "india_markets"


def test_extract_json_array_invalid_raises():
    with pytest.raises(Exception):
        _extract_json_array("not json at all")


# ── Category validation tests ─────────────────────────────────────────────────

def test_all_fixture_articles_have_valid_categories():
    for article in ARTICLES:
        assert article.category in CATEGORIES, \
            f"{article.url} has unknown category '{article.category}'"


def test_category_assignment_updates_article():
    """Simulate what classify_articles does: mapping overrides article.category."""
    article = Article(
        title="Sensex drops 500 points on global cues",
        url="https://example.com/sensex",
        published="2025-04-22T10:00:00Z",
        content="Markets fell sharply...",
        source="ET",
        category="other",  # before classification
        trust=0.8,
    )
    # Simulate the mapping step from classify_articles
    mapping = {0: "india_markets"}
    cat = mapping.get(0)
    if cat and cat in CATEGORIES:
        article.category = cat
    assert article.category == "india_markets"


def test_category_assignment_ignores_unknown():
    """Unknown categories returned by LLM should not override."""
    article = Article(
        title="Something obscure",
        url="https://example.com/x",
        published="2025-04-22T10:00:00Z",
        content="...",
        source="X",
        category="other",
        trust=0.5,
    )
    mapping = {0: "made_up_category"}
    cat = mapping.get(0)
    if cat and cat in CATEGORIES:
        article.category = cat
    assert article.category == "other"  # unchanged


# ── Keyword following tests ───────────────────────────────────────────────────

def test_keyword_boost_moves_matching_clusters_first():
    """pipeline.build_user_digest keyword logic: matching clusters bubble to top."""
    from newstome.rank import RankedCluster
    from .fixtures import ARTICLES

    rc_rbi   = RankedCluster(articles=[ARTICLES[0]], score=0.5, recency=0.5, trust=0.9, cluster_boost=1.0)
    rc_openai = RankedCluster(articles=[ARTICLES[1]], score=0.9, recency=0.9, trust=0.85, cluster_boost=1.0)
    rc_isro  = RankedCluster(articles=[ARTICLES[2]], score=0.7, recency=0.7, trust=0.88, cluster_boost=1.0)

    ranked = [rc_openai, rc_isro, rc_rbi]  # OpenAI has highest score
    keywords = ["rbi"]

    keyword_hits = [rc for rc in ranked if any(kw in " ".join(a.title.lower() for a in rc.articles) for kw in keywords)]
    rest = [rc for rc in ranked if rc not in keyword_hits]
    reranked = keyword_hits + rest

    assert reranked[0].articles[0].title == ARTICLES[0].title  # RBI is now first
    assert len(reranked) == 3


def test_keyword_no_match_preserves_order():
    from newstome.rank import RankedCluster
    from .fixtures import ARTICLES

    rc1 = RankedCluster(articles=[ARTICLES[0]], score=0.9, recency=0.9, trust=0.9, cluster_boost=1.0)
    rc2 = RankedCluster(articles=[ARTICLES[1]], score=0.5, recency=0.5, trust=0.85, cluster_boost=1.0)
    ranked = [rc1, rc2]
    keywords = ["nonexistent_keyword_xyz"]

    hits = [rc for rc in ranked if any(kw in " ".join(a.title.lower() for a in rc.articles) for kw in keywords)]
    rest = [rc for rc in ranked if rc not in hits]
    reranked = hits + rest

    assert reranked == ranked  # unchanged
