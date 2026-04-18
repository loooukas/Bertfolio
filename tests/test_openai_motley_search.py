from finbert_site.openai_motley_search import (
    MotleyTranscriptCandidate,
    _pick_best_candidate_by_quarter,
    _quarter_window,
    infer_year_quarter,
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
