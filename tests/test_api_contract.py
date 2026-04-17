from __future__ import annotations

from fastapi.testclient import TestClient

from finbert_site.main import app
from finbert_site import main


class _DummyAnalysisResult:
    def model_dump(self):
        return {
            "ticker": "AAPL",
            "transcripts_found": 1,
            "overall_sentiment_score": 0.2913,
            "overall_sentiment_label": "cautiously_bullish",
            "warnings": ["No transcript for AAPL 2026-Q2"],
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
            "news_summary": {
                "article_count": 12,
                "avg_sentiment_score": 0.367,
                "sentiment_label": "bullish",
            },
            "social_summary": {
                "post_count": 12,
                "avg_sentiment_score": -0.028,
                "sentiment_label": "mixed",
            },
            "analyst_team": [],
            "research_team": {
                "bullish_points": [],
                "bearish_points": [],
                "discussion_summary": "summary",
                "buy_evidence_score": 63.93,
                "sell_evidence_score": 42.07,
            },
            "trader_plan": {
                "action": "hold",
                "conviction_score": 23.1,
                "thesis": "thesis",
                "horizon": "1-4 weeks",
            },
            "risk_management": {
                "views": [],
                "consensus": "consensus",
            },
            "manager_decision": {
                "action": "hold",
                "rationale": ["r1"],
                "execution_plan": ["p1"],
            },
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
                    "id": "summary",
                    "title": "Summary",
                    "markdown": "# Summary",
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


def test_api_contract_includes_new_and_legacy_fields(monkeypatch):
    monkeypatch.setattr(main, "build_analysis", lambda ticker, settings: _DummyAnalysisResult())

    client = TestClient(app)
    response = client.get("/api/analyze", params={"ticker": "AAPL"})

    assert response.status_code == 200
    payload = response.json()

    for key in ["run_summary", "data_health", "report_tabs", "charts"]:
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
    ]:
        assert key in payload
