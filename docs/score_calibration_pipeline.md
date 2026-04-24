# Historical Event-Study Score Calibration Pipeline

This pipeline builds an event-level historical table and calibrates score weights out-of-sample.

## Scope
- Not a trading simulator.
- Event-level calibration for earnings-call analysis.
- Targets are abnormal returns vs a benchmark (`SPY` by default).
- Time-aware splits are default (`train` -> `validation` -> `test` in chronological order).

## Scripts
- `scripts/build_historical_event_table.py`
- `scripts/prepare_score_calibration_dataset.py`
- `scripts/calibrate_score_weights.py`
- `scripts/score_calibration_utils.py` (shared helpers)

## Phase 1: Build Historical Event Table

### What gets built per row
- Event identity:
  - `ticker`, `company_name`, `event_date`, `quarter_label`, `transcript_source_url`, `transcript_id`
- Transcript features:
  - `transcript_coverage`
  - `management_confidence`
  - `management_directness`
  - `management_outlook_strength`
  - `management_specificity`
  - `management_risk_intensity`
  - `transcript_sentiment_directional_score`
  - `management_block_count`, `analyst_block_count`, `qa_block_count`, `prepared_remarks_block_count`
- Component features (when available):
  - `fundamentals_signal`, `news_signal`, `social_signal`
  - `current_handset_overall_score`, `current_handset_transcript_score`
  - selected raw subfeatures (`fundamentals_revenue_qoq_growth_pct`, `fundamentals_eps_qoq_growth_pct`, etc.)
- Market outcomes:
  - stock closes (`t-1`, `t`, `t+1`, `t+3`, `t+5`)
  - benchmark closes (`t-1`, `t`, `t+1`, `t+3`, `t+5`)
  - stock returns (`1d`, `3d`, `5d`)
  - benchmark returns (`1d`, `3d`, `5d`)
  - abnormal returns (`1d`, `3d`, `5d`)
  - binary abnormal-up labels (`1d`, `3d`, `5d`)

### Event alignment assumptions
- Event date priority:
  1. transcript `published_date`
  2. Motley URL date
  3. quarter midpoint fallback
- Trading-day anchor options:
  - `on_or_next_trading_day` (default)
  - `next_trading_day`
- Return windows are post-event close-to-close:
  - `1d`: `close(t+1) / close(t) - 1`
  - `3d`: `close(t+3) / close(t) - 1`
  - `5d`: `close(t+5) / close(t) - 1`

### Component-source modes
- `analysis_cache`: use existing cached analysis outputs.
- `live_current`: fetch a current snapshot (not strict event-time as-of).
- `analysis_cache_then_live` (default): analysis cache first, then live fallback.
- `none`: no component enrichment.

Transcript metric modes:
- `--transcript-metric-mode fast_recompute` (default): recompute block metrics quickly with student/AI extras disabled.
- `--transcript-metric-mode site_default`: recompute using the site's current `Settings` defaults (student metrics + feature classifier behavior as configured).

## Phase 2: Prepare Modeling Dataset

`prepare_score_calibration_dataset.py`:
- selects horizon and target mode
- filters missing rows if requested
- builds chronological train/validation/test splits
- optionally standardizes features using train-split stats
- exports:
  - `prepared_calibration_dataset.csv`
  - `prepared_train.csv`
  - `prepared_validation.csv`
  - `prepared_test.csv`
  - `prepared_dataset_summary.json`
  - optional `prepared_feature_scaler.json`

## Phase 3: Calibrate Weights

`calibrate_score_weights.py` includes:

### Models
- Continuous target: ridge regression
- Binary target: logistic regression (L2)

### Two-stage calibration
1. Transcript-internal stage
   - learns transcript aggregate from transcript submetrics
2. Full-score stage
   - learns blend from transcript aggregate + fundamentals/news/social

### Direct comparison model
- Single-stage model using transcript + component features directly.

### Baseline comparisons
- current hand-set overall
- equal-weight blend
- transcript-only
- fundamentals-only
- news-only
- social-only
- zero-return (continuous) / majority-direction (binary)

### Optional local search
- `--enable-local-search`
- samples a narrow neighborhood around learned stage-2 coefficients on validation data
- reports best nearby vector and OOS test metrics

### Outputs
- `metrics.json`
- `coefficients.json`
- `predictions_test.csv`
- `comparison_table.json`
- `calibration_summary.md`

## End-to-End Example

```bash
# 1) Build event table
.venv/bin/python scripts/build_historical_event_table.py \
  --normalized-transcripts-dir output/teacher_dataset_kaggle_v2/normalized_transcripts \
  --analysis-cache-glob "output/analysis_cache/*.json" \
  --component-source analysis_cache_then_live \
  --transcript-metric-mode fast_recompute \
  --benchmark-ticker SPY \
  --event-alignment-mode on_or_next_trading_day \
  --output-dir output/score_calibration

# 2) Prepare modeling dataset
.venv/bin/python scripts/prepare_score_calibration_dataset.py \
  --input output/score_calibration/historical_event_table.csv \
  --target-horizon 3 \
  --target-mode continuous \
  --drop-missing-target \
  --output-dir output/score_calibration

# 3) Calibrate weights
.venv/bin/python scripts/calibrate_score_weights.py \
  --input output/score_calibration/prepared_calibration_dataset.csv \
  --target-mode continuous \
  --target-horizon 3 \
  --output-dir output/score_calibration/calibration_run
```

Progress UX:
- Phase 1 shows live progress bars for event-row build, price fetch, and outcome enrichment.
- Phase 2 and Phase 3 show explicit step counters (`Step X/Y`).
- Disable progress output with `--no-progress` on any script.

## Binary-mode example

```bash
.venv/bin/python scripts/prepare_score_calibration_dataset.py \
  --input output/score_calibration/historical_event_table.csv \
  --target-horizon 5 \
  --target-mode binary \
  --drop-missing-target \
  --output-dir output/score_calibration/binary

.venv/bin/python scripts/calibrate_score_weights.py \
  --input output/score_calibration/binary/prepared_calibration_dataset.csv \
  --target-mode binary \
  --target-horizon 5 \
  --output-dir output/score_calibration/binary/calibration_run
```
