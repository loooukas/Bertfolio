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

## Quick Start

```bash
cd <local-repo-path>
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn finbert_site.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000).

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

`/api/analyze` now uses the deterministic Motley pipeline by default (`TRANSCRIPT_PIPELINE_MODE=motley_cli`) and falls back to legacy provider retrieval when the deterministic path hard-fails.

Primary sources:

- `https://www.fool.com/sitemap/` (monthly sitemap index + month sitemap URLs)
- `https://www.fool.com/author/20032/` (+ pagination fallback)
- OpenAI web-search fallback only for unresolved quarters

Flow:

1. Discover candidate transcript URLs.
2. Resolve quarter window with deterministic source priority: `Sitemap -> Author -> OpenAI`.
3. Keep only date-slug transcript URLs and deterministically rank by ticker/company match.
4. Attempt a larger fetch window and stop after the first N successfully parsed transcripts.
5. Fetch raw HTML with requests/httpx.
6. Parse transcript body via start/stop markers (with JSON-LD and script-payload extraction fallback).
7. Normalize into strict transcript structure (deterministic parser first, OpenAI when parser confidence is low).

Missing transcript coverage is surfaced in Data Audit with discovery/scrape diagnostics.

### Pipeline Runtime Modes

- `TRANSCRIPT_PIPELINE_MODE=motley_cli` (default): deterministic sitemap-first discovery and section-aware scrape pipeline.
- `TRANSCRIPT_PIPELINE_MODE=legacy`: legacy in-app provider flow.
- `TRANSCRIPT_PIPELINE_FALLBACK_TO_LEGACY=1` (default): graceful fallback when `motley_cli` fails.

### Best-Known Settings

Development profile (fast feedback + reliability):

- `MOTLEY_DISCOVERY_MODE=hybrid`
- `MOTLEY_SITEMAP_LOOKBACK_MONTHS=24`
- `MOTLEY_AUTHOR_MAX_PAGES=0`
- `MOTLEY_TIMEOUT_SECONDS=45`
- `MOTLEY_OPENAI_RETRIES=3`
- `MOTLEY_SCRAPE_CACHE_MODE=refresh`
- `MOTLEY_DISCOVERY_CACHE_MODE=refresh`
- `MOTLEY_SCRAPE_COUNT=4`

Production-like profile (cost/stability):

- `MOTLEY_DISCOVERY_MODE=hybrid`
- `MOTLEY_SITEMAP_LOOKBACK_MONTHS=24`
- `MOTLEY_AUTHOR_MAX_PAGES=0`
- `MOTLEY_TIMEOUT_SECONDS=45`
- `MOTLEY_OPENAI_RETRIES=2`
- `MOTLEY_SCRAPE_CACHE_MODE=use`
- `MOTLEY_DISCOVERY_CACHE_MODE=use`
- `MOTLEY_SCRAPE_COUNT=4`

### Long Speaker-Block Sentiment Segmentation

Long speaker blocks are now segmented before FinBERT scoring and robustly re-aggregated to preserve block-level compatibility while improving directional signal quality.

Defaults:

- `TRANSCRIPT_SENTIMENT_SEGMENT_CHARS=650`
- `TRANSCRIPT_SENTIMENT_SEGMENT_MAX=1000`
- `TRANSCRIPT_SENTIMENT_SEGMENT_MIN=180`
- `TRANSCRIPT_SENTIMENT_SEGMENT_OVERLAP_SENTENCES=1`

### Expanded News + Social Coverage

News is now combined from:

- Alpha Vantage (`NEWS_SENTIMENT`)
- Yahoo Finance (`yfinance` news feed)

Social is now combined from:

- Reddit
- Stocktwits

Volume controls:

- `NEWS_LIMIT`, `NEWS_POOL_SIZE`, `NEWS_LOOKBACK_DAYS`
- `SOCIAL_LIMIT`, `SOCIAL_POOL_SIZE`, `SOCIAL_LOOKBACK_DAYS`

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
- `OPENAI_API_KEY` for transcript normalization and deterministic Motley pipeline OpenAI fallback
- `OPENAI_NORMALIZER_MODEL` (default `gpt-4o-mini`)
- `OPENAI_SEARCH_MODEL` (default `gpt-5-mini`) for deterministic discovery/scrape
- `TRANSCRIPT_PIPELINE_MODE` (`motley_cli` or `legacy`)
- `TRANSCRIPT_PIPELINE_FALLBACK_TO_LEGACY` (`1` or `0`)
- `MOTLEY_*` discovery/scrape controls in `.env.example`
- `TRANSCRIPT_SENTIMENT_SEGMENT_*` segmentation controls in `.env.example`
- `NEWS_*` and `SOCIAL_*` controls in `.env.example` for higher feed volume

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

This prototype script now uses a deterministic discovery + scrape flow per ticker:

1. Discover URLs with `Sitemap -> Author -> OpenAI fallback`.
2. Resolve most-recent target quarter window and select transcript links.
3. Fetch page text from selected URLs (browser-render text when available, static text otherwise).
4. Build speaker-by-speaker sections with deterministic parsing first, then optionally apply OpenAI structuring only when parser confidence is low.

```bash
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL MSFT --pretty
```

Verbose progress logs:

```bash
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL MSFT --pretty --verbose
```

Discover links and scrape the most recent 4 transcript pages into per-speaker JSON sections:

```bash
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL --pretty --verbose --scrape --scrape-count 4
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

Auto-write readable output files (no shell redirection needed):

```bash
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL MSFT \
  --pretty --verbose --scrape --scrape-count 4 \
  --write-output-dir output
```

This writes files like:

- `output/2026-04-19__214059.json`
- `output/2026-04-19__214059.log`
- `output/2026-04-19__214059.html`

Optional custom stamp:

```bash
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL \
  --pretty --verbose --scrape --write-output-dir output \
  --write-output-stamp 2026-04-19__run01
```

Cache controls for scraped transcript JSON:

- `--cache-mode refresh` (default): always fetch + re-run parsing/structuring pipeline, then overwrite cache
- `--cache-mode use`: use cached transcript JSON when present, fetch only on cache miss
- `--cache-mode off`: disable cache read/write
- `--cache-dir output/openai_motley_cache`: override cache location

Deterministic discovery controls:

- `--discovery-mode hybrid` (default): `Sitemap -> Author (optional) -> OpenAI fallback`
- `--discovery-mode sitemap_only`: deterministic sitemap + author-disabled crawl only
- `--discovery-mode openai_only`: legacy OpenAI web-search-only discovery
- `--sitemap-lookback-months 24`: number of recent monthly sitemaps to scan (recommended for current quarter-coverage stability)
- `--author-max-pages 0` (default): author archive page cap for fallback crawl (`0` disables author fallback)
- `--discovery-cache-mode refresh|use|off`: discovery-cache behavior (separate from scrape cache)
- `--discovery-cache-dir output/openai_motley_discovery_cache`: discovery cache location

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
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL MSFT --pretty --verbose --openai-retries 5
```

Output shape (per ticker):

- `requested_quarters`, `found_quarters`, `missing_quarters`
- `quarters` with `status`, `title`, and `url`
- `quarters[].resolution_source` and `quarters[].resolution_attempts`
- `found_transcript_links` and `links` for copy-ready URL lists in terminal JSON output
- `candidate_pool` and `search_sources` for debugging slug discovery quality
- `discovery_methods_used`, `discovery_trace`, and `discovery_cache` for deterministic discovery diagnostics
- `selected_recent_links`, `scraped_transcripts`, and `scrape_errors` when `--scrape` is enabled
- `scrape_method`, `line_source`, `marker_detection`, and `line_count` diagnostics on scraped transcript payloads
- `section_parse_method` (`regex_from_page_text` or `openai_page_text`) and optional `section_parse_reason`
- Scraping runs OpenAI transcript structuring only when deterministic parsing is low-confidence.
- OpenAI HTTP calls use a retrying session and capped read timeout to reduce hangs from intermittent `RemoteDisconnected` transport errors.
- OpenAI transport-level retries now default to `0` (`OPENAI_TRANSPORT_RETRIES`) so application-level retry logic does not multiply timeout delays.
- OpenAI transcript-structuring retries are now fail-fast for non-retryable JSON parse failures (for example, malformed/truncated JSON), so scraping quickly falls back to deterministic parsing instead of burning all retries.
- Transcript structuring also short-circuits after repeated read-timeout failures and on DNS resolution failures, then falls back to deterministic parsing.
- `llm_input_diagnostics` and `llm_input_preview` show the actual page-derived content passed to OpenAI for transcript structuring.
- If only low-quality parser output is available, output includes `quality_flags` (for example `parser_low_confidence`, reason, and optional OpenAI/browser errors).
- If you interrupt a long run (`Ctrl+C`), CLI now returns partial JSON results cleanly without a Python traceback.
- Discovery is deterministic-first: sitemap and author crawling run before OpenAI fallback, and OpenAI candidate extraction is source-first so missing schema output no longer hard-fails discovery.
- In hybrid mode, OpenAI fallback only runs when deterministic discovery still has unresolved quarters, and the OpenAI query is constrained to exact unresolved quarter labels (no adjacent-quarter substitution).
- Scrape selection is strict to the requested quarter window; it does not backfill missing window quarters with older transcripts.
- Candidate cleanup now drops likely off-ticker transcript URLs (for example, unrelated symbols that appear in search-source spillover) and prefers quarter-resolved links for scraping.
- OpenAI discovery fallback now filters candidates against unresolved quarter labels and ticker/company tokens to reduce off-ticker quarter collisions.
- Transcript start markers are now heading-aware, so inline phrases like "in your prepared remarks" no longer incorrectly reset parsing into mid-call Q&A.
- When transcript headings are missing, section typing is inferred from call flow (prepared remarks vs Q&A), and participants are backfilled from parsed speaker sections so the output remains usable.
- Q&A transitions now detect moderator handoff phrases (for example, "Operator, may we have the first question") even when spoken by investor-relations speakers, reducing delayed `prepared_remarks` -> `qa` switching.
- Q&A transition detection now avoids flipping long prepared-remarks blocks to `qa` when they only end with a trailing handoff sentence like "let's open the call to questions."
- Multi-ticker runs now share deterministic discovery fetches (sitemap/author URLs) inside a single run to reduce repeated network work.
- HTML reports now include a top "Jump To" navigation with ticker-level and transcript-level anchors.
- Verbose logging now emits phase separators (`DISCOVERY:SITEMAP`, `DISCOVERY:AUTHOR`, `DISCOVERY:OPENAI_FALLBACK`, `SCRAPE`, `RUN COMPLETE`) plus phase timings and failure categories.

## Notes

- FinBERT (`ProsusAI/finbert`) is BERT-base scale and runs locally on Apple Silicon.
- This tool is an analysis workspace, not trading advice.
