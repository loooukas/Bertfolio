from __future__ import annotations

from finbert_site import analysis
from finbert_site.normalizer import NormalizationResult
from finbert_site.providers import (
    FeedFetchAudit,
    NewsRecord,
    PriceVolumeRecord,
    SocialRecord,
    TranscriptDiscoveryAudit,
    TranscriptFetchDiagnostics,
    TranscriptFetchOutcome,
    TranscriptRecord,
)
from finbert_site.schemas import TranscriptDocument, TranscriptParticipant, TranscriptSectionBlock, TranscriptSpeakerAnalysis
from finbert_site.settings import Settings


class _StubEngine:
    def score_text(self, text: str):
        return {
            "positive": 0.6,
            "negative": 0.2,
            "neutral": 0.2,
            "directional_score": 0.4,
            "label": "cautiously_positive",
        }


def _settings(**overrides) -> Settings:
    base = Settings(
        alpha_vantage_api_key="x",
        finbert_model_name="stub",
        request_timeout_seconds=1,
        transcript_target_count=4,
        openai_api_key="",
        openai_normalizer_model="gpt-4o-mini",
    )
    return base.__class__(**{**base.__dict__, **overrides})


def test_build_analysis_returns_new_sections_and_legacy_fields(monkeypatch):
    transcript_record = TranscriptRecord(
        symbol="AAPL",
        year=2026,
        quarter=1,
        date="2026-01-29",
        content="Prepared Remarks\nTim Cook: Demand remained strong.\nQuestions and Answers\nAnalyst: margins?",
        source="motley_fool",
        source_url="https://example.com/transcript",
        title="Apple (AAPL) Q1 2026 Earnings Call Transcript",
        extraction_confidence=0.88,
        parsing_warnings=[],
        participants=[{"name": "Tim Cook", "role": "CEO"}],
    )

    transcript_diag = TranscriptFetchDiagnostics(
        requested_quarters=["2026-Q1"],
        found_quarters=["2026-Q1"],
        missing_quarters=[],
        errors=[],
        outcomes=[TranscriptFetchOutcome("2026-Q1", "found")],
    )

    transcript_discovery = TranscriptDiscoveryAudit(
        pages_scanned=2,
        candidates_total=8,
        transcript_like_count=4,
        match_filtered_count=2,
        selected_count=1,
        discarded_near_matches=["Apple Q4 2025 Earnings Call Transcript (...)"],
        fetch_failures=[],
        playwright_fallback_used=False,
    )

    monkeypatch.setattr(
        analysis,
        "fetch_transcripts_motley_fool",
        lambda symbol, company_name, settings, target_count=4: (
            [transcript_record],
            [],
            transcript_diag,
            transcript_discovery,
        ),
    )

    monkeypatch.setattr(
        analysis,
        "fetch_news_alpha_vantage",
        lambda symbol, settings, limit=16, pool_size=80, company_name=None, lookback_days=14: (
            [
                NewsRecord(
                    title="Apple demand remains resilient",
                    summary="Supply chain commentary remains stable.",
                    url="https://example.com/news/1",
                    source="example",
                    time_published="20260416T120000",
                    sentiment_score=0.2,
                    sentiment_label="bullish",
                )
            ],
            [],
            FeedFetchAudit(fetched_pool=10, deduped_pool=6, displayed_count=1),
        ),
    )

    monkeypatch.setattr(
        analysis,
        "fetch_social_reddit",
        lambda symbol, settings, limit=16, pool_size=120, company_name=None, lookback_days=14: (
            [
                SocialRecord(
                    source="reddit",
                    title="AAPL discussion thread",
                    body="Long body text for modal rendering.",
                    excerpt="Long body text for modal rendering.",
                    url="https://reddit.com/r/stocks/aapl",
                    subreddit="stocks",
                    created_utc=1776316800,
                    relevance_score=7.8,
                )
            ],
            [],
            FeedFetchAudit(fetched_pool=20, deduped_pool=11, displayed_count=1),
        ),
    )

    monkeypatch.setattr(
        analysis,
        "fetch_fundamentals",
        lambda symbol: {
            "company_name": "Apple Inc",
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

    normalized_document = TranscriptDocument(
        ticker="AAPL",
        company_name="Apple Inc",
        source="motley_fool",
        source_url="https://example.com/transcript",
        title="Apple (AAPL) Q1 2026 Earnings Call Transcript",
        published_date="2026-01-29",
        has_full_transcript=True,
        extraction_confidence=0.88,
        parsing_warnings=[],
        participants=[TranscriptParticipant(name="Tim Cook", role="CEO")],
        sections=[
            TranscriptSectionBlock(
                section_type="prepared_remarks",
                speaker="Tim Cook",
                speaker_role="management",
                text="Demand remained strong.",
                order_index=0,
                evidence_snippets=["Demand remained strong."],
            )
        ],
        key_quotes=["Demand remained strong."],
        normalization_mode="deterministic_degraded",
    )

    monkeypatch.setattr(
        analysis,
        "normalize_transcript_document",
        lambda **kwargs: NormalizationResult(document=normalized_document, warnings=["OPENAI_API_KEY missing"]),
    )

    monkeypatch.setattr(
        analysis,
        "build_speaker_analysis",
        lambda sections, score_text_fn: [
            TranscriptSpeakerAnalysis(
                speaker="Tim Cook",
                section_type="prepared_remarks",
                sentiment_direction=0.41,
                confidence=74.0,
                evasiveness=29.0,
                specificity=71.0,
                forward_looking_strength=66.0,
                risk_language_intensity=24.0,
                topic_label="demand",
                evidence_snippets=["Demand remained strong."],
            )
        ],
    )

    monkeypatch.setattr(
        analysis,
        "summarize_transcript_findings",
        lambda speaker_analysis: (
            "Transcript shows confident tone with low evasiveness.",
            ["Confidence stayed strong in prepared remarks."],
            ["Margins question had softer specificity."],
        ),
    )

    monkeypatch.setattr(analysis, "get_engine", lambda model_name: _StubEngine())

    result = analysis.build_analysis("AAPL", _settings())

    assert result.analysis_version.startswith("2026.04")
    assert result.ui_copy.app_title == "FinBERT Earnings Signals"

    assert result.overview.ticker == "AAPL"
    assert result.transcript.transcript_count_found == 1
    assert result.market_reaction.news_count == 1
    assert result.fundamentals_workspace.table
    assert result.data_audit.transcript_discovery.pages_scanned == 2

    # strict chart gating for timeline: only one point should disable it
    assert result.market_reaction.chart_enabled is False

    # dual contract still present
    assert result.trader_plan.action == "hold"
    assert result.manager_decision.action == "hold"
    assert result.report_tabs


class _SegmentEngine:
    def score_text(self, text: str):
        mapping = {
            "SEG00": -0.9,
            "SEG01": -0.6,
            "SEG02": -0.4,
            "SEG03": -0.2,
            "SEG04": -0.1,
            "SEG05": 0.1,
            "SEG06": 0.2,
            "SEG07": 0.4,
            "SEG08": 0.6,
            "SEG09": 0.9,
        }
        directional = 0.0
        for token, score in mapping.items():
            if token in text:
                directional = score
                break
        positive = max(0.0, directional)
        negative = max(0.0, -directional)
        neutral = max(0.0, 1.0 - positive - negative)
        return {
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "directional_score": directional,
            "label": "mixed",
        }


def test_score_text_with_segmentation_trims_tail_segments():
    settings = _settings(
        transcript_sentiment_segment_chars=260,
        transcript_sentiment_segment_max=320,
        transcript_sentiment_segment_min=180,
        transcript_sentiment_segment_overlap_sentences=0,
    )
    engine = _SegmentEngine()

    sentences: list[str] = []
    for idx in range(10):
        token = f"SEG{idx:02d}"
        sentences.append(
            f"{token} "
            + ("Management provided detailed commentary on demand, margin, and guidance trends. " * 3).strip()
            + "."
        )
    block = " ".join(sentences)

    scored = analysis._score_text_with_segmentation(block, engine, settings)

    directional = float(scored["directional_score"])
    assert abs(directional) < 0.25
    diagnostics = scored.get("segment_diagnostics")
    assert isinstance(diagnostics, dict)
    assert diagnostics["segment_count"] >= 8
    assert diagnostics["kept_segment_count"] < diagnostics["segment_count"]


def test_score_text_with_segmentation_skips_short_blocks():
    settings = _settings()
    engine = _SegmentEngine()
    short_text = "SEG07 Management reiterated confident demand and margin outlook."

    scored = analysis._score_text_with_segmentation(short_text, engine, settings)

    assert float(scored["directional_score"]) == 0.4
    assert "segment_diagnostics" not in scored
