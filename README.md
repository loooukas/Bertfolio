# Bertfolio

Bertfolio is a local earnings-call intelligence app. It combines a Next.js dashboard with a FastAPI analysis backend to pull company context, score transcript tone, summarize market reaction, and show data-quality diagnostics in one report.

The app is designed to run locally first, with provider credentials and model artifacts supplied from the developer's machine.

## What It Does

- Runs a Next.js frontend on `127.0.0.1:3000`.
- Runs a FastAPI backend on `127.0.0.1:8000`.
- Uses FinBERT (`ProsusAI/finbert`) for directional financial tone scoring.
- Supports optional student classifiers for transcript communication metrics such as confidence, directness, and outlook strength.
- Pulls market/news/social/fundamental context when the relevant provider keys are configured.
- Shows a 10-stage analysis progress flow, final report sections, source diagnostics, and cached run browsing.

## Requirements

- macOS, Linux, or Windows with a POSIX-like shell for the bundled dev script.
- Python 3.9 or newer.
- Node.js and pnpm.
- Optional: Alpha Vantage API key for Alpha Vantage news/fundamental enrichment.
- Optional: OpenAI API key for transcript normalization and search fallback.

## Setup

```bash
git clone <repo-url> bertfolio
cd bertfolio
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pnpm install
cp .env.example .env
```

Then edit `.env` for your local providers. You can leave optional providers blank while testing the UI and fallback paths.

## Run Locally

Start the full stack with one command:

```bash
pnpm dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

`pnpm dev` starts:

- Next.js frontend: `127.0.0.1:3000`
- FastAPI backend: `127.0.0.1:8000`

You can also run services separately:

```bash
pnpm dev:web
pnpm dev:api
```

## Environment Variables

Most useful variables:

- `ALPHAVANTAGE_API_KEY`: optional Alpha Vantage provider key.
- `OPENAI_API_KEY`: optional OpenAI key for transcript normalization and fallback discovery.
- `FINBERT_BACKEND_URL`: frontend-to-backend proxy target, default `http://127.0.0.1:8000`.
- `FINBERT_MODEL_NAME`: Hugging Face model name for the FinBERT tone scorer, default `ProsusAI/finbert`.
- `TRANSCRIPT_PIPELINE_MODE`: transcript retrieval mode, default `motley_cli`.
- `NEWS_*` and `SOCIAL_*`: feed limits, source toggles, and lookback settings.
- `STUDENT_MODEL_*_DIR`: optional local paths for student classifier model directories.

Local generated directories under `output/` are ignored by Git.

## Analysis Flow

The frontend uses async job polling so the loading screen reflects backend progress. The canonical stages are:

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

The final report is organized into five primary sections:

1. Overview
2. Transcript
3. Market Reaction
4. Fundamentals
5. Data Audit

## Models

Bertfolio has two model layers:

- FinBERT is the default local sentiment scorer for finance-specific directional tone. It downloads through Hugging Face/Transformers the first time it is needed unless already cached on the machine.
- Student metric classifiers are loaded from local directories under `output/student_models/...` by default. These directories are not part of the repository; if they exist on the machine running the app, Bertfolio uses them automatically.
- When a configured student model directory is missing, the backend logs a warning in the Data Audit path and falls back to deterministic lexical scoring for that metric. The app still runs, but it is not using the trained student-classifier layer for that metric.

Default student model paths:

- `output/student_models/confidence_three_band_deberta_v3_base_strict070/model`
- `output/student_models/directness_three_band_deberta_v3_base_strict070/model`
- `output/student_models/outlook_strength_five_band_deberta_v3_base_strict070/model`
- `output/student_models/specificity_deberta_v3_base_cpu/model`
- `output/student_models/risk_intensity_three_band_deberta_v3_base_strict070/model`

If your trained models live somewhere else, set the corresponding `STUDENT_MODEL_*_DIR` variables in `.env`.

## Testing

```bash
pnpm lint
pnpm build
pytest -q
```

If dependencies are missing, install the Python and Node dependencies from the setup section first.

## Notes

Bertfolio is an analysis and research-support tool, not trading advice.
