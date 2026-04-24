#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <prepared_dataset.csv> <output_dir> [horizon]"
  exit 1
fi

INPUT_PATH="$1"
OUTPUT_DIR="$2"
HORIZON="${3:-126}"

MIN_TRAIN_SIZE="${MIN_TRAIN_SIZE:-36}"
VAL_SIZE="${VAL_SIZE:-8}"
TEST_SIZE="${TEST_SIZE:-8}"
MAX_FOLDS="${MAX_FOLDS:-0}"

.venv/bin/python scripts/run_walkforward_calibration.py \
  --input "$INPUT_PATH" \
  --target-mode binary \
  --target-horizon "$HORIZON" \
  --binary-rank-metric macro_f1 \
  --min-train-size "$MIN_TRAIN_SIZE" \
  --val-size "$VAL_SIZE" \
  --test-size "$TEST_SIZE" \
  --max-folds "$MAX_FOLDS" \
  --output-dir "$OUTPUT_DIR"

