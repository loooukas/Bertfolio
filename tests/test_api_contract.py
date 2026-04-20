from __future__ import annotations

from fastapi.testclient import TestClient

from finbert_site import main
from finbert_site.main import app


class _DummyAnalysisResult:
    def model_dump(self):
        return {
            "analysis_version": "2026.04-earnings-signals-v1",
            "ui_copy": {
                "app_title": "FinBERT Earnings Signals",
                "app_subtitle": "Transcript-first workspace",
                "section_labels": {
                    "overview": "Overview",
                    "transcript": "Transcript",
                    "market_reaction": "Market Reaction",
                    "fundamentals": "Fundamentals",
                    "data_audit": "Data Audit",
                },
                "ui_labels": {"run_analysis": "Run Analysis", "ticker": "Ticker"},
                "empty_states": {"transcript": "No transcript"},
            },
            "overview": {
                "ticker": "AAPL",
                "company_name": "Apple Inc",
                "stance_label": "bullish",
                "executive_summary": "summary",
                "key_takeaways": ["t1", "t2", "t3"],
                "metrics": [{"key": "confidence", "label": "Management Confidence", "value": "74.0"}],
            },
            "transcript": {
                "availability": "partial",
                "transcript_count_requested": 4,
                "transcript_count_found": 1,
                "latest_summary": "latest summary",
                "prepared_vs_qa_note": "Prepared remarks blocks: 2; Q&A blocks: 1.",
                "speaker_analysis": [],
                "key_quotes": ["quote"],
                "qa_pressure_points": ["point"],
                "transcripts": [],
                "speaker_confidence_profile": [],
                "chart_enabled": False,
                "sparse_note": "Not enough speaker diversity",
            },
            "market_reaction": {
                "balance_summary": "news bullish social mixed",
                "news_count": 12,
                "social_count": 12,
                "news_items": [],
                "social_items": [],
                "chart_enabled": False,
                "sparse_note": "Not enough timeline depth",
            },
            "fundamentals_workspace": {
                "operating_context": "context",
                "metrics": [{"key": "trailing_pe", "label": "Trailing PE", "value": "30"}],
                "table": [],
                "trend_series": [],
                "chart_enabled": False,
                "sparse_note": "Not enough quarterly depth",
            },
            "data_audit": {
                "transcript_discovery": {
                    "pages_scanned": 2,
                    "candidates_total": 8,
                    "transcript_like_count": 4,
                    "match_filtered_count": 2,
                    "selected_count": 1,
                    "discarded_near_matches": [],
                    "fetch_failures": [],
                    "playwright_fallback_used": False,
                },
                "source_counts": {"transcripts": 1, "news": 12, "social": 12},
                "dedupe_counts": {"news_pool": 20, "news_deduped": 14, "social_pool": 30, "social_deduped": 18},
                "parsing_warnings": [],
                "missing_items": [],
                "normalization_mode": "deterministic_degraded",
                "warnings": [],
                "confidence_note": "Average transcript extraction confidence is 0.81.",
            },
            "ticker": "AAPL",
            "transcripts_found": 1,
            "overall_sentiment_score": 0.2913,
            "overall_sentiment_label": "cautiously_bullish",
            "warnings": [],
            "aggregate_scores": {
                "company_strength_score": 66.44,
                "outlook_score": 50.0,
                "confidence_score": 50.0,
                "evasiveness_score": 35.0,
                "sentiment_label": "cautiously_bullish",
            },
            "fundamentals": {
                "currency": "USD",
                "market_cap": 3871433555968,
                "trailing_pe": 33.3,
                "forward_pe": 28.29,
                "debt_to_equity": 102.63,
                "quarterly": [],
                "revenue_qoq_growth_pct": 40.3,
                "eps_qoq_growth_pct": None,
            },
            "news_summary": {"article_count": 12, "avg_sentiment_score": 0.367, "sentiment_label": "bullish"},
            "social_summary": {"post_count": 12, "avg_sentiment_score": -0.028, "sentiment_label": "mixed"},
            "analyst_team": [],
            "research_team": {
                "bullish_points": [],
                "bearish_points": [],
                "discussion_summary": "legacy",
                "buy_evidence_score": 55,
                "sell_evidence_score": 45,
            },
            "trader_plan": {"action": "hold", "conviction_score": 0, "thesis": "legacy", "horizon": "n/a"},
            "risk_management": {
                "views": [
                    {"profile": "aggressive", "recommendation": "legacy", "max_position_pct": 0},
                    {"profile": "neutral", "recommendation": "legacy", "max_position_pct": 0},
                    {"profile": "conservative", "recommendation": "legacy", "max_position_pct": 0},
                ],
                "consensus": "legacy",
            },
            "manager_decision": {"action": "hold", "rationale": ["legacy"], "execution_plan": ["legacy"]},
            "workflow": [],
            "run_summary": {
                "ticker": "AAPL",
                "overall_label": "cautiously_bullish",
                "overall_score": 0.2913,
                "transcripts_found": 1,
                "news_count": 12,
                "social_count": 12,
            },
            "data_health": {
                "transcripts": {
                    "requested_quarters": ["2026-Q2", "2026-Q1"],
                    "found_quarters": ["2026-Q1"],
                    "missing_quarters": ["2026-Q2"],
                    "errors": [],
                    "outcomes": [
                        {"quarter": "2026-Q2", "status": "not_found", "detail": None},
                        {"quarter": "2026-Q1", "status": "found", "detail": None},
                    ],
                },
                "warnings_compact": ["Transcripts 1/2 found."],
            },
            "report_tabs": [
                {
                    "id": "overview",
                    "title": "Overview",
                    "markdown": "# Overview",
                    "kpis": [{"label": "overall", "value": "cautiously_bullish"}],
                    "tables": [{"title": "Core KPI", "columns": ["Metric", "Value"], "rows": [["Overall", "x"]]}],
                }
            ],
            "charts": {
                "price_volume": [{"date": "2026-04-16", "close": 199.33, "volume": 61200000}],
                "sentiment_timeline": [{"date": "2026-04-16", "news": 0.4, "social": -0.1, "blended": 0.15}],
                "fundamentals_trend": [{"quarter": "2025-Q4", "revenue": 143756000000, "net_income": 42097000000, "eps": 2.33}],
            },
            "news": [],
            "social": [],
            "transcripts": [],
        }


def test_api_contract_includes_new_sections_and_legacy_fields(monkeypatch):
    monkeypatch.setattr(main, "build_analysis", lambda ticker, settings: _DummyAnalysisResult())

    client = TestClient(app)
    response = client.get("/api/analyze", params={"ticker": "AAPL"})

    assert response.status_code == 200
    payload = response.json()

    for key in [
        "analysis_version",
        "ui_copy",
        "overview",
        "transcript",
        "market_reaction",
        "fundamentals_workspace",
        "data_audit",
    ]:
        assert key in payload

    for key in [
        "ticker",
        "overall_sentiment_score",
        "overall_sentiment_label",
        "aggregate_scores",
        "fundamentals",
        "news_summary",
        "social_summary",
        "news",
        "social",
        "transcripts",
        "workflow",
        "trader_plan",
        "manager_decision",
    ]:
        assert key in payload


def test_snapshot_endpoint_returns_preview_payload(monkeypatch):
    monkeypatch.setattr(
        main,
        "build_sentiment_snapshot",
        lambda ticker, settings: {
            "ticker": "AAPL",
            "company_name": "Apple Inc",
            "overall_sentiment_score": 0.12,
            "overall_sentiment_label": "cautiously_bullish",
            "overview": {
                "ticker": "AAPL",
                "company_name": "Apple Inc",
                "stance_label": "bullish",
                "executive_summary": "snapshot summary",
                "key_takeaways": ["takeaway"],
                "metrics": [],
            },
            "market_reaction": {
                "balance_summary": "snapshot market",
                "news_count": 4,
                "social_count": 3,
                "news_items": [],
                "social_items": [],
                "chart_enabled": False,
                "sparse_note": None,
            },
            "warnings": [],
            "ui_copy": {"section_labels": {"overview": "Overview"}},
        },
    )

    client = TestClient(app)
    response = client.get("/api/analyze/snapshot", params={"ticker": "AAPL"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert "overview" in payload
    assert "market_reaction" in payload
