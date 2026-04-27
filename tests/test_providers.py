from __future__ import annotations

from finbert_site import providers
from finbert_site.providers import TranscriptCandidate, TranscriptDiscoveryAudit
from finbert_site.settings import Settings


def _settings() -> Settings:
    return Settings(
        alpha_vantage_api_key="test",
        finbert_model_name="stub",
        request_timeout_seconds=1,
        transcript_target_count=4,
        openai_api_key="",
        openai_normalizer_model="gpt-4o-mini",
    )


def test_discover_candidates_prefers_exact_ticker(monkeypatch):
    pages = {
        "https://www.fool.com/author/20032/": """
            <html><body>
              <a href='/earnings/call-transcripts/2026/01/29/apple-q1-2026-earnings-call-transcript/'>Apple Q1 2026 Earnings Call Transcript</a>
              <a href='/earnings/call-transcripts/2026/01/30/microsoft-msft-q2-2026-earnings-call-transcript/'>Microsoft (MSFT) Q2 2026 Earnings Call Transcript</a>
            </body></html>
        """,
        "https://www.fool.com/author/20032/?page=2": """
            <html><body>
              <a href='/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/'>Apple (AAPL) Q1 2026 Earnings Call Transcript</a>
              <a href='/earnings/call-transcripts/2026/01/27/rivian-rivn-q4-2025-earnings-call-transcript/'>Rivian (RIVN) Q4 2025 Earnings Call Transcript</a>
            </body></html>
        """,
        "https://www.fool.com/author/20032/?page=3": "<html><body></body></html>",
        "https://www.fool.com/author/20032/?page=4": "<html><body></body></html>",
        "https://www.fool.com/search/?q=AAPL%20earnings%20call%20transcript": "<html><body></body></html>",
    }

    monkeypatch.setattr(providers, "_request_html", lambda url, timeout_seconds: pages[url])

    candidates, audit = providers.discover_motley_fool_candidates(
        "AAPL",
        "Apple Inc",
        _settings(),
        max_author_pages=4,
    )

    assert candidates
    assert "AAPL" in candidates[0].title.upper()
    assert audit.pages_scanned == 5
    assert audit.candidates_total >= 4
    assert audit.transcript_like_count >= 4


def test_fetch_transcripts_motley_fool_parses_markers_and_trims_footer(monkeypatch):
    candidate = TranscriptCandidate(
        title="Apple (AAPL) Q1 2026 Earnings Call Transcript",
        url="https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
        published_date="2026-01-29",
        author="Motley Fool Transcribing",
        surface="author",
        match_score=110.0,
    )

    discovery = TranscriptDiscoveryAudit(
        pages_scanned=1,
        candidates_total=1,
        transcript_like_count=1,
        match_filtered_count=1,
        selected_count=0,
        discarded_near_matches=[],
        fetch_failures=[],
        playwright_fallback_used=False,
    )

    html = """
      <html><body>
        <article>
          <h2>DATE</h2>
          <p>January 29, 2026</p>
          <h2>CALL PARTICIPANTS</h2>
          <p>Tim Cook - Chief Executive Officer</p>
          <p>Luca Maestri - Chief Financial Officer</p>
          <h2>Prepared Remarks</h2>
          <p>Operator: Welcome everyone.</p>
          <p>Tim Cook: Demand was strong across product lines and guidance remains resilient.</p>
          <h2>Questions and Answers</h2>
          <p>Analyst: How are margins trending?</p>
          <p>Luca Maestri: We are watching cost pressure and near-term mix effects.</p>
          <h3>Read Next</h3>
          <p>This footer text should be removed.</p>
        </article>
      </body></html>
    """

    monkeypatch.setattr(
        providers,
        "discover_motley_fool_candidates",
        lambda symbol, company_name, settings, max_author_pages=4: ([candidate], discovery),
    )
    monkeypatch.setattr(providers, "_request_html", lambda url, timeout_seconds: html)

    transcripts, warnings, diagnostics, audit = providers.fetch_transcripts_motley_fool(
        symbol="AAPL",
        company_name="Apple Inc",
        settings=_settings(),
        target_count=1,
    )

    assert len(transcripts) == 1
    assert "Prepared Remarks" in transcripts[0].content
    assert "Read Next" not in transcripts[0].content
    assert diagnostics.found_quarters
    assert audit.selected_count == 1
    assert not any("empty" in warning.lower() for warning in warnings)


def test_fetch_social_reddit_dedupes_and_truncates(monkeypatch):
    class _Response:
        status_code = 200

        def json(self):
            return {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "AAPL earnings thoughts",
                                "selftext": "First sentence. Second sentence has extra detail.",
                                "permalink": "/r/stocks/comments/abc1/test",
                                "subreddit": "stocks",
                                "created_utc": 1776316800,
                            }
                        },
                        {
                            "data": {
                                "title": "AAPL earnings thoughts!!!",
                                "selftext": "First sentence. duplicated variant.",
                                "permalink": "/r/stocks/comments/abc2/test2",
                                "subreddit": "stocks",
                                "created_utc": 1776316810,
                            }
                        },
                    ]
                }
            }

    monkeypatch.setattr(providers.requests, "get", lambda *args, **kwargs: _Response())

    records, warnings, audit = providers.fetch_social_reddit("AAPL", _settings(), limit=12, pool_size=20)

    assert len(records) == 1
    assert records[0].excerpt == "First sentence."
    assert audit.fetched_pool == 2
    assert audit.deduped_pool == 1
    assert not warnings


def test_fetch_transcripts_scans_beyond_initial_failure(monkeypatch):
    candidates = [
        TranscriptCandidate(
            title="Apple (AAPL) Q1 2026 Earnings Call Transcript",
            url="https://www.fool.com/earnings/call-transcripts/2026/01/29/apple-aapl-q1-2026-earnings-call-transcript/",
            published_date="2026-01-29",
            author="Motley Fool Transcribing",
            surface="author",
            match_score=120.0,
        ),
        TranscriptCandidate(
            title="Apple (AAPL) Q4 2025 Earnings Call Transcript",
            url="https://www.fool.com/earnings/call-transcripts/2025/10/30/apple-aapl-q4-2025-earnings-call-transcript/",
            published_date="2025-10-30",
            author="Motley Fool Transcribing",
            surface="author",
            match_score=118.0,
        ),
    ]

    discovery = TranscriptDiscoveryAudit(
        pages_scanned=2,
        candidates_total=2,
        transcript_like_count=2,
        match_filtered_count=2,
        selected_count=0,
        discarded_near_matches=[],
        fetch_failures=[],
        playwright_fallback_used=False,
    )

    html_ok = """
      <html><body><article>
      <h2>Prepared Remarks</h2>
      <p>Tim Cook: Demand remained healthy.</p>
      <h2>Questions and Answers</h2>
      <p>Analyst: Margins?</p>
      <p>Luca Maestri: We are focused on cost discipline.</p>
      </article></body></html>
    """

    monkeypatch.setattr(
        providers,
        "discover_motley_fool_candidates",
        lambda symbol, company_name, settings, max_author_pages=4: (candidates, discovery),
    )

    def _request(url, timeout_seconds):
        if "2026/01/29" in url:
            raise RuntimeError("404 not found")
        return html_ok

    monkeypatch.setattr(providers, "_request_html", _request)

    transcripts, warnings, diagnostics, audit = providers.fetch_transcripts_motley_fool(
        symbol="AAPL",
        company_name="Apple Inc",
        settings=_settings(),
        target_count=1,
    )

    assert len(transcripts) == 1
    assert diagnostics.found_quarters
    assert any("404 not found" in warning for warning in warnings)
    assert audit.selected_count >= 2


def test_fetch_news_alpha_vantage_filters_unrelated(monkeypatch):
    def _alpha_get(params, timeout_seconds):
        return {
            "feed": [
                {
                    "title": "Apple (AAPL) launches new device",
                    "summary": "Apple management highlighted demand trends.",
                    "url": "https://example.com/apple",
                    "source": "example",
                    "time_published": "20260416T120000",
                    "overall_sentiment_score": "0.5",
                    "overall_sentiment_label": "Bullish",
                    "ticker_sentiment": [{"ticker": "AAPL", "relevance_score": "0.81"}],
                },
                {
                    "title": "Fertilizer stocks rally",
                    "summary": "No mention of Apple in this story.",
                    "url": "https://example.com/fertilizer",
                    "source": "example",
                    "time_published": "20260416T130000",
                    "overall_sentiment_score": "0.2",
                    "overall_sentiment_label": "Neutral",
                    "ticker_sentiment": [{"ticker": "MOS", "relevance_score": "0.92"}],
                },
            ]
        }

    monkeypatch.setattr(providers, "_alpha_get", _alpha_get)
    records, warnings, audit = providers.fetch_news_alpha_vantage(
        "AAPL",
        _settings(),
        limit=12,
        pool_size=20,
        company_name="Apple Inc",
        lookback_days=14,
    )

    assert len(records) == 1
    assert "AAPL" in records[0].title
    assert not warnings
    assert audit.displayed_count == 1


def test_fetch_news_multi_source_merges_and_dedupes(monkeypatch):
    monkeypatch.setattr(
        providers,
        "fetch_news_alpha_vantage",
        lambda *args, **kwargs: (
            [
                providers.NewsRecord(
                    title="Apple demand update",
                    summary="alpha summary",
                    url="https://example.com/news/alpha",
                    source="alpha",
                    time_published="20260420T100000",
                    sentiment_score=0.2,
                    sentiment_label="bullish",
                )
            ],
            [],
            providers.FeedFetchAudit(5, 1, 1),
        ),
    )
    monkeypatch.setattr(
        providers,
        "fetch_news_yahoo_finance",
        lambda *args, **kwargs: (
            [
                providers.NewsRecord(
                    title="Apple demand update",
                    summary="duplicate title",
                    url="https://example.com/news/alpha",
                    source="yahoo",
                    time_published="20260420T100100",
                    sentiment_score=0.0,
                    sentiment_label="neutral",
                ),
                providers.NewsRecord(
                    title="Apple services momentum",
                    summary="yahoo summary",
                    url="https://example.com/news/yahoo",
                    source="yahoo",
                    time_published="20260420T110000",
                    sentiment_score=0.0,
                    sentiment_label="neutral",
                ),
            ],
            [],
            providers.FeedFetchAudit(7, 2, 2),
        ),
    )

    records, warnings, audit = providers.fetch_news_multi_source(
        "AAPL",
        _settings(),
        limit=5,
        pool_size=10,
        company_name="Apple Inc",
        lookback_days=14,
    )

    assert len(records) == 2
    assert not warnings
    assert audit.fetched_pool == 12
    assert audit.displayed_count == 2


def test_fetch_social_multi_source_merges_and_dedupes(monkeypatch):
    monkeypatch.setattr(
        providers,
        "fetch_social_reddit",
        lambda *args, **kwargs: (
            [
                providers.SocialRecord(
                    source="reddit",
                    title="AAPL thread",
                    body="reddit body",
                    excerpt="reddit body",
                    url="https://example.com/social/1",
                    subreddit="stocks",
                    created_utc=1776316800,
                    relevance_score=6.2,
                )
            ],
            [],
            providers.FeedFetchAudit(8, 1, 1),
        ),
    )
    monkeypatch.setattr(
        providers,
        "fetch_social_stocktwits",
        lambda *args, **kwargs: (
            [
                providers.SocialRecord(
                    source="stocktwits",
                    title="AAPL thread",
                    body="stocktwits body",
                    excerpt="stocktwits body",
                    url="https://example.com/social/1",
                    subreddit=None,
                    created_utc=1776316810,
                    relevance_score=5.1,
                ),
                providers.SocialRecord(
                    source="stocktwits",
                    title="AAPL new message",
                    body="new body",
                    excerpt="new body",
                    url="https://example.com/social/2",
                    subreddit=None,
                    created_utc=1776316820,
                    relevance_score=6.8,
                ),
            ],
            [],
            providers.FeedFetchAudit(9, 2, 2),
        ),
    )

    records, warnings, audit = providers.fetch_social_multi_source(
        "AAPL",
        _settings(),
        limit=5,
        pool_size=10,
        company_name="Apple Inc",
        lookback_days=14,
    )

    assert len(records) == 2
    assert not warnings
    assert audit.fetched_pool == 17
    assert audit.displayed_count == 2
