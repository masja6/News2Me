from newstome.rank import rank
from newstome.fetch import Article

def test_personalized_rank_boost(mock_ranking_config):
    # Two identical articles in different categories
    a1 = Article(title="AI Story", url="u1", source="s1", category="global_ai", trust=0.8, content="...", published="Wed, 23 Apr 2026 10:00:00 +0000")
    a2 = Article(title="Politics Story", url="u2", source="s2", category="india_politics", trust=0.8, content="...", published="Wed, 23 Apr 2026 10:00:00 +0000")
    
    clusters = [[a1], [a2]]
    
    # Without boost, they should have similar scores
    base_ranked = rank(clusters, mock_ranking_config)
    
    # With boost for AI
    boosts = {"global_ai": 0.5}
    personalized_ranked = rank(clusters, mock_ranking_config, category_boosts=boosts)
    
    ai_score = next(r.score for r in personalized_ranked if r.articles[0].category == "global_ai")
    politics_score = next(r.score for r in personalized_ranked if r.articles[0].category == "india_politics")
    
    # AI should have a higher score because of the 0.5 boost
    assert ai_score > politics_score
    assert ai_score == pytest.approx(politics_score * 1.5)

import pytest
