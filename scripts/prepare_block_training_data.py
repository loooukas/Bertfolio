#!/usr/bin/env python3
"""Prepare cleaned train/validation/test block datasets from teacher labels."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rocky.training_utils import (
    BAND_LABELS,
    METRICS,
    build_input_text,
    get_dataset_quality_score,
    get_metric_band,
    get_metric_score,
    get_teacher_confidence,
    infer_group_key,
    looks_like_admin_or_junk,
    read_jsonl,
    split_group_keys,
    target_metric_band_key,
    target_metric_score_key,
    write_json,
    write_jsonl,
)


DEFAULT_INPUT = "output/teacher_dataset_kaggle_v2/labeled_blocks.jsonl"
DEFAULT_OUTPUT_DIR = "output/student_training_data"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare cleaned block-level training data from teacher labels.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help=f"Input labeled JSONL (default: {DEFAULT_INPUT}).")
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory for train/validation/test buckets (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--min-dataset-quality",
        type=float,
        default=0.55,
        help="Minimum dataset_quality_score for trainable rows (default: 0.55).",
    )
    parser.add_argument(
        "--min-teacher-confidence",
        type=float,
        default=0.60,
        help="Minimum teacher_confidence for trainable rows (default: 0.60).",
    )
    parser.add_argument("--max-rows", type=int, default=0, help="Optional cap on loaded input rows.")
    parser.add_argument("--seed", type=int, default=42, help="Split seed.")
    parser.add_argument("--train-ratio", type=float, default=0.8, help="Train split ratio (default: 0.8).")
    parser.add_argument("--validation-ratio", type=float, default=0.1, help="Validation split ratio (default: 0.1).")
    parser.add_argument("--test-ratio", type=float, default=0.1, help="Test split ratio (default: 0.1).")
    parser.add_argument(
        "--drop-obvious-junk",
        action="store_true",
        help="Drop obvious junk rows instead of routing them to review_bucket.jsonl.",
    )
    return parser.parse_args(argv)


def _prepare_row(row: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    reasons: list[str] = []
    text = str(row.get("text") or "").strip()
    if not text:
        reasons.append("missing_text")

    prepared = dict(row)
    prepared["input_text"] = build_input_text(
        speaker_role=str(row.get("speaker_role") or ""),
        section_type=str(row.get("section_type") or ""),
        text=text,
    )

    for metric in METRICS:
        band = get_metric_band(row, metric)
        score = get_metric_score(row, metric)
        if band is None or band not in BAND_LABELS:
            reasons.append(f"missing_{metric}_band")
        else:
            prepared[target_metric_band_key(metric)] = band
        if score is None:
            reasons.append(f"missing_{metric}_score")
        else:
            prepared[target_metric_score_key(metric)] = float(score)

    dataset_quality_score = get_dataset_quality_score(row)
    teacher_confidence = get_teacher_confidence(row)
    if dataset_quality_score is None:
        reasons.append("missing_dataset_quality_score")
    else:
        prepared["dataset_quality_score"] = float(dataset_quality_score)
    if teacher_confidence is None:
        reasons.append("missing_teacher_confidence")
    else:
        prepared["teacher_confidence"] = float(teacher_confidence)

    if reasons:
        return None, reasons
    return prepared, []


def _band_distribution(rows: list[dict[str, Any]], metric: str) -> dict[str, int]:
    key = target_metric_band_key(metric)
    counts = Counter(str(row.get(key) or "missing") for row in rows)
    return {label: int(counts.get(label, 0)) for label in list(BAND_LABELS) + ["missing"]}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_path = Path(args.input)
    if not input_path.exists():
        raise RuntimeError(f"Input labeled dataset not found: {input_path}")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(input_path, max_rows=max(0, int(args.max_rows)))
    print(f"[prepare] Loaded rows: {len(rows)}")

    trainable_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    dropped_rows: list[dict[str, Any]] = []
    bucket_reason_counts = Counter()

    for row in rows:
        prepared, hard_reasons = _prepare_row(row)
        if prepared is None:
            dropped = dict(row)
            dropped["bucket"] = "dropped"
            dropped["bucket_reasons"] = hard_reasons
            dropped_rows.append(dropped)
            bucket_reason_counts.update(hard_reasons)
            continue

        ds_quality = float(prepared["dataset_quality_score"])
        teacher_conf = float(prepared["teacher_confidence"])
        junk_like, junk_reasons = looks_like_admin_or_junk(prepared)

        bucket_reasons: list[str] = []
        if ds_quality < float(args.min_dataset_quality):
            bucket_reasons.append("below_min_dataset_quality")
        if teacher_conf < float(args.min_teacher_confidence):
            bucket_reasons.append("below_min_teacher_confidence")
        if junk_like:
            bucket_reasons.extend(junk_reasons)

        if bucket_reasons:
            bucket_reason_counts.update(bucket_reasons)
            if args.drop_obvious_junk and junk_like:
                prepared["bucket"] = "dropped"
                prepared["bucket_reasons"] = sorted(set(bucket_reasons))
                dropped_rows.append(prepared)
            else:
                prepared["bucket"] = "review"
                prepared["bucket_reasons"] = sorted(set(bucket_reasons))
                review_rows.append(prepared)
            continue

        prepared["bucket"] = "trainable"
        prepared["bucket_reasons"] = []
        prepared["split_group"] = infer_group_key(prepared)
        trainable_rows.append(prepared)

    group_to_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in trainable_rows:
        group_to_rows[str(row["split_group"])].append(row)

    group_assignments = split_group_keys(
        group_to_row_count={key: len(value) for key, value in group_to_rows.items()},
        seed=int(args.seed),
        train_ratio=float(args.train_ratio),
        validation_ratio=float(args.validation_ratio),
        test_ratio=float(args.test_ratio),
    )

    split_rows = {"train": [], "validation": [], "test": []}
    for group, values in group_to_rows.items():
        split = group_assignments.get(group, "train")
        for row in values:
            row["split"] = split
            split_rows[split].append(row)

    train_path = output_dir / "train.jsonl"
    validation_path = output_dir / "validation.jsonl"
    test_path = output_dir / "test.jsonl"
    review_path = output_dir / "review_bucket.jsonl"
    dropped_path = output_dir / "dropped.jsonl"
    summary_path = output_dir / "summary_stats.json"

    write_jsonl(train_path, split_rows["train"])
    write_jsonl(validation_path, split_rows["validation"])
    write_jsonl(test_path, split_rows["test"])
    write_jsonl(review_path, review_rows)
    write_jsonl(dropped_path, dropped_rows)

    split_group_counts = Counter(group_assignments.values())
    summary: dict[str, Any] = {
        "created_at": _utc_now_iso(),
        "input_file": str(input_path),
        "output_dir": str(output_dir),
        "filters": {
            "min_dataset_quality": float(args.min_dataset_quality),
            "min_teacher_confidence": float(args.min_teacher_confidence),
            "drop_obvious_junk": bool(args.drop_obvious_junk),
        },
        "split": {
            "seed": int(args.seed),
            "ratios": {
                "train": float(args.train_ratio),
                "validation": float(args.validation_ratio),
                "test": float(args.test_ratio),
            },
            "group_key": "transcript_id (fallback ticker+quarter)",
            "group_counts": {
                "train": int(split_group_counts.get("train", 0)),
                "validation": int(split_group_counts.get("validation", 0)),
                "test": int(split_group_counts.get("test", 0)),
            },
        },
        "counts": {
            "input_rows": len(rows),
            "train_rows": len(split_rows["train"]),
            "validation_rows": len(split_rows["validation"]),
            "test_rows": len(split_rows["test"]),
            "review_rows": len(review_rows),
            "dropped_rows": len(dropped_rows),
        },
        "bucket_reason_counts": dict(bucket_reason_counts),
        "metric_band_distribution": {
            metric: {
                "train": _band_distribution(split_rows["train"], metric),
                "validation": _band_distribution(split_rows["validation"], metric),
                "test": _band_distribution(split_rows["test"], metric),
            }
            for metric in METRICS
        },
    }
    write_json(summary_path, summary)

    print(
        "[prepare] Done."
        f" train={len(split_rows['train'])}"
        f" validation={len(split_rows['validation'])}"
        f" test={len(split_rows['test'])}"
        f" review={len(review_rows)}"
        f" dropped={len(dropped_rows)}"
    )
    print(f"[prepare] Summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
