#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
INPUT_TABLE="${1:-output/score_calibration/historical_event_table.repaired.126d.csv}"
OUTPUT_BASE="${2:-output/score_calibration_walkforward}"
HORIZONS="${HORIZONS:-63 126}"
TRAIN_FRACTION="${TRAIN_FRACTION:-0.60}"
VAL_FRACTION="${VAL_FRACTION:-0.20}"
MIN_PER_SPLIT="${MIN_PER_SPLIT:-8}"
MIN_TRAIN_SIZE="${MIN_TRAIN_SIZE:-36}"
VAL_SIZE="${VAL_SIZE:-8}"
TEST_SIZE="${TEST_SIZE:-8}"
MAX_FOLDS="${MAX_FOLDS:-0}"

if [[ ! -f "$INPUT_TABLE" ]]; then
  echo "Input table not found: $INPUT_TABLE" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python binary not found/executable: $PYTHON_BIN" >&2
  exit 1
fi

for H in $HORIZONS; do
  PREP_DIR="$OUTPUT_BASE/h${H}_binary/prepared"
  WF_DIR="$OUTPUT_BASE/h${H}_binary/walkforward"

  echo "[walkforward-runner] horizon=$H step=prepare output=$PREP_DIR"
  "$PYTHON_BIN" scripts/prepare_score_calibration_dataset.py \
    --input "$INPUT_TABLE" \
    --target-horizon "$H" \
    --target-mode binary \
    --drop-missing-target \
    --train-fraction "$TRAIN_FRACTION" \
    --val-fraction "$VAL_FRACTION" \
    --min-per-split "$MIN_PER_SPLIT" \
    --output-dir "$PREP_DIR"

  echo "[walkforward-runner] horizon=$H step=walkforward output=$WF_DIR"
  "$PYTHON_BIN" scripts/run_walkforward_calibration.py \
    --input "$PREP_DIR/prepared_calibration_dataset.csv" \
    --target-mode binary \
    --target-horizon "$H" \
    --output-dir "$WF_DIR" \
    --min-per-split "$MIN_PER_SPLIT" \
    --min-train-size "$MIN_TRAIN_SIZE" \
    --val-size "$VAL_SIZE" \
    --test-size "$TEST_SIZE" \
    --max-folds "$MAX_FOLDS"
done

echo "[walkforward-runner] done"
