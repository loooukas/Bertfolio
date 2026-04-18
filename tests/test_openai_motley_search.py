from finbert_site.openai_motley_search import (
    MotleyTranscriptCandidate,
    _build_request_payload,
    _build_speaker_sections,
    _dedupe_links,
    _extract_participants_from_lines,
    _extract_transcript_lines,
    _extract_sources,
    _pick_best_candidate_by_quarter,
    _quarter_window,
    _select_most_recent_candidates,
    infer_year_quarter,
    scrape_recent_transcripts_for_report,
)


def test_infer_year_quarter_from_title() -> None:
    year, quarter = infer_year_quarter(
        title="Apple (AAPL) Q1 2026 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
        published_date="2026-01-29",
    )
    assert (year, quarter) == (2026, 1)


def test_infer_year_quarter_from_slug_when_title_missing() -> None:
    year, quarter = infer_year_quarter(
        title="Apple Earnings Recap",
        url="https://www.fool.com/earnings/call-transcripts/2025/10/28/apple-aapl-q4-2025-earnings-call-transcript/",
        published_date="",
    )
    assert (year, quarter) == (2025, 4)


def test_quarter_window_rolls_back_across_year_boundary() -> None:
    assert _quarter_window(2026, 1, 4) == [(2026, 1), (2025, 4), (2025, 3), (2025, 2)]


def test_pick_best_candidate_by_quarter_prefers_high_quality() -> None:
    low_quality = MotleyTranscriptCandidate(
        title="Apple Q1 2026 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-q1-2026-earnings-call-transcript/",
        published_date="2026-01-29",
        source="search result",
        year=2026,
        quarter=1,
        quality_score=2.0,
    )
    high_quality = MotleyTranscriptCandidate(
        title="Apple (AAPL) Q1 2026 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
        published_date="2026-01-29",
        source="search result",
        year=2026,
        quarter=1,
        quality_score=9.0,
    )
    selected = _pick_best_candidate_by_quarter([low_quality, high_quality])
    assert selected[(2026, 1)].url == high_quality.url


def test_build_request_payload_omits_temperature() -> None:
    payload = _build_request_payload(
        model="gpt-5-mini",
        ticker="AAPL",
        max_candidates=10,
        tool_type="web_search",
    )
    assert "temperature" not in payload


def test_extract_sources_collects_web_search_and_annotations() -> None:
    payload = {
        "output": [
            {
                "type": "web_search_call",
                "action": {
                    "sources": [
                        {"url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript"},
                    ]
                },
            },
            {
                "type": "message",
                "content": [
                    {
                        "annotations": [
                            {
                                "type": "url_citation",
                                "url": "https://www.fool.com/earnings/call-transcripts/2025/10/31/apple-aapl-q4-2025-earnings-call-transcript/",
                            }
                        ]
                    }
                ],
            },
        ]
    }
    links = _extract_sources(payload)
    assert links == [
        "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
        "https://www.fool.com/earnings/call-transcripts/2025/10/31/apple-aapl-q4-2025-earnings-call-transcript/",
    ]


def test_dedupe_links_normalizes_and_deduplicates() -> None:
    links = _dedupe_links(
        [
            "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript",
            "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
            "",
        ]
    )
    assert links == [
        "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/"
    ]


def test_extract_participants_from_lines_role_first_format() -> None:
    lines = [
        "Call participants",
        "Chief Executive Officer — Timothy D. Cook",
        "Chief Financial Officer — Kevan Parekh",
        "Takeaways",
    ]
    participants = _extract_participants_from_lines(lines)
    assert participants == [
        {"name": "Timothy D. Cook", "role": "Chief Executive Officer"},
        {"name": "Kevan Parekh", "role": "Chief Financial Officer"},
    ]


def test_extract_transcript_lines_from_full_transcript_heading() -> None:
    lines = [
        "Summary",
        "Full Conference Call Transcript",
        "Timothy D. Cook: Opening remarks.",
        "Operator: Next question.",
        "Read Next",
    ]
    transcript = _extract_transcript_lines(lines)
    assert transcript == [
        "Timothy D. Cook: Opening remarks.",
        "Operator: Next question.",
    ]


def test_build_speaker_sections_preserves_sequence() -> None:
    sections = _build_speaker_sections(
        [
            "Prepared Remarks",
            "Timothy D. Cook: We had a great quarter.",
            "Demand was strong.",
            "Questions and Answers",
            "Operator: First question.",
            "Analyst: Can you comment on guidance?",
        ]
    )
    assert len(sections) == 3
    assert sections[0]["speaker"] == "Timothy D. Cook"
    assert sections[0]["section_type"] == "prepared_remarks"
    assert sections[1]["speaker"] == "Operator"
    assert sections[1]["section_type"] == "qa"
    assert sections[2]["speaker"] == "Analyst"


def test_select_most_recent_candidates_from_candidate_pool() -> None:
    report = {
        "candidate_pool": [
            {"quarter": "2026-Q1", "title": "T1", "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/a/"},
            {"quarter": "2025-Q4", "title": "T2", "url": "https://www.fool.com/earnings/call-transcripts/2025/10/31/b/"},
            {"quarter": "2025-Q3", "title": "T3", "url": "https://www.fool.com/earnings/call-transcripts/2025/08/01/c/"},
        ]
    }
    selected = _select_most_recent_candidates(report, 2)
    assert [item["quarter"] for item in selected] == ["2026-Q1", "2025-Q4"]


def test_scrape_recent_transcripts_for_report_uses_selected_links(monkeypatch) -> None:
    report = {
        "ticker": "AAPL",
        "candidate_pool": [
            {"quarter": "2026-Q1", "title": "T1", "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/a/", "published_date": "2026-01-29"},
            {"quarter": "2025-Q4", "title": "T2", "url": "https://www.fool.com/earnings/call-transcripts/2025/10/31/b/", "published_date": "2025-10-31"},
        ],
    }

    def _fake_fetch(**kwargs):
        return {
            "quarter": kwargs["quarter"],
            "title": kwargs["title"],
            "url": kwargs["url"],
            "published_date": kwargs["published_date"],
            "participants": [],
            "speaker_sections": [{"speaker": "Operator", "text": "Hello"}],
            "speaker_count": 1,
            "speakers": ["Operator"],
            "section_count": 1,
            "transcript_line_count": 1,
            "transcript_char_count": 5,
        }

    monkeypatch.setattr("finbert_site.openai_motley_search._fetch_transcript_sections", _fake_fetch)
    payload = scrape_recent_transcripts_for_report(
        report=report,
        scrape_count=2,
        timeout_seconds=10,
    )
    assert payload["scraped_count"] == 2
    assert len(payload["scraped_transcripts"]) == 2
    assert payload["scrape_errors"] == []
