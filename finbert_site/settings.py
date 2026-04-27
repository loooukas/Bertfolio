"""Runtime configuration for the local Bertfolio app."""

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
    openai_request_retries: int = int(os.getenv("OPENAI_REQUEST_RETRIES", "2"))
    openai_retry_backoff_seconds: float = float(os.getenv("OPENAI_RETRY_BACKOFF_SECONDS", "1.5"))

    transcript_pipeline_mode: str = os.getenv("TRANSCRIPT_PIPELINE_MODE", "motley_cli")
    transcript_pipeline_fallback_to_legacy: bool = _env_bool("TRANSCRIPT_PIPELINE_FALLBACK_TO_LEGACY", True)

    motley_timeout_seconds: int = int(os.getenv("MOTLEY_TIMEOUT_SECONDS", "45"))
    motley_openai_retries: int = int(os.getenv("MOTLEY_OPENAI_RETRIES", "3"))
    motley_discovery_mode: str = os.getenv("MOTLEY_DISCOVERY_MODE", "hybrid")
    motley_sitemap_lookback_months: int = int(os.getenv("MOTLEY_SITEMAP_LOOKBACK_MONTHS", "24"))
    motley_author_max_pages: int = int(os.getenv("MOTLEY_AUTHOR_MAX_PAGES", "0"))
    motley_scrape_count: int = int(os.getenv("MOTLEY_SCRAPE_COUNT", "4"))
    motley_scrape_cache_mode: str = os.getenv("MOTLEY_SCRAPE_CACHE_MODE", "use")
    motley_scrape_cache_dir: str = os.getenv("MOTLEY_SCRAPE_CACHE_DIR", "output/openai_motley_cache")
    motley_discovery_cache_mode: str = os.getenv("MOTLEY_DISCOVERY_CACHE_MODE", "use")
    motley_discovery_cache_dir: str = os.getenv(
        "MOTLEY_DISCOVERY_CACHE_DIR",
        "output/openai_motley_discovery_cache",
    )
    use_cache: bool = _env_bool("USE_CACHE", True)
    analysis_result_cache_dir: str = os.getenv("ANALYSIS_RESULT_CACHE_DIR", "output/analysis_cache")

    transcript_sentiment_segment_chars: int = int(os.getenv("TRANSCRIPT_SENTIMENT_SEGMENT_CHARS", "650"))
    transcript_sentiment_segment_max: int = int(os.getenv("TRANSCRIPT_SENTIMENT_SEGMENT_MAX", "1000"))
    transcript_sentiment_segment_min: int = int(os.getenv("TRANSCRIPT_SENTIMENT_SEGMENT_MIN", "180"))
    transcript_sentiment_segment_overlap_sentences: int = int(
        os.getenv("TRANSCRIPT_SENTIMENT_SEGMENT_OVERLAP_SENTENCES", "1")
    )
    transcript_feature_ai_enabled: bool = _env_bool("TRANSCRIPT_FEATURE_AI_ENABLED", True)
    transcript_feature_ai_model: str = os.getenv("TRANSCRIPT_FEATURE_AI_MODEL", "gpt-4o-mini")
    transcript_feature_ai_weight: float = float(os.getenv("TRANSCRIPT_FEATURE_AI_WEIGHT", "0.35"))
    transcript_feature_ai_max_blocks: int = int(os.getenv("TRANSCRIPT_FEATURE_AI_MAX_BLOCKS", "48"))
    transcript_feature_ai_batch_size: int = int(os.getenv("TRANSCRIPT_FEATURE_AI_BATCH_SIZE", "12"))
    transcript_feature_ai_timeout_seconds: int = int(os.getenv("TRANSCRIPT_FEATURE_AI_TIMEOUT_SECONDS", "24"))
    transcript_feature_ai_min_batch_size: int = int(os.getenv("TRANSCRIPT_FEATURE_AI_MIN_BATCH_SIZE", "3"))
    transcript_feature_counter_weight: float = float(os.getenv("TRANSCRIPT_FEATURE_COUNTER_WEIGHT", "0.65"))
    transcript_feature_density_smoothing: float = float(os.getenv("TRANSCRIPT_FEATURE_DENSITY_SMOOTHING", "0.35"))
    use_student_confidence: bool = _env_bool("USE_STUDENT_CONFIDENCE", True)
    use_student_directness: bool = _env_bool("USE_STUDENT_DIRECTNESS", True)
    use_student_outlook_strength: bool = _env_bool("USE_STUDENT_OUTLOOK_STRENGTH", True)
    use_student_specificity: bool = _env_bool("USE_STUDENT_SPECIFICITY", False)
    use_student_risk_intensity: bool = _env_bool("USE_STUDENT_RISK_INTENSITY", False)
    student_metrics_shadow_compare: bool = _env_bool("STUDENT_METRICS_SHADOW_COMPARE", True)
    student_metrics_force_lexical_fallback: bool = _env_bool("STUDENT_METRICS_FORCE_LEXICAL_FALLBACK", False)
    student_metrics_specificity_blend_enabled: bool = _env_bool(
        "STUDENT_METRICS_SPECIFICITY_BLEND_ENABLED",
        False,
    )
    student_metrics_specificity_blend_weight: float = float(
        os.getenv("STUDENT_METRICS_SPECIFICITY_BLEND_WEIGHT", "0.35")
    )
    student_metrics_batch_size: int = int(os.getenv("STUDENT_METRICS_BATCH_SIZE", "8"))
    student_metrics_max_length: int = int(os.getenv("STUDENT_METRICS_MAX_LENGTH", "256"))
    student_model_confidence_dir: str = os.getenv(
        "STUDENT_MODEL_CONFIDENCE_DIR",
        "output/student_models/confidence_three_band_deberta_v3_base_strict070/model",
    )
    student_model_directness_dir: str = os.getenv(
        "STUDENT_MODEL_DIRECTNESS_DIR",
        "output/student_models/directness_three_band_deberta_v3_base_strict070/model",
    )
    student_model_outlook_strength_dir: str = os.getenv(
        "STUDENT_MODEL_OUTLOOK_STRENGTH_DIR",
        "output/student_models/outlook_strength_five_band_deberta_v3_base_strict070/model",
    )
    student_model_specificity_dir: str = os.getenv(
        "STUDENT_MODEL_SPECIFICITY_DIR",
        "output/student_models/specificity_deberta_v3_base_cpu/model",
    )
    student_model_risk_intensity_dir: str = os.getenv(
        "STUDENT_MODEL_RISK_INTENSITY_DIR",
        "output/student_models/risk_intensity_three_band_deberta_v3_base_strict070/model",
    )

    score_weight_transcript: float = float(os.getenv("SCORE_WEIGHT_TRANSCRIPT", "40"))
    score_weight_fundamentals: float = float(os.getenv("SCORE_WEIGHT_FUNDAMENTALS", "35"))
    score_weight_news: float = float(os.getenv("SCORE_WEIGHT_NEWS", "15"))
    score_weight_social: float = float(os.getenv("SCORE_WEIGHT_SOCIAL", "10"))

    # Transcript-internal calibrated scorer (defaults from 126d binary stage-1 calibration).
    transcript_internal_model_enabled: bool = _env_bool("TRANSCRIPT_INTERNAL_MODEL_ENABLED", True)
    transcript_internal_intercept: float = float(os.getenv("TRANSCRIPT_INTERNAL_INTERCEPT", "-0.019738131823252437"))
    transcript_internal_weight_sentiment: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_WEIGHT_SENTIMENT", "-0.1401634692187762")
    )
    transcript_internal_weight_confidence: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_WEIGHT_CONFIDENCE", "-0.018278288860921532")
    )
    transcript_internal_weight_directness: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_WEIGHT_DIRECTNESS", "0.015206414272671791")
    )
    transcript_internal_weight_outlook_strength: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_WEIGHT_OUTLOOK_STRENGTH", "-0.11552397904346766")
    )
    transcript_internal_weight_specificity: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_WEIGHT_SPECIFICITY", "-0.08887882362418172")
    )
    transcript_internal_weight_risk_intensity: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_WEIGHT_RISK_INTENSITY", "-0.0394870057888973")
    )

    transcript_internal_mean_sentiment: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_MEAN_SENTIMENT", "0.21078121062965025")
    )
    transcript_internal_mean_confidence: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_MEAN_CONFIDENCE", "66.75376972941926")
    )
    transcript_internal_mean_directness: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_MEAN_DIRECTNESS", "66.07434537052912")
    )
    transcript_internal_mean_outlook_strength: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_MEAN_OUTLOOK_STRENGTH", "43.44859716002433")
    )
    transcript_internal_mean_specificity: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_MEAN_SPECIFICITY", "55.778186220330234")
    )
    transcript_internal_mean_risk_intensity: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_MEAN_RISK_INTENSITY", "58.85238912055554")
    )

    transcript_internal_std_sentiment: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_STD_SENTIMENT", "0.19059907568499407")
    )
    transcript_internal_std_confidence: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_STD_CONFIDENCE", "2.6604270552701204")
    )
    transcript_internal_std_directness: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_STD_DIRECTNESS", "3.489541394240505")
    )
    transcript_internal_std_outlook_strength: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_STD_OUTLOOK_STRENGTH", "3.6659477149803137")
    )
    transcript_internal_std_specificity: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_STD_SPECIFICITY", "5.680196748327937")
    )
    transcript_internal_std_risk_intensity: float = float(
        os.getenv("TRANSCRIPT_INTERNAL_STD_RISK_INTENSITY", "2.562695988859408")
    )

    news_limit: int = int(os.getenv("NEWS_LIMIT", "50"))
    news_pool_size: int = int(os.getenv("NEWS_POOL_SIZE", "240"))
    news_lookback_days: int = int(os.getenv("NEWS_LOOKBACK_DAYS", "30"))
    news_enable_alpha_vantage: bool = _env_bool("NEWS_ENABLE_ALPHA_VANTAGE", True)
    news_enable_yahoo_finance: bool = _env_bool("NEWS_ENABLE_YAHOO_FINANCE", True)

    social_limit: int = int(os.getenv("SOCIAL_LIMIT", "50"))
    social_pool_size: int = int(os.getenv("SOCIAL_POOL_SIZE", "260"))
    social_lookback_days: int = int(os.getenv("SOCIAL_LOOKBACK_DAYS", "30"))
    social_enable_reddit: bool = _env_bool("SOCIAL_ENABLE_REDDIT", True)
    social_enable_stocktwits: bool = _env_bool("SOCIAL_ENABLE_STOCKTWITS", True)


settings = Settings()
