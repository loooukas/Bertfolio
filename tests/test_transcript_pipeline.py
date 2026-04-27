from __future__ import annotations

from finbert_site import transcript_pipeline
from finbert_site.providers import TranscriptDiscoveryAudit, TranscriptFetchDiagnostics, TranscriptFetchOutcome, TranscriptRecord
from finbert_site.settings import Settings


def _settings(**overrides) -> Settings:
    base = Settings(
        alpha_vantage_api_key="test",
        finbert_model_name="stub",
        request_timeout_seconds=30,
        transcript_target_count=4,
        openai_api_key="sk-test",
        openai_normalizer_model="gpt-4o-mini",
        openai_search_model="gpt-5-mini",
        transcript_pipeline_mode="motley_cli",
        transcript_pipeline_fallback_to_legacy=True,
        motley_timeout_seconds=45,
        motley_openai_retries=3,
        motley_discovery_mode="hybrid",
        motley_sitemap_lookback_months=24,
        motley_author_max_pages=0,
        motley_scrape_count=4,
        motley_scrape_cache_mode="refresh",
        motley_scrape_cache_dir="output/openai_motley_cache",
        motley_discovery_cache_mode="refresh",
        motley_discovery_cache_dir="output/openai_motley_discovery_cache",
        transcript_sentiment_segment_chars=650,
        transcript_sentiment_segment_max=1000,
        transcript_sentiment_segment_min=180,
        transcript_sentiment_segment_overlap_sentences=1,
    )
    return base.__class__(**{**base.__dict__, **overrides})


def test_fetch_transcripts_for_analysis_maps_discovery_and_scrape_payload(monkeypatch):
    monkeypatch.setattr(
        transcript_pipeline,
        "discover_last_quarter_links",
        lambda **kwargs: {
            "ticker": "AAPL",
            "requested_quarters": ["2026-Q1", "2025-Q4", "2025-Q3", "2025-Q2"],
            "found_quarters": ["2026-Q1", "2025-Q4", "2025-Q3"],
            "missing_quarters": ["2025-Q2"],
            "quarters": [
                {"quarter": "2026-Q1", "status": "found"},
                {"quarter": "2025-Q4", "status": "found"},
                {"quarter": "2025-Q3", "status": "found"},
                {"quarter": "2025-Q2", "status": "not_found"},
            ],
            "raw_candidate_count": 7,
            "accepted_candidate_count": 4,
            "warnings": ["Dropped 1 off-ticker candidate during cleanup."],
            "discovery_trace": {
                "phases": [
                    {"phase": "sitemap", "months_scanned": 24, "failures": []},
                    {"phase": "author", "pages_scanned": 0, "failures": []},
                ]
            },
        },
    )

    monkeypatch.setattr(
        transcript_pipeline,
        "scrape_recent_transcripts_for_report",
        lambda **kwargs: {
            "scraped_transcripts": [
                {
                    "quarter": "2026-Q1",
                    "title": "Apple (AAPL) Q1 2026 Earnings Call Transcript",
                    "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
                    "published_date": "2026-01-29",
                    "speaker_sections": [
                        {"speaker": "Operator", "text": "Welcome."},
                        {"speaker": "Tim Cook", "text": "Demand remained resilient."},
                    ],
                    "participants": [{"name": "Tim Cook", "role": "CEO"}],
                    "section_parse_method": "openai_page_text",
                },
                {
                    "quarter": "2025-Q4",
                    "title": "Apple (AAPL) Q4 2025 Earnings Call Transcript",
                    "url": "https://www.fool.com/earnings/call-transcripts/2025/10/31/apple-aapl-q4-2025-earnings-call-transcript/",
                    "published_date": "2025-10-31",
                    "speaker_sections": [{"speaker": "Tim Cook", "text": "Margins improved."}],
                    "participants": [{"name": "Tim Cook", "role": "CEO"}],
                    "section_parse_method": "regex_from_page_text",
                    "quality_flags": {"parser_low_confidence": False},
                },
            ],
            "scrape_errors": [
                {"quarter": "2025-Q3", "error": "HTTP 503", "error_category": "http_error"},
            ],
        },
    )

    transcripts, warnings, diagnostics, discovery = transcript_pipeline.fetch_transcripts_for_analysis(
        symbol="AAPL",
        company_name="Apple Inc",
        settings=_settings(),
        target_count=4,
    )

    assert len(transcripts) == 2
    assert diagnostics.requested_quarters == ["2026-Q1", "2025-Q4", "2025-Q3", "2025-Q2"]
    assert diagnostics.found_quarters == ["2026-Q1", "2025-Q4"]
    assert diagnostics.missing_quarters == ["2025-Q2"]
    assert any(outcome.quarter == "2025-Q3" and outcome.status == "error" for outcome in diagnostics.outcomes)
    assert discovery.pages_scanned == 24
    assert discovery.candidates_total == 7
    assert discovery.transcript_like_count == 4
    assert any("off-ticker" in warning.lower() for warning in warnings)


def test_fetch_transcripts_for_analysis_fallbacks_to_legacy(monkeypatch):
    monkeypatch.setattr(
        transcript_pipeline,
        "_fetch_transcripts_motley_cli",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("OPENAI timeout")),
    )

    legacy_diag = TranscriptFetchDiagnostics(
        requested_quarters=["2026-Q1"],
        found_quarters=["2026-Q1"],
        missing_quarters=[],
        errors=[],
        outcomes=[TranscriptFetchOutcome(quarter="2026-Q1", status="found", detail=None)],
    )
    legacy_discovery = TranscriptDiscoveryAudit(
        pages_scanned=2,
        candidates_total=5,
        transcript_like_count=3,
        match_filtered_count=2,
        selected_count=1,
        discarded_near_matches=[],
        fetch_failures=[],
        playwright_fallback_used=False,
    )
    legacy_transcript = TranscriptRecord(
        symbol="AAPL",
        year=2026,
        quarter=1,
        date="2026-01-29",
        content="Tim Cook: We had a strong quarter.",
        source="motley_fool",
        source_url="https://example.com/legacy",
        title="Legacy transcript",
        extraction_confidence=0.7,
        parsing_warnings=[],
        participants=[],
    )

    monkeypatch.setattr(
        transcript_pipeline,
        "fetch_transcripts_motley_fool",
        lambda **kwargs: ([legacy_transcript], [], legacy_diag, legacy_discovery),
    )

    transcripts, warnings, diagnostics, discovery = transcript_pipeline.fetch_transcripts_for_analysis(
        symbol="AAPL",
        company_name="Apple Inc",
        settings=_settings(transcript_pipeline_mode="motley_cli"),
        target_count=4,
    )

    assert transcripts and transcripts[0].source == "motley_fool"
    assert warnings and "fallback to legacy provider" in warnings[0].lower()
    assert diagnostics.errors and "fallback to legacy provider" in diagnostics.errors[0].lower()
    assert discovery.fetch_failures and "fallback to legacy provider" in discovery.fetch_failures[0].lower()

