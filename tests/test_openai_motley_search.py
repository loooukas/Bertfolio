import pytest

from finbert_site.openai_motley_search import (
    MotleyTranscriptCandidate,
    TranscriptExtractionError,
    _build_html_report,
    _build_request_payload,
    _build_speaker_sections,
    _clean_candidates,
    _dedupe_links,
    _extract_month_sitemap_urls_from_index,
    _extract_participants_from_lines,
    _extract_sources,
    _extract_text_lines_from_script_payloads,
    _extract_text_lines_relaxed,
    _extract_transcript_lines,
    _extract_transcript_lines_with_diagnostics,
    _fetch_text_with_retries,
    _fetch_transcript_sections,
    _is_low_quality_structured_sections,
    _parse_speaker_sections_from_text,
    _parse_transcript_from_html,
    _pick_best_candidate_by_quarter,
    _quarter_window,
    _is_retryable_openai_request_error,
    _is_retryable_openai_structuring_error,
    _select_most_recent_candidates,
    discover_last_quarter_links,
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


def test_build_request_payload_includes_missing_quarter_focus() -> None:
    payload = _build_request_payload(
        model="gpt-5-mini",
        ticker="AAPL",
        max_candidates=6,
        tool_type="web_search",
        missing_quarters=["2025-Q2"],
    )
    prompt = str(payload.get("input") or "")
    assert "2025-Q2" in prompt
    assert "Focus only on unresolved quarter labels" in prompt


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


def test_extract_sources_parses_urls_from_output_text_fallback() -> None:
    payload = {
        "output_text": (
            "Latest links: https://www.fool.com/earnings/call-transcripts/2026/01/28/"
            "microsoft-msft-q2-2026-earnings-call-transcript/ and "
            "https://www.fool.com/earnings/call-transcripts/2025/10/29/"
            "microsoft-msft-q1-2026-earnings-call-transcript/"
        )
    }
    links = _extract_sources(payload)
    assert links == [
        "https://www.fool.com/earnings/call-transcripts/2026/01/28/microsoft-msft-q2-2026-earnings-call-transcript/",
        "https://www.fool.com/earnings/call-transcripts/2025/10/29/microsoft-msft-q1-2026-earnings-call-transcript/",
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


def test_extract_month_sitemap_urls_from_index_parses_month_entries() -> None:
    xml_text = """
    <sitemapindex>
      <sitemap><loc>https://www.fool.com/sitemap/2026/04</loc></sitemap>
      <sitemap><loc>https://www.fool.com/sitemap/2026/03/</loc></sitemap>
      <sitemap><loc>https://www.fool.com/sitemap/authors/</loc></sitemap>
    </sitemapindex>
    """
    month_urls = _extract_month_sitemap_urls_from_index(xml_text)
    assert month_urls == {
        "2026-04": "https://www.fool.com/sitemap/2026/04",
        "2026-03": "https://www.fool.com/sitemap/2026/03",
    }


def test_extract_month_sitemap_urls_from_index_supports_query_and_relative_urls() -> None:
    xml_text = """
    <sitemapindex>
      <sitemap><loc>/sitemap/2026/01?</loc></sitemap>
      <sitemap><loc>//www.fool.com/sitemap/2026/02?x=1</loc></sitemap>
      <sitemap><loc>https://example.com/sitemap/2026/03</loc></sitemap>
    </sitemapindex>
    """
    month_urls = _extract_month_sitemap_urls_from_index(xml_text)
    assert month_urls == {
        "2026-01": "https://www.fool.com/sitemap/2026/01",
        "2026-02": "https://www.fool.com/sitemap/2026/02",
    }


def test_fetch_text_with_retries_does_not_retry_404(monkeypatch) -> None:
    class _Resp404:
        status_code = 404

        def raise_for_status(self) -> None:
            import requests

            raise requests.HTTPError("404 Client Error", response=self)

    calls = {"count": 0, "sleep": 0}

    def _fake_get(*args, **kwargs):
        calls["count"] += 1
        return _Resp404()

    monkeypatch.setattr("finbert_site.openai_motley_search.requests.get", _fake_get)
    monkeypatch.setattr("finbert_site.openai_motley_search.time.sleep", lambda *_args, **_kwargs: calls.__setitem__("sleep", calls["sleep"] + 1))

    with pytest.raises(RuntimeError) as exc:
        _fetch_text_with_retries(url="https://www.fool.com/sitemap/2026/04", timeout_seconds=5, retries=3)

    assert "http_error" in str(exc.value)
    assert calls["count"] == 1
    assert calls["sleep"] == 0


def test_fetch_text_with_retries_uses_response_cache(monkeypatch) -> None:
    class _Resp200:
        status_code = 200
        text = "ok"

        def raise_for_status(self) -> None:
            return None

    calls = {"count": 0}

    def _fake_get(*args, **kwargs):
        calls["count"] += 1
        return _Resp200()

    monkeypatch.setattr("finbert_site.openai_motley_search.requests.get", _fake_get)
    cache: dict[str, str] = {}
    first = _fetch_text_with_retries(
        url="https://www.fool.com/sitemap/2026/01",
        timeout_seconds=5,
        retries=1,
        response_cache=cache,
    )
    second = _fetch_text_with_retries(
        url="https://www.fool.com/sitemap/2026/01",
        timeout_seconds=5,
        retries=1,
        response_cache=cache,
    )
    assert first == "ok"
    assert second == "ok"
    assert calls["count"] == 1


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


def test_extract_transcript_lines_does_not_treat_inline_phrase_as_heading() -> None:
    lines = [
        "Timothy D. Cook: Opening remarks.",
        "Operator: Next question.",
        "Analyst: Sorry, I missed that in your prepared remarks.",
        "Operator: Thank you.",
    ]
    transcript, marker = _extract_transcript_lines_with_diagnostics(lines)
    assert marker["start_reason"] in {"repeated_speaker", "single_speaker_fallback"}
    assert transcript[0].startswith("Timothy D. Cook:")


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


def test_parse_speaker_sections_from_text_infers_qa_and_participants() -> None:
    transcript_text = """
Timothy D. Cook: We delivered a strong quarter and exceeded guidance.
Kevan Parekh: Revenue grew double digits year over year.
Suhasini Chandramouli: Thank you, Kevan. Operator, may we have the first question please?
Operator: Certainly. We will now take our first question.
Amit Daryanani: Thanks for taking my question. Can you comment on margins?
Timothy D. Cook: We are pleased with margin performance this quarter.
""".strip()
    parsed = _parse_speaker_sections_from_text(transcript_text)
    sections = parsed["speaker_sections"]
    assert len(sections) >= 5
    assert sections[0]["section_type"] == "prepared_remarks"
    assert sections[3]["speaker"] == "Operator"
    assert sections[3]["section_type"] == "qa"
    participant_names = {item["name"] for item in parsed["participants"]}
    assert "Timothy D. Cook" in participant_names
    assert "Amit Daryanani" in participant_names
    assert "Operator" in participant_names


def test_parse_speaker_sections_from_text_marks_qa_on_moderator_transition() -> None:
    transcript_text = """
Timothy D. Cook: We delivered a strong quarter and exceeded guidance.
Kevan Parekh: Revenue grew double digits year over year.
Suhasini Chandramouli: Thank you, Kevin. We ask that you limit yourself to two questions. Operator, may we have the first question, please?
Operator: Certainly.
Amit Daryanani: We will go ahead and take our first question from Amit Daryanani of Evercore. Yes. I have two. Maybe to start with, there is a lot of focus on memory impact.
Timothy D. Cook: Yeah. Amit, hi. Let me answer both at once.
""".strip()
    parsed = _parse_speaker_sections_from_text(transcript_text)
    sections = parsed["speaker_sections"]
    # The moderator handoff line should start Q&A rather than staying in prepared remarks.
    assert sections[2]["section_type"] == "qa"
    assert sections[3]["section_type"] == "qa"
    assert sections[4]["section_type"] == "qa"
    assert sections[4]["speaker_role"] == "analyst"


def test_low_quality_structured_sections_can_allow_single_section_per_segment() -> None:
    sections = [
        {
            "speaker": "Timothy D. Cook",
            "speaker_role": "management",
            "section_type": "prepared_remarks",
            "order_index": 0,
            "text": "Opening remarks",
        }
    ]
    default_low, default_reason = _is_low_quality_structured_sections(sections)
    assert default_low is True
    assert default_reason == "too_few_sections"
    segment_low, _ = _is_low_quality_structured_sections(sections, min_sections=1)
    assert segment_low is False


def test_retryable_openai_structuring_error_marks_json_decode_as_non_retryable() -> None:
    import json

    exc = json.JSONDecodeError("Unterminated string", doc='{"a":"x', pos=5)
    assert _is_retryable_openai_structuring_error(exc) is False


def test_retryable_openai_structuring_error_marks_connection_reset_as_retryable() -> None:
    exc = RuntimeError("HTTPSConnectionPool(host='api.openai.com', port=443): Read timed out.")
    assert _is_retryable_openai_structuring_error(exc) is True


def test_retryable_openai_request_error_marks_dns_resolution_as_non_retryable() -> None:
    exc = RuntimeError(
        "HTTPSConnectionPool(host='api.openai.com', port=443): Max retries exceeded with url: /v1/responses "
        "(Caused by NewConnectionError('<urllib3.connection.HTTPSConnection object at 0x1>: "
        "Failed to establish a new connection: [Errno 8] nodename nor servname provided, or not known'))"
    )
    assert _is_retryable_openai_request_error(exc) is False


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


def test_scrape_recent_transcripts_error_contains_category(monkeypatch) -> None:
    report = {
        "ticker": "AAPL",
        "candidate_pool": [
            {
                "quarter": "2026-Q1",
                "title": "T1",
                "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/a/",
                "published_date": "2026-01-29",
            }
        ],
    }

    def _fake_fetch(**kwargs):
        raise RuntimeError("Read timed out while scraping")

    monkeypatch.setattr("finbert_site.openai_motley_search._fetch_transcript_sections", _fake_fetch)
    payload = scrape_recent_transcripts_for_report(
        report=report,
        scrape_count=1,
        timeout_seconds=10,
    )
    assert payload["scraped_count"] == 0
    assert len(payload["scrape_errors"]) == 1
    assert payload["scrape_errors"][0]["error_category"] == "timeout"


def test_scrape_recent_transcripts_cache_use_mode_reads_cached_payload(monkeypatch, tmp_path) -> None:
    report = {
        "ticker": "AAPL",
        "candidate_pool": [
            {
                "quarter": "2026-Q1",
                "title": "T1",
                "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/a/",
                "published_date": "2026-01-29",
            }
        ],
    }

    def _fake_fetch(**kwargs):
        return {
            "quarter": kwargs["quarter"],
            "title": kwargs["title"],
            "url": kwargs["url"],
            "published_date": kwargs["published_date"],
            "participants": [],
            "speaker_sections": [
                {
                    "speaker": "Fetched",
                    "speaker_role": None,
                    "section_type": "other",
                    "order_index": 0,
                    "text": "fetched",
                }
            ],
            "speaker_count": 1,
            "speakers": ["Fetched"],
            "section_count": 1,
            "transcript_line_count": 1,
            "transcript_char_count": 7,
        }

    monkeypatch.setattr("finbert_site.openai_motley_search._fetch_transcript_sections", _fake_fetch)

    cache_dir = tmp_path / "cache"
    payload_refresh = scrape_recent_transcripts_for_report(
        report=report,
        scrape_count=1,
        timeout_seconds=10,
        cache_mode="refresh",
        cache_dir=str(cache_dir),
        api_key="test-key",
        model="gpt-5-mini",
        retry_attempts=1,
        log_fn=lambda _: None,
    )
    assert payload_refresh["scraped_count"] == 1
    cache_file = payload_refresh["scraped_transcripts"][0]["cache_file"]

    # Overwrite the cached file with a known payload, then ensure use-mode returns it.
    cached = {
        "quarter": "2026-Q1",
        "title": "T1",
        "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/a/",
        "published_date": "2026-01-29",
        "participants": [],
        "speaker_sections": [{"speaker": "Cached", "speaker_role": None, "section_type": "other", "order_index": 0, "text": "cached"}],
        "speaker_count": 1,
        "speakers": ["Cached"],
        "section_count": 1,
        "transcript_line_count": 1,
        "transcript_char_count": 6,
    }
    from pathlib import Path
    import json

    Path(cache_file).write_text(json.dumps(cached), encoding="utf-8")

    def _should_not_fetch(**kwargs):
        raise AssertionError("fetch should not be called when cache_mode=use and cache exists")

    monkeypatch.setattr("finbert_site.openai_motley_search._fetch_transcript_sections", _should_not_fetch)
    payload_use = scrape_recent_transcripts_for_report(
        report=report,
        scrape_count=1,
        timeout_seconds=10,
        cache_mode="use",
        cache_dir=str(cache_dir),
        api_key="test-key",
        model="gpt-5-mini",
        retry_attempts=1,
        log_fn=lambda _: None,
    )
    assert payload_use["scraped_count"] == 1
    assert payload_use["scraped_transcripts"][0]["from_cache"] is True
    assert payload_use["scraped_transcripts"][0]["speaker_sections"][0]["speaker"] == "Cached"


def test_extract_text_lines_relaxed_supports_div_only_content() -> None:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup("<div><div>Full Conference Call Transcript</div><div>Operator: Hello</div></div>", "html.parser")
    lines = _extract_text_lines_relaxed(soup)
    assert "Full Conference Call Transcript" in lines
    assert "Operator: Hello" in lines


def test_extract_text_lines_from_script_payloads_supports_embedded_json() -> None:
    from bs4 import BeautifulSoup

    html = """
    <html><body>
      <script type="application/json">
        {"content":"Call participants\\nChief Executive Officer — Timothy D. Cook\\nFull Conference Call Transcript\\nTimothy D. Cook: Welcome everyone.\\nRead Next"}
      </script>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    lines = _extract_text_lines_from_script_payloads(soup)
    assert "Call participants" in lines
    assert "Full Conference Call Transcript" in lines
    assert "Timothy D. Cook: Welcome everyone." in lines


def test_discover_last_quarter_links_uses_source_fallback_when_structured_missing(monkeypatch) -> None:
    class _Resp:
        status_code = 200

        def json(self) -> dict:
            return {
                "output": [
                    {
                        "type": "web_search_call",
                        "action": {
                            "sources": [
                                {
                                    "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/"
                                }
                            ]
                        },
                    }
                ]
            }

    monkeypatch.setattr("finbert_site.openai_motley_search._openai_post_responses", lambda **kwargs: _Resp())
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._extract_structured_output",
        lambda payload: (_ for _ in ()).throw(RuntimeError("no schema payload")),
    )

    report = discover_last_quarter_links(
        ticker="AAPL",
        api_key="test-key",
        target_quarters=1,
        max_candidates=4,
        retry_attempts=1,
        discovery_mode="openai_only",
        discovery_cache_mode="off",
    )
    assert report["found_quarters"] == ["2026-Q1"]
    assert len(report["candidate_pool"]) >= 1
    assert "Candidates derived from OpenAI web_search sources" in report.get("notes", "")


def test_discover_last_quarter_links_hybrid_pipeline_uses_sitemap_author_openai(monkeypatch) -> None:
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_from_sitemaps",
        lambda **kwargs: (
            [
                {
                    "title": "Apple (AAPL) Q1 2026 Earnings Call Transcript",
                    "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
                    "published_date": "2026-01-29",
                    "source": "sitemap_month:2026-01",
                }
            ],
            {"aapl", "apple"},
            {"phase": "sitemap", "status": "ok", "duration_ms": 5, "candidates_added": 1},
        ),
    )
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_from_author_pages",
        lambda **kwargs: (
            [
                {
                    "title": "Apple Q4 2025 Earnings Call Transcript",
                    "url": "https://www.fool.com/earnings/call-transcripts/2025/10/31/apple-q4-2025-earnings-call-transcript/",
                    "published_date": "2025-10-31",
                    "source": "author_page:1",
                }
            ],
            {"aapl", "apple"},
            {"phase": "author", "status": "ok", "duration_ms": 7, "candidates_added": 1},
        ),
    )
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_with_openai",
        lambda **kwargs: (
            [
                {
                    "title": "Apple (AAPL) Q3 2025 Earnings Call Transcript",
                    "url": "https://www.fool.com/earnings/call-transcripts/2025/08/01/apple-aapl-q3-2025-earnings-call-transcript/",
                    "published_date": "2025-08-01",
                    "source": "openai_web_search",
                }
            ],
            {
                "selected_tool": "web_search",
                "search_sources": [
                    "https://www.fool.com/earnings/call-transcripts/2025/08/01/apple-aapl-q3-2025-earnings-call-transcript/"
                ],
                "notes": "fallback-note",
                "trace": {"phase": "openai_fallback", "status": "ok", "duration_ms": 11, "raw_candidates_count": 1},
            },
        ),
    )

    report = discover_last_quarter_links(
        ticker="AAPL",
        api_key="test-key",
        target_quarters=3,
        discovery_mode="hybrid",
        author_max_pages=40,
        discovery_cache_mode="off",
    )

    assert report["found_quarters"] == ["2026-Q1", "2025-Q4", "2025-Q3"]
    assert report["missing_quarters"] == []
    assert report["discovery_methods_used"] == ["sitemap", "author", "openai_web_search"]
    assert [phase.get("phase") for phase in report["discovery_trace"]["phases"]] == [
        "sitemap",
        "author",
        "openai_fallback",
    ]
    quarter_map = {row["quarter"]: row for row in report["quarters"]}
    assert quarter_map["2025-Q4"]["resolution_source"] == "author_page:1"
    assert quarter_map["2025-Q3"]["resolution_source"] == "openai_web_search"


def test_discover_last_quarter_links_hybrid_skips_author_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_from_sitemaps",
        lambda **kwargs: (
            [
                {
                    "title": "Apple (AAPL) Q1 2026 Earnings Call Transcript",
                    "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
                    "published_date": "2026-01-29",
                    "source": "sitemap_month:2026-01",
                }
            ],
            {"aapl", "apple"},
            {"phase": "sitemap", "status": "ok", "duration_ms": 3, "candidates_added": 1},
        ),
    )
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_from_author_pages",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("author fallback should be skipped")),
    )
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_with_openai",
        lambda **kwargs: (
            [],
            {
                "selected_tool": "web_search",
                "search_sources": [],
                "notes": "noop",
                "trace": {"phase": "openai_fallback", "status": "empty", "duration_ms": 1, "raw_candidates_count": 0},
            },
        ),
    )
    report = discover_last_quarter_links(
        ticker="AAPL",
        api_key="test-key",
        target_quarters=2,
        discovery_mode="hybrid",
        author_max_pages=0,
        discovery_cache_mode="off",
    )
    phases = [phase.get("phase") for phase in report["discovery_trace"]["phases"]]
    assert phases == ["sitemap", "author", "openai_fallback"]
    author_phase = report["discovery_trace"]["phases"][1]
    assert author_phase.get("status") == "skipped"


def test_discover_last_quarter_links_sitemap_only_skips_openai(monkeypatch) -> None:
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_from_sitemaps",
        lambda **kwargs: (
            [
                {
                    "title": "Apple (AAPL) Q1 2026 Earnings Call Transcript",
                    "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
                    "published_date": "2026-01-29",
                    "source": "sitemap_month:2026-01",
                }
            ],
            {"aapl", "apple"},
            {"phase": "sitemap", "status": "ok", "duration_ms": 3, "candidates_added": 1},
        ),
    )
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_with_openai",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("openai fallback should not be called")),
    )

    report = discover_last_quarter_links(
        ticker="AAPL",
        api_key="test-key",
        target_quarters=1,
        discovery_mode="sitemap_only",
        discovery_cache_mode="off",
    )
    assert report["found_quarters"] == ["2026-Q1"]
    assert report["discovery_methods_used"] == ["sitemap"]
    assert report["openai_search_tool"] == "not_used"


def test_discover_last_quarter_links_discovery_cache_use_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_with_openai",
        lambda **kwargs: (
            [
                {
                    "title": "Apple (AAPL) Q1 2026 Earnings Call Transcript",
                    "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
                    "published_date": "2026-01-29",
                    "source": "openai_web_search",
                }
            ],
            {
                "selected_tool": "web_search",
                "search_sources": [],
                "notes": "cached-note",
                "trace": {"phase": "openai_fallback", "status": "ok", "duration_ms": 1, "raw_candidates_count": 1},
            },
        ),
    )

    report_refresh = discover_last_quarter_links(
        ticker="AAPL",
        api_key="test-key",
        target_quarters=1,
        discovery_mode="openai_only",
        discovery_cache_mode="refresh",
        discovery_cache_dir=str(tmp_path),
    )
    assert report_refresh["discovery_cache"]["written"] is True

    monkeypatch.setattr(
        "finbert_site.openai_motley_search._discover_candidates_with_openai",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("discovery should have used cache")),
    )
    report_use = discover_last_quarter_links(
        ticker="AAPL",
        api_key="test-key",
        target_quarters=1,
        discovery_mode="openai_only",
        discovery_cache_mode="use",
        discovery_cache_dir=str(tmp_path),
    )
    assert report_use["discovery_cache"]["hit"] is True
    assert report_use["found_quarters"] == ["2026-Q1"]


def test_clean_candidates_drops_off_ticker_urls_using_company_tokens() -> None:
    raw_candidates = [
        {
            "title": "Apple (AAPL) Q1 2026 Earnings Call Transcript",
            "url": "https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
            "published_date": "2026-01-29",
            "source": "web_search",
        },
        {
            "title": "Apple Q4 2025 Earnings Call Transcript",
            "url": "https://www.fool.com/earnings/call-transcripts/2025/10/31/apple-q4-2025-earnings-call-transcript/",
            "published_date": "2025-10-31",
            "source": "web_search",
        },
        {
            "title": "Macerich (MAC) Q4 2025 Earnings Call Transcript",
            "url": "https://www.fool.com/earnings/call-transcripts/2026/02/24/macerich-mac-q4-2025-earnings-call-transcript/",
            "published_date": "2026-02-24",
            "source": "web_search",
        },
    ]
    cleaned, warnings = _clean_candidates(ticker="AAPL", raw_candidates=raw_candidates)
    urls = [c.url for c in cleaned]
    assert any("apple-aapl-q1-2026" in url for url in urls)
    assert any("apple-q4-2025" in url for url in urls)
    assert not any("macerich-mac-q4-2025" in url for url in urls)
    assert any("off-ticker" in warning.lower() for warning in warnings)


def test_parse_transcript_from_html_semantic_dom_source() -> None:
    html = """
    <html><body><article>
      <h2>Call participants</h2>
      <p>Chief Executive Officer — Satya Nadella</p>
      <h2>Full Conference Call Transcript</h2>
      <p>Operator: Welcome everyone.</p>
      <p>Satya Nadella: Thank you for joining.</p>
      <p>Read Next</p>
    </article></body></html>
    """
    payload = _parse_transcript_from_html(html=html, scrape_method="static")
    assert payload["line_source"] == "semantic_dom"
    assert payload["scrape_method"] == "static"
    assert payload["section_count"] >= 1
    assert payload["line_count"]["transcript_line_count"] >= 2
    assert payload["marker_detection"]["start_found"] is True


def test_parse_transcript_from_html_jsonld_source() -> None:
    html = """
    <html><body>
      <script type="application/ld+json">
        {"@type":"NewsArticle","articleBody":"Call participants\\nChief Executive Officer — Satya Nadella\\nFull Conference Call Transcript\\nOperator: Welcome everyone.\\nSatya Nadella: Thanks all.\\nRead Next"}
      </script>
      <main><div>No transcript in rendered DOM.</div></main>
    </body></html>
    """
    payload = _parse_transcript_from_html(html=html, scrape_method="static")
    assert payload["line_source"] == "jsonld_article_body"
    assert payload["section_count"] >= 1


def test_parse_transcript_from_html_script_payload_source() -> None:
    html = """
    <html><body>
      <script id="__NEXT_DATA__" type="application/json">
        {"props":{"pageProps":{"content":"Call participants\\nChief Executive Officer — Satya Nadella\\nFull Conference Call Transcript\\nOperator: Welcome everyone.\\nSatya Nadella: Thanks all.\\nRead Next"}}}
      </script>
      <main><div>No transcript in rendered DOM.</div></main>
    </body></html>
    """
    payload = _parse_transcript_from_html(html=html, scrape_method="static")
    assert payload["line_source"] == "script_payload"
    assert payload["section_count"] >= 1


def test_parse_transcript_from_html_repeated_speaker_fallback_without_markers() -> None:
    html = """
    <html><body><article>
      <div>Market data and intro content</div>
      <div>Operator: Welcome everyone.</div>
      <div>Satya Nadella: Thank you for joining.</div>
      <div>Amy Hood: Let me walk through the quarter.</div>
      <div>Read Next</div>
    </article></body></html>
    """
    payload = _parse_transcript_from_html(html=html, scrape_method="static")
    assert payload["marker_detection"]["start_reason"] in {"repeated_speaker", "single_speaker_fallback"}
    assert payload["section_count"] >= 2


def test_parse_transcript_from_html_no_transcript_content_raises() -> None:
    html = "<html><body><article><div>Generic page without call text.</div></article></body></html>"
    with pytest.raises(TranscriptExtractionError) as exc:
        _parse_transcript_from_html(html=html, scrape_method="static")
    assert "Transcript section markers were not found" in str(exc.value)
    assert exc.value.scrape_method == "static"


def test_fetch_transcript_sections_falls_back_to_browser(monkeypatch) -> None:
    class _Resp:
        status_code = 200
        text = "<html><body><article><div>No transcript in static html.</div></article></body></html>"

        def raise_for_status(self) -> None:
            return None

    browser_html = """
    <html><body><article>
      <h2>Full Conference Call Transcript</h2>
      <p>Operator: Welcome.</p>
      <p>Satya Nadella: Thanks everyone.</p>
      <p>Read Next</p>
    </article></body></html>
    """

    monkeypatch.setattr("finbert_site.openai_motley_search.requests.get", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._render_playwright_snapshot",
        lambda **kwargs: (browser_html, "Full Conference Call Transcript\nOperator: Welcome.\nSatya Nadella: Thanks everyone."),
    )

    payload = _fetch_transcript_sections(
        url="https://www.fool.com/earnings/call-transcripts/x/",
        ticker="MSFT",
        quarter="2025-Q4",
        title="T",
        published_date="2025-10-31",
        timeout_seconds=10,
    )
    assert payload["scrape_method"] == "browser"
    assert payload["section_count"] >= 1
    assert payload["marker_detection"]["start_found"] is True


def test_fetch_transcript_sections_browser_unavailable_returns_install_hint(monkeypatch) -> None:
    class _Resp:
        status_code = 200
        text = "<html><body><article><div>No transcript in static html.</div></article></body></html>"

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr("finbert_site.openai_motley_search.requests.get", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._render_playwright_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Playwright is not installed. Install optional browser fallback with `pip install playwright` and `python -m playwright install chromium`.")),
    )

    with pytest.raises(TranscriptExtractionError) as exc:
        _fetch_transcript_sections(
            url="https://www.fool.com/earnings/call-transcripts/x/",
            ticker="MSFT",
            quarter="2025-Q4",
            title="T",
            published_date="2025-10-31",
            timeout_seconds=10,
        )
    assert "pip install playwright" in str(exc.value)
    assert exc.value.scrape_method == "browser"


def test_fetch_transcript_sections_low_quality_uses_openai_section_fallback(monkeypatch) -> None:
    class _Resp:
        status_code = 200
        text = "<html><body><article><div>stub</div></article></body></html>"

        def raise_for_status(self) -> None:
            return None

    low_quality_payload = {
        "participants": [],
        "speaker_sections": [
            {
                "speaker": "unknown",
                "speaker_role": None,
                "section_type": "other",
                "order_index": 0,
                "text": 'self.__next_f.push([1,"46:[\\"$\\",..."])',
            }
        ],
        "speaker_count": 1,
        "speakers": ["unknown"],
        "section_count": 1,
        "transcript_line_count": 1,
        "transcript_char_count": 42,
        "scrape_method": "static",
        "line_source": "script_payload",
        "marker_detection": {"start_found": True},
        "line_count": {"source_line_count": 12, "transcript_line_count": 1},
        "section_parse_method": "regex",
        "raw_text": "self.__next_f.push([1,\"46:[\\\"$\\\",...\"])",
    }

    monkeypatch.setattr("finbert_site.openai_motley_search.requests.get", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr("finbert_site.openai_motley_search._parse_transcript_from_html", lambda **kwargs: low_quality_payload)
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._render_playwright_snapshot",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("Playwright missing")),
    )
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._structure_transcript_with_openai",
        lambda **kwargs: {
            "participants": [{"name": "Satya Nadella", "role": "Chief Executive Officer"}],
            "speaker_sections": [
                {
                    "speaker": "Operator",
                    "speaker_role": "operator",
                    "section_type": "qa",
                    "order_index": 0,
                    "text": "Welcome everyone.",
                },
                {
                    "speaker": "Satya Nadella",
                    "speaker_role": "management",
                    "section_type": "qa",
                    "order_index": 1,
                    "text": "Thank you.",
                },
            ],
            "speaker_count": 2,
            "speakers": ["Operator", "Satya Nadella"],
            "section_count": 2,
            "transcript_line_count": 2,
            "transcript_char_count": 26,
            "section_parse_method": "openai",
            "section_parse_notes": "fallback",
        },
    )

    payload = _fetch_transcript_sections(
        url="https://www.fool.com/earnings/call-transcripts/x/",
        ticker="MSFT",
        quarter="2025-Q4",
        title="T",
        published_date="2025-10-31",
        timeout_seconds=10,
        openai_api_key="test-key",
        openai_model="gpt-5-mini",
    )
    assert payload["section_parse_method"] == "openai_page_text"
    assert payload["section_count"] == 2
    assert payload["speaker_sections"][0]["speaker"] == "Operator"


def test_fetch_transcript_sections_low_quality_parser_returns_quality_flags(monkeypatch) -> None:
    class _Resp:
        status_code = 200
        text = "<html><body><article><div>stub</div></article></body></html>"

        def raise_for_status(self) -> None:
            return None

    low_quality_payload = {
        "participants": [],
        "speaker_sections": [
            {
                "speaker": "unknown",
                "speaker_role": None,
                "section_type": "other",
                "order_index": 0,
                "text": 'self.__next_f.push([1,"46:[\\"$\\",..."])',
            }
        ],
        "speaker_count": 1,
        "speakers": ["unknown"],
        "section_count": 1,
        "transcript_line_count": 1,
        "transcript_char_count": 42,
        "scrape_method": "static",
        "line_source": "script_payload",
        "marker_detection": {"start_found": True},
        "line_count": {"source_line_count": 12, "transcript_line_count": 1},
        "section_parse_method": "regex",
        "raw_text": "self.__next_f.push([1,\\\"46:[\\\\\\\"$\\\\\\\",...\\\"])",
    }

    monkeypatch.setattr("finbert_site.openai_motley_search.requests.get", lambda *args, **kwargs: _Resp())
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._build_source_first_llm_input",
        lambda **kwargs: {
            "text": "self.__next_f.push([1,'x'])",
            "input_source": "static_html",
            "input_source_detail": "script_payload_text",
            "input_char_count": 28,
            "input_speaker_line_count": 0,
            "input_line_count": 1,
            "marker_detection": {"start_found": False},
            "input_candidates": [],
        },
    )
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._parse_speaker_sections_from_text",
        lambda text: dict(low_quality_payload),
    )
    monkeypatch.setattr(
        "finbert_site.openai_motley_search._render_playwright_snapshot",
        lambda **kwargs: ("<html><body>stub</body></html>", ""),
    )

    payload = _fetch_transcript_sections(
        url="https://www.fool.com/earnings/call-transcripts/x/",
        ticker="MSFT",
        quarter="2025-Q4",
        title="T",
        published_date="2025-10-31",
        timeout_seconds=10,
    )

    assert payload["section_count"] == 1
    assert payload["quality_flags"]["parser_low_confidence"] is True
    assert payload["quality_flags"]["parser_low_confidence_reason"] in {"script_wrapped_text", "single_unknown_section"}
    assert payload["section_parse_reason"] == "openai_unavailable_low_quality_regex_fallback"


def test_is_low_quality_structured_sections_rejects_implausible_speakers() -> None:
    sections = [
        {
            "speaker": "Greetings",
            "speaker_role": "operator",
            "section_type": "prepared_remarks",
            "order_index": 0,
            "text": "Welcome to the call.",
        },
        {
            "speaker": "Good Afternoon",
            "speaker_role": None,
            "section_type": "prepared_remarks",
            "order_index": 1,
            "text": "Thank you for joining.",
        },
        {
            "speaker": "Satya Nadella",
            "speaker_role": "management",
            "section_type": "prepared_remarks",
            "order_index": 2,
            "text": "We had a strong quarter.",
        },
    ]
    low, reason = _is_low_quality_structured_sections(sections)
    assert low is True
    assert reason == "implausible_speaker_labels"


def test_build_html_report_contains_ticker_and_section_text() -> None:
    output = {
        "generated_at": "2026-04-19T12:00:00Z",
        "model": "gpt-5-mini",
        "results": [
            {
                "ticker": "MSFT",
                "found_quarters": ["2025-Q4"],
                "missing_quarters": [],
                "scraped_count": 1,
                "scraped_transcripts": [
                    {
                        "quarter": "2025-Q4",
                        "title": "Microsoft (MSFT) Q4 2025 Earnings Call Transcript",
                        "url": "https://www.fool.com/earnings/call-transcripts/2025/08/05/microsoft-msft-q4-2025-earnings-call-transcript/",
                        "published_date": "2025-08-05",
                        "section_parse_method": "openai_page_text",
                        "scrape_method": "browser",
                        "participants": [{"name": "Satya Nadella", "role": "Chief Executive Officer"}],
                        "speaker_sections": [
                            {
                                "speaker": "Operator",
                                "speaker_role": "operator",
                                "section_type": "qa",
                                "order_index": 0,
                                "text": "Welcome everyone.",
                            }
                        ],
                    }
                ],
                "scrape_errors": [],
            }
        ],
    }
    html = _build_html_report(output)
    assert "MSFT" in html
    assert "Welcome everyone." in html
    assert "OpenAI Motley Transcript Report" in html
