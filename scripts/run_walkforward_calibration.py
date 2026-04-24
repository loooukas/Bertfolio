#!/usr/bin/env python3
"""Run expanding-window walk-forward calibration across chronological folds."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.score_calibration_utils import ProgressBar, ensure_dir, parse_date, safe_float, write_json

TARGET_HORIZON_CHOICES = [1, 3, 5, 21, 63, 126]


@dataclass
class FoldWindow:
    fold_index: int
    train_end: int
    val_end: int
    test_end: int

    @property
    def train_size(self) -> int:
        return self.train_end

    @property
    def val_size(self) -> int:
        return self.val_end - self.train_end

    @property
    def test_size(self) -> int:
        return self.test_end - self.val_end


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Walk-forward calibration over expanding chronological windows.")
    parser.add_argument("--input", required=True, help="Prepared calibration dataset CSV/JSON/JSONL.")
    parser.add_argument("--output-dir", required=True, help="Output directory for fold artifacts and summary.")
    parser.add_argument("--target-mode", choices=["continuous", "binary"], default="binary")
    parser.add_argument(
        "--binary-rank-metric",
        choices=["accuracy", "macro_f1", "roc_auc"],
        default="accuracy",
        help="Primary aggregate ranking metric for binary mode.",
    )
    parser.add_argument("--target-horizon", type=int, choices=TARGET_HORIZON_CHOICES, default=126)
    parser.add_argument("--target-column", default="target")
    parser.add_argument("--event-date-column", default="event_date")
    parser.add_argument("--split-column", default="split")
    parser.add_argument("--min-train-size", type=int, default=36)
    parser.add_argument("--val-size", type=int, default=8)
    parser.add_argument("--test-size", type=int, default=8)
    parser.add_argument("--max-folds", type=int, default=0, help="0 means run all possible folds.")
    parser.add_argument("--min-per-split", type=int, default=8)
    parser.add_argument("--ridge-alpha", type=float, default=1.0)
    parser.add_argument("--logistic-alpha", type=float, default=1.0)
    parser.add_argument("--logistic-learning-rate", type=float, default=0.05)
    parser.add_argument("--logistic-max-iter", type=int, default=5000)
    parser.add_argument("--logistic-tol", type=float, default=1e-6)
    parser.add_argument("--no-progress", action="store_true", default=False)
    return parser.parse_args(argv)


def _load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".jsonl":
        return pd.read_json(path, orient="records", lines=True)
    raise RuntimeError(f"Unsupported input format: {path}")


def _target_column_from_horizon(horizon: int, mode: str) -> str:
    return f"binary_abnormal_up_{horizon}d" if mode == "binary" else f"abnormal_return_{horizon}d"


def _coerce_target(frame: pd.DataFrame, *, mode: str, target_col: str) -> pd.DataFrame:
    data = frame.copy()
    if mode == "binary":
        data[target_col] = data[target_col].apply(lambda v: int(float(v)) if pd.notna(v) else np.nan)
    else:
        data[target_col] = pd.to_numeric(data[target_col], errors="coerce")
    data = data.loc[data[target_col].notna()].copy()
    return data


def _ensure_sorted_by_date(frame: pd.DataFrame, event_date_col: str) -> pd.DataFrame:
    if event_date_col not in frame.columns:
        raise RuntimeError(f"Missing event date column: {event_date_col}")
    parsed = frame[event_date_col].apply(parse_date)
    keep = parsed.notna()
    ordered = frame.loc[keep].copy()
    ordered["_event_date_parsed"] = parsed[keep].values
    ordered.sort_values("_event_date_parsed", inplace=True)
    ordered[event_date_col] = ordered["_event_date_parsed"].apply(lambda d: d.strftime("%Y-%m-%d"))
    ordered.drop(columns=["_event_date_parsed"], inplace=True)
    ordered.reset_index(drop=True, inplace=True)
    return ordered


def _build_folds(
    *,
    n_rows: int,
    min_train_size: int,
    val_size: int,
    test_size: int,
    max_folds: int,
) -> list[FoldWindow]:
    if min_train_size <= 0 or val_size <= 0 or test_size <= 0:
        raise RuntimeError("min-train-size, val-size, and test-size must all be positive.")
    if n_rows < (min_train_size + val_size + test_size):
        raise RuntimeError(
            f"Not enough rows ({n_rows}) for requested fold geometry "
            f"(min_train={min_train_size}, val={val_size}, test={test_size})."
        )

    folds: list[FoldWindow] = []
    train_end = min_train_size
    fold_idx = 1
    while True:
        val_end = train_end + val_size
        test_end = val_end + test_size
        if test_end > n_rows:
            break
        folds.append(FoldWindow(fold_index=fold_idx, train_end=train_end, val_end=val_end, test_end=test_end))
        fold_idx += 1
        train_end += test_size
        if max_folds > 0 and len(folds) >= max_folds:
            break

    if not folds:
        raise RuntimeError("No valid folds generated. Lower split sizes or min_train_size.")
    return folds


def _aggregate_metric_dicts(rows: list[dict[str, Any]]) -> dict[str, Optional[float]]:
    if not rows:
        return {}
    keys = sorted({k for row in rows for k in row.keys() if k != "name"})
    out: dict[str, Optional[float]] = {}
    for key in keys:
        values: list[float] = []
        for row in rows:
            value = safe_float(row.get(key))
            if value is not None and np.isfinite(value):
                values.append(float(value))
        out[f"{key}_mean"] = float(np.mean(values)) if values else None
        out[f"{key}_std"] = float(np.std(values, ddof=0)) if values else None
    return out


def _sort_aggregate_rows(rows: list[dict[str, Any]], target_mode: str, binary_rank_metric: str) -> list[dict[str, Any]]:
    if target_mode == "binary":
        primary = f"{str(binary_rank_metric)}_mean"
        secondary = "accuracy_mean" if binary_rank_metric != "accuracy" else "macro_f1_mean"
        tertiary = "roc_auc_mean" if binary_rank_metric != "roc_auc" else "macro_f1_mean"
        return sorted(
            rows,
            key=lambda row: (
                -(safe_float(row.get(primary)) or -999.0),
                -(safe_float(row.get(secondary)) or -999.0),
                -(safe_float(row.get(tertiary)) or -999.0),
            ),
        )
    return sorted(
        rows,
        key=lambda row: (
            safe_float(row.get("mae_mean")) if safe_float(row.get("mae_mean")) is not None else 1e12,
            safe_float(row.get("rmse_mean")) if safe_float(row.get("rmse_mean")) is not None else 1e12,
            -(safe_float(row.get("spearman_mean")) or -999.0),
        ),
    )


def _invoke_calibration(
    *,
    fold_input: Path,
    fold_out: Path,
    args: argparse.Namespace,
    target_col: str,
) -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "calibrate_score_weights.py"),
        "--input",
        str(fold_input),
        "--output-dir",
        str(fold_out),
        "--target-mode",
        str(args.target_mode),
        "--target-horizon",
        str(args.target_horizon),
        "--target-column",
        str(target_col),
        "--split-column",
        str(args.split_column),
        "--event-date-column",
        str(args.event_date_column),
        "--min-per-split",
        str(args.min_per_split),
        "--ridge-alpha",
        str(args.ridge_alpha),
        "--logistic-alpha",
        str(args.logistic_alpha),
        "--logistic-learning-rate",
        str(args.logistic_learning_rate),
        "--logistic-max-iter",
        str(args.logistic_max_iter),
        "--logistic-tol",
        str(args.logistic_tol),
    ]
    if args.no_progress:
        cmd.append("--no-progress")
    subprocess.run(cmd, check=True)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    input_path = Path(args.input)
    if not input_path.exists():
        raise RuntimeError(f"Input dataset not found: {input_path}")

    if not args.no_progress:
        print("[walkforward] Step 1/5: loading and ordering dataset...")
    frame = _load_table(input_path)
    if frame.empty:
        raise RuntimeError("Input dataset is empty.")

    requested_target = str(args.target_column)
    fallback_target = _target_column_from_horizon(args.target_horizon, args.target_mode)
    if requested_target in frame.columns:
        target_col = requested_target
    elif fallback_target in frame.columns:
        target_col = fallback_target
    else:
        raise RuntimeError(f"Target column not found. Tried {requested_target} and fallback {fallback_target}.")

    frame = _coerce_target(frame, mode=args.target_mode, target_col=target_col)
    frame = _ensure_sorted_by_date(frame, str(args.event_date_column))
    n_rows = len(frame)
    if n_rows == 0:
        raise RuntimeError("No rows remain after filtering missing target/date.")

    if not args.no_progress:
        print("[walkforward] Step 2/5: generating expanding folds...")
    folds = _build_folds(
        n_rows=n_rows,
        min_train_size=int(args.min_train_size),
        val_size=int(args.val_size),
        test_size=int(args.test_size),
        max_folds=int(args.max_folds),
    )

    out_dir = Path(args.output_dir)
    ensure_dir(out_dir)
    folds_dir = out_dir / "folds"
    ensure_dir(folds_dir)

    if not args.no_progress:
        print("[walkforward] Step 3/5: running per-fold calibration...")
    fold_bar = ProgressBar(total=len(folds), label="WalkForward Folds", enabled=not args.no_progress)
    fold_records: list[dict[str, Any]] = []
    model_metric_map: dict[str, list[dict[str, Any]]] = {}
    baseline_metric_map: dict[str, list[dict[str, Any]]] = {}

    for fold in folds:
        fold_dir = folds_dir / f"fold_{fold.fold_index:02d}"
        ensure_dir(fold_dir)

        fold_frame = frame.iloc[: fold.test_end].copy()
        split = np.array(["train"] * len(fold_frame), dtype=object)
        split[fold.train_end : fold.val_end] = "validation"
        split[fold.val_end : fold.test_end] = "test"
        fold_frame[str(args.split_column)] = split.tolist()

        fold_input = fold_dir / "prepared_fold.csv"
        fold_out = fold_dir / "calibration_run"
        fold_frame.to_csv(fold_input, index=False)

        _invoke_calibration(
            fold_input=fold_input,
            fold_out=fold_out,
            args=args,
            target_col=target_col,
        )

        metrics_payload = json.loads((fold_out / "metrics.json").read_text(encoding="utf-8"))
        comparison_payload = json.loads((fold_out / "comparison_table.json").read_text(encoding="utf-8"))
        coeffs_payload = json.loads((fold_out / "coefficients.json").read_text(encoding="utf-8"))

        for model_name, bucket in (metrics_payload.get("models") or {}).items():
            test_metrics = dict(bucket.get("test") or {})
            test_metrics["name"] = f"model:{model_name}"
            model_metric_map.setdefault(model_name, []).append(test_metrics)
        for base_name, bucket in (metrics_payload.get("baselines") or {}).items():
            test_metrics = dict(bucket.get("test") or {})
            test_metrics["name"] = f"baseline:{base_name}"
            baseline_metric_map.setdefault(base_name, []).append(test_metrics)

        fold_records.append(
            {
                "fold_index": fold.fold_index,
                "rows_total_used": int(fold.test_end),
                "split_counts": {
                    "train": int(fold.train_size),
                    "validation": int(fold.val_size),
                    "test": int(fold.test_size),
                },
                "date_range": {
                    "train_start": str(fold_frame.iloc[0][args.event_date_column]),
                    "train_end": str(fold_frame.iloc[fold.train_end - 1][args.event_date_column]),
                    "validation_start": str(fold_frame.iloc[fold.train_end][args.event_date_column]),
                    "validation_end": str(fold_frame.iloc[fold.val_end - 1][args.event_date_column]),
                    "test_start": str(fold_frame.iloc[fold.val_end][args.event_date_column]),
                    "test_end": str(fold_frame.iloc[fold.test_end - 1][args.event_date_column]),
                },
                "metrics_path": str((fold_out / "metrics.json").resolve()),
                "comparison_table_path": str((fold_out / "comparison_table.json").resolve()),
                "coefficients_path": str((fold_out / "coefficients.json").resolve()),
                "stage2_coefficients": (coeffs_payload.get("stage2") or {}).get("coefficients", {}),
                "top_test_row": comparison_payload[0] if isinstance(comparison_payload, list) and comparison_payload else {},
            }
        )
        fold_bar.update(1)
    fold_bar.close()

    if not args.no_progress:
        print("[walkforward] Step 4/5: aggregating fold metrics...")
    aggregate_rows: list[dict[str, Any]] = []
    for model_name, records in model_metric_map.items():
        aggregate_rows.append(
            {
                "name": f"model:{model_name}",
                "folds": len(records),
                **_aggregate_metric_dicts(records),
            }
        )
    for base_name, records in baseline_metric_map.items():
        aggregate_rows.append(
            {
                "name": f"baseline:{base_name}",
                "folds": len(records),
                **_aggregate_metric_dicts(records),
            }
        )
    aggregate_rows = _sort_aggregate_rows(aggregate_rows, args.target_mode, str(args.binary_rank_metric))

    summary = {
        "target_mode": args.target_mode,
        "binary_rank_metric": str(args.binary_rank_metric) if args.target_mode == "binary" else None,
        "target_horizon": int(args.target_horizon),
        "target_column": target_col,
        "input_rows_after_filtering": int(n_rows),
        "fold_count": int(len(folds)),
        "fold_geometry": {
            "min_train_size": int(args.min_train_size),
            "val_size": int(args.val_size),
            "test_size": int(args.test_size),
            "max_folds": int(args.max_folds),
        },
        "best_aggregate_row": aggregate_rows[0] if aggregate_rows else {},
        "aggregate_comparison": aggregate_rows,
    }

    if not args.no_progress:
        print("[walkforward] Step 5/5: writing outputs...")
    write_json(out_dir / "walkforward_folds.json", fold_records)
    write_json(out_dir / "walkforward_comparison_table.json", aggregate_rows)
    write_json(out_dir / "walkforward_summary.json", summary)

    print(f"[walkforward] Wrote folds: {out_dir / 'walkforward_folds.json'}")
    print(f"[walkforward] Wrote aggregate comparison: {out_dir / 'walkforward_comparison_table.json'}")
    print(f"[walkforward] Wrote summary: {out_dir / 'walkforward_summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
