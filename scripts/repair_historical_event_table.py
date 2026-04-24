#!/usr/bin/env python3
"""Repair missing/malformed rows in an existing historical event table."""

from __future__ import annotations

import argparse
from datetime import timedelta
from pathlib import Path
import sys
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finbert_site.settings import Settings
from scripts.build_historical_event_table import LiveComponentFetcher, _choose_sentiment_fn
from scripts.score_calibration_utils import (
    ProgressBar,
    compute_event_window,
    ensure_dir,
    fetch_close_series_with_diagnostics,
    parse_date,
    safe_float,
    write_json,
)


MARKET_COLUMNS = [
    "close_t_minus_1",
    "close_t",
    "close_t_plus_1",
    "close_t_plus_3",
    "close_t_plus_5",
    "stock_return_1d",
    "stock_return_3d",
    "stock_return_5d",
    "benchmark_t_minus_1",
    "benchmark_t",
    "benchmark_t_plus_1",
    "benchmark_t_plus_3",
    "benchmark_t_plus_5",
    "benchmark_return_1d",
    "benchmark_return_3d",
    "benchmark_return_5d",
    "abnormal_return_1d",
    "abnormal_return_3d",
    "abnormal_return_5d",
]

COMPONENT_COLUMNS = [
    "fundamentals_signal",
    "news_signal",
    "social_signal",
    "current_handset_overall_score",
]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Repair missing/malformed rows in historical_event_table.csv.")
    parser.add_argument("--input", default="output/score_calibration/historical_event_table.csv")
    parser.add_argument(
        "--output",
        default="output/score_calibration/historical_event_table.repaired.csv",
        help="Output repaired CSV path.",
    )
    parser.add_argument(
        "--report-output",
        default="output/score_calibration/event_table_repair_report.json",
        help="Repair report JSON path.",
    )
    parser.add_argument("--target-horizon", type=int, choices=[1, 3, 5], default=3)
    parser.add_argument(
        "--repair-market",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Repair market outcome fields using yfinance.",
    )
    parser.add_argument(
        "--market-row-filter",
        choices=["missing_target", "any_missing_market_field", "all"],
        default="missing_target",
        help="Which rows are selected for market repair.",
    )
    parser.add_argument(
        "--repair-components",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="Repair missing fundamentals/news/social snapshot signals with live fetches.",
    )
    parser.add_argument(
        "--component-row-filter",
        choices=["any_missing_component", "all"],
        default="any_missing_component",
        help="Which rows are selected for component repair.",
    )
    parser.add_argument(
        "--component-sentiment-mode",
        choices=["lexical", "finbert", "neutral"],
        default="lexical",
        help="Sentiment mode used when re-scoring social text in live component fetches.",
    )
    parser.add_argument("--benchmark-ticker", default="SPY")
    parser.add_argument(
        "--price-source",
        choices=["yfinance", "yfinance_then_alpha"],
        default="yfinance",
        help="Market price source for repair.",
    )
    parser.add_argument(
        "--event-alignment-mode",
        choices=["on_or_next_trading_day", "next_trading_day"],
        default="on_or_next_trading_day",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        default=False,
        help="Overwrite existing numeric values. Default fills only missing/malformed cells.",
    )
    parser.add_argument("--no-progress", action="store_true", default=False, help="Disable terminal progress bars.")
    return parser.parse_args(argv)


def _is_missing_or_malformed_numeric(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float):
        return not np.isfinite(value)
    if isinstance(value, (int, np.integer)):
        return False
    text = str(value).strip()
    if not text or text.lower() in {"none", "nan", "null", "-"}:
        return True
    try:
        out = float(text)
    except Exception:
        return True
    return not np.isfinite(out)


def _coerce_float_or_none(value: Any) -> Optional[float]:
    out = safe_float(value)
    if out is None:
        return None
    if not np.isfinite(float(out)):
        return None
    return float(out)


def _should_update(existing: Any, overwrite_existing: bool) -> bool:
    if overwrite_existing:
        return True
    return _is_missing_or_malformed_numeric(existing)


def _ensure_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    for col in columns:
        if col not in frame.columns:
            frame[col] = np.nan


def _market_row_mask(frame: pd.DataFrame, *, target_horizon: int, mode: str) -> pd.Series:
    target_col = f"abnormal_return_{int(target_horizon)}d"
    if target_col not in frame.columns:
        frame[target_col] = np.nan

    if mode == "all":
        return pd.Series([True] * len(frame), index=frame.index)

    if mode == "missing_target":
        return frame[target_col].apply(_is_missing_or_malformed_numeric)

    # any_missing_market_field
    mask = pd.Series([False] * len(frame), index=frame.index)
    for col in MARKET_COLUMNS:
        if col not in frame.columns:
            mask = mask | True
            continue
        mask = mask | frame[col].apply(_is_missing_or_malformed_numeric)
    return mask


def _component_row_mask(frame: pd.DataFrame, *, mode: str) -> pd.Series:
    if mode == "all":
        return pd.Series([True] * len(frame), index=frame.index)
    # any_missing_component
    mask = pd.Series([False] * len(frame), index=frame.index)
    for col in COMPONENT_COLUMNS:
        if col not in frame.columns:
            mask = mask | True
            continue
        mask = mask | frame[col].apply(_is_missing_or_malformed_numeric)
    return mask


def _apply_market_repair(
    frame: pd.DataFrame,
    row_mask: pd.Series,
    *,
    benchmark_ticker: str,
    price_source: str,
    alignment_mode: str,
    overwrite_existing: bool,
    show_progress: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = frame.copy()
    _ensure_columns(out, MARKET_COLUMNS + ["aligned_trading_date"])
    _ensure_columns(out, ["binary_abnormal_up_1d", "binary_abnormal_up_3d", "binary_abnormal_up_5d"])

    selected = out.loc[row_mask].copy()
    selected = selected.loc[selected["event_date"].apply(parse_date).notna()].copy()

    diag: dict[str, Any] = {
        "rows_selected": int(len(selected)),
        "tickers_selected": int(selected["ticker"].nunique()) if not selected.empty else 0,
        "ticker_price_diagnostics": {},
        "benchmark_price_diagnostics": {},
    }
    if selected.empty:
        return out, diag

    event_dates = [parse_date(value) for value in selected["event_date"].tolist()]
    event_dates = [value for value in event_dates if value is not None]
    if not event_dates:
        return out, diag

    start = min(event_dates) - timedelta(days=30)
    end = max(event_dates) + timedelta(days=30)

    ticker_series: dict[str, pd.Series] = {}
    tickers = sorted({str(item).upper().strip() for item in selected["ticker"].tolist() if str(item).strip()})
    fetch_bar = ProgressBar(total=len(tickers), label="Repair Prices", enabled=show_progress)
    use_alpha_fallback = str(price_source) == "yfinance_then_alpha"
    for ticker in tickers:
        series, ticker_diag = fetch_close_series_with_diagnostics(
            ticker,
            start,
            end,
            enable_alpha_fallback=use_alpha_fallback,
        )
        ticker_series[ticker] = series
        diag["ticker_price_diagnostics"][ticker] = ticker_diag
        fetch_bar.update(1)
    fetch_bar.close()

    benchmark_series, benchmark_diag = fetch_close_series_with_diagnostics(
        benchmark_ticker,
        start,
        end,
        enable_alpha_fallback=use_alpha_fallback,
    )
    diag["benchmark_price_diagnostics"] = benchmark_diag

    row_bar = ProgressBar(total=len(selected), label="Repair Outcomes", enabled=show_progress)
    for idx in selected.index.tolist():
        ticker = str(out.at[idx, "ticker"]).upper().strip()
        event_dt = parse_date(out.at[idx, "event_date"])
        if event_dt is None:
            row_bar.update(1)
            continue

        stock_window = compute_event_window(ticker_series.get(ticker, pd.Series(dtype=float)), event_dt, alignment_mode)
        bench_window = compute_event_window(benchmark_series, event_dt, alignment_mode)

        scalar_updates = {
            "aligned_trading_date": stock_window.aligned_trading_date,
            "close_t_minus_1": stock_window.close_t_minus_1,
            "close_t": stock_window.close_t,
            "close_t_plus_1": stock_window.close_t_plus_1,
            "close_t_plus_3": stock_window.close_t_plus_3,
            "close_t_plus_5": stock_window.close_t_plus_5,
            "stock_return_1d": stock_window.return_1d,
            "stock_return_3d": stock_window.return_3d,
            "stock_return_5d": stock_window.return_5d,
            "benchmark_t_minus_1": bench_window.close_t_minus_1,
            "benchmark_t": bench_window.close_t,
            "benchmark_t_plus_1": bench_window.close_t_plus_1,
            "benchmark_t_plus_3": bench_window.close_t_plus_3,
            "benchmark_t_plus_5": bench_window.close_t_plus_5,
            "benchmark_return_1d": bench_window.return_1d,
            "benchmark_return_3d": bench_window.return_3d,
            "benchmark_return_5d": bench_window.return_5d,
        }
        for key, value in scalar_updates.items():
            if key == "aligned_trading_date":
                if overwrite_existing or not str(out.at[idx, key]).strip():
                    out.at[idx, key] = value
                continue
            if _should_update(out.at[idx, key], overwrite_existing):
                out.at[idx, key] = value

        sr1 = _coerce_float_or_none(out.at[idx, "stock_return_1d"])
        sr3 = _coerce_float_or_none(out.at[idx, "stock_return_3d"])
        sr5 = _coerce_float_or_none(out.at[idx, "stock_return_5d"])
        br1 = _coerce_float_or_none(out.at[idx, "benchmark_return_1d"])
        br3 = _coerce_float_or_none(out.at[idx, "benchmark_return_3d"])
        br5 = _coerce_float_or_none(out.at[idx, "benchmark_return_5d"])

        abnormal_updates: dict[str, Optional[float]] = {
            "abnormal_return_1d": (None if sr1 is None or br1 is None else float(sr1 - br1)),
            "abnormal_return_3d": (None if sr3 is None or br3 is None else float(sr3 - br3)),
            "abnormal_return_5d": (None if sr5 is None or br5 is None else float(sr5 - br5)),
        }
        for key, value in abnormal_updates.items():
            if _should_update(out.at[idx, key], overwrite_existing):
                out.at[idx, key] = value

        for horizon in (1, 3, 5):
            abnormal_key = f"abnormal_return_{horizon}d"
            binary_key = f"binary_abnormal_up_{horizon}d"
            abnormal_value = _coerce_float_or_none(out.at[idx, abnormal_key])
            binary_value: Optional[int] = None if abnormal_value is None else int(abnormal_value > 0.0)
            if overwrite_existing or pd.isna(out.at[idx, binary_key]):
                out.at[idx, binary_key] = binary_value

        row_bar.update(1)
    row_bar.close()

    return out, diag


def _apply_component_repair(
    frame: pd.DataFrame,
    row_mask: pd.Series,
    *,
    overwrite_existing: bool,
    sentiment_mode: str,
    show_progress: bool,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    out = frame.copy()
    _ensure_columns(out, COMPONENT_COLUMNS + ["component_source"])
    _ensure_columns(out, ["news_count_snapshot", "social_count_snapshot"])
    _ensure_columns(out, ["fundamentals_revenue_qoq_growth_pct", "fundamentals_eps_qoq_growth_pct"])
    _ensure_columns(out, ["current_handset_transcript_score"])

    selected = out.loc[row_mask].copy()
    selected = selected.loc[selected["ticker"].notna()].copy()
    tickers = sorted({str(item).upper().strip() for item in selected["ticker"].tolist() if str(item).strip()})

    settings = Settings()
    sentiment_fn = _choose_sentiment_fn(sentiment_mode, settings)
    live_fetcher = LiveComponentFetcher(settings=settings, sentiment_fn=sentiment_fn)

    diag: dict[str, Any] = {
        "rows_selected": int(len(selected)),
        "tickers_selected": int(len(tickers)),
        "ticker_component_diagnostics": {},
    }
    if not tickers:
        return out, diag

    fetch_bar = ProgressBar(total=len(tickers), label="Repair Components", enabled=show_progress)
    payload_by_ticker: dict[str, dict[str, Any]] = {}
    for ticker in tickers:
        subset = selected.loc[selected["ticker"] == ticker]
        company_name = None
        if not subset.empty and "company_name" in subset.columns:
            first_name = str(subset["company_name"].iloc[0]).strip()
            company_name = first_name or None
        payload, ticker_diag = live_fetcher.fetch_with_diagnostics(ticker=ticker, company_name=company_name)
        payload_by_ticker[ticker] = payload
        diag["ticker_component_diagnostics"][ticker] = ticker_diag
        fetch_bar.update(1)
    fetch_bar.close()

    row_bar = ProgressBar(total=len(selected), label="Apply Components", enabled=show_progress)
    for idx in selected.index.tolist():
        ticker = str(out.at[idx, "ticker"]).upper().strip()
        payload = payload_by_ticker.get(ticker)
        if not payload:
            row_bar.update(1)
            continue

        component_updates = {
            "fundamentals_signal": payload.get("fundamentals_signal"),
            "news_signal": payload.get("news_signal"),
            "social_signal": payload.get("social_signal"),
            "fundamentals_revenue_qoq_growth_pct": payload.get("fundamentals_revenue_qoq_growth_pct"),
            "fundamentals_eps_qoq_growth_pct": payload.get("fundamentals_eps_qoq_growth_pct"),
            "news_count_snapshot": payload.get("news_count_snapshot"),
            "social_count_snapshot": payload.get("social_count_snapshot"),
        }
        for key, value in component_updates.items():
            if key not in out.columns:
                continue
            if _should_update(out.at[idx, key], overwrite_existing):
                out.at[idx, key] = value

        fs = _coerce_float_or_none(out.at[idx, "fundamentals_signal"])
        ns = _coerce_float_or_none(out.at[idx, "news_signal"])
        ss = _coerce_float_or_none(out.at[idx, "social_signal"])
        ts = _coerce_float_or_none(out.at[idx, "current_handset_transcript_score"])
        if ts is None:
            ts = _coerce_float_or_none(out.at[idx, "transcript_sentiment_directional_score"])
        implied_overall = None if None in {ts, fs, ns, ss} else float(ts * 0.40 + fs * 0.35 + ns * 0.15 + ss * 0.10)
        if _should_update(out.at[idx, "current_handset_overall_score"], overwrite_existing):
            out.at[idx, "current_handset_overall_score"] = implied_overall

        if overwrite_existing or not str(out.at[idx, "component_source"]).strip():
            out.at[idx, "component_source"] = str(payload.get("component_source") or "live_current_snapshot")

        row_bar.update(1)
    row_bar.close()

    return out, diag


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_path = Path(args.input)
    if not input_path.exists():
        raise RuntimeError(f"Input event table not found: {input_path}")

    print("[repair] Step 1/5: loading event table...")
    frame = pd.read_csv(input_path)
    if frame.empty:
        raise RuntimeError("Input event table is empty.")
    if "ticker" not in frame.columns or "event_date" not in frame.columns:
        raise RuntimeError("Input event table must include ticker and event_date columns.")

    before_missing_target = int(frame[f"abnormal_return_{int(args.target_horizon)}d"].apply(_is_missing_or_malformed_numeric).sum())
    before_missing_component = int(
        _component_row_mask(frame, mode="any_missing_component").sum()
    )

    market_diag: dict[str, Any] = {"skipped": True}
    component_diag: dict[str, Any] = {"skipped": True}

    out = frame.copy()

    print("[repair] Step 2/5: selecting rows...")
    if args.repair_market:
        market_mask = _market_row_mask(out, target_horizon=int(args.target_horizon), mode=args.market_row_filter)
        print(f"[repair] Market rows selected: {int(market_mask.sum())}")
        print("[repair] Step 3/5: repairing market outcomes...")
        out, market_diag = _apply_market_repair(
            out,
            market_mask,
            benchmark_ticker=str(args.benchmark_ticker).upper(),
            price_source=str(args.price_source),
            alignment_mode=str(args.event_alignment_mode),
            overwrite_existing=bool(args.overwrite_existing),
            show_progress=not args.no_progress,
        )

    if args.repair_components:
        component_mask = _component_row_mask(out, mode=args.component_row_filter)
        print(f"[repair] Component rows selected: {int(component_mask.sum())}")
        print("[repair] Step 4/5: repairing components...")
        out, component_diag = _apply_component_repair(
            out,
            component_mask,
            overwrite_existing=bool(args.overwrite_existing),
            sentiment_mode=str(args.component_sentiment_mode),
            show_progress=not args.no_progress,
        )

    print("[repair] Step 5/5: writing outputs...")
    output_path = Path(args.output)
    ensure_dir(output_path.parent)
    out.to_csv(output_path, index=False)

    after_missing_target = int(out[f"abnormal_return_{int(args.target_horizon)}d"].apply(_is_missing_or_malformed_numeric).sum())
    after_missing_component = int(_component_row_mask(out, mode="any_missing_component").sum())

    report = {
        "input": str(input_path),
        "output": str(output_path),
        "target_horizon": int(args.target_horizon),
        "before": {
            "rows": int(len(frame)),
            "missing_target_rows": before_missing_target,
            "rows_with_any_missing_component": before_missing_component,
        },
        "after": {
            "rows": int(len(out)),
            "missing_target_rows": after_missing_target,
            "rows_with_any_missing_component": after_missing_component,
        },
        "repair_market": {
            "enabled": bool(args.repair_market),
            "row_filter": args.market_row_filter,
            "price_source": str(args.price_source),
            "diagnostics": market_diag,
        },
        "repair_components": {
            "enabled": bool(args.repair_components),
            "row_filter": args.component_row_filter,
            "diagnostics": component_diag,
        },
        "assumptions": [
            "This script patches existing event-table rows in place and does not rebuild transcript rows.",
            "Market outcomes are recomputed from event_date and alignment mode against Yahoo/yfinance close data.",
            "Component repair uses current snapshot providers and is not strict event-time as-of data.",
        ],
    }
    report_path = Path(args.report_output)
    write_json(report_path, report)

    print(f"[repair] Wrote repaired table -> {output_path}")
    print(f"[repair] Wrote repair report -> {report_path}")
    print(
        "[repair] Missing target rows "
        f"{before_missing_target} -> {after_missing_target}; "
        f"missing component rows {before_missing_component} -> {after_missing_component}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
