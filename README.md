# FinBERT Multi-Agent Signal Board (Local)

A local FastAPI app that keeps **FinBERT** as the sentiment engine, but now uses a
TradingAgents-style decision flow:

1. Analyst ingestion (`fundamentals`, `news`, `social`, `transcripts`)
2. Bull vs bear researcher synthesis
3. Trader proposal
4. Risk management team views
5. Manager execution decision

The UI now follows a pipeline board format and uses the imported Modrinth design-language token set (color, spacing, radii, and shadow system).

## What Changed

- FinBERT sentiment now scores:
  - Earnings transcripts
  - News headlines/summaries
  - Social posts (Reddit)
- New API response stages:
  - `analyst_team`
  - `research_team`
  - `trader_plan`
  - `risk_management`
  - `manager_decision`
  - `workflow`
- Existing evidence surfaces are preserved:
  - fundamentals snapshots + chart
  - news/social feed cards
  - transcript signal/quotes drilldown

## Can This Run on a 24GB M4 Mac?

Yes. This workload is realistic on Apple Silicon with local PyTorch (`mps`) for FinBERT inference.
The current model default is `ProsusAI/finbert`.

## Project Structure

- `finbert_site/main.py` — FastAPI entrypoint + endpoints
- `finbert_site/providers.py` — Alpha Vantage + Yahoo Finance + Reddit data providers
- `finbert_site/finbert_model.py` — local FinBERT wrapper
- `finbert_site/analysis.py` — multi-stage scoring and synthesis pipeline
- `finbert_site/schemas.py` — API contracts for analyst/research/trader/risk/manager stages
- `templates/index.html` — pipeline board UI
- `static/style.css` — Modrinth token-based styling
- `docs/phased_implementation_plan.md` — migration plan and phase tracking

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy environment file and add keys:

```bash
cp .env.example .env
```

4. Run server:

```bash
uvicorn finbert_site.main:app --reload
```

5. Open:

- [http://127.0.0.1:8000](http://127.0.0.1:8000)

## API Keys

- `ALPHAVANTAGE_API_KEY`: required for transcripts and Alpha Vantage news.

Social feed currently uses Reddit search and does not require an additional key.

## Caveat

This is an analyst-support tool, not trading advice. It is designed for `Augment & Verify` human oversight.
