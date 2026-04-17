# FinBERT Report Desk (Local)

Local FastAPI app that keeps **FinBERT** as the core sentiment engine and renders a compact, tabbed trading research workflow.

## What This Build Implements

- Dark Modrinth-inspired design language and compact layout
  - left rail (progress + report nav)
  - tabbed workspace (no tall stacked report columns)
- Deterministic report tabs (markdown + structured KPI tables)
  - `summary`, `analyst`, `research`, `trader`, `risk_manager`, `data_health`
- Expanded API payload while preserving legacy compatibility
  - new: `run_summary`, `data_health`, `report_tabs`, `charts`
  - existing: `news`, `social`, `fundamentals`, `transcripts`, etc.
- Transcript retrieval reliability upgrades (Alpha Vantage only)
  - earnings-date quarter candidates + historical fallback scan
  - stop after first 4 valid transcript payloads
  - per-quarter outcome classification: `found` / `not_found` / `error`
- Social ingestion quality upgrades
  - broad Reddit ingestion + relevance ranking
  - relevance score surfaced in social records
- Three core charts
  - price + volume (3 months)
  - sentiment timeline (news/social/blended)
  - fundamentals trend (revenue/net income/EPS)

## Can You Run FinBERT Locally on an M4 Mac (24GB RAM)?

Yes. `ProsusAI/finbert` is a BERT-base scale model (~110M parameters) and runs locally on Apple Silicon with PyTorch MPS for this workload.

## Project Structure

- `finbert_site/main.py` — FastAPI routes (`/`, `/api/health`, `/api/analyze`)
- `finbert_site/analysis.py` — deterministic analysis pipeline + report/chart assembly
- `finbert_site/providers.py` — Alpha Vantage, yfinance, Reddit providers
- `finbert_site/finbert_model.py` — local FinBERT scoring/chunking wrapper
- `finbert_site/schemas.py` — API response models
- `templates/index.html` — left-rail + tabbed report UI
- `static/style.css` — dark design language styles
- `docs/phased_implementation_plan.md` — implementation phases and checks

## Local Run

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment:

```bash
cp .env.example .env
# Add ALPHAVANTAGE_API_KEY in .env
```

4. Start app:

```bash
uvicorn finbert_site.main:app --reload
```

5. Open:

- [http://127.0.0.1:8000](http://127.0.0.1:8000)

## API Key

- `ALPHAVANTAGE_API_KEY` is required for transcript and news retrieval.
- Reddit social search currently uses public endpoint (no additional key in this build).

## Test

```bash
pytest
```

## Note

This is an analyst-support interface, not trading advice.
