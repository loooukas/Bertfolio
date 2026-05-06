# How It Works (Pipeline)

## End-to-end flow

1. User submits ticker in UI.
2. Frontend creates an async job and polls job status.
3. Backend executes 10 weighted stages.
4. Backend returns a typed `AnalysisResponse`.
5. Frontend adapts payload to UI model and renders report.

## Canonical execution stages

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

## Model and scoring layers

- FinBERT sentiment engine for sentiment classification.
- Optional local student metric models (confidence, directness, outlook, specificity, risk intensity).
- Transcript-internal weighted component plus fundamentals/news/social weighted blend for overall score.

## Failure and fallback posture

- Cache read path can short-circuit compute.
- LLM-assisted paths are bounded by deterministic validation/fallback behavior.
- Data Audit surfaces warnings/notices when degradation occurs.

## Citations

- `app/page.tsx:81`
- `lib/finbert/client.ts:39`
- `finbert_site/jobs.py:98`
- `finbert_site/progress.py:15`
- `finbert_site/finbert_model.py:13`
- `finbert_site/student_metrics.py:104`
- `finbert_site/main.py:350`
- `finbert_site/schemas.py:397`
