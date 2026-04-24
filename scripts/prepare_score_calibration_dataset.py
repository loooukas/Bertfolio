#!/usr/bin/env python3
"""Prepare train/validation/test-ready calibration dataset from event table."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.score_calibration_utils import (
    chronological_split_indices,
    ensure_dir,
    parse_date,
    safe_float,
    write_json,
)

DEFAULT_OUTPUT_DIR = "output/score_calibration"

DEFAULT_FEATURE_COLUMNS = [
    "management_confidence",
    "management_directness",
    "management_outlook_strength",
    "management_specificity",
    "management_risk_intensity",
    "transcript_sentiment_directional_score",
    "fundamentals_signal",
    "news_signal",
    "social_signal",
]

DEFAULT_META_COLUMNS = [
    "ticker",
    "company_name",
    "event_date",
    "quarter_label",
    "transcript_source_url",
    "transcript_id",
    "component_source",
    "aligned_trading_date",
]



def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare score calibration dataset from historical event table.")
    parser.add_argument("--input", required=True, help="Input event table CSV/JSON/JSONL.")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--target-horizon", type=int, choices=[1, 3, 5], default=3)
    parser.add_argument("--target-mode", choices=["continuous", "binary"], default="continuous")
    parser.add_argument(
        "--feature-columns",
        help="Comma-separated feature columns. Defaults to transcript + fundamentals/news/social columns.",
    )
    parser.add_argument(
        "--metadata-columns",
        help="Comma-separated metadata columns to keep in output. Defaults to ticker/event identifiers.",
    )
    parser.add_argument("--drop-missing-target", action="store_true", default=False)
    parser.add_argument("--drop-missing-features", action="store_true", default=False)
    parser.add_argument("--min-events", type=int, default=30)
    parser.add_argument("--time-split-mode", choices=["chronological"], default="chronological")
    parser.add_argument("--train-fraction", type=float, default=0.60)
    parser.add_argument("--val-fraction", type=float, default=0.20)
    parser.add_argument("--min-per-split", type=int, default=10)
    parser.add_argument("--standardize", action="store_true", default=False)
    parser.add_argument("--no-progress", action="store_true", default=False, help="Disable terminal progress messages.")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def _target_column(horizon: int, mode: str) -> str:
    if mode == "binary":
        return f"binary_abnormal_up_{horizon}d"
    return f"abnormal_return_{horizon}d"


def _load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        payload = pd.read_json(path)
        if isinstance(payload, pd.DataFrame):
            return payload
    if suffix == ".jsonl":
        return pd.read_json(path, orient="records", lines=True)
    raise RuntimeError(f"Unsupported input format: {path}")


def _parse_list_arg(raw: str | None, default_values: list[str]) -> list[str]:
    if not raw:
        return list(default_values)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _standardize_by_train(
    frame: pd.DataFrame,
    feature_columns: list[str],
    train_mask: pd.Series,
) -> tuple[pd.DataFrame, dict[str, dict[str, float]]]:
    out = frame.copy()
    stats: dict[str, dict[str, float]] = {}

    train_frame = out.loc[train_mask]
    for col in feature_columns:
        series = pd.to_numeric(out[col], errors="coerce")
        train_series = pd.to_numeric(train_frame[col], errors="coerce")
        mean_value = float(train_series.mean()) if train_series.notna().any() else 0.0
        std_value = float(train_series.std(ddof=0)) if train_series.notna().any() else 0.0
        if std_value == 0:
            std_value = 1.0
        out[col] = (series - mean_value) / std_value
        stats[col] = {"mean": mean_value, "std": std_value}

    return out, stats


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    in_path = Path(args.input)
    if not in_path.exists():
        raise RuntimeError(f"Input file not found: {in_path}")

    feature_columns = _parse_list_arg(args.feature_columns, DEFAULT_FEATURE_COLUMNS)
    meta_columns = _parse_list_arg(args.metadata_columns, DEFAULT_META_COLUMNS)
    target_column = _target_column(args.target_horizon, args.target_mode)

    if not args.no_progress:
        print("[prepare] Step 1/5: loading input table...")
    frame = _load_table(in_path)
    if frame.empty:
        raise RuntimeError(f"Input table is empty: {in_path}")

    if "event_date" not in frame.columns:
        raise RuntimeError("Input table is missing required event_date column.")

    frame["event_date"] = frame["event_date"].astype(str)
    parsed_dates = frame["event_date"].apply(parse_date)
    date_mask = parsed_dates.notna()
    frame = frame.loc[date_mask].copy()
    frame["event_date"] = parsed_dates[date_mask].apply(lambda d: d.strftime("%Y-%m-%d"))

    if target_column not in frame.columns:
        raise RuntimeError(f"Target column not found in input: {target_column}")

    if args.target_mode == "binary":
        frame[target_column] = frame[target_column].apply(lambda value: int(float(value)) if pd.notna(value) else None)
    else:
        frame[target_column] = pd.to_numeric(frame[target_column], errors="coerce")

    if args.drop_missing_target:
        before = len(frame)
        frame = frame.loc[frame[target_column].notna()].copy()
        print(f"[prepare] Dropped missing target rows: {before - len(frame)}")

    for col in feature_columns:
        if col not in frame.columns:
            frame[col] = pd.NA
        frame[col] = pd.to_numeric(frame[col], errors="coerce")

    if args.drop_missing_features:
        before = len(frame)
        frame = frame.dropna(subset=feature_columns).copy()
        print(f"[prepare] Dropped missing feature rows: {before - len(frame)}")

    if len(frame) < int(args.min_events):
        raise RuntimeError(f"Not enough events ({len(frame)}) after filtering; required at least {args.min_events}.")

    frame = frame.sort_values(["event_date", "ticker", "transcript_id"], ascending=[True, True, True]).reset_index(drop=True)

    train_idx, val_idx, test_idx = chronological_split_indices(
        n_rows=len(frame),
        train_fraction=float(args.train_fraction),
        val_fraction=float(args.val_fraction),
        min_per_split=int(args.min_per_split),
    )

    frame["split"] = "train"
    frame.loc[val_idx, "split"] = "validation"
    frame.loc[test_idx, "split"] = "test"

    standardize_stats: dict[str, Any] | None = None
    if args.standardize:
        train_mask = frame["split"] == "train"
        frame, standardize_stats = _standardize_by_train(frame, feature_columns, train_mask)

    for col in meta_columns:
        if col not in frame.columns:
            frame[col] = pd.NA

    frame["target"] = frame[target_column]

    out_columns = []
    for col in meta_columns + ["split", "target", target_column] + feature_columns:
        if col not in out_columns:
            out_columns.append(col)

    prepared = frame[out_columns].copy()

    out_dir = Path(args.output_dir)
    ensure_dir(out_dir)

    prepared_path = out_dir / "prepared_calibration_dataset.csv"
    train_path = out_dir / "prepared_train.csv"
    val_path = out_dir / "prepared_validation.csv"
    test_path = out_dir / "prepared_test.csv"
    summary_path = out_dir / "prepared_dataset_summary.json"
    scaler_path = out_dir / "prepared_feature_scaler.json"

    prepared.to_csv(prepared_path, index=False)
    prepared.loc[prepared["split"] == "train"].to_csv(train_path, index=False)
    prepared.loc[prepared["split"] == "validation"].to_csv(val_path, index=False)
    prepared.loc[prepared["split"] == "test"].to_csv(test_path, index=False)

    summary = {
        "input": str(in_path),
        "target_mode": args.target_mode,
        "target_horizon": int(args.target_horizon),
        "target_column": target_column,
        "events_total": int(len(prepared)),
        "split_counts": prepared["split"].value_counts().to_dict(),
        "feature_columns": feature_columns,
        "metadata_columns": meta_columns,
        "missing_rate": {
            col: float(prepared[col].isna().mean())
            for col in [target_column, "target", *feature_columns]
            if col in prepared.columns
        },
        "event_date_min": str(prepared["event_date"].min()) if "event_date" in prepared.columns else None,
        "event_date_max": str(prepared["event_date"].max()) if "event_date" in prepared.columns else None,
    }
    write_json(summary_path, summary)

    if standardize_stats is not None:
        write_json(
            scaler_path,
            {
                "target_column": target_column,
                "feature_columns": feature_columns,
                "stats": standardize_stats,
            },
        )

    print(f"[prepare] Wrote prepared dataset: {prepared_path}")
    print(f"[prepare] Wrote train/validation/test splits under: {out_dir}")
    print(f"[prepare] Wrote summary: {summary_path}")
    if standardize_stats is not None:
        print(f"[prepare] Wrote scaler stats: {scaler_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
    if not args.no_progress:
        print("[prepare] Step 2/5: parsing dates and selecting target...")
    if not args.no_progress:
        print("[prepare] Step 3/5: cleaning feature columns...")
    if not args.no_progress:
        print("[prepare] Step 4/5: creating chronological split...")
    if not args.no_progress:
        print("[prepare] Step 5/5: writing output artifacts...")
