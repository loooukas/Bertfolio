# FinBERT Earnings Signals (Local)

Local FinBERT stack with a Next.js frontend and FastAPI backend.

- Frontend: Next.js App Router (root app, promoted from `newsite/`)
- Backend: `finbert_site` FastAPI APIs and analysis pipeline
- Browser API path: Next proxy routes under `/api/*`

## Product Structure

The app is organized into exactly 5 primary sections:

1. Overview
2. Transcript
3. Market Reaction
4. Fundamentals
5. Data Audit

## UI Implementation (Current, Root Next.js App)

The frontend now follows the provided FinBERT reference design (dark institutional dashboard) with:

- Top navigation (`Analysis`, `Charts Test`, `Docs`, settings icon, API online indicator)
- Settings modal on the header cog with live controls for polling mode and display density
- In-app docs route at `/docs` (wired from the top-nav Docs action)
- Geist Sans / Geist Mono loaded from the local `geist` package (no remote font fetch required)
- Analyze hero/input panel that fades out after a run starts to keep report focus high
- Header brand click reset (top-left FinBERT) to return to a fresh analysis start state
- Report header that shows company, ticker chip, analysis version, overall signal, and score
- Full-screen real progress overlay with stage descriptions and running/complete/error states
- Horizontal report tabs for the 5 canonical sections
- Transcript-first deep-dive patterns:
  - quarter availability actions + structured transcript modal
  - richer transcript coverage diagnostics (coverage ratio, confidence/evasiveness rollups, prepared vs Q&A block counts)
  - key-quote cards with speaker attribution from transcript evidence
  - speaker rollups with mention modal by transcript/quarter and disabled no-mention states
  - filterable/sortable speaker block table
- Market reaction drilldowns:
  - two-column news card grid on desktop
  - two-column social card grid on desktop with detail modal
  - sentiment distribution chart (news vs social)
- Fundamentals workspace:
  - analyst-signals summary cards (consensus rating, target stats, recommendation mean)
  - key metrics + highlights
  - dedicated revenue, net-income, and EPS-vs-estimate chart panels
- Data audit workspace:
  - confidence grading
  - source count quality table
  - task-duration breakdown
  - transcript discovery funnel
  - fundamentals cross-validation mismatch table

Execution-role UI language (trader/risk/manager workflows) is removed from the primary interface. Legacy API fields remain for one migration window.

The UI now keeps a full-screen progress experience until every section finishes, then reveals the full report in one pass.
Progress stages now focus on actionable work only (`Market Reaction`, `Fundamentals`, `Transcript`, `Data Audit`).
Polling cadence is user-configurable in the settings modal (`Fast`, `Balanced`, `Eco`).

## Quick Start (Single Command)

```bash
cd <local-repo-path>
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
pnpm install
pnpm dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

`pnpm dev` starts both:

- Next.js frontend (`127.0.0.1:3000`)
- FastAPI backend (`127.0.0.1:8000`)

The dev launcher restarts any stale backend listener on `:8000` and scopes backend `--reload` watching to `finbert_site/` + `scripts/` to avoid `.next` reload thrash.

## Backend/UI Routing Notes

- FastAPI remains the source-of-truth API surface (`/api/analyze`, jobs, snapshot, health).
- Next route handlers proxy browser requests from `/api/*` to the backend service URL.
- Backend URL for proxying is configurable with:
  - `FINBERT_BACKEND_URL` (default `http://127.0.0.1:8000`)
- Legacy FastAPI-rendered HTML routes (`/`, `/charts-test`) still exist on the backend service but are now deprecated in favor of the Next frontend.

## What This Refactor Implements

- Transcript-first workspace with reference-faithful top-header + horizontal tab IA
- Deterministic Motley Fool transcript discovery and parsing pipeline
- Async run-job orchestration with real backend progress polling
- Optional OpenAI normalization for strict transcript JSON output
- Deterministic degraded normalization mode when OpenAI is unavailable
- Market reaction feed ranking improvements with 14-day lookback + recency weighting
- News/social relevance filtering tightened to ticker/company-linked items
- Social cards now show short excerpts only, with full-post modal view and top-right open-in-new-tab icon
- News/social cards use 2-column desktop grids for cleaner scan density
- Chart.js rendering with lazy-init per visible section and full-width responsive surfaces
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

Selection behavior:

- Pull larger candidate pools (up to ~200 per source family when available)
- Relevance-rank first, then apply dedupe, then keep top `*_LIMIT` rows
- Apply source balancing in social output so one provider does not dominate the final list

Volume controls:

- `NEWS_LIMIT`, `NEWS_POOL_SIZE`, `NEWS_LOOKBACK_DAYS`
- `SOCIAL_LIMIT`, `SOCIAL_POOL_SIZE`, `SOCIAL_LOOKBACK_DAYS`

Current defaults in `.env.example`:

- `NEWS_LIMIT=50`
- `NEWS_POOL_SIZE=240`
- `SOCIAL_LIMIT=50`
- `SOCIAL_POOL_SIZE=260`

### Expanded Fundamentals Metrics

Fundamentals now include additional metrics such as:

- `beta`
- `debt_to_equity`
- `current_ratio`
- `quick_ratio`
- `return_on_equity`
- `operating_margin`
- `enterprise_value`
- `total_debt`
- `total_cash`
- `free_cashflow`

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

### Async Progress API

- `POST /api/analyze/jobs` with JSON body `{ "ticker": "AAPL" }`
- `GET /api/analyze/jobs/{job_id}` for run status + progress stages/subtasks
- `GET /api/analyze/jobs/{job_id}/result` for the completed report payload

The frontend now uses this job flow so the loading screen reflects real backend stage completion.

### Charts Test Surface

Open [http://127.0.0.1:3000/charts-test](http://127.0.0.1:3000/charts-test) to validate chart rendering without waiting on a full analysis run.

## Local Run

1. Create and activate virtual environment
2. Install backend dependencies

```bash
pip install -r requirements.txt
```

3. Install frontend dependencies

```bash
pnpm install
```

4. Configure env

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

5. Start both frontend and backend

```bash
pnpm dev
```

6. Open [http://127.0.0.1:3000](http://127.0.0.1:3000)

Optional separate runs:

```bash
pnpm dev:web
pnpm dev:api
```

The FastAPI HTML routes still exist for compatibility on `127.0.0.1:8000` but are deprecated.

## Test

```bash
pnpm lint
pnpm build
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
