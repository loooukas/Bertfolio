from __future__ import annotations

import re
from datetime import datetime, timezone

import pandas as pd

from finbert_site import providers
from finbert_site.providers import TranscriptRecord
from finbert_site.settings import Settings


class _FakeTickerWithEarnings:
    def __init__(self, frame: pd.DataFrame) -> None:
        self._frame = frame

    def get_earnings_dates(self, limit: int = 12) -> pd.DataFrame:
        return self._frame


class _FakeTickerWithoutEarnings:
    def get_earnings_dates(self, limit: int = 12):
        raise RuntimeError("no earnings dates")


def test_transcript_candidate_quarters_prefers_earnings_dates(monkeypatch):
    frame = pd.DataFrame(
        {"Reported EPS": [1, 1, 1, 1, 1]},
        index=pd.to_datetime([
            "2099-01-15",
            "2026-03-20",
            "2025-12-18",
            "2025-09-22",
            "2025-06-30",
        ]),
    )

    monkeypatch.setattr(providers.yf, "Ticker", lambda symbol: _FakeTickerWithEarnings(frame))

    labels = providers.transcript_candidate_quarters("AAPL", limit=4)

    assert labels == ["2026-Q1", "2025-Q4", "2025-Q3", "2025-Q2"]


def test_transcript_candidate_quarters_falls_back_to_historical_scan(monkeypatch):
    monkeypatch.setattr(providers.yf, "Ticker", lambda symbol: _FakeTickerWithoutEarnings())

    labels = providers.transcript_candidate_quarters("AAPL", limit=6)

    now = datetime.now(timezone.utc)
    expected_first = f"{now.year}-Q{providers._quarter_from_month(now.month)}"

    assert len(labels) == 6
    assert labels[0] == expected_first
    assert len(set(labels)) == 6
    assert all(re.match(r"^\d{4}-Q[1-4]$", label) for label in labels)


def test_fetch_last_4_transcripts_stops_after_first_four_valid(monkeypatch):
    candidates = [
        "2026-Q2",
        "2026-Q1",
        "2025-Q4",
        "2025-Q3",
        "2025-Q2",
        "2025-Q1",
        "2024-Q4",
    ]
    processed: list[str] = []

    monkeypatch.setattr(providers, "transcript_candidate_quarters", lambda symbol, limit=12: candidates)

    def _fake_fetch(symbol: str, year: int, quarter: int, api_key: str, timeout_seconds: int):
        label = f"{year}-Q{quarter}"
        processed.append(label)

        if label == "2026-Q1":
            return None
        if label == "2025-Q4":
            raise RuntimeError("simulated alpha failure")

        found = {"2026-Q2", "2025-Q3", "2025-Q2", "2025-Q1", "2024-Q4"}
        if label in found:
            return TranscriptRecord(
                symbol=symbol,
                year=year,
                quarter=quarter,
                date=f"{year}-0{quarter}-15",
                content="Transcript payload",
                source="alpha_vantage",
            )
        return None

    monkeypatch.setattr(providers, "fetch_transcript_alpha_vantage", _fake_fetch)

    settings = Settings(alpha_vantage_api_key="test-key", finbert_model_name="x", request_timeout_seconds=1)

    transcripts, warnings, diagnostics = providers.fetch_last_4_transcripts("AAPL", settings)

    assert len(transcripts) == 4
    assert processed == [
        "2026-Q2",
        "2026-Q1",
        "2025-Q4",
        "2025-Q3",
        "2025-Q2",
        "2025-Q1",
    ]
    assert diagnostics.requested_quarters == processed
    assert diagnostics.found_quarters == ["2026-Q2", "2025-Q3", "2025-Q2", "2025-Q1"]
    assert diagnostics.missing_quarters == ["2026-Q1"]
    assert diagnostics.errors == ["2025-Q4: simulated alpha failure"]

    status_map = {outcome.quarter: outcome.status for outcome in diagnostics.outcomes}
    assert status_map["2026-Q2"] == "found"
    assert status_map["2026-Q1"] == "not_found"
    assert status_map["2025-Q4"] == "error"
    assert all("2024-Q4" not in outcome.quarter for outcome in diagnostics.outcomes)
    assert any("Alpha Vantage transcript error" in warning for warning in warnings)
