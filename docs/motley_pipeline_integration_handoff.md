# Motley Transcript Pipeline: Integration Handoff

## Goal
Integrate the deterministic Motley transcript pipeline into the main local analysis pipeline so `/api/analyze` uses high-quality quarter discovery + transcript parsing + diagnostics, with stable behavior and predictable costs.

This handoff describes:
- How the current CLI pipeline works end-to-end
- The settings that currently perform best
- How to integrate it into the main site pipeline
- How to improve transcript sentiment scoring when speaker blocks are long
- Ready-to-paste prompts for a new Codex chat

## Current State (Important)
The repository currently has two transcript paths:
- Newer path: `finbert_site/openai_motley_search.py` + `scripts/openai_motley_transcript_cli.py`
- Older in-app path: `finbert_site/providers.py::fetch_transcripts_motley_fool()` used by `finbert_site/analysis.py::build_analysis()`

The main site (`/api/analyze`) still uses the older provider path today.

## End-to-End Pipeline (CLI path)

### 1) Discovery
Entry: `discover_last_quarter_links(...)`

Flow:
1. Deterministic discovery from Motley monthly sitemap index + monthly sitemap pages.
2. Optional author-page fallback (`/author/20032/`) if enabled.
3. OpenAI web-search fallback only for unresolved quarters.

Key behavior:
- Quarter window is computed as contiguous latest N quarters from the newest discovered quarter.
- Candidate cleanup is strict: Motley transcript path required, off-ticker links dropped, URL normalized.
- Resolution source is tracked per quarter (`sitemap_month`, `author_page`, `openai_web_search`).
- In hybrid mode, OpenAI fallback is constrained to unresolved quarter labels.
- OpenAI fallback prompt now enforces exact unresolved quarter matches (no adjacent-quarter substitution).

### 2) Scrape
Entry: `scrape_recent_transcripts_for_report(...)`

Flow:
1. Select links from resolved quarter rows (strict window behavior).
2. Fetch page content (`requests`) and optionally browser-render text (Playwright) for hard pages.
3. Extract transcript-like text with marker-aware slicing and stop-markers.
4. Parse speaker sections deterministically first.
5. If deterministic parse confidence is low, optionally run OpenAI structuring with strict JSON schema.
6. If OpenAI fails or quality checks fail, fall back to deterministic parse and attach quality flags.

### 3) Structure and Diagnostics
Per transcript payload can include:
- `participants`
- `speaker_sections`
- `scrape_method`, `line_source`
- `marker_detection`, `line_count`
- `section_parse_method`, `section_parse_reason`
- `llm_input_diagnostics`, `llm_input_preview`
- `quality_flags`

### 4) Artifacts
With `--write-output-dir output`, each run auto-writes:
- `output/YYYY-MM-DD__HHMMSS.json`
- `output/YYYY-MM-DD__HHMMSS.log`
- `output/YYYY-MM-DD__HHMMSS.html`

Cache dirs:
- Scrape cache: `output/openai_motley_cache/`
- Discovery cache: `output/openai_motley_discovery_cache/`

## Settings That Currently Work Best

Recommended testing profile (fast feedback + high reliability):
- `--discovery-mode hybrid`
- `--sitemap-lookback-months 24`
- `--author-max-pages 0`
- `--timeout 45`
- `--openai-retries 3`
- `--cache-mode refresh`
- `--discovery-cache-mode refresh`
- `--scrape --scrape-count 4`
- `--write-output-dir output`

Recommended production profile (cost/stability):
- `--discovery-mode hybrid`
- `--sitemap-lookback-months 24`
- `--author-max-pages 0`
- `--timeout 45`
- `--openai-retries 2`
- `--cache-mode use`
- `--discovery-cache-mode use`
- `--scrape --scrape-count 4`

Transport hardening defaults already in code:
- OpenAI transport retries default to `0` (prevents timeout multiplication)
- OpenAI read timeout is capped
- Structuring retries short-circuit after repeated read timeouts or non-retryable JSON failures

## Why Quarter 4 Sometimes Missing
If you repeatedly get 3/4 quarters:
1. It is often a source availability gap on Motley for that exact quarter URL.
2. Not always a lookback issue.
3. Increasing sitemap lookback helps only when URL exists in older months.
4. With exact-quarter fallback, unresolved quarters remain explicitly missing instead of silently substituting adjacent quarters.

## Integration Plan Into Main Site (`/api/analyze`)

### Step A: Add pipeline adapter
Create a module that wraps `discover_last_quarter_links` + `scrape_recent_transcripts_for_report` and returns `TranscriptRecord`-like objects expected by `analysis.py`.

Target file:
- `finbert_site/transcript_pipeline.py`

Adapter responsibilities:
- Input: `ticker`, `company_name`, `settings`
- Output:
  - normalized transcript records for analysis
  - transcript warnings
  - transcript fetch diagnostics (requested/found/missing/outcomes)
  - discovery audit payload for Data Audit section

### Step B: Switch analysis entrypoint to new adapter
Current call in `analysis.py`:
- `fetch_transcripts_motley_fool(...)`

Replace with new adapter call so the site uses deterministic sitemap-first discovery and richer diagnostics.

### Step C: Preserve schema compatibility
Keep `AnalysisResponse` shape stable:
- `transcript` section
- `data_audit.transcript_discovery`
- `data_health.transcripts`
- legacy compatibility fields still populated

### Step D: Add feature flag and fallback
Add env toggle (example):
- `TRANSCRIPT_PIPELINE_MODE=motley_cli|legacy`

Behavior:
- default `motley_cli`
- fallback to `legacy` when hard failure occurs
- log mode + fallback reason into warnings and data audit

### Step E: Add regression tests
Add tests for:
- exact 4-quarter request behavior
- unresolved quarter remains missing (no adjacent substitution)
- off-ticker links rejected
- scrape parser + OpenAI fallback behavior
- analysis response schema unchanged

## Sentiment Optimization for Long Speaker Blocks
Current behavior in app analysis:
- `build_speaker_analysis` scores one sentiment per full speaker block.

Problem:
- Long speaker blocks dilute directional signal.
- One mixed block may hide strong positive/negative local segments.

Recommended approach:

### 1) Split long speaker blocks into subsegments
Rules:
- Keep block as-is if `< 700` chars.
- Split if `>= 700` chars.
- Segment at sentence boundaries.
- Target segment length: `450-750` chars.
- Hard cap segment length: `1000` chars.
- Carry 1 sentence overlap between neighboring segments.

### 2) Score each subsegment with FinBERT
For each subsegment, compute:
- directional score
- optional confidence proxy from class spread (if exposed)
- metadata: block index, segment index, char count

### 3) Aggregate robustly to block-level
Use weighted robust aggregation:
- weight by `sqrt(char_count)` capped at 2.5
- drop top and bottom 10% by absolute outlier score when segment_count >= 8
- aggregate with weighted mean after trim

### 4) Preserve explainability
Store:
- block-level score (for existing schema)
- segment-level scores (for diagnostics and future UI)
- top positive and top negative evidence sentences per block

### 5) Role-aware weighting (optional)
For management quality metrics (confidence/evasiveness):
- weight management responses higher than operator handoff lines
- do not remove analyst questions; keep them for Q&A pressure context

### 6) Practical defaults
Use these env defaults:
- `TRANSCRIPT_SENTIMENT_SEGMENT_CHARS=650`
- `TRANSCRIPT_SENTIMENT_SEGMENT_MAX=1000`
- `TRANSCRIPT_SENTIMENT_SEGMENT_MIN=180`
- `TRANSCRIPT_SENTIMENT_SEGMENT_OVERLAP_SENTENCES=1`

## Suggested New Chat Prompts

### Prompt 1: Integrate pipeline into site
Use this in a new chat:

"Integrate the deterministic Motley transcript pipeline into `/api/analyze` in this repo.

Requirements:
1. Replace transcript retrieval in `finbert_site/analysis.py` so it uses `finbert_site/openai_motley_search.py` discovery+scrape flow via a clean adapter module.
2. Keep `AnalysisResponse` and existing frontend contracts stable.
3. Preserve `data_audit` and `data_health` sections, but enrich them with discovery/scrape diagnostics from the new pipeline.
4. Add env-gated fallback mode (`TRANSCRIPT_PIPELINE_MODE=motley_cli|legacy`) with graceful fallback to legacy provider.
5. Add tests for quarter-window behavior, off-ticker filtering, and schema stability.
6. Update README with runbook and env variables.

Use these defaults:
- discovery mode hybrid
- sitemap lookback 24
- author max pages 0
- timeout 45
- openai retries 3
- cache mode refresh for dev, use for prod
- exact unresolved quarter matching only (no adjacent substitution)."

### Prompt 2: Sentiment segmentation upgrade
Use this in a new chat:

"Upgrade transcript sentiment scoring so long speaker blocks are segmented before FinBERT scoring.

Requirements:
1. Implement sentence-aware segmentation for each speaker block.
2. Segment only when block is long (>=700 chars).
3. Score each segment with existing FinBERT engine.
4. Aggregate to block-level score with weighted robust mean and outlier trimming.
5. Keep existing API fields unchanged, but add optional diagnostics payload for segment-level scores.
6. Add tests for segment split behavior and aggregation correctness.
7. Update docs with settings and rationale.

Target defaults:
- segment target 650 chars
- segment max 1000 chars
- segment min 180 chars
- overlap 1 sentence"

### Prompt 3: Production hardening + observability
Use this in a new chat:

"Harden transcript pipeline for production reliability and cost.

Requirements:
1. Add structured phase timing metrics for discovery/scrape/structure in app logs.
2. Add circuit-breaker behavior for repeated OpenAI timeouts.
3. Add cache hit/miss metrics for discovery and scrape caches.
4. Add one-command smoke script that runs AAPL+MSFT and verifies output files + missing quarter semantics.
5. Provide an operations runbook section in README for failure categories and remediation.

Keep schema and user-facing UI unchanged."

## Runbook Commands

### Development validation run
```zsh
cd bertfolio
mkdir -p output
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL MSFT \
  --pretty --verbose --scrape --scrape-count 4 \
  --timeout 45 --openai-retries 3 \
  --discovery-mode hybrid --sitemap-lookback-months 24 \
  --author-max-pages 0 --cache-mode refresh --discovery-cache-mode refresh \
  --write-output-dir output
```

### Production-like cached run
```zsh
cd bertfolio
.venv/bin/python scripts/openai_motley_transcript_cli.py AAPL MSFT \
  --pretty --verbose --scrape --scrape-count 4 \
  --timeout 45 --openai-retries 2 \
  --discovery-mode hybrid --sitemap-lookback-months 24 \
  --author-max-pages 0 --cache-mode use --discovery-cache-mode use \
  --write-output-dir output
```

## Quick Integration Checklist
- [ ] Add transcript adapter module using `openai_motley_search` functions
- [ ] Wire adapter into `analysis.py`
- [ ] Preserve response schema and UI contracts
- [ ] Add env flag for fallback mode
- [ ] Add segmentation-based transcript sentiment scoring
- [ ] Add tests + update README runbook
