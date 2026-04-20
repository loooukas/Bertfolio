# UI Fidelity Update (2026-04-20)

## Scope
This update aligns the existing FastAPI-served UI with the latest redesign direction while keeping backend routes and run commands unchanged.

## Key behavior changes
- Replaced mixed iconography in report tabs with a consistent SVG icon set (no emoji tab icons).
- Removed the repeated hero status line from normal successful runs; inline status now only shows input and runtime errors.
- Slowed job polling cadence from `1800ms` to `3600ms`.
- Standardized directional sentiment displays in UI to signed percentages (unit-score `-1..1` shown as `-100%..+100%`).

## Transcript improvements
- Key quote selection now filters low-information snippets and ranks quotes by a weighted signal (sentiment magnitude, confidence, evasiveness, specificity, forward-looking strength, and length).
- Added optional OpenAI reranking of shortlisted quotes when `OPENAI_API_KEY` is configured; deterministic ranking remains default fallback.
- Q&A pressure table now hides automatically when no meaningful Q&A pressure rows exist (prevents `n/a` filler output).
- Speaker analysis table now renders one consolidated row per speaker, excluding Operator, with weighted averages and statement counts.
- Added min filters for confidence, evasiveness, and specificity.
- Added sortable header carets for speaker table columns.

## Fundamentals layout ordering
Fundamentals section now follows this order:
1. Metrics
2. Charts
3. Quarterly table
4. Fundamentals report narrative

## API/schema compatibility
- `TranscriptSpeakerAnalysis` now includes `segment_char_count` (default `0`) to support consolidation quality controls.
- Existing API fields remain present; this is additive.

