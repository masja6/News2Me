from unittest.mock import patch
from newstome.summarize import summarize
from newstome.fetch import Article
from newstome.config import Summarizer

@patch("newstome.summarize.get_cached_summary")
@patch("newstome.summarize._client.messages.create")
def test_summarize_uses_cache(mock_create, mock_get_cache):
    article = Article(title="Test", url="http://test", source="Test", category="AI", trust=1.0, published="", content="")
    cfg = Summarizer()
    
    # Simulate cache hit
    mock_get_cache.return_value = {
        "headline": "Cached Headline", "body": "Cached Body", "url": "http://test", 
        "source": "Test", "category": "AI", "date": ""
    }
    
    result = summarize(article, cfg, "Standard", False)
    
    assert result.headline == "Cached Headline"
    assert result.body == "Cached Body"
    # Ensure LLM was not called
    assert not mock_create.called
