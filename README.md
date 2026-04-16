# FinBERT Earnings + News Analyzer (Local)

A local web app that takes a stock ticker, pulls the latest 4 quarterly earnings call transcripts from Alpha Vantage, fetches recent Alpha Vantage news, runs FinBERT sentiment locally, and scores:

- Company Strength
- Outlook
- Management Confidence
- Evasiveness / hedging behavior

It also pulls fundamentals and EPS to compare narrative vs. numbers, then returns an overall sentiment score and label.

## Can this run on a 24GB Mac?

Yes. `ProsusAI/finbert` runs locally on CPU or Apple Silicon (`mps`) for this workload. First-run model download may take a few minutes.

## Project Structure

- `finbert_site/main.py` — FastAPI app + endpoints
- `finbert_site/providers.py` — Alpha Vantage transcript/news + fundamentals data providers
- `finbert_site/finbert_model.py` — local FinBERT chunked inference
- `finbert_site/analysis.py` — Week 1 scoring logic and aggregation
- `templates/index.html` — dashboard page
- `static/style.css` — UI styles

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

- `ALPHAVANTAGE_API_KEY`: required for transcripts and news

If transcripts are unavailable for a quarter, the app will still show news cards and overall sentiment when possible.

## Notes on your original Colab snippet

Your Colab baseline was ported into local modules and extended:

- keeps chunked FinBERT analysis of long transcripts
- robust transcript response parsing
- supports last-4-quarter workflow from Alpha Vantage
- adds news-card grid and news sentiment summary
- adds fundamentals/EPS comparison layer
- includes a local dashboard and API endpoint

## Week 1 alignment

The scoring logic follows your Week 1 deliverable categories:

- sentiment in financial context (not generic tone)
- forward-looking language emphasis for outlook
- hedging/evasiveness detection in Q&A sections
- confidence based on specificity vs. hedging
- traceable quotes and signal lists

## Caveat

This is an analyst-support tool, not trading advice. It is intentionally conservative and designed for `Augment & Verify` oversight.
