#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-.venv/bin/python}"
INPUT_TABLE="${1:-output/score_calibration/historical_event_table.repaired.v2.csv}"
OUTPUT_BASE="${2:-output/score_calibration_73}"
HORIZON="${HORIZON:-3}"

if [[ ! -f "$INPUT_TABLE" ]]; then
  echo "Input table not found: $INPUT_TABLE" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Python binary not found/executable: $PYTHON_BIN" >&2
  exit 1
fi

run_mode() {
  local mode="$1"
  local out_dir="$OUTPUT_BASE/$mode"

  echo "[runner] mode=$mode horizon=$HORIZON output=$out_dir"
  "$PYTHON_BIN" scripts/prepare_score_calibration_dataset.py \
    --input "$INPUT_TABLE" \
    --target-horizon "$HORIZON" \
    --target-mode "$mode" \
    --drop-missing-target \
    --output-dir "$out_dir"

  "$PYTHON_BIN" scripts/calibrate_score_weights.py \
    --input "$out_dir/prepared_calibration_dataset.csv" \
    --target-mode "$mode" \
    --target-horizon "$HORIZON" \
    --output-dir "$out_dir/calibration_run"
}

run_mode continuous
run_mode binary

echo "[runner] done"
echo "[runner] continuous metrics: $OUTPUT_BASE/continuous/calibration_run/metrics.json"
echo "[runner] binary metrics: $OUTPUT_BASE/binary/calibration_run/metrics.json"
