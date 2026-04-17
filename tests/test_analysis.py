from __future__ import annotations

from finbert_site import analysis
from finbert_site.providers import (
    NewsRecord,
    PriceVolumeRecord,
    SocialRecord,
    TranscriptFetchDiagnostics,
    TranscriptFetchOutcome,
    TranscriptRecord,
)
from finbert_site.settings import Settings


class _StubEngine:
    def score_text(self, text: str):
        return {
            "positive": 0.68,
            "negative": 0.14,
            "neutral": 0.18,
            "directional_score": 0.54,
            "label": "cautiously_positive",
        }

    def classify_sentences(self, sentences):
        return [
            {
                "sentence": sentence,
                "label": "positive",
                "score": 0.7,
                "positive": 0.7,
                "negative": 0.1,
                "neutral": 0.2,
            }
            for sentence in sentences
        ]


def test_build_analysis_includes_data_health_report_tabs_and_charts(monkeypatch):
    diagnostics = TranscriptFetchDiagnostics(
        requested_quarters=["2026-Q2", "2026-Q1", "2025-Q4", "2025-Q3"],
        found_quarters=["2025-Q4"],
        missing_quarters=["2026-Q2", "2026-Q1", "2025-Q3"],
        errors=["2026-Q1: timeout"],
        outcomes=[
            TranscriptFetchOutcome("2026-Q2", "not_found"),
            TranscriptFetchOutcome("2026-Q1", "error", "timeout"),
            TranscriptFetchOutcome("2025-Q4", "found"),
            TranscriptFetchOutcome("2025-Q3", "not_found"),
        ],
    )

    monkeypatch.setattr(
        analysis,
        "fetch_last_4_transcripts",
        lambda symbol, settings: (
            [
                TranscriptRecord(
                    symbol=symbol,
                    year=2025,
                    quarter=4,
                    date="2025-12-20",
                    content=(
                        "We expect strong demand and margin expansion. "
                        "Question-and-answer section follows. "
                        "We remain confident in guidance."
                    ),
                    source="alpha_vantage",
                )
            ],
            ["No transcript for AAPL 2026-Q2"],
            diagnostics,
        ),
    )

    monkeypatch.setattr(
        analysis,
        "fetch_news_alpha_vantage",
        lambda symbol, settings, limit=12: (
            [
                NewsRecord(
                    title="Apple demand remains resilient",
                    summary="Supply chain looks stable.",
                    url="https://example.com/news/1",
                    source="example",
                    time_published="20260416T120000",
                    sentiment_score=0.32,
                    sentiment_label="bullish",
                )
            ],
            [],
        ),
    )

    monkeypatch.setattr(
        analysis,
        "fetch_social_reddit",
        lambda symbol, settings, limit=12: (
            [
                SocialRecord(
                    source="reddit",
                    title="AAPL discussion thread",
                    body="I think earnings sentiment improved this quarter.",
                    url="https://reddit.com/r/stocks/aapl",
                    subreddit="stocks",
                    created_utc=1776316800,
                    relevance_score=7.8,
                )
            ],
            [],
        ),
    )

    monkeypatch.setattr(
        analysis,
        "fetch_fundamentals",
        lambda symbol: {
            "currency": "USD",
            "market_cap": 3500000000000,
            "trailing_pe": 32.1,
            "forward_pe": 28.4,
            "debt_to_equity": 105.3,
            "quarterly": [
                {
                    "quarter": "2025-Q4",
                    "revenue": 143756000000.0,
                    "net_income": 42097000000.0,
                    "reported_eps": 2.33,
                    "eps_estimate": 2.21,
                },
                {
                    "quarter": "2025-Q3",
                    "revenue": 102466000000.0,
                    "net_income": 27466000000.0,
                    "reported_eps": 1.87,
                    "eps_estimate": 1.81,
                },
            ],
            "revenue_qoq_growth_pct": 40.3,
            "eps_qoq_growth_pct": 24.6,
        },
    )

    monkeypatch.setattr(
        analysis,
        "fetch_price_volume_history",
        lambda symbol, period="3mo": [
            PriceVolumeRecord(date="2026-04-15", close=198.12, volume=52100000),
            PriceVolumeRecord(date="2026-04-16", close=199.33, volume=61200000),
        ],
    )

    monkeypatch.setattr(analysis, "get_engine", lambda model_name: _StubEngine())

    response = analysis.build_analysis(
        ticker="AAPL",
        settings=Settings(alpha_vantage_api_key="x", finbert_model_name="stub", request_timeout_seconds=1),
    )

    assert response.run_summary.ticker == "AAPL"
    assert response.data_health.transcripts.requested_quarters == diagnostics.requested_quarters
    assert response.data_health.warnings_compact[0].startswith("Transcripts 1/4 found")

    tab_ids = {tab.id for tab in response.report_tabs}
    assert tab_ids == {"summary", "analyst", "research", "trader", "risk_manager", "data_health"}
    for tab in response.report_tabs:
        assert tab.kpis
        assert tab.tables

    assert len(response.charts.price_volume) == 2
    assert len(response.charts.sentiment_timeline) >= 1
    assert len(response.charts.fundamentals_trend) == 2

    assert response.run_summary.news_count == len(response.news)
    assert response.run_summary.social_count == len(response.social)
