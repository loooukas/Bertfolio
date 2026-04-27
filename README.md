# Bertfolio

Bertfolio is a local earnings-call intelligence workspace. It combines a Next.js dashboard with a FastAPI analysis backend to score transcript tone, summarize market reaction, inspect fundamentals, and surface data-quality diagnostics in one report.

## Features

- Transcript-first earnings-call analysis with FinBERT directional tone scoring.
- Optional local student classifiers for communication metrics such as confidence, directness, outlook strength, specificity, and risk intensity.
- News, social, fundamentals, transcript discovery, normalization, scoring, and audit stages in one async job flow.
- Explainable report sections for overview, transcript, market reaction, fundamentals, and data audit.
- Local cache browsing for previously generated ticker reports.
- Next.js proxy routes so the browser talks to `/api/*` while the backend remains a separate FastAPI service.

## Architecture

```text
Next.js app                 FastAPI backend
127.0.0.1:3000   /api/* -> 127.0.0.1:8000
   |                          |
   |                          +-- FinBERT sentiment engine
   |                          +-- optional local student classifiers
   |                          +-- transcript/news/social/fundamentals providers
   |                          +-- local cache under output/
```

Main paths:

- `app/`: Next.js App Router frontend and proxy route handlers.
- `components/finbert/`: report UI components.
- `finbert_site/`: FastAPI app, analysis pipeline, providers, model runtime, schemas, and jobs.
- `scripts/dev.sh`: single-command local launcher for both services.

## Requirements

- Python 3.9 or newer.
- Node.js with `pnpm`.
- Optional Alpha Vantage API key for Alpha Vantage news/fundamental enrichment.
- Optional OpenAI API key for transcript normalization and fallback discovery.

## Quick Start

```bash
git clone <repository-url> bertfolio
cd bertfolio
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
pnpm install
cp .env.example .env
pnpm dev
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

`pnpm dev` starts both services:

- Next.js frontend: `127.0.0.1:3000`
- FastAPI backend: `127.0.0.1:8000`

## Configuration

Edit `.env` after copying `.env.example`.

Common settings:

| Variable | Purpose | Default |
| --- | --- | --- |
| `ALPHAVANTAGE_API_KEY` | Alpha Vantage provider access | blank |
| `OPENAI_API_KEY` | OpenAI transcript normalization and fallback discovery | blank |
| `FINBERT_BACKEND_URL` | Next.js proxy target for FastAPI | `http://127.0.0.1:8000` |
| `FINBERT_MODEL_NAME` | Hugging Face model for financial sentiment | `ProsusAI/finbert` |
| `TRANSCRIPT_PIPELINE_MODE` | Transcript retrieval pipeline | `motley_cli` |
| `NEWS_*` / `SOCIAL_*` | Feed source toggles, lookbacks, and pool sizes | see `.env.example` |
| `STUDENT_MODEL_*_DIR` | Local classifier model directories | `output/student_models/...` |

## Model Artifacts

Bertfolio has two model layers:

1. FinBERT runs through Hugging Face/Transformers and downloads on first use unless already cached on the machine.
2. Student metric classifiers are included under `output/student_models/...` and load from local directories at runtime.

Default student model paths:

```text
output/student_models/confidence_three_band_deberta_v3_base_strict070/model
output/student_models/directness_three_band_deberta_v3_base_strict070/model
output/student_models/outlook_strength_five_band_deberta_v3_base_strict070/model
output/student_models/specificity_deberta_v3_base_cpu/model
output/student_models/risk_intensity_three_band_deberta_v3_base_strict070/model
```

Those directories are committed as Git LFS artifacts. After cloning, run `git lfs pull` if your Git client did not download LFS files automatically. If your artifacts live elsewhere, set the matching `STUDENT_MODEL_*_DIR` value in `.env`.

## Git LFS

The student classifier weight files are stored with Git LFS because each DeBERTa weight file is larger than GitHub's normal file limit. Install Git LFS before cloning if you want a one-step checkout of the model artifacts:

```bash
brew install git-lfs
git lfs install
```

If you already cloned the repo and see pointer text instead of binary weight files, run:

```bash
git lfs pull
```

## Run Commands

```bash
pnpm dev      # start frontend and backend together
pnpm dev:web  # start only Next.js
pnpm dev:api  # start only FastAPI
pnpm lint     # generate Next route types and run TypeScript checks
pnpm build    # production Next.js build
```

## Analysis Flow

The frontend starts an async backend job and polls real stage progress:

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

The report renders five primary sections:

- Overview
- Transcript
- Market Reaction
- Fundamentals
- Data Audit

## Repository Scope

Included:

- Product source for the Next.js and FastAPI app.
- Runtime prompt templates used by the backend.
- Trained student classifier model artifacts required by the app.

Not included:

- Source datasets.
- Generated analysis caches and reports.
- Historical backtesting/calibration outputs.
- Training, testing, and backtesting scripts used during model development.

## Troubleshooting

If `uvicorn` is not found, make sure the virtual environment is active or run the backend through the repo-local script:

```bash
. .venv/bin/activate
pnpm dev:api
```

If student metrics show fallback warnings, confirm the configured `STUDENT_MODEL_*_DIR` paths exist and contain Hugging Face-compatible model/tokenizer files.

If transcript normalization or fallback discovery is unavailable, confirm `OPENAI_API_KEY` is set for the shell running `pnpm dev`.

## Disclaimer

Bertfolio is an analysis and research-support tool. It is not financial advice.
