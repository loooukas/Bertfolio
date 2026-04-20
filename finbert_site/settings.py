"""Runtime configuration for the local FinBERT app."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    alpha_vantage_api_key: str = os.getenv("ALPHAVANTAGE_API_KEY", "")
    finbert_model_name: str = os.getenv("FINBERT_MODEL_NAME", "ProsusAI/finbert")
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    transcript_target_count: int = int(os.getenv("TRANSCRIPT_TARGET_COUNT", "4"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_normalizer_model: str = os.getenv("OPENAI_NORMALIZER_MODEL", "gpt-4o-mini")
    openai_search_model: str = os.getenv("OPENAI_SEARCH_MODEL", "gpt-5-mini")

    transcript_pipeline_mode: str = os.getenv("TRANSCRIPT_PIPELINE_MODE", "motley_cli")
    transcript_pipeline_fallback_to_legacy: bool = _env_bool("TRANSCRIPT_PIPELINE_FALLBACK_TO_LEGACY", True)

    motley_timeout_seconds: int = int(os.getenv("MOTLEY_TIMEOUT_SECONDS", "45"))
    motley_openai_retries: int = int(os.getenv("MOTLEY_OPENAI_RETRIES", "3"))
    motley_discovery_mode: str = os.getenv("MOTLEY_DISCOVERY_MODE", "hybrid")
    motley_sitemap_lookback_months: int = int(os.getenv("MOTLEY_SITEMAP_LOOKBACK_MONTHS", "24"))
    motley_author_max_pages: int = int(os.getenv("MOTLEY_AUTHOR_MAX_PAGES", "0"))
    motley_scrape_count: int = int(os.getenv("MOTLEY_SCRAPE_COUNT", "4"))
    motley_scrape_cache_mode: str = os.getenv("MOTLEY_SCRAPE_CACHE_MODE", "refresh")
    motley_scrape_cache_dir: str = os.getenv("MOTLEY_SCRAPE_CACHE_DIR", "output/openai_motley_cache")
    motley_discovery_cache_mode: str = os.getenv("MOTLEY_DISCOVERY_CACHE_MODE", "refresh")
    motley_discovery_cache_dir: str = os.getenv(
        "MOTLEY_DISCOVERY_CACHE_DIR",
        "output/openai_motley_discovery_cache",
    )

    transcript_sentiment_segment_chars: int = int(os.getenv("TRANSCRIPT_SENTIMENT_SEGMENT_CHARS", "650"))
    transcript_sentiment_segment_max: int = int(os.getenv("TRANSCRIPT_SENTIMENT_SEGMENT_MAX", "1000"))
    transcript_sentiment_segment_min: int = int(os.getenv("TRANSCRIPT_SENTIMENT_SEGMENT_MIN", "180"))
    transcript_sentiment_segment_overlap_sentences: int = int(
        os.getenv("TRANSCRIPT_SENTIMENT_SEGMENT_OVERLAP_SENTENCES", "1")
    )

    news_limit: int = int(os.getenv("NEWS_LIMIT", "36"))
    news_pool_size: int = int(os.getenv("NEWS_POOL_SIZE", "220"))
    news_lookback_days: int = int(os.getenv("NEWS_LOOKBACK_DAYS", "21"))

    social_limit: int = int(os.getenv("SOCIAL_LIMIT", "36"))
    social_pool_size: int = int(os.getenv("SOCIAL_POOL_SIZE", "260"))
    social_lookback_days: int = int(os.getenv("SOCIAL_LOOKBACK_DAYS", "21"))


settings = Settings()
