# Rocky Student Training Pipeline (First Pass)

This document covers the local student-model pipeline built on top of the completed Gemma teacher labels.

## Scope

This first pass is block-level only and targets:

- `confidence`
- `specificity`
- `outlook_strength`
- `directness`
- `risk_intensity`

It intentionally avoids Q&A pairing and multi-task architecture for now.

## Scripts

- `scripts/prepare_block_training_data.py`
- `scripts/train_block_metric_classifier.py`
- `scripts/evaluate_block_metric_classifier.py`
- `scripts/infer_block_metrics.py`

Shared helpers:

- `rocky/training_utils.py`

## Prerequisites

For DeBERTa-v3 runs, install SentencePiece in the repo venv:

```bash
.venv/bin/pip install sentencepiece
```

## 1) Prepare data

```bash
.venv/bin/python scripts/prepare_block_training_data.py \
  --input output/teacher_dataset_kaggle_v2/labeled_blocks.jsonl \
  --output-dir output/student_training_data \
  --min-dataset-quality 0.55 \
  --min-teacher-confidence 0.60 \
  --label-mode five_band \
  --seed 42
```

Outputs:

- `train.jsonl`
- `validation.jsonl`
- `test.jsonl`
- `review_bucket.jsonl`
- `dropped.jsonl`
- `summary_stats.json`

Split grouping is transcript-first (`transcript_id`, fallback `ticker+quarter`) to reduce leakage.

Label modes:

- `five_band`: `very_low/low/medium/high/very_high`
- `three_band`: merges to `low/medium/high`
- `binary`: merges to `low/high` (maps `very_low|low|medium -> low`, `high|very_high -> high`)

Use `three_band` or `binary` when a metric is too imbalanced for stable 5-band training.

## 2) Train one metric classifier

Confidence example:

```bash
.venv/bin/python scripts/train_block_metric_classifier.py \
  --train-file output/student_training_data/train.jsonl \
  --validation-file output/student_training_data/validation.jsonl \
  --metric confidence \
  --label-mode five_band \
  --model-name deberta-v3-base \
  --output-dir output/student_models/confidence_deberta_v3_base \
  --epochs 3 \
  --batch-size 8 \
  --learning-rate 2e-5 \
  --max-length 384 \
  --seed 42
```

Memory-constrained Apple Silicon example (recommended starting point):

```bash
.venv/bin/python scripts/train_block_metric_classifier.py \
  --train-file output/student_training_data/train.jsonl \
  --validation-file output/student_training_data/validation.jsonl \
  --metric confidence \
  --label-mode five_band \
  --model-name deberta-v3-base \
  --output-dir output/student_models/confidence_deberta_v3_base \
  --epochs 3 \
  --batch-size 4 \
  --eval-batch-size 4 \
  --gradient-accumulation-steps 2 \
  --learning-rate 2e-5 \
  --max-length 320 \
  --mps-memory-fraction 0.75 \
  --seed 42
```

Supported model aliases:

- `deberta-v3-base` -> `microsoft/deberta-v3-base`
- `modernbert-base` -> `answerdotai/ModernBERT-base`

Confidence 3-band example:

```bash
.venv/bin/python scripts/train_block_metric_classifier.py \
  --train-file output/student_training_data_three_band/train.jsonl \
  --validation-file output/student_training_data_three_band/validation.jsonl \
  --metric confidence \
  --label-mode three_band \
  --model-name deberta-v3-base \
  --output-dir output/student_models/confidence_three_band_deberta_v3_base \
  --epochs 3 \
  --batch-size 4 \
  --eval-batch-size 4 \
  --gradient-accumulation-steps 2 \
  --learning-rate 2e-5 \
  --max-length 256 \
  --device cpu \
  --seed 42
```

## 3) Evaluate held-out test split

```bash
.venv/bin/python scripts/evaluate_block_metric_classifier.py \
  --model-dir output/student_models/confidence_deberta_v3_base/model \
  --test-file output/student_training_data/test.jsonl \
  --output-dir output/student_models/confidence_deberta_v3_base/eval \
  --metric confidence \
  --label-mode five_band \
  --max-length 384
```

Outputs:

- `metrics.json`
- `confusion_matrix.json`
- `predictions.jsonl`
- `error_examples.jsonl`

## 4) Inference on block rows

```bash
.venv/bin/python scripts/infer_block_metrics.py \
  --model-dir output/student_models/confidence_deberta_v3_base/model \
  --input output/student_training_data/test.jsonl \
  --output output/student_models/confidence_deberta_v3_base/infer_test_predictions.jsonl \
  --metric confidence \
  --max-length 384
```

Inference output includes class probabilities and a default band-to-score mapping:

- `very_low=0.10`
- `low=0.30`
- `medium=0.50`
- `high=0.70`
- `very_high=0.90`

`infer_block_metrics.py` now reads the class labels from the saved model config, so 5-band/3-band/binary models are supported automatically.

## 5) Site Hybrid Rollout (student + lexical)

The backend transcript scorer now supports policy-driven hybrid routing:

- Student-primary by default: `confidence`, `directness`, `outlook_strength`
- Lexical-primary by default: `specificity`, `risk_intensity`

Key runtime toggles:

- `USE_STUDENT_CONFIDENCE`
- `USE_STUDENT_DIRECTNESS`
- `USE_STUDENT_OUTLOOK_STRENGTH`
- `USE_STUDENT_SPECIFICITY`
- `USE_STUDENT_RISK_INTENSITY`
- `STUDENT_METRICS_SHADOW_COMPARE`
- `STUDENT_METRICS_FORCE_LEXICAL_FALLBACK`
- `STUDENT_METRICS_SPECIFICITY_BLEND_ENABLED` (experimental; default off)

Model directories can be overridden with:

- `STUDENT_MODEL_CONFIDENCE_DIR`
- `STUDENT_MODEL_DIRECTNESS_DIR`
- `STUDENT_MODEL_OUTLOOK_STRENGTH_DIR`
- `STUDENT_MODEL_SPECIFICITY_DIR`
- `STUDENT_MODEL_RISK_INTENSITY_DIR`

Per-block source/debug metadata is written under:

- `speaker_analysis[].segment_diagnostics.feature_diagnostics.metric_source_debug`

This includes source selection (`student_primary`, `lexical_primary`, `lexical_fallback`) and shadow lexical/student values when enabled.
