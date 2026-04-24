#!/usr/bin/env python3
"""Audit score-calibration event table failures and feature coverage."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.score_calibration_utils import read_structured_records, write_json
from scripts.score_calibration_utils import fetch_close_series_with_diagnostics, parse_date


FEATURE_COLUMNS = [
    "fundamentals_signal",
    "news_signal",
    "social_signal",
    "current_handset_overall_score",
    "current_handset_transcript_score",
]

COMPONENT_SIGNAL_COLUMNS = ["fundamentals_signal", "news_signal", "social_signal"]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit event table failures and missing-feature causes.")
    parser.add_argument("--input", default="output/score_calibration/historical_event_table.csv")
    parser.add_argument("--failures-json", default="output/score_calibration/event_table_failures.json")
    parser.add_argument("--horizon", type=int, choices=[1, 3, 5, 21, 63, 126], default=3)
    parser.add_argument(
        "--probe-missing-tickers",
        action="store_true",
        default=False,
        help="Actively re-probe missing-target tickers with yfinance diagnostics if failure JSON is missing/incomplete.",
    )
    parser.add_argument("--output", default="output/score_calibration/event_table_audit.json")
    return parser.parse_args(argv)


def _load_failures(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    rows = read_structured_records(path)
    if not rows:
        return {}
    if len(rows) == 1 and isinstance(rows[0], dict):
        return rows[0]
    # read_structured_records for json returns [payload]
    return rows[0] if isinstance(rows[0], dict) else {}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    in_path = Path(args.input)
    if not in_path.exists():
        raise RuntimeError(f"Event table input not found: {in_path}")

    df = pd.read_csv(in_path)
    target_col = f"abnormal_return_{int(args.horizon)}d"
    if target_col not in df.columns:
        raise RuntimeError(f"Target column missing in event table: {target_col}")

    missing_target = df[df[target_col].isna()].copy()
    present_target = df[df[target_col].notna()].copy()

    parsed_dates = df["event_date"].apply(parse_date) if "event_date" in df.columns else pd.Series([], dtype=object)
    date_values = [d for d in parsed_dates.tolist() if d is not None]
    window_start = min(date_values) if date_values else None
    window_end = max(date_values) if date_values else None

    feature_coverage = {}
    for col in FEATURE_COLUMNS:
        if col not in df.columns:
            continue
        feature_coverage[col] = {
            "nonnull": int(df[col].notna().sum()),
            "null": int(df[col].isna().sum()),
            "nunique_nonnull": int(df[col].dropna().nunique()),
        }

    failures_payload = _load_failures(Path(args.failures_json))
    ticker_diag = failures_payload.get("ticker_price_diagnostics") if isinstance(failures_payload, dict) else {}
    ticker_diag = ticker_diag if isinstance(ticker_diag, dict) else {}
    component_diag = failures_payload.get("component_fetch_diagnostics") if isinstance(failures_payload, dict) else {}
    component_diag = component_diag if isinstance(component_diag, dict) else {}

    missing_details: list[dict[str, Any]] = []
    for ticker, group in missing_target.groupby("ticker"):
        diag = ticker_diag.get(ticker) if isinstance(ticker_diag, dict) else None
        if (
            (not isinstance(diag, dict) or not diag.get("attempts"))
            and args.probe_missing_tickers
            and window_start is not None
            and window_end is not None
        ):
            _series, diag = fetch_close_series_with_diagnostics(ticker, window_start, window_end)
        attempts = []
        if isinstance(diag, dict):
            raw_attempts = diag.get("attempts")
            if isinstance(raw_attempts, list):
                for row in raw_attempts:
                    if not isinstance(row, dict):
                        continue
                    attempts.append(
                        {
                            "candidate": row.get("candidate"),
                            "close_rows": row.get("close_rows"),
                            "frame_rows": row.get("frame_rows"),
                            "exception": row.get("exception"),
                            "stdout_head": (str(row.get("stdout") or "")[:280] or None),
                            "stderr_head": (str(row.get("stderr") or "")[:280] or None),
                        }
                    )

        missing_details.append(
            {
                "ticker": ticker,
                "missing_rows": int(len(group)),
                "sample_dates": sorted(group["event_date"].astype(str).head(5).tolist()),
                "price_diag_status": (diag.get("status") if isinstance(diag, dict) else None),
                "ticker_used": (diag.get("ticker_used") if isinstance(diag, dict) else None),
                "attempts": attempts,
            }
        )

    missing_details.sort(key=lambda row: (-row["missing_rows"], row["ticker"]))

    component_missing = df[df[COMPONENT_SIGNAL_COLUMNS].isna().all(axis=1)].copy()
    component_missing_details: list[dict[str, Any]] = []
    for ticker, group in component_missing.groupby("ticker"):
        diag = component_diag.get(ticker)
        component_missing_details.append(
            {
                "ticker": ticker,
                "missing_rows": int(len(group)),
                "component_source_values": sorted({str(v) for v in group["component_source"].dropna().tolist()})
                if "component_source" in group.columns
                else [],
                "diagnostics": diag if isinstance(diag, dict) else None,
            }
        )

    component_missing_details.sort(key=lambda row: (-row["missing_rows"], row["ticker"]))

    summary = {
        "rows_total": int(len(df)),
        "rows_with_target": int(len(present_target)),
        "rows_missing_target": int(len(missing_target)),
        "target_column": target_col,
        "unique_tickers_total": int(df["ticker"].nunique()) if "ticker" in df.columns else None,
        "unique_tickers_missing_target": int(missing_target["ticker"].nunique()) if not missing_target.empty else 0,
        "component_source_counts": df["component_source"].fillna("missing").value_counts().to_dict()
        if "component_source" in df.columns
        else {},
        "feature_coverage": feature_coverage,
        "missing_target_by_ticker": missing_target["ticker"].value_counts().to_dict() if not missing_target.empty else {},
        "missing_target_details": missing_details,
        "rows_missing_all_component_signals": int(len(component_missing)),
        "missing_component_by_ticker": component_missing["ticker"].value_counts().to_dict() if not component_missing.empty else {},
        "missing_component_details": component_missing_details,
    }

    out_path = Path(args.output)
    write_json(out_path, summary)

    print(f"[audit] rows_total={summary['rows_total']} rows_with_target={summary['rows_with_target']} rows_missing_target={summary['rows_missing_target']}")
    print(f"[audit] target_column={summary['target_column']}")
    print(f"[audit] missing tickers={summary['unique_tickers_missing_target']}")
    print(f"[audit] output={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
