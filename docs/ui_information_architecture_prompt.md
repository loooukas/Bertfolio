# FinBERT UI Redesign: Information Architecture Prompt

Copy/paste the prompt below into ChatGPT to design a completely new interface from the data model and content goals, without inheriting the current visual structure.

---

You are designing the best possible product UI and interaction system for a transcript-first earnings intelligence platform called **FinBERT Earnings Signals**.

Your job is to design the information experience from first principles based on the exact information inventory below. Do not assume any existing layout, component style, or current visual hierarchy; treat this as a clean redesign with modern, high-signal UX.

## Product Goal
The platform helps an analyst understand earnings-call quality and direction by combining:
- transcript-derived communication quality and sentiment,
- market reaction from news + social feeds,
- fundamentals context and quarter trends,
- explicit diagnostics and data reliability reporting.

The system must support both confident interpretation and skeptical validation. Users should be able to move from summary to evidence quickly.

## Primary Surfaces
Design for these surfaces and flows:
1. Main analysis workspace (`/`): run analysis for a ticker and consume the full report.
2. Full-report loading/progress state: report is hidden until run completion.
3. Transcript detail viewer (quarter-level structured transcript content).
4. Social item detail viewer (full post content and metadata).
5. Chart test utility (`/charts-test`): synthetic data page used to validate chart behavior without full backend runs.

Also account for backend status and polling surfaces:
- `GET /api/health`
- `POST /api/analyze/jobs`
- `GET /api/analyze/jobs/{job_id}`
- `GET /api/analyze/jobs/{job_id}/result`
- `GET /api/analyze`
- `GET /api/analyze/snapshot`

## Run Lifecycle + Progress Data
Each analysis run has job-level progress. The UI should interpret these fields as first-class information:
- `job_id`, `ticker`, job `status` (`queued`, `running`, `completed`, `failed`), `created_at`, `updated_at`, optional `error`.
- `progress.percent` (weighted completion percentage).
- `progress.active_stage`, `progress.active_subtask`.
- `progress.stages[]`, each stage with:
  - `key`, `label`, `status` (`pending`, `loading`, `done`, `error`),
  - `progress` (0.0-1.0),
  - `message`, `subtask`,
  - `duration_ms`.
- `progress.messages[]`: timestamped run log entries with `level`, `stage`, `subtask`, `message`.

Canonical stages and intended meaning:
- `overview`: run initialization and top-level synthesis readiness.
- `market_reaction`: feed acquisition, filtering, and sentiment scoring.
- `fundamentals`: metric retrieval and cross-provider checks.
- `transcript`: discovery, scrape, normalization, speaker scoring, summary.
- `data_audit`: diagnostics assembly and reliability reporting.

## Global Report Context (cross-section)
The complete report contains global context fields:
- `ticker`
- `analysis_version`
- `overall_sentiment_score` (continuous directional score)
- `overall_sentiment_label` (strongly/cautiously bullish, mixed, strongly/cautiously bearish)
- `transcripts_found`
- `warnings[]` (global warnings)
- `run_summary`:
  - `ticker`, `overall_label`, `overall_score`, `transcripts_found`, `news_count`, `social_count`.

Global context should support immediate orientation and confidence calibration before deep reading.

## Canonical Analysis Sections
There are five canonical sections; all must be represented.

### 1) Overview
Purpose: concise executive synthesis across transcript tone, fundamentals, and market reaction.

Data:
- `overview.ticker`
- `overview.company_name`
- `overview.stance_label`
- `overview.executive_summary`
- `overview.key_takeaways[]`
- `overview.metrics[]` where each metric has `key`, `label`, `value`.

Common metric themes include management confidence, evasiveness, outlook strength, and transcript coverage.

### 2) Transcript
Purpose: evaluate management communication quality and directional implications using structured speaker-level analysis.

Data:
- `transcript.availability` (`available`, `partial`, `missing`)
- `transcript.transcript_count_requested`
- `transcript.transcript_count_found`
- `transcript.latest_summary`
- `transcript.prepared_vs_qa_note`
- `transcript.key_quotes[]`
- `transcript.qa_pressure_points[]`
- `transcript.chart_enabled`
- `transcript.sparse_note`

Speaker-level rows (`transcript.speaker_analysis[]`):
- `speaker`
- `section_type` (`prepared_remarks`, `qa`, `other`)
- `sentiment_direction` (-1 to 1)
- `confidence` (0-100)
- `evasiveness` (0-100)
- `specificity` (0-100)
- `forward_looking_strength` (0-100)
- `risk_language_intensity` (0-100)
- `topic_label`
- `evidence_snippets[]`
- optional `segment_diagnostics`.

Speaker rollups (`transcript.speaker_rollup[]`):
- `speaker`, `mention_count`, `avg_sentiment_direction`, `avg_confidence`, `avg_evasiveness`, `dominant_topic`.

Speaker chart profile (`transcript.speaker_confidence_profile[]`):
- `speaker`, `mentions`, `confidence`, `evasiveness`, `sentiment`.

Quarter availability (`transcript.quarter_status[]`):
- `quarter`
- `status` (`found`, `not_found`, `error`)
- optional `detail`.

Normalized transcript documents (`transcript.transcripts[]`):
- `ticker`, `company_name`
- `source`, `source_url`, `title`, `published_date`
- `has_full_transcript`
- `extraction_confidence` (0-1)
- `normalization_mode` (`openai`, `deterministic_degraded`)
- `parsing_warnings[]`
- `participants[]` with `name`, optional `role`
- `sections[]` with:
  - `section_type`, `speaker`, `speaker_role`, `text`, `order_index`, `evidence_snippets[]`
- `key_quotes[]`.

Important behavior constraints:
- Operator speech is excluded from transcript analysis and transcript charts.
- Speaker exploration needs filtering by speaker, section, topic, sentiment bucket, confidence floor, evasiveness ceiling, specificity floor.
- Speaker ordering should prioritize who speaks most.

### 3) Market Reaction
Purpose: summarize near-term external narrative and crowd signal around the ticker.

Data:
- `market_reaction.balance_summary`
- `market_reaction.news_count`
- `market_reaction.social_count`
- `market_reaction.chart_enabled`
- `market_reaction.sparse_note`

News items (`market_reaction.news_items[]`):
- `title`, `summary`, `url`, `source`, `time_published`, `sentiment_score`, `sentiment_label`.

Social items (`market_reaction.social_items[]`):
- `source`, `title`, `body`, `excerpt`, `url`, `subreddit`, `created_utc`, `relevance_score`, `sentiment_score`, `sentiment_label`.

Design should support both quick triage (headline/excerpt) and deep verification (full text + outbound link).

### 4) Fundamentals
Purpose: combine valuation context with quarter momentum and EPS trajectory.

Data:
- `fundamentals_workspace.operating_context`
- `fundamentals_workspace.metrics[]` (`key`, `label`, `value`)
- `fundamentals_workspace.table[]` (quarter rows)
- `fundamentals_workspace.trend_series[]`
- `fundamentals_workspace.chart_enabled`
- `fundamentals_workspace.sparse_note`

Quarter row fields:
- `quarter`, `revenue`, `net_income`, `reported_eps`, `eps_estimate`.

Trend series fields:
- `quarter`, `revenue`, `net_income`, `eps`, `eps_estimate`.

Metric coverage includes values such as market cap, trailing/forward PE, beta, debt/equity, liquidity ratios, ROE, operating margin, enterprise value, debt/cash totals, revenue QoQ, EPS QoQ.

### 5) Data Audit
Purpose: make reliability, failure modes, and source quality explicit.

Data:
- `data_audit.confidence_note`
- `data_audit.normalization_mode`
- `data_audit.warnings[]`
- `data_audit.missing_items[]`
- `data_audit.parsing_warnings[]`
- `data_audit.source_counts` (transcripts/news/social counts)
- `data_audit.dedupe_counts` (pool vs deduped counts)
- `data_audit.slowest_tasks[]`

Transcript discovery audit (`data_audit.transcript_discovery`):
- `pages_scanned`
- `candidates_total`
- `transcript_like_count`
- `match_filtered_count`
- `selected_count`
- `discarded_near_matches[]`
- `fetch_failures[]`
- `playwright_fallback_used`.

Task granularity (`data_audit.task_breakdown[]`):
- `key`, `label`, `status` (`done`, `error`, `skipped`), `duration_ms`, `detail`.

Fundamentals cross-check audit (`data_audit.fundamentals_validation`):
- `yahoo_source_used`, `alpha_source_used`
- `compared_fields[]`
- `notes[]`
- `mismatches[]`, each with `key`, `yahoo_value`, `alpha_value`, `relative_diff_pct`, `note`.

## Auxiliary Surfaces and Payloads
Treat these as product-relevant information surfaces, not just technical internals.

### Snapshot payload (`GET /api/analyze/snapshot`)
Purpose: provide a fast pre-analysis orientation before full transcript processing finishes.

Data includes:
- top-level `ticker`, `company_name`, `overall_sentiment_score`, `overall_sentiment_label`
- `overview` (snapshot executive summary, key takeaways, compact metrics)
- `market_reaction` (snapshot balance summary, news/social counts, ranked items, sparse note)
- `warnings[]`
- `ui_copy`.

### Health payload (`GET /api/health`)
Purpose: liveness signal for operations and environment checks.

Data:
- `status` (expected value: `ok`).

### Copy dictionary (`ui_copy`)
Purpose: semantic labeling and empty-state language under a centralized dictionary.

Data groups:
- `app_title`, `app_subtitle`
- `section_labels` (section keys to user-facing labels)
- `ui_labels` (action/input terminology)
- `empty_states` (section-level sparse/fallback language)
- `headings` (content heading dictionary)
- `microcopy` (notes and small instructional labels).

### Transcript quarter detail surface
Purpose: deep inspection of normalized transcript structure for a specific quarter.

Data displayed for selected quarter:
- transcript identity (`title`, `source`, `published_date`, `source_url`)
- participant roster (`name`, `role`)
- normalized section stream (`speaker`, `section_type`, `text`, order sequence)
- parse/normalization quality context (`extraction_confidence`, `normalization_mode`, `parsing_warnings`).

### Social detail surface
Purpose: read the full underlying social content for a selected record.

Data displayed:
- post identity (`title`, `source`, optional `subreddit`)
- timing (`created_utc`)
- sentiment context (`sentiment_label`, `sentiment_score`)
- full post text (`body`)
- outbound source link (`url`).

### Chart test utility (`/charts-test`)
Purpose: verify chart rendering logic and responsiveness using synthetic data, independent of backend analysis runtime.

Synthetic domains used:
- speaker profile domain:
  - speakers: `Tim Cook`, `Kevan Parekh`, `Suhasini`, `Amit`, `David`, `Wamsi`
  - metrics: confidence and evasiveness in 0-100 style ranges.
- fundamentals trend domain:
  - quarters: `2025-Q1` to `2026-Q2`
  - mixed metrics: revenue (USD scale), net income (USD scale), reported EPS, EPS estimate.

## Additional Data Available (Compatibility and Extended Context)
Beyond canonical sections, the API also provides extended structures that may deserve UI exposure in a redesign:
- `aggregate_scores` (company strength, outlook, confidence, evasiveness, sentiment label).
- `fundamentals` summary object (raw numeric fundamentals + quarterly snapshots + QoQ growth fields).
- `news_summary`, `social_summary`.
- `data_health` (requested/found/missing quarters, errors, compact warnings).
- `workflow[]` stage outcomes (`completed`, `partial`, `skipped`) with details.
- `report_tabs[]` (prebuilt markdown, KPI rows, tables for each section).
- `charts` payload (`price_volume`, `sentiment_timeline`, `fundamentals_trend`).
- legacy compatibility objects: `analyst_team`, `research_team`, `trader_plan`, `risk_management`, `manager_decision`, plus `news`, `social`, `transcripts` legacy arrays.

Treat these as optional enhancement inputs; prioritize canonical sections but preserve access to rich context where useful.

## Data Quality and Edge-State Requirements
Your UI concept must handle these realities gracefully:
- Transcript coverage can be `missing` or `partial` while other sections are strong.
- News or social can be sparse/empty after filtering.
- Fundamentals cross-check can detect provider mismatch.
- Parsing and normalization can degrade to deterministic fallback mode.
- Progress stages can fail independently.
- Some fields are optional or null and must not collapse the information architecture.

## Semantic and Formatting Rules to Preserve
- Human-readable labels should transform underscored tokens to title-cased phrases.
- Sentiment thresholds should preserve directional semantics (bullish/mixed/bearish boundaries around small absolute values).
- Quarter identity and chronology are critical for transcript/fundamentals interpretation.
- Provenance (source, link, timestamp/date) is mandatory for externally sourced items.
- Reliability indicators should be visible, not hidden.

## Request to ChatGPT (Deliverable)
Produce a complete UI/UX redesign proposal that includes:
1. A full information architecture for all surfaces listed above.
2. An interaction model for run lifecycle, loading, completion gating, and deep-drill transitions.
3. A data-first presentation strategy for each canonical section and for compatibility/extended data.
4. A prioritization strategy: what appears at first glance vs on demand.
5. Error/sparse-data UX for every major failure mode.
6. A chart strategy that preserves comparability, scale readability, and provenance context.
7. A filter/exploration strategy for transcript speaker analysis and quarter drilldown.
8. Recommendations for text hierarchy and narrative structure that improve analyst decision speed.

Do not mirror the old UI. Optimize for analytical clarity, auditability, and speed-to-insight while preserving all required information coverage.

---
