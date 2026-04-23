"""Shared utilities for block-level student training scripts."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import random
import re
from typing import Any, Iterable


METRICS = ("confidence", "specificity", "outlook_strength", "directness", "risk_intensity")
BAND_LABELS = ("very_low", "low", "medium", "high", "very_high")
BAND_TO_ID = {label: idx for idx, label in enumerate(BAND_LABELS)}
ID_TO_BAND = {idx: label for label, idx in BAND_TO_ID.items()}
BAND_TO_SCORE_DEFAULT = {
    "very_low": 0.10,
    "low": 0.30,
    "medium": 0.50,
    "high": 0.70,
    "very_high": 0.90,
}

_ADMIN_HINT_RE = re.compile(
    r"(?:next question|please go ahead|line is open|operator instructions|turn the call over|opening remarks|closing remarks)",
    flags=re.IGNORECASE,
)


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                yield payload


def read_jsonl(path: Path, *, max_rows: int = 0) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, row in enumerate(iter_jsonl(path), start=1):
        out.append(row)
        if max_rows > 0 and idx >= max_rows:
            break
    return out


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False))
            fh.write("\n")
            count += 1
    return count


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def build_input_text(*, speaker_role: str | None, section_type: str | None, text: str) -> str:
    role = normalize_text(speaker_role or "unknown").lower() or "unknown"
    section = normalize_text(section_type or "other").lower() or "other"
    body = normalize_text(text)
    return f"[ROLE={role}] [SECTION={section}] {body}".strip()


def metric_band_key(metric: str) -> str:
    return f"{metric}_band"


def metric_score_key(metric: str) -> str:
    return f"{metric}_score"


def target_metric_band_key(metric: str) -> str:
    return f"target_{metric}_band"


def target_metric_score_key(metric: str) -> str:
    return f"target_{metric}_score"


def get_teacher_label(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("teacher_label")
    return payload if isinstance(payload, dict) else {}


def get_metric_band(row: dict[str, Any], metric: str) -> str | None:
    direct = row.get(target_metric_band_key(metric))
    if isinstance(direct, str) and direct in BAND_TO_ID:
        return direct
    teacher = get_teacher_label(row)
    nested = teacher.get(metric_band_key(metric))
    if isinstance(nested, str) and nested in BAND_TO_ID:
        return nested
    return None


def get_metric_score(row: dict[str, Any], metric: str) -> float | None:
    direct = row.get(target_metric_score_key(metric))
    if isinstance(direct, (int, float)):
        return float(direct)
    teacher = get_teacher_label(row)
    nested = teacher.get(metric_score_key(metric))
    if isinstance(nested, (int, float)):
        return float(nested)
    return None


def get_teacher_confidence(row: dict[str, Any]) -> float | None:
    teacher = get_teacher_label(row)
    value = teacher.get("teacher_confidence")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def get_dataset_quality_score(row: dict[str, Any]) -> float | None:
    teacher = get_teacher_label(row)
    value = teacher.get("dataset_quality_score")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def infer_group_key(row: dict[str, Any]) -> str:
    transcript_id = normalize_text(str(row.get("transcript_id") or ""))
    if transcript_id:
        return transcript_id
    ticker = normalize_text(str(row.get("ticker") or ""))
    quarter = normalize_text(str(row.get("quarter") or ""))
    if ticker and quarter:
        return f"{ticker}::{quarter}"
    if ticker:
        return f"{ticker}::unknown"
    sample_id = normalize_text(str(row.get("sample_id") or ""))
    return sample_id or "unknown_group"


def looks_like_admin_or_junk(row: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    text = normalize_text(str(row.get("text") or ""))
    if not text or len(text) < 20:
        reasons.append("malformed_or_too_short_text")
    if bool(row.get("is_operator_or_host_like")):
        reasons.append("operator_or_host_like")
    if bool(row.get("is_short_block")) and _ADMIN_HINT_RE.search(text):
        reasons.append("short_admin_block")
    if bool(row.get("should_skip_labeling")):
        reasons.append("teacher_pipeline_skip")
    return bool(reasons), reasons


def split_group_keys(
    *,
    group_to_row_count: dict[str, int],
    seed: int,
    train_ratio: float = 0.8,
    validation_ratio: float = 0.1,
    test_ratio: float = 0.1,
) -> dict[str, str]:
    if not group_to_row_count:
        return {}

    ratios = [train_ratio, validation_ratio, test_ratio]
    if any(r < 0 for r in ratios):
        raise ValueError("Split ratios must be non-negative.")
    total_ratio = sum(ratios)
    if total_ratio <= 0:
        raise ValueError("Split ratios must sum to > 0.")

    normalized = [r / total_ratio for r in ratios]
    group_keys = list(group_to_row_count.keys())
    rng = random.Random(seed)
    rng.shuffle(group_keys)

    total_rows = sum(group_to_row_count.values())
    train_target = int(total_rows * normalized[0])
    validation_target = int(total_rows * normalized[1])

    out: dict[str, str] = {}
    running_train = 0
    running_validation = 0
    for key in group_keys:
        count = group_to_row_count[key]
        if running_train < train_target:
            out[key] = "train"
            running_train += count
        elif running_validation < validation_target:
            out[key] = "validation"
            running_validation += count
        else:
            out[key] = "test"

    # Ensure split non-emptiness where possible.
    counts_by_split = Counter(out.values())
    needed = [name for name in ("train", "validation", "test") if counts_by_split.get(name, 0) == 0]
    if needed and len(group_keys) >= 3:
        # Move one group from the largest split to each missing split.
        for missing in needed:
            largest = max(("train", "validation", "test"), key=lambda s: counts_by_split.get(s, 0))
            if counts_by_split.get(largest, 0) <= 1:
                continue
            donor = next((g for g in group_keys if out[g] == largest), None)
            if donor is None:
                continue
            out[donor] = missing
            counts_by_split[largest] -= 1
            counts_by_split[missing] += 1

    return out


def compute_classification_metrics(
    *,
    y_true: list[int],
    y_pred: list[int],
    labels: tuple[str, ...] = BAND_LABELS,
) -> dict[str, Any]:
    if len(y_true) != len(y_pred):
        raise ValueError("y_true and y_pred length mismatch.")

    num_labels = len(labels)
    confusion = [[0 for _ in range(num_labels)] for _ in range(num_labels)]
    for truth, pred in zip(y_true, y_pred):
        if 0 <= truth < num_labels and 0 <= pred < num_labels:
            confusion[truth][pred] += 1

    total = len(y_true)
    correct = sum(confusion[idx][idx] for idx in range(num_labels))
    accuracy = (correct / total) if total else 0.0

    per_class: dict[str, dict[str, float]] = {}
    f1_values: list[float] = []
    for idx, label in enumerate(labels):
        tp = confusion[idx][idx]
        fp = sum(confusion[row][idx] for row in range(num_labels) if row != idx)
        fn = sum(confusion[idx][col] for col in range(num_labels) if col != idx)
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        support = sum(confusion[idx])
        per_class[label] = {
            "precision": precision,
            "recall": recall,
            "f1": f1,
            "support": support,
        }
        f1_values.append(f1)

    macro_f1 = (sum(f1_values) / len(f1_values)) if f1_values else 0.0
    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": {
            "labels": list(labels),
            "matrix": confusion,
        },
        "total_examples": total,
    }

