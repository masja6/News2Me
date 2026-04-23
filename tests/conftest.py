import pytest
from newstome.config import Ranking

@pytest.fixture
def mock_ranking_config():
    return Ranking(
        max_items=10,
        per_category_max=2,
        per_region_max=6,
        dedupe_similarity=82,
        recency_weight=0.5,
        trust_weight=0.3,
        cluster_size_weight=0.2
    )
