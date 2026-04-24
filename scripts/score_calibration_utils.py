#!/usr/bin/env python3
"""Shared helpers for historical event-study score calibration scripts."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
import json
import os
from pathlib import Path
import time
from contextlib import redirect_stderr, redirect_stdout
from typing import Any, Iterable, Optional, Sequence

import numpy as np
import pandas as pd
import requests
import yfinance as yf


DATE_FMT = "%Y-%m-%d"


class ProgressBar:
    """Minimal terminal progress bar without extra dependencies."""

    def __init__(self, *, total: int, label: str, enabled: bool = True, width: int = 28) -> None:
        self.total = max(0, int(total))
        self.label = str(label)
        self.enabled = bool(enabled)
        self.width = max(10, int(width))
        self.current = 0
        self.start = time.perf_counter()
        if self.enabled:
            self._render(final=False)

    def update(self, step: int = 1) -> None:
        self.current = min(self.total, self.current + max(0, int(step)))
        if self.enabled:
            self._render(final=False)

    def close(self) -> None:
        self.current = self.total
        if self.enabled:
            self._render(final=True)

    def _render(self, *, final: bool) -> None:
        if self.total <= 0:
            message = f"{self.label}: 0/0"
            end = "\n" if final else "\r"
            print(message.ljust(80), end=end, flush=True)
            return

        ratio = min(1.0, max(0.0, self.current / float(self.total)))
        filled = int(round(ratio * self.width))
        bar = "#" * filled + "-" * (self.width - filled)
        elapsed = time.perf_counter() - self.start
        message = (
            f"{self.label} [{bar}] {self.current}/{self.total} "
            f"({ratio * 100:5.1f}%) elapsed {elapsed:6.1f}s"
        )
        end = "\n" if final else "\r"
        print(message.ljust(120), end=end, flush=True)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def parse_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def date_to_str(value: date) -> str:
    return value.strftime(DATE_FMT)


def safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        text = str(value).strip()
        if not text or text.lower() in {"none", "nan", "null", "-"}:
            return None
        return float(text)
    except Exception:
        return None


def clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def mean_or_none(values: Iterable[Optional[float]]) -> Optional[float]:
    arr = [float(v) for v in values if v is not None and np.isfinite(float(v))]
    if not arr:
        return None
    return float(np.mean(np.asarray(arr, dtype=float)))


def read_structured_records(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".jsonl":
        rows: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                payload = json.loads(raw)
                if isinstance(payload, dict):
                    rows.append(payload)
        return rows
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict):
            return [payload]
        return []
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [dict(row) for row in reader]
    raise RuntimeError(f"Unsupported input format for {path}")


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=False) + "\n")


def fetch_close_series(
    ticker: str,
    start_date: date,
    end_date: date,
) -> pd.Series:
    """Load daily close series [start_date, end_date] from Yahoo Finance."""
    series, _diag = fetch_close_series_with_diagnostics(
        ticker,
        start_date,
        end_date,
        enable_alpha_fallback=False,
    )
    return series


def _extract_close_series_from_frame(frame: pd.DataFrame) -> pd.Series:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.Series(dtype=float)

    close: Optional[pd.Series] = None
    columns = frame.columns
    # yfinance can return either flat columns (e.g. "Close") or MultiIndex
    # columns (e.g. ("Close", "AAPL")) depending on version/settings.
    if isinstance(columns, pd.MultiIndex):
        level0 = [str(item) for item in columns.get_level_values(0)]
        if "Close" in level0:
            try:
                close_df = frame.xs("Close", axis=1, level=0)
                if isinstance(close_df, pd.DataFrame) and not close_df.empty:
                    close = close_df.iloc[:, 0]
            except Exception:
                close = None
        if close is None and "Adj Close" in level0:
            try:
                adj_df = frame.xs("Adj Close", axis=1, level=0)
                if isinstance(adj_df, pd.DataFrame) and not adj_df.empty:
                    close = adj_df.iloc[:, 0]
            except Exception:
                close = None
    else:
        if "Close" in frame.columns:
            close = frame["Close"]
        elif "Adj Close" in frame.columns:
            close = frame["Adj Close"]

    if close is None:
        return pd.Series(dtype=float)

    close = close.copy().dropna()
    if close.empty:
        return pd.Series(dtype=float)
    idx = pd.to_datetime(close.index).tz_localize(None)
    close.index = idx
    return close.sort_index()


def _candidate_tickers(ticker: str) -> list[str]:
    base = str(ticker or "").strip().upper()
    if not base:
        return []
    candidates: list[str] = [base]
    dot_dash = base.replace(".", "-")
    if dot_dash not in candidates:
        candidates.append(dot_dash)
    # Some historical symbols include market suffixes like ".Y" that can fail
    # under Yahoo. Try base prefix as a fallback probe.
    if "." in base:
        prefix = base.split(".", 1)[0].strip()
        if prefix and prefix not in candidates:
            candidates.append(prefix)
    return candidates


def fetch_close_series_with_diagnostics(
    ticker: str,
    start_date: date,
    end_date: date,
    *,
    enable_alpha_fallback: bool = False,
) -> tuple[pd.Series, dict[str, Any]]:
    """Load daily close series and return detailed attempt diagnostics."""
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=1)
    attempts: list[dict[str, Any]] = []
    candidates = _candidate_tickers(ticker)

    for candidate in candidates:
        out_buf = io.StringIO()
        err_buf = io.StringIO()
        frame: pd.DataFrame | None = None
        exc_text: Optional[str] = None
        try:
            with redirect_stdout(out_buf), redirect_stderr(err_buf):
                frame = yf.download(
                    candidate,
                    start=start,
                    end=end,
                    interval="1d",
                    auto_adjust=False,
                    progress=False,
                    threads=False,
                )
        except Exception as exc:
            exc_text = str(exc)
            frame = None

        close = _extract_close_series_from_frame(frame) if isinstance(frame, pd.DataFrame) else pd.Series(dtype=float)
        attempt = {
            "source": "yfinance",
            "candidate": candidate,
            "frame_rows": int(len(frame)) if isinstance(frame, pd.DataFrame) else 0,
            "close_rows": int(len(close)),
            "stdout": out_buf.getvalue().strip(),
            "stderr": err_buf.getvalue().strip(),
            "exception": exc_text,
        }
        attempts.append(attempt)

        if not close.empty:
            return close, {
                "ticker_requested": str(ticker),
                "ticker_used": candidate,
                "status": "ok",
                "source_used": "yfinance",
                "attempts": attempts,
            }

    if enable_alpha_fallback:
        for candidate in candidates:
            close, alpha_diag = _fetch_close_series_alpha_vantage(candidate, start_date, end_date)
            attempts.append(
                {
                    "source": "alpha_vantage",
                    "candidate": candidate,
                    "frame_rows": int(len(close)),
                    "close_rows": int(len(close)),
                    "stdout": "",
                    "stderr": str(alpha_diag.get("error") or ""),
                    "exception": None,
                    "meta": alpha_diag,
                }
            )
            if not close.empty:
                return close, {
                    "ticker_requested": str(ticker),
                    "ticker_used": candidate,
                    "status": "ok",
                    "source_used": "alpha_vantage",
                    "attempts": attempts,
                }

    return pd.Series(dtype=float), {
        "ticker_requested": str(ticker),
        "ticker_used": None,
        "status": "no_data",
        "source_used": None,
        "attempts": attempts,
    }


def _fetch_close_series_alpha_vantage(
    ticker: str,
    start_date: date,
    end_date: date,
) -> tuple[pd.Series, dict[str, Any]]:
    api_key = os.getenv("ALPHAVANTAGE_API_KEY", "").strip()
    if not api_key:
        return pd.Series(dtype=float), {"status": "error", "error": "ALPHAVANTAGE_API_KEY missing"}

    try:
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": ticker,
                "outputsize": "full",
                "apikey": api_key,
            },
            timeout=20,
        )
    except Exception as exc:
        return pd.Series(dtype=float), {"status": "error", "error": f"request_error: {exc}"}

    text = response.text or ""
    try:
        payload = response.json()
    except Exception:
        return pd.Series(dtype=float), {"status": "error", "error": f"non_json_response: {text[:220]}"}

    if not isinstance(payload, dict):
        return pd.Series(dtype=float), {"status": "error", "error": "invalid_json_payload"}

    note = str(payload.get("Note") or "").strip()
    info = str(payload.get("Information") or "").strip()
    err = str(payload.get("Error Message") or "").strip()
    if note:
        return pd.Series(dtype=float), {"status": "error", "error": note}
    if info:
        return pd.Series(dtype=float), {"status": "error", "error": info}
    if err:
        return pd.Series(dtype=float), {"status": "error", "error": err}

    ts = payload.get("Time Series (Daily)")
    if not isinstance(ts, dict) or not ts:
        return pd.Series(dtype=float), {"status": "error", "error": "missing_time_series_daily"}

    values: list[tuple[pd.Timestamp, float]] = []
    for raw_date, row in ts.items():
        if not isinstance(row, dict):
            continue
        try:
            day = pd.Timestamp(raw_date).tz_localize(None)
        except Exception:
            continue
        if day.date() < start_date or day.date() > end_date:
            continue
        close_value = safe_float(row.get("5. adjusted close"))
        if close_value is None:
            close_value = safe_float(row.get("4. close"))
        if close_value is None:
            continue
        values.append((day, float(close_value)))

    if not values:
        return pd.Series(dtype=float), {"status": "error", "error": "no_rows_in_requested_range"}

    values.sort(key=lambda item: item[0])
    idx = pd.DatetimeIndex([item[0] for item in values])
    ser = pd.Series([item[1] for item in values], index=idx, dtype=float)
    return ser, {"status": "ok", "rows": int(len(ser))}


@dataclass
class EventWindow:
    aligned_trading_date: Optional[str]
    close_t_minus_1: Optional[float]
    close_t: Optional[float]
    close_t_plus_1: Optional[float]
    close_t_plus_3: Optional[float]
    close_t_plus_5: Optional[float]
    return_1d: Optional[float]
    return_3d: Optional[float]
    return_5d: Optional[float]


def _return_between(start_value: Optional[float], end_value: Optional[float]) -> Optional[float]:
    if start_value in (None, 0) or end_value is None:
        return None
    return float((float(end_value) / float(start_value)) - 1.0)


def compute_event_window(
    close_series: pd.Series,
    event_date: date,
    alignment_mode: str,
) -> EventWindow:
    """
    Align event to trading day.

    alignment_mode:
    - on_or_next_trading_day: first close on or after event_date
    - next_trading_day: first close strictly after event_date
    """
    if close_series.empty:
        return EventWindow(None, None, None, None, None, None, None, None, None)

    trading_days = [ts.date() for ts in close_series.index]
    anchor_idx: Optional[int] = None
    for idx, day in enumerate(trading_days):
        if alignment_mode == "next_trading_day":
            if day > event_date:
                anchor_idx = idx
                break
        else:
            if day >= event_date:
                anchor_idx = idx
                break
    if anchor_idx is None:
        return EventWindow(None, None, None, None, None, None, None, None, None)

    def get_close(idx: int) -> Optional[float]:
        if idx < 0 or idx >= len(close_series):
            return None
        value = safe_float(close_series.iloc[idx])
        return float(value) if value is not None else None

    close_tm1 = get_close(anchor_idx - 1)
    close_t = get_close(anchor_idx)
    close_tp1 = get_close(anchor_idx + 1)
    close_tp3 = get_close(anchor_idx + 3)
    close_tp5 = get_close(anchor_idx + 5)

    return EventWindow(
        aligned_trading_date=date_to_str(trading_days[anchor_idx]),
        close_t_minus_1=close_tm1,
        close_t=close_t,
        close_t_plus_1=close_tp1,
        close_t_plus_3=close_tp3,
        close_t_plus_5=close_tp5,
        return_1d=_return_between(close_t, close_tp1),
        return_3d=_return_between(close_t, close_tp3),
        return_5d=_return_between(close_t, close_tp5),
    )


def chronological_split_indices(
    n_rows: int,
    train_fraction: float,
    val_fraction: float,
    min_per_split: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    if n_rows < max(3, min_per_split * 3):
        raise RuntimeError(
            f"Not enough rows ({n_rows}) for chronological train/val/test split with min_per_split={min_per_split}."
        )

    train_end = int(round(n_rows * train_fraction))
    val_end = int(round(n_rows * (train_fraction + val_fraction)))

    train_end = max(min_per_split, train_end)
    val_end = max(train_end + min_per_split, val_end)

    if n_rows - val_end < min_per_split:
        val_end = n_rows - min_per_split
    if val_end - train_end < min_per_split:
        train_end = val_end - min_per_split

    if train_end < min_per_split or val_end - train_end < min_per_split or n_rows - val_end < min_per_split:
        raise RuntimeError(
            f"Could not satisfy split constraints: n_rows={n_rows}, train_end={train_end}, val_end={val_end}, min_per_split={min_per_split}."
        )

    all_idx = np.arange(n_rows)
    return all_idx[:train_end], all_idx[train_end:val_end], all_idx[val_end:]


def _pearson_corr(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[float]:
    if y_true.size == 0:
        return None
    if np.std(y_true) == 0 or np.std(y_pred) == 0:
        return None
    corr = np.corrcoef(y_true, y_pred)[0, 1]
    if np.isnan(corr):
        return None
    return float(corr)


def _rankdata(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values)
    ranks = np.zeros(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg_rank = (i + j + 2) / 2.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg_rank
        i = j + 1
    return ranks


def _spearman_corr(y_true: np.ndarray, y_pred: np.ndarray) -> Optional[float]:
    if y_true.size == 0:
        return None
    rt = _rankdata(y_true)
    rp = _rankdata(y_pred)
    return _pearson_corr(rt, rp)


def regression_metrics(y_true: Sequence[float], y_pred: Sequence[float]) -> dict[str, Optional[float]]:
    yt = np.asarray(list(y_true), dtype=float)
    yp = np.asarray(list(y_pred), dtype=float)
    if yt.size == 0:
        return {"mae": None, "rmse": None, "r2": None, "pearson": None, "spearman": None}

    residual = yt - yp
    mae = float(np.mean(np.abs(residual)))
    rmse = float(np.sqrt(np.mean(residual**2)))
    ss_tot = float(np.sum((yt - np.mean(yt)) ** 2))
    ss_res = float(np.sum(residual**2))
    r2 = None if ss_tot == 0 else float(1.0 - (ss_res / ss_tot))

    return {
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "pearson": _pearson_corr(yt, yp),
        "spearman": _spearman_corr(yt, yp),
    }


def _safe_div(num: float, den: float) -> float:
    return 0.0 if den == 0 else float(num / den)


def _roc_auc_score(y_true: np.ndarray, y_score: np.ndarray) -> Optional[float]:
    pos_mask = y_true == 1
    neg_mask = y_true == 0
    n_pos = int(np.sum(pos_mask))
    n_neg = int(np.sum(neg_mask))
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = _rankdata(y_score)
    rank_sum_pos = float(np.sum(ranks[pos_mask]))
    auc = (rank_sum_pos - (n_pos * (n_pos + 1) / 2.0)) / (n_pos * n_neg)
    return float(auc)


def classification_metrics(
    y_true: Sequence[int],
    y_pred_label: Sequence[int],
    y_pred_score: Sequence[float],
) -> dict[str, Optional[float]]:
    yt = np.asarray(list(y_true), dtype=int)
    yp = np.asarray(list(y_pred_label), dtype=int)
    ys = np.asarray(list(y_pred_score), dtype=float)
    if yt.size == 0:
        return {
            "accuracy": None,
            "macro_f1": None,
            "precision": None,
            "recall": None,
            "roc_auc": None,
        }

    accuracy = float(np.mean(yt == yp))

    class_metrics = []
    for label in (0, 1):
        tp = float(np.sum((yp == label) & (yt == label)))
        fp = float(np.sum((yp == label) & (yt != label)))
        fn = float(np.sum((yp != label) & (yt == label)))
        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        class_metrics.append((precision, recall, f1))

    macro_precision = float(np.mean([item[0] for item in class_metrics]))
    macro_recall = float(np.mean([item[1] for item in class_metrics]))
    macro_f1 = float(np.mean([item[2] for item in class_metrics]))

    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "precision": macro_precision,
        "recall": macro_recall,
        "roc_auc": _roc_auc_score(yt, ys),
    }


def bucket_analysis(
    *,
    scores: Sequence[float],
    abnormal_returns: Sequence[float],
    n_buckets: int,
) -> list[dict[str, Any]]:
    raw_scores = np.asarray(list(scores), dtype=float)
    raw_returns = np.asarray(list(abnormal_returns), dtype=float)
    if raw_scores.size == 0:
        return []

    order = np.argsort(raw_scores)
    buckets: list[dict[str, Any]] = []
    n = len(order)
    for bucket_idx in range(n_buckets):
        start = int(np.floor(bucket_idx * n / n_buckets))
        end = int(np.floor((bucket_idx + 1) * n / n_buckets))
        if start >= end:
            continue
        slice_idx = order[start:end]
        bucket_scores = raw_scores[slice_idx]
        bucket_returns = raw_returns[slice_idx]
        buckets.append(
            {
                "bucket": bucket_idx + 1,
                "count": int(len(slice_idx)),
                "score_min": float(np.min(bucket_scores)),
                "score_max": float(np.max(bucket_scores)),
                "score_mean": float(np.mean(bucket_scores)),
                "abnormal_return_mean": float(np.mean(bucket_returns)),
                "abnormal_return_median": float(np.median(bucket_returns)),
            }
        )
    return buckets
