# Architecture Notes

## Architecture in business context

Bertfolio separates user experience from analysis execution so each can evolve without breaking the other. This supports faster product iteration and cleaner operational ownership.

## Major components

- `Next.js frontend`: user input, progress polling, report rendering.
- `FastAPI backend`: job orchestration, scoring, report assembly.
- `Providers layer`: source-specific collection from transcript/news/social/fundamentals channels.
- `Model layer`: FinBERT and optional local communication-style models.
- `Schema layer`: typed contracts for stable payloads.
- `Cache layer`: local persistence for reruns and revisit workflows.

## Reliability mechanisms

- Typed schemas enforce payload consistency.
- Stage-level progress provides runtime observability.
- Deterministic fallback behaviors reduce hard failures.
- Data Audit makes uncertainty visible to users.

## Why this matters to deployment

- Easier separation of product, data, and model responsibilities.
- Better maintainability as sources/models evolve.
- More controlled path from local prototype to managed deployment.

## Citations

- `lib/server/backend-proxy.ts:53`
- `finbert_site/main.py:54`
- `finbert_site/jobs.py:31`
- `finbert_site/progress.py:42`
- `finbert_site/schemas.py:413`
- `finbert_site/analysis_cache.py:44`
- `lib/finbert/adapters.ts:289`
