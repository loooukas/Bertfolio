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
- Market reaction feed ranking and social dedupe improvements
- Social cards now show short excerpts only, with full-post modal view
- Sparse-data chart gating:
  - timeline charts require at least 3 points
  - sparse states render explicit notes instead of filler charts
- Canonical API section payloads + legacy compatibility contract

## Transcript Pipeline (Current)

Primary source is Motley Fool transcript surfaces:

- `https://www.fool.com/earnings/call-transcripts/`
- `https://www.fool.com/author/20032/` (+ pagination)

Flow:

1. Discover candidate transcript URLs
2. Deterministically filter/rank by transcript title and ticker/company match
3. Fetch raw HTML with requests/httpx
4. Parse transcript body via start/stop markers
5. Normalize into strict transcript structure (OpenAI default, deterministic fallback)

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

4. Start app

```bash
uvicorn finbert_site.main:app --reload
```

5. Open [http://127.0.0.1:8000](http://127.0.0.1:8000)

## Test

```bash
pytest -q
```

## Notes

- FinBERT (`ProsusAI/finbert`) is BERT-base scale and runs locally on Apple Silicon.
- This tool is an analysis workspace, not trading advice.
