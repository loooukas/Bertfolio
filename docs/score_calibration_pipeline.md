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
- `scripts/compare_weight_methodologies.py`
- `scripts/run_walkforward_calibration.py`
- `scripts/run_walkforward_binary_long_horizons.sh`
- `scripts/audit_event_table_failures.py`
- `scripts/repair_historical_event_table.py`
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
  - stock closes (`t-1`, `t`, `t+1`, `t+3`, `t+5`, `t+21`, `t+63`, `t+126`)
  - benchmark closes (`t-1`, `t`, `t+1`, `t+3`, `t+5`, `t+21`, `t+63`, `t+126`)
  - stock returns (`1d`, `3d`, `5d`, `21d`, `63d`, `126d`)
  - benchmark returns (`1d`, `3d`, `5d`, `21d`, `63d`, `126d`)
  - abnormal returns (`1d`, `3d`, `5d`, `21d`, `63d`, `126d`)
  - binary abnormal-up labels (`1d`, `3d`, `5d`, `21d`, `63d`, `126d`)
- Phase-1 diagnostics artifacts:
  - `event_table_summary.json`
  - `event_table_failures.json` (ticker-level price-fetch attempts plus live component-fetch diagnostics)

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
  - `21d`: `close(t+21) / close(t) - 1`
  - `63d`: `close(t+63) / close(t) - 1` (about 3 trading months)
  - `126d`: `close(t+126) / close(t) - 1` (about 6 trading months)

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
- supported horizons: `1`, `3`, `5`, `21`, `63`, `126`
- in binary mode, can rebuild labels from abnormal return sign and apply a neutral dead-zone:
  - `--binary-deadzone-eps <float>`
  - `--drop-binary-deadzone`
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
- Binary target: logistic regression (L2), with optional class balancing (`--binary-class-weight balanced|none`)
- Binary decision threshold can be tuned on validation (`--tune-binary-threshold`, default on) using:
  - `--binary-threshold-metric macro_f1|accuracy|precision|recall`
  - `--binary-threshold-grid-size <int>`

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

## Methodology Head-to-Head (Fixed Weights vs Stage Models)

`compare_weight_methodologies.py` lets you compare specific top-level weight profiles against:
- `model_stage1` (transcript-stage calibrated score)
- `model_direct` (single-stage calibrated model, if present in coefficients)

It reuses the prepared split (`train`/`validation`/`test`), tunes binary thresholds on validation, and reports test metrics for each method.
You can also freeze the threshold at `0.5` to match older runs:
- `--no-tune-binary-threshold --binary-fixed-threshold 0.5`

Example:

```bash
.venv/bin/python scripts/compare_weight_methodologies.py \
  --input output/score_calibration_126d/binary_v2/prepared_calibration_dataset.csv \
  --coefficients output/score_calibration_126d/binary_v2/calibration_run/coefficients.json \
  --target-mode binary \
  --target-column target \
  --profile blend_43_5_15_10:43,5,15,10 \
  --profile blend_40_35_15_10:40,35,15,10 \
  --profile blend_100_0_0_0:100,0,0,0 \
  --output-dir output/score_calibration_126d/binary_v2/method_compare
```

Outputs:
- `methodology_comparison.json`
- `methodology_comparison.md`

Binary outputs include:
- per-model tuned threshold in `metrics.json` (`models.<name>.threshold`)
- selected model block in `metrics.json` (`model_selection`)
- `model:selected_by_validation` row in `comparison_table.json`
- label columns in `predictions_test.csv` for each model and selected-by-validation model

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

# Optional: audit missing targets + per-ticker failure causes
.venv/bin/python scripts/audit_event_table_failures.py \
  --input output/score_calibration/historical_event_table.csv \
  --failures-json output/score_calibration/event_table_failures.json \
  --horizon 3 \
  --output output/score_calibration/event_table_audit.json
```

Progress UX:
- Phase 1 shows live progress bars for event-row build, price fetch, and outcome enrichment.
- Phase 2 and Phase 3 show explicit step counters (`Step X/Y`).
- Disable progress output with `--no-progress` on any script.

## Walk-Forward OOS Evaluation (Recommended for small samples)

Use expanding chronological windows to evaluate stability across multiple out-of-sample slices.

### One-shot binary run for 3-month and 6-month horizons

```bash
HORIZONS="63 126" ./scripts/run_walkforward_binary_long_horizons.sh \
  output/score_calibration/historical_event_table.repaired.126d.csv \
  output/score_calibration_walkforward
```

### Direct walk-forward command

```bash
.venv/bin/python scripts/run_walkforward_calibration.py \
  --input output/score_calibration_126d/binary/prepared_calibration_dataset.csv \
  --target-mode binary \
  --target-horizon 126 \
  --binary-rank-metric macro_f1 \
  --output-dir output/score_calibration_126d/binary/walkforward \
  --min-train-size 36 \
  --val-size 8 \
  --test-size 8
```

### Binary macro-F1 helper script

```bash
./scripts/run_walkforward_binary_macrof1.sh \
  output/score_calibration_126d/binary_v2/prepared_calibration_dataset.csv \
  output/score_calibration_126d/binary_v2/walkforward_macrof1 \
  126
```

### Walk-forward outputs

- `walkforward_folds.json`: fold-by-fold date ranges, split sizes, and artifact paths.
- `walkforward_comparison_table.json`: aggregate mean/std metrics over folds for models and baselines.
- `walkforward_summary.json`: run config plus best aggregate row.

## Incremental Repair (No Full Rebuild)

Use `repair_historical_event_table.py` to patch only missing/malformed rows in an existing event table.

```bash
.venv/bin/python scripts/repair_historical_event_table.py \
  --input output/score_calibration/historical_event_table.csv \
  --output output/score_calibration/historical_event_table.repaired.csv \
  --target-horizon 3 \
  --repair-market \
  --market-row-filter missing_target \
  --repair-components \
  --component-row-filter any_missing_component \
  --price-source yfinance_then_alpha
```

Notes:
- `--price-source yfinance_then_alpha` enables Alpha Vantage fallback when Yahoo/yfinance fails.
- Alpha Vantage rate limits can still leave unresolved rows for large batches on free keys.

## Binary-mode example

```bash
.venv/bin/python scripts/prepare_score_calibration_dataset.py \
  --input output/score_calibration/historical_event_table.csv \
  --target-horizon 5 \
  --target-mode binary \
  --binary-deadzone-eps 0.002 \
  --drop-binary-deadzone \
  --drop-missing-target \
  --output-dir output/score_calibration/binary

.venv/bin/python scripts/calibrate_score_weights.py \
  --input output/score_calibration/binary/prepared_calibration_dataset.csv \
  --target-mode binary \
  --target-horizon 5 \
  --binary-class-weight balanced \
  --binary-threshold-metric macro_f1 \
  --binary-threshold-grid-size 201 \
  --output-dir output/score_calibration/binary/calibration_run
```

## App Toggle: Optimized Score Defaults

The web app settings modal supports an optimized-defaults toggle in `Score Weights (%)`:

- `Use optimized defaults` (default: on)
  - when enabled, the top-level component weights are set to calibrated defaults:
    - transcript: `100`
    - fundamentals: `0`
    - news: `0`
    - social: `0`
  - when disabled, those four top-level weights are manually editable.
- transcript internal sub-weights are always pinned to calibrated values in all modes.

Runtime overrides passed by the UI include:
- `use_optimized_score_weight_defaults`
- `score_weight_transcript`
- `score_weight_fundamentals`
- `score_weight_news`
- `score_weight_social`
- `transcript_internal_model_enabled`
- `transcript_internal_intercept`
- `transcript_internal_weight_sentiment`
- `transcript_internal_weight_confidence`
- `transcript_internal_weight_directness`
- `transcript_internal_weight_outlook_strength`
- `transcript_internal_weight_specificity`
- `transcript_internal_weight_risk_intensity`
