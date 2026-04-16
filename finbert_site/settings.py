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


settings = Settings()
