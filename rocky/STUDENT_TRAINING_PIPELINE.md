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

## 1) Prepare data

```bash
.venv/bin/python scripts/prepare_block_training_data.py \
  --input output/teacher_dataset_kaggle_v2/labeled_blocks.jsonl \
  --output-dir output/student_training_data \
  --min-dataset-quality 0.55 \
  --min-teacher-confidence 0.60 \
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

## 2) Train one metric classifier

Confidence example:

```bash
.venv/bin/python scripts/train_block_metric_classifier.py \
  --train-file output/student_training_data/train.jsonl \
  --validation-file output/student_training_data/validation.jsonl \
  --metric confidence \
  --model-name deberta-v3-base \
  --output-dir output/student_models/confidence_deberta_v3_base \
  --epochs 3 \
  --batch-size 8 \
  --learning-rate 2e-5 \
  --max-length 384 \
  --seed 42
```

Supported model aliases:

- `deberta-v3-base` -> `microsoft/deberta-v3-base`
- `modernbert-base` -> `answerdotai/ModernBERT-base`

## 3) Evaluate held-out test split

```bash
.venv/bin/python scripts/evaluate_block_metric_classifier.py \
  --model-dir output/student_models/confidence_deberta_v3_base/model \
  --test-file output/student_training_data/test.jsonl \
  --output-dir output/student_models/confidence_deberta_v3_base/eval \
  --metric confidence \
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
