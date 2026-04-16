# Week 1 Deliverable Mapping

## Problem framing implemented

The app is built as an analyst-support system for reducing transcript review time while keeping traceability:

- transcript ingestion is explicit and auditable
- Alpha Vantage news ingestion adds current external sentiment context
- sentiment and confidence are separated from factual transcript text
- warnings are surfaced when transcript quality/source access is insufficient

## Constitution-oriented behavior

- No investment recommendation outputs (no buy/sell/hold).
- Quotes and keyword evidence are returned for interpretive claims.
- Ambiguous / low-data cases fail with explicit warnings instead of forced conclusions.
- Evasiveness is estimated from Q&A hedging density and reported as a score, not a claim of intent.

## Oversight Matrix posture

This implementation intentionally targets **Augment & Verify**:

- AI performs repetitive extraction and scoring.
- Human reviews evidence quotes, warning flags, and fundamentals before acting.
