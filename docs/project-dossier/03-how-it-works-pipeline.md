# How It Works (Pipeline)

## Executive summary

Bertfolio takes a ticker input and produces a decision-ready report by collecting multi-source data, scoring it with finance-aware models, and surfacing quality diagnostics.

## Plain-English walkthrough

1. User enters a ticker in the web app.
2. Next.js sends a job request to the backend.
3. FastAPI creates and runs the analysis job.
4. The backend fetches transcript, news, social, and fundamentals inputs.
5. FinBERT scores sentiment across retained text inputs.
6. Optional local models score communication-style transcript features.
7. The system assembles a five-section report.
8. Data Audit surfaces warnings, missing items, and validation outcomes.
9. The frontend renders the final report and progress history.

## Where each signal comes from

- `Transcripts`:
Motley Fool transcript discovery/scrape pipeline (active mode), with structured normalization before downstream scoring.

- `News`:
Alpha Vantage plus Yahoo Finance via multi-source news fetch and ranking.

- `Social`:
Reddit plus Stocktwits via multi-source social fetch and ranking.

- `Fundamentals`:
Yahoo Finance baseline metrics with Alpha Vantage cross-validation/backfill logic.

- `Sentiment model`:
FinBERT, a financial-language sentiment model.

- `Communication metrics`:
Optional local student metric models with deterministic fallback when unavailable.

## Canonical stage sequence

1. News Fetch
2. Social Fetch
3. News Sentiment Scoring
4. Social Sentiment Scoring
5. Fundamentals Fetch
6. Fundamentals Validation
7. Transcript Discovery + Scrape
8. Transcript Normalization
9. Transcript Sentiment + Speaker Scoring
10. Data Audit / Report Assembly

## Why this design matters in operations

- Predictable stage flow supports repeatable SLAs.
- Progress transparency reduces “black box” behavior during runs.
- Data Audit prevents silent degradation from being mistaken as complete confidence.

## Citations

- `app/page.tsx:81`
- `lib/finbert/client.ts:39`
- `finbert_site/main.py:434`
- `finbert_site/progress.py:15`
- `finbert_site/analysis.py:170`
- `finbert_site/analysis.py:1700`
- `finbert_site/analysis.py:1718`
- `finbert_site/analysis.py:1776`
- `finbert_site/analysis.py:1789`
- `finbert_site/analysis.py:1833`
- `finbert_site/finbert_model.py:13`
- `finbert_site/student_metrics.py:104`
- `finbert_site/settings.py:171`
- `finbert_site/settings.py:177`
- `finbert_site/transcript_pipeline.py:150`
- `finbert_site/schemas.py:397`
