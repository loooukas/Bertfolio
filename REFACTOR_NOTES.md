# REFACTOR_NOTES

## Scope

This refactor converts the app from a roleplay trading flow into a compact earnings-intelligence workspace centered on transcript quality analysis.

Primary sections:

1. Overview
2. Transcript
3. Market Reaction
4. Fundamentals
5. Data Audit

## Transcript Sourcing Strategy

Primary transcript source is now Motley Fool discovery/parsing, not Alpha Vantage transcripts.

Deterministic pipeline:

1. Discover transcript candidates from Motley Fool call-transcript surfaces and the paginated Motley Fool Transcribing archive.
2. Normalize candidate metadata (`title`, `url`, `published_date`, `author`).
3. Deterministically filter and rank by transcript markers and ticker/company match.
4. Fetch article HTML using `requests`/`httpx`.
5. Parse transcript body with start/stop markers.

Key start markers include:

- `Prepared Remarks`
- `Questions and Answers`
- `CALL PARTICIPANTS`
- `DATE`

Key stop markers include:

- `Read Next`
- `Stocks Mentioned`
- related promo/disclosure/footer sections

## Why Deterministic Discovery Is Used

Motley Fool transcript slugs are not fully stable across companies and quarters. URL guessing from ticker alone is brittle. Discovery + deterministic filtering is more reliable, inspectable, and debuggable.

## OpenAI Normalization and Degraded Mode

Normalization is performed after deterministic extraction succeeds.

- Default mode: OpenAI strict JSON normalization (`normalizer_v1.md` constitution)
- Fallback mode: deterministic transcript blocks when OpenAI is unavailable or fails validation

Data Audit exposes normalization mode as:

- `openai`
- `deterministic_degraded`

## When Playwright Is Used

Playwright is fallback-only in this architecture and should be used only when server-delivered HTML is blocked or materially incomplete.

Current implementation reports Playwright usage via audit field:

- `transcript_discovery.playwright_fallback_used`

## UI Structure Changes

- Removed fake workflow panels and roleplay execution flow from primary UI
- Added left-rail section navigation only
- Added section-specific workspace panes for the 5 canonical sections
- Added compact run context card
- Added social modal pattern: cards are short; full post opens in modal
- Added centralized copy dictionary (`ui_copy`) for labels/headings/microcopy

## Sparse-Data Behavior Changes

Charts now must earn space:

- sentiment timeline requires at least 3 points
- fundamentals trend requires at least 3 points
- sparse conditions render explicit empty-state notes

No one-point filler timeline chart is rendered.

## Data Audit Changes

Data Audit now surfaces:

- transcript discovery counts
- fetch failures
- discarded near-matches
- dedupe counts
- parsing warnings
- missing coverage items
- normalization mode and confidence note

## Future Fallback Transcript Sources (Not in This Phase)

Potential future transcript sources:

- issuer IR transcript pages
- SEC filing-linked transcript disclosures where available
- earnings call transcript providers with stable APIs/licensing

## Manual Validation Targets

Refactor defaults and QA targets used for validation:

- `AAPL`
- `MSFT`
