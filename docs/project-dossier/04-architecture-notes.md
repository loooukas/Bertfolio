# Architecture Notes

## System boundaries

- Frontend: Next.js App Router (`app/`) with client orchestration in `app/page.tsx`.
- Edge/backend boundary: Next route handlers proxy browser traffic to FastAPI.
- Backend: FastAPI routes, async job manager, analysis pipeline, provider adapters, transcript pipeline, normalizer.

## Runtime and configuration model

- Environment-driven `Settings` dataclass holds provider/model/cache/scoring toggles.
- Per-run runtime overrides are validated and sanitized before use.
- Cache directories are explicit and configurable.

## Data contracts

- Strong Pydantic schemas for transcript blocks, report sections, audit payloads, and full response.
- Frontend adapter normalizes payload details for presentation and resilience.

## Architectural principles visible in code

- Deterministic-first with bounded LLM fallbacks.
- Graceful degradation with diagnostics instead of silent failure.
- Separation of concerns: fetching/scoring/normalizing/assembly/proxy each have dedicated modules.

## Citations

- `app/page.tsx:44`
- `app/api/analyze/route.ts:5`
- `lib/server/backend-proxy.ts:53`
- `finbert_site/main.py:54`
- `finbert_site/settings.py:20`
- `finbert_site/main.py:144`
- `finbert_site/schemas.py:262`
- `lib/finbert/adapters.ts:289`
