# FinBERT Earnings Signals (Local)

Local FastAPI app for transcript-first earnings analysis with FinBERT sentiment.

## Product Structure

The app is organized into exactly 5 primary sections:

1. Overview
2. Transcript
3. Market Reaction
4. Fundamentals
5. Data Audit

Execution-role UI language (trader/risk/manager workflows) is removed from the primary interface. Legacy API fields remain for one migration window.

## What This Refactor Implements

- Transcript-first workspace IA with left-rail section navigation
- Centralized UI copy dictionary for hard-coded labels and microcopy
- Deterministic Motley Fool transcript discovery and parsing pipeline
- Optional OpenAI normalization for strict transcript JSON output
- Deterministic degraded normalization mode when OpenAI is unavailable
- Market reaction feed ranking improvements with 14-day lookback + recency weighting
- News/social relevance filtering tightened to ticker/company-linked items
- Social cards now show short excerpts only, with full-post modal view and top-right open-in-new-tab icon
- News/social cards use 3-column desktop grids for cleaner scan density
- ECharts-based visual system for higher-fidelity fundamentals and speaker profile charts
- Sentiment timeline panel removed from UI by design (per latest UX decision)
- Canonical API section payloads + legacy compatibility contract

## Transcript Pipeline (Current)

Primary source is Motley Fool transcript surfaces:

- `https://www.fool.com/author/20032/` (+ pagination)
- `https://www.fool.com/search/?q=<ticker>%20earnings%20call%20transcript` (deterministic discovery fallback)

Flow:

1. Discover candidate transcript URLs
2. Keep only date-slug transcript URLs and deterministically rank by ticker/company match
3. Attempt a larger fetch window and stop after the first N successfully parsed transcripts
4. Fetch raw HTML with requests/httpx
5. Parse transcript body via start/stop markers (with JSON-LD fallback extraction)
6. Normalize into strict transcript structure (OpenAI default, deterministic fallback)

No transcript fallback source is used in this phase. Missing transcript coverage is surfaced in Data Audit.

## API Contract

`GET /api/analyze?ticker=AAPL`

Canonical fields:

- `analysis_version`
- `ui_copy`
- `overview`
- `transcript`
- `market_reaction`
- `fundamentals_workspace`
- `data_audit`

Legacy fields remain during migration:

- `aggregate_scores`, `fundamentals`, `news_summary`, `social_summary`
- `analyst_team`, `research_team`, `trader_plan`, `risk_management`, `manager_decision`
- `report_tabs`, `charts`, `news`, `social`, `transcripts`

## Local Run

1. Create and activate virtual environment
2. Install dependencies

```bash
pip install -r requirements.txt
```

3. Configure env

```bash
cp .env.example .env
```

Optional keys:

- `ALPHAVANTAGE_API_KEY` for Alpha Vantage news feed
- `OPENAI_API_KEY` for transcript normalization
- `OPENAI_NORMALIZER_MODEL` (default `gpt-4o-mini`)
- `OPENAI_SEARCH_MODEL` (default `gpt-5-mini`) for OpenAI web-search test script

4. Start app

```bash
uvicorn finbert_site.main:app --reload
```

5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Test

```bash
pytest -q
```

## OpenAI Web-Search Transcript Slug Test

This prototype script now uses a strict 3-step flow per ticker:

1. OpenAI `web_search` discovers Motley Fool transcript URLs.
2. The script fetches page text from each selected URL (browser-render text when available, static text otherwise).
3. The script builds speaker-by-speaker sections from page text with deterministic parsing first, then optionally applies OpenAI structuring (with deterministic fallback if OpenAI fails).

```bash
python scripts/openai_motley_transcript_cli.py AAPL MSFT --pretty
```

Verbose progress logs:

```bash
python scripts/openai_motley_transcript_cli.py AAPL MSFT --pretty --verbose
```

Discover links and scrape the most recent 4 transcript pages into per-speaker JSON sections:

```bash
python scripts/openai_motley_transcript_cli.py AAPL --pretty --verbose --scrape --scrape-count 4
```

Write JSON + verbose logs to files:

```bash
mkdir -p output
TS=$(date +"%Y%m%d_%H%M%S")
JSON="output/openai_motley_${TS}.json"
LOG="output/openai_motley_${TS}.log"
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL MSFT --pretty --verbose --scrape --scrape-count 4 --cache-mode refresh > "$JSON" 2> "$LOG"
echo "$JSON"
echo "$LOG"
```

Also generate a simple HTML viewer from the same run:

```bash
mkdir -p output
TS=$(date +"%Y%m%d_%H%M%S")
JSON="output/openai_motley_${TS}.json"
LOG="output/openai_motley_${TS}.log"
HTML="output/openai_motley_${TS}.html"
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL MSFT --pretty --verbose --scrape --scrape-count 4 --cache-mode refresh --html-report "$HTML" > "$JSON" 2> "$LOG"
echo "$JSON"
echo "$LOG"
echo "$HTML"
```

Cache controls for scraped transcript JSON:

- `--cache-mode refresh` (default): always fetch + re-run parsing/structuring pipeline, then overwrite cache
- `--cache-mode use`: use cached transcript JSON when present, fetch only on cache miss
- `--cache-mode off`: disable cache read/write
- `--cache-dir output/openai_motley_cache`: override cache location

OpenAI I/O inspection options:

- `--debug-openai-io`: print request/response previews for transcript structuring to stderr (best with `--verbose`)
- `--debug-openai-io-max-chars 4000`: increase preview length in terminal logs
- `--debug-openai-dir output/openai_debug`: write full page input, request payloads, and raw/structured OpenAI responses to files

Optional browser-render fallback for difficult pages:

```bash
.venv/bin/python -m pip install playwright
.venv/bin/python -m playwright install chromium
```

If you see `NotOpenSSLWarning` (`LibreSSL` on macOS Python), install compatible urllib3 in the venv:

```bash
.venv/bin/python -m pip install "urllib3<2"
```

If OpenAI web-search calls are flaky, increase retries:

```bash
python scripts/openai_motley_transcript_cli.py AAPL MSFT --pretty --verbose --openai-retries 5
```

Output shape (per ticker):

- `requested_quarters`, `found_quarters`, `missing_quarters`
- `quarters` with `status`, `title`, and `url`
- `found_transcript_links` and `links` for copy-ready URL lists in terminal JSON output
- `candidate_pool` and `search_sources` for debugging slug discovery quality
- `selected_recent_links`, `scraped_transcripts`, and `scrape_errors` when `--scrape` is enabled
- `scrape_method`, `line_source`, `marker_detection`, and `line_count` diagnostics on scraped transcript payloads
- `section_parse_method` (`regex_from_page_text` or `openai_page_text`) and optional `section_parse_reason`
- Scraping runs OpenAI transcript structuring from extracted page text. If OpenAI fails, it attempts a regex fallback from the same extracted page text.
- OpenAI HTTP calls use a retrying session and capped read timeout to reduce hangs from intermittent `RemoteDisconnected` transport errors.
- OpenAI transport-level retries now default to `0` (`OPENAI_TRANSPORT_RETRIES`) so application-level retry logic does not multiply timeout delays.
- OpenAI transcript-structuring retries are now fail-fast for non-retryable JSON parse failures (for example, malformed/truncated JSON), so scraping quickly falls back to deterministic parsing instead of burning all retries.
- Transcript structuring also short-circuits after repeated read-timeout failures and on DNS resolution failures, then falls back to deterministic parsing.
- `llm_input_diagnostics` and `llm_input_preview` show the actual page-derived content passed to OpenAI for transcript structuring.
- If only low-quality parser output is available, scraping records a `scrape_error` instead of returning misleading single `unknown` speaker sections.
- If you interrupt a long run (`Ctrl+C`), CLI now returns partial JSON results cleanly without a Python traceback.
- Discovery is source-first: candidates are built from `web_search` source URLs so missing schema output no longer hard-fails discovery.
- Candidate cleanup now drops likely off-ticker transcript URLs (for example, unrelated symbols that appear in search-source spillover) and prefers quarter-resolved links for scraping.
- Transcript start markers are now heading-aware, so inline phrases like "in your prepared remarks" no longer incorrectly reset parsing into mid-call Q&A.
- When transcript headings are missing, section typing is inferred from call flow (prepared remarks vs Q&A), and participants are backfilled from parsed speaker sections so the output remains usable.

## Notes

- FinBERT (`ProsusAI/finbert`) is BERT-base scale and runs locally on Apple Silicon.
- This tool is an analysis workspace, not trading advice.
