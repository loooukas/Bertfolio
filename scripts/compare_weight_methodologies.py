#!/usr/bin/env python3
"""Compare fixed score-weight methodologies against calibrated stage models."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from score_calibration_utils import (
    ProgressBar,
    classification_metrics,
    ensure_dir,
    regression_metrics,
    safe_float,
    write_json,
)


DEFAULT_PROFILES = [
    "blend_43_5_15_10:43,5,15,10",
    "blend_40_35_15_10:40,35,15,10",
    "blend_100_0_0_0:100,0,0,0",
]


@dataclass
class WeightProfile:
    name: str
    transcript: float
    fundamentals: float
    news: float
    social: float

    @property
    def total(self) -> float:
        return float(self.transcript + self.fundamentals + self.news + self.social)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare stage model vs fixed top-level weight methodologies.")
    parser.add_argument("--input", required=True, help="Prepared calibration dataset CSV.")
    parser.add_argument("--coefficients", required=True, help="Calibration coefficients.json path.")
    parser.add_argument("--output-dir", default="output/score_calibration/method_compare")
    parser.add_argument("--target-mode", choices=["binary", "continuous"], default="binary")
    parser.add_argument("--target-column", default="target")
    parser.add_argument("--split-column", default="split")
    parser.add_argument("--binary-threshold-metric", choices=["macro_f1", "accuracy", "precision", "recall"], default="macro_f1")
    parser.add_argument("--binary-threshold-grid-size", type=int, default=201)
    parser.add_argument(
        "--profile",
        action="append",
        default=[],
        help="Repeated profile spec: name:t,f,n,s (example: blend_43_5_15_10:43,5,15,10).",
    )
    parser.add_argument("--no-progress", action="store_true", default=False)
    return parser.parse_args(argv)


def _load_table(path: Path) -> pd.DataFrame:
    if path.suffix.lower() != ".csv":
        raise RuntimeError(f"Only CSV input is currently supported: {path}")
    return pd.read_csv(path)


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return payload


def _normalize_split(raw: pd.Series) -> pd.Series:
    mapping = {"train": "train", "validation": "validation", "val": "validation", "test": "test"}
    out = raw.astype(str).str.strip().str.lower().map(mapping)
    return out


def _parse_profiles(raw_specs: list[str]) -> list[WeightProfile]:
    specs = list(raw_specs) if raw_specs else list(DEFAULT_PROFILES)
    out: list[WeightProfile] = []
    for raw in specs:
        text = str(raw).strip()
        if ":" not in text:
            raise RuntimeError(f"Invalid --profile spec (missing ':'): {raw}")
        name, payload = text.split(":", 1)
        values = [item.strip() for item in payload.split(",")]
        if len(values) != 4:
            raise RuntimeError(f"Invalid --profile spec (need 4 weights): {raw}")
        weights = [float(item) for item in values]
        profile = WeightProfile(
            name=name.strip(),
            transcript=weights[0],
            fundamentals=weights[1],
            news=weights[2],
            social=weights[3],
        )
        if profile.total <= 0:
            raise RuntimeError(f"Profile weights must sum to > 0: {raw}")
        out.append(profile)
    return out


def _apply_model(frame: pd.DataFrame, model_payload: dict[str, Any], *, binary_link: bool) -> np.ndarray:
    features = list(model_payload.get("features") or [])
    means = dict(model_payload.get("means") or {})
    stds = dict(model_payload.get("stds") or {})
    standardize = bool(model_payload.get("standardize", False))
    intercept = float(model_payload.get("intercept", 0.0))
    coef_map = dict(model_payload.get("coefficients") or {})
    coefs = np.asarray([float(coef_map.get(col, 0.0)) for col in features], dtype=float)

    cols: list[np.ndarray] = []
    for col in features:
        mean_value = float(means.get(col, 0.0))
        std_value = float(stds.get(col, 1.0))
        if std_value == 0:
            std_value = 1.0
        series = pd.to_numeric(frame[col], errors="coerce") if col in frame.columns else pd.Series(np.nan, index=frame.index)
        arr = series.fillna(mean_value).to_numpy(dtype=float)
        if standardize:
            arr = (arr - mean_value) / std_value
        cols.append(arr)

    X = np.column_stack(cols) if cols else np.zeros((len(frame), 0), dtype=float)
    score = (X @ coefs) + intercept
    if binary_link:
        logits = np.clip(score, -35.0, 35.0)
        return 1.0 / (1.0 + np.exp(-logits))
    return score


def _tune_binary_threshold(
    *,
    y_true: np.ndarray,
    y_score: np.ndarray,
    metric_name: str,
    grid_size: int,
) -> float:
    thresholds = np.linspace(0.05, 0.95, num=max(3, int(grid_size)), dtype=float)
    best_threshold = 0.5
    best_metric = -1.0
    best_accuracy = -1.0
    for threshold in thresholds:
        y_label = (y_score >= float(threshold)).astype(int)
        metrics = classification_metrics(y_true=y_true.astype(int), y_pred_label=y_label, y_pred_score=y_score)
        metric_value = safe_float(metrics.get(metric_name))
        accuracy_value = safe_float(metrics.get("accuracy"))
        if metric_value is None:
            continue
        if accuracy_value is None:
            accuracy_value = -1.0
        if (
            metric_value > best_metric
            or (metric_value == best_metric and accuracy_value > best_accuracy)
            or (
                metric_value == best_metric
                and accuracy_value == best_accuracy
                and abs(float(threshold) - 0.5) < abs(best_threshold - 0.5)
            )
        ):
            best_metric = float(metric_value)
            best_accuracy = float(accuracy_value)
            best_threshold = float(threshold)
    return float(best_threshold)


def _score_metrics(
    *,
    target_mode: str,
    y_true: np.ndarray,
    y_score: np.ndarray,
    threshold: float,
) -> dict[str, Optional[float]]:
    if target_mode == "binary":
        y_label = (y_score >= float(threshold)).astype(int)
        return classification_metrics(y_true=y_true.astype(int), y_pred_label=y_label, y_pred_score=y_score)
    return regression_metrics(y_true=y_true, y_pred=y_score)


def _blend_score(
    profile: WeightProfile,
    *,
    transcript_score: np.ndarray,
    fundamentals_signal: np.ndarray,
    news_signal: np.ndarray,
    social_signal: np.ndarray,
) -> np.ndarray:
    denom = profile.total
    return (
        (profile.transcript * transcript_score)
        + (profile.fundamentals * fundamentals_signal)
        + (profile.news * news_signal)
        + (profile.social * social_signal)
    ) / denom


def _sort_rows(rows: list[dict[str, Any]], target_mode: str) -> list[dict[str, Any]]:
    if target_mode == "binary":
        return sorted(
            rows,
            key=lambda row: (
                -(safe_float((row.get("test") or {}).get("macro_f1")) or -999.0),
                -(safe_float((row.get("test") or {}).get("accuracy")) or -999.0),
                str(row.get("name", "")),
            ),
        )
    return sorted(
        rows,
        key=lambda row: (
            -(safe_float((row.get("test") or {}).get("spearman")) or -999.0),
            -(safe_float((row.get("test") or {}).get("pearson")) or -999.0),
            str(row.get("name", "")),
        ),
    )


def _numeric_column(frame: pd.DataFrame, column: str) -> np.ndarray:
    if column in frame.columns:
        series = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
        return series.to_numpy(dtype=float)
    return np.zeros(len(frame), dtype=float)


def _metric_text(value: Any) -> str:
    parsed = safe_float(value)
    return "n/a" if parsed is None else f"{parsed:.4f}"


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    input_path = Path(args.input)
    coefficients_path = Path(args.coefficients)
    out_dir = Path(args.output_dir)

    if not input_path.exists():
        raise RuntimeError(f"Input dataset not found: {input_path}")
    if not coefficients_path.exists():
        raise RuntimeError(f"Coefficients file not found: {coefficients_path}")

    frame = _load_table(input_path)
    coefficients = _load_json(coefficients_path)

    split_col = str(args.split_column)
    target_col = str(args.target_column)
    if split_col not in frame.columns:
        raise RuntimeError(f"Missing split column: {split_col}")
    if target_col not in frame.columns:
        raise RuntimeError(f"Missing target column: {target_col}")

    frame = frame.copy()
    frame[split_col] = _normalize_split(frame[split_col])
    frame = frame.loc[frame[split_col].isin({"train", "validation", "test"})].reset_index(drop=True)
    if frame.empty:
        raise RuntimeError("No usable rows after split normalization.")

    val_mask = frame[split_col] == "validation"
    test_mask = frame[split_col] == "test"
    if int(val_mask.sum()) == 0 or int(test_mask.sum()) == 0:
        raise RuntimeError("Need both validation and test rows for methodology comparison.")

    target = pd.to_numeric(frame[target_col], errors="coerce")
    frame = frame.loc[target.notna()].copy()
    target = target.loc[target.notna()].to_numpy(dtype=float)
    val_mask = frame[split_col] == "validation"
    test_mask = frame[split_col] == "test"
    y_val = target[val_mask.to_numpy()]
    y_test = target[test_mask.to_numpy()]
    if args.target_mode == "binary":
        y_val = y_val.astype(int)
        y_test = y_test.astype(int)

    stage1_payload = dict(coefficients.get("stage1") or {})
    direct_payload = dict(coefficients.get("direct") or {})
    if not stage1_payload:
        raise RuntimeError("Missing `stage1` section in coefficients JSON.")

    stage1_score = _apply_model(frame, stage1_payload, binary_link=(args.target_mode == "binary"))
    direct_score = (
        _apply_model(frame, direct_payload, binary_link=(args.target_mode == "binary"))
        if direct_payload
        else None
    )
    fundamentals_signal = _numeric_column(frame, "fundamentals_signal")
    news_signal = _numeric_column(frame, "news_signal")
    social_signal = _numeric_column(frame, "social_signal")

    profiles = _parse_profiles(list(args.profile))

    methods: list[tuple[str, np.ndarray, Optional[dict[str, float]]]] = [
        ("model_stage1", stage1_score, None),
    ]
    if direct_score is not None:
        methods.append(("model_direct", direct_score, None))
    for profile in profiles:
        score = _blend_score(
            profile,
            transcript_score=stage1_score,
            fundamentals_signal=fundamentals_signal,
            news_signal=news_signal,
            social_signal=social_signal,
        )
        methods.append(
            (
                f"blend:{profile.name}",
                score,
                {
                    "transcript": profile.transcript,
                    "fundamentals": profile.fundamentals,
                    "news": profile.news,
                    "social": profile.social,
                },
            )
        )

    progress = ProgressBar(total=len(methods), label="Compare Methods", enabled=(not args.no_progress))
    rows: list[dict[str, Any]] = []
    for name, score_all, weights in methods:
        val_score = score_all[val_mask.to_numpy()]
        test_score = score_all[test_mask.to_numpy()]
        if args.target_mode == "binary":
            threshold = _tune_binary_threshold(
                y_true=y_val.astype(int),
                y_score=val_score,
                metric_name=str(args.binary_threshold_metric),
                grid_size=int(args.binary_threshold_grid_size),
            )
        else:
            threshold = 0.0
        val_metrics = _score_metrics(
            target_mode=str(args.target_mode),
            y_true=y_val,
            y_score=val_score,
            threshold=threshold,
        )
        test_metrics = _score_metrics(
            target_mode=str(args.target_mode),
            y_true=y_test,
            y_score=test_score,
            threshold=threshold,
        )
        rows.append(
            {
                "name": name,
                "threshold": float(threshold),
                "weights": weights,
                "validation": val_metrics,
                "test": test_metrics,
            }
        )
        progress.update()
    progress.close()

    sorted_rows = _sort_rows(
        [
            {
                "name": row["name"],
                "threshold": row["threshold"],
                "weights": row["weights"],
                "validation": row["validation"],
                "test": row["test"],
            }
            for row in rows
        ],
        str(args.target_mode),
    )

    ensure_dir(out_dir)
    comparison_path = out_dir / "methodology_comparison.json"
    summary_path = out_dir / "methodology_comparison.md"
    write_json(
        comparison_path,
        {
            "input": str(input_path),
            "coefficients": str(coefficients_path),
            "target_mode": str(args.target_mode),
            "target_column": target_col,
            "split_counts": frame[split_col].value_counts().to_dict(),
            "rows": sorted_rows,
        },
    )

    lines = [
        "# Methodology Comparison",
        "",
        f"- target_mode: `{args.target_mode}`",
        f"- target_column: `{target_col}`",
        f"- validation_rows: `{int(val_mask.sum())}`",
        f"- test_rows: `{int(test_mask.sum())}`",
        "",
        "## Ranked Results",
        "",
    ]
    for row in sorted_rows:
        test_metrics = row["test"] or {}
        val_metrics = row["validation"] or {}
        if args.target_mode == "binary":
            lines.append(
                (
                    f"- `{row['name']}`: "
                    f"test_accuracy={_metric_text(test_metrics.get('accuracy'))}, "
                    f"test_macro_f1={_metric_text(test_metrics.get('macro_f1'))}, "
                    f"test_roc_auc={_metric_text(test_metrics.get('roc_auc'))}, "
                    f"val_macro_f1={_metric_text(val_metrics.get('macro_f1'))}, "
                    f"threshold={float(row['threshold']):.4f}"
                )
            )
        else:
            lines.append(
                (
                    f"- `{row['name']}`: "
                    f"test_spearman={_metric_text(test_metrics.get('spearman'))}, "
                    f"test_pearson={_metric_text(test_metrics.get('pearson'))}, "
                    f"test_rmse={_metric_text(test_metrics.get('rmse'))}"
                )
            )
    summary_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[compare] Wrote comparison: {comparison_path}")
    print(f"[compare] Wrote summary: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
