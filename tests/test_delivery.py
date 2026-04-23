import pytest
from unittest.mock import patch, MagicMock
from newstome.delivery import run_delivery_cycle

@patch("newstome.delivery.prepare_clusters")
@patch("newstome.delivery.send_email")
@patch("newstome.delivery.load_subscribers")
@patch("newstome.delivery.save_delivery_log")
def test_delivery_cycle_calls_email(mock_save_log, mock_load_subs, mock_send_email, mock_prepare, mock_ranking_config):
    # Mock data
    from newstome.fetch import Article
    from newstome.rank import RankedCluster
    
    a1 = Article(title="T1", url="u1", source="s1", category="c1", trust=0.8, content="C1", published="...")
    mock_prepare.return_value = [RankedCluster(articles=[a1], score=0.9, recency=0.9, trust=0.8, cluster_boost=0.2)]
    
    mock_load_subs.return_value = [{"email": "test@example.com", "tone": "Standard"}]
    mock_send_email.return_value = (True, None)
    
    # We also need to mock secrets or ensure they are present
    with patch("newstome.delivery.secrets") as mock_secrets:
        mock_secrets.gmail_address = "test@gmail.com"
        mock_secrets.gmail_app_password = "password"
        
        # We also need to mock cfg.delivery.channels
        with patch("newstome.delivery.load_config") as mock_load_cfg:
            mock_cfg = MagicMock()
            mock_cfg.delivery.channels = ["email"]
            mock_cfg.delivery.email_to = None
            mock_cfg.telegram.digest_title = "Daily Digest"
            mock_cfg.ranking.max_items = 10
            mock_load_cfg.return_value = mock_cfg
            
            with patch("newstome.delivery.build_user_digest") as mock_build:
                mock_build.return_value = ([MagicMock()], None)
                run_delivery_cycle(verbose=False)
    
    assert mock_send_email.called
    # Check that it was called for the mocked subscriber
    args, kwargs = mock_send_email.call_args
    assert kwargs['to'] == "test@example.com"
