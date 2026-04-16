# FinBERT + TradingAgents Flow Migration Plan

## Goal
Preserve FinBERT-specific sentiment analysis while upgrading the product flow to a multi-stage analyst/researcher/trader/risk/manager experience.

## Phase Plan

### Phase 1: Data + Signal Foundation
Status: Completed

- Keep existing transcript/news/fundamentals ingestion.
- Add social ingestion (`Reddit`) for short-horizon crowd signal.
- Apply local FinBERT scoring across transcript/news/social text.
- Extend API schema with stage-based outputs for downstream UI.

### Phase 2: Multi-Stage Synthesis Engine
Status: Completed

- Build analyst team outputs for:
  - transcript analyst
  - fundamentals analyst
  - news analyst
  - social analyst
- Add bull/bear researcher synthesis with buy vs sell evidence scores.
- Add deterministic trader proposal + conviction.
- Add risk team (aggressive/neutral/conservative) and manager decision object.

### Phase 3: UX Pipeline Board
Status: Completed

- Replace report-stacked UI with pipeline board layout:
  - analyst ingestion
  - research debate
  - trader proposal
  - risk management
  - manager decision
- Keep detailed drilldown panels (analysts, fundamentals, feeds, transcripts).

### Phase 4: Design Language Alignment
Status: Completed

- Import and map the provided design language token system (Modrinth package):
  - palette
  - typography hierarchy
  - border radius
  - shadow system
- Apply tokenized styling to all main views and cards.

## Next Recommended Phases

### Phase 5: Local Inference Flex Layer
Status: Pending

- Introduce pluggable sentiment backends:
  - native HF/PyTorch FinBERT (default)
  - optional local API adapter (e.g., OpenAI-compatible endpoint)
- Add runtime backend health checks and latency telemetry.

### Phase 6: Evaluation + Guardrails
Status: Pending

- Add regression fixtures for representative tickers.
- Snapshot API shape checks for stage outputs.
- Add confidence/coverage guardrails for sparse-data scenarios.
