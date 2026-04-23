from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv(override=True)

CONFIG_PATH = Path("config.yaml")


class Secrets(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    gemini_api_key: str = ""
    gmail_address: str = ""
    gmail_app_password: str = ""
    mongodb_uri: str = ""
    app_url: str = "http://localhost:8000"

    admin_user: str = "admin"
    admin_password: str = ""
    unsubscribe_secret: str = ""
    alert_chat_id: str = ""
    google_client_id: str = ""
    session_secret: str = "fallback-secret-for-dev-only-change-me"

    summary_model: str = "claude-haiku-4-5-20251001"
    classify_model: str = "claude-haiku-4-5-20251001"


class Feed(BaseModel):
    name: str
    url: str
    category: str
    trust: float = 0.7


class Ranking(BaseModel):
    max_items: int = 10
    per_category_max: int = 2
    per_region_max: int = 6
    dedupe_similarity: int = 82
    recency_weight: float = 0.5
    trust_weight: float = 0.3
    cluster_size_weight: float = 0.2


class Summarizer(BaseModel):
    request_delay_sec: int = 13
    max_article_chars: int = 6000


class Qc(BaseModel):
    min_categories: int = 4
    max_share_per_category: float = 0.5


class Delivery(BaseModel):
    channels: list[str] = ["telegram"]
    email_to: str = ""


class TelegramCfg(BaseModel):
    digest_title: str = "Morning Digest"


class AppConfig(BaseModel):
    feeds: list[Feed]
    categories: list[str] = []
    ranking: Ranking = Ranking()
    summarizer: Summarizer = Summarizer()
    qc: Qc = Qc()
    delivery: Delivery = Delivery()
    telegram: TelegramCfg = TelegramCfg()


def load_config() -> AppConfig:
    raw = yaml.safe_load(CONFIG_PATH.read_text())
    return AppConfig(**raw)


def save_config(cfg: AppConfig) -> None:
    CONFIG_PATH.write_text(yaml.safe_dump(cfg.model_dump(), sort_keys=False))


secrets = Secrets()
