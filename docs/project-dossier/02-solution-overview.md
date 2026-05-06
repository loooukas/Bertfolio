# Solution Overview

Bertfolio is a local two-service system: Next.js frontend + FastAPI backend, with the frontend talking to backend capabilities through `/api/*` proxy routes.

## What the solution delivers

- Async analysis jobs with visible stage-level progress.
- Combined report sections for Overview, Transcript, Market Reaction, Fundamentals, and Data Audit.
- Cache-backed re-openable runs.
- Runtime overrides for per-run tuning without editing environment files.

## Why this shape was chosen

- Keeps browser integration simple (`/api/*` from frontend), while backend can evolve independently.
- Preserves deterministic fallbacks and diagnostics in backend while still allowing bounded LLM assists.
- Makes the full output serializable and cacheable as one object.

## Citations

- `lib/server/backend-proxy.ts:3`
- `lib/server/backend-proxy.ts:53`
- `finbert_site/main.py:434`
- `finbert_site/jobs.py:31`
- `finbert_site/progress.py:15`
- `finbert_site/schemas.py:413`
