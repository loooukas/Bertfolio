"""Runtime configuration for the local FinBERT app."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    alpha_vantage_api_key: str = os.getenv("ALPHAVANTAGE_API_KEY", "")
    finbert_model_name: str = os.getenv("FINBERT_MODEL_NAME", "ProsusAI/finbert")
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30"))
    transcript_target_count: int = int(os.getenv("TRANSCRIPT_TARGET_COUNT", "4"))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    openai_normalizer_model: str = os.getenv("OPENAI_NORMALIZER_MODEL", "gpt-4o-mini")


settings = Settings()
