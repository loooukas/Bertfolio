# Bertfolio Report Desk Redesign Plan (Implemented)

## Scope
Preserve finance-model-first sentiment analysis while moving from a tall report stack to a compact left-rail + tabbed workspace with deterministic report outputs.

## Phase 1: Retrieval + Scoring Reliability
Status: Completed

- Transcript retrieval uses smarter quarter candidate generation:
  - earnings-date candidates from yfinance when available
  - historical fallback scan over 12 quarter labels
  - stop after first 4 valid transcript payloads
- Transcript diagnostics now track:
  - requested quarters
  - found/missing quarters
  - per-quarter outcomes (`found` / `not_found` / `error`)
- FinBERT scoring path keeps chunking and suppresses tokenizer max-length warning noise.
- Social ingestion remains broad and is relevance-ranked instead of hard-filtered.

## Phase 2: API Contract Expansion
Status: Completed

- Added response fields:
  - `run_summary`
  - `data_health`
  - `report_tabs`
  - `charts`
- Kept compatibility fields for legacy UI/detail rendering:
  - `news`, `social`, `fundamentals`, `transcripts`, etc.

## Phase 3: UI Architecture Rewrite
Status: Completed

- Replaced tall card-board layout with:
  - left rail for workflow/progress + tab navigation
  - tabbed main workspace for reports and data surfaces
- Fixed tab set:
  - Summary
  - Analyst Reports
  - Research Debate
  - Trader Plan
  - Risk + Final Verdict
  - Data Health
  - News Feed
  - Social Feed
  - Fundamentals
  - Transcript
- Top status is compact; warning detail moved into Data Health tab.
- Removed excessive chip/tooltip-like visual clutter.

## Phase 4: Charts + Compact Presentation
Status: Completed

- Added normalized chart series payload and rendering for:
  - `price_volume`
  - `sentiment_timeline`
  - `fundamentals_trend`
- Added empty-state handling for charts and compact card spacing.

## Phase 5: Testing + Validation
Status: Completed

- Provider tests cover:
  - quarter candidate generation (earnings + fallback paths)
  - scan stop condition after first four valid transcripts
  - per-quarter outcome classification
- Analysis tests cover:
  - `data_health` and compact warnings
  - deterministic report tab payload shape and chart outputs
- API contract test covers:
  - new fields present
  - legacy fields preserved

## Manual Acceptance Checklist

- Long inline warning string removed from top status area.
- Left rail + tab navigation active on desktop/mobile breakpoints.
- No oversized blank report columns in primary flow.
- Three core charts render and show graceful empty states.
- Transcript health explanation moved to Data Health tab.
