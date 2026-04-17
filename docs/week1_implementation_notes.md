# Implementation Notes

## Current behavior

- The app is a deterministic analyst-support pipeline built around FinBERT sentiment scoring.
- It synthesizes fundamentals, news, social, and transcript signals into staged outputs:
  - analyst reports
  - research debate
  - trader plan
  - risk views
  - manager decision
- Output remains evidence-linked through structured report tables and source cards.

## Transcript health behavior

- Transcript retrieval is Alpha Vantage-only in this build.
- Missing transcript data is treated as coverage degradation, not a fatal UI error.
- Retrieval diagnostics are surfaced in `data_health` with per-quarter outcomes.

## UX behavior

- Top header shows compact run status only.
- Full warning detail and retrieval outcomes are isolated to the Data Health tab.
- News/social cards are rendered beneath summary metadata to reduce visual noise.

## Guardrails

- The interface is decision-support tooling, not financial advice.
- Sparse data conditions are explicitly surfaced via compact warnings and health diagnostics.
