"""External data providers for transcripts and fundamentals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests
import yfinance as yf

from .settings import Settings


@dataclass
class TranscriptRecord:
    symbol: str
    year: int
    quarter: int
    date: Optional[str]
    content: str
    source: str


def _quarter_from_month(month: int) -> int:
    return ((month - 1) // 3) + 1


def _quarter_label(year: int, quarter: int) -> str:
    return f"{year}-Q{quarter}"


def recent_quarters(symbol: str, limit: int = 4) -> list[tuple[int, int]]:
    ticker = yf.Ticker(symbol)
    targets: list[tuple[int, int]] = []

    try:
        earnings_dates = ticker.get_earnings_dates(limit=12)
    except Exception:
        earnings_dates = None

    if isinstance(earnings_dates, pd.DataFrame) and not earnings_dates.empty:
        now = pd.Timestamp.utcnow()
        for idx in earnings_dates.index:
            ts = pd.Timestamp(idx).tz_localize(None)
            if ts > now.tz_localize(None):
                continue
            year = int(ts.year)
            quarter = _quarter_from_month(int(ts.month))
            pair = (year, quarter)
            if pair not in targets:
                targets.append(pair)
            if len(targets) >= limit:
                break

    if len(targets) < limit:
        now = datetime.utcnow()
        year = now.year
        quarter = _quarter_from_month(now.month)
        while len(targets) < limit:
            pair = (year, quarter)
            if pair not in targets:
                targets.append(pair)
            quarter -= 1
            if quarter == 0:
                quarter = 4
                year -= 1

    return targets[:limit]


def _extract_fmp_content(payload: Any) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(payload, list) or not payload:
        return None, None

    first = payload[0]
    if isinstance(first, list) and len(first) >= 5:
        # Legacy array shape: [symbol, quarter, date, ???, content]
        date = str(first[2]) if len(first) > 2 else None
        content = str(first[4])
        return date, content

    if isinstance(first, dict):
        content = first.get("content") or first.get("transcript") or first.get("text")
        date = first.get("date")
        if isinstance(content, str) and content.strip():
            return str(date) if date else None, content

    return None, None


def fetch_transcript_fmp(
    symbol: str,
    year: int,
    quarter: int,
    api_key: str,
    timeout_seconds: int,
) -> Optional[TranscriptRecord]:
    if not api_key:
        return None

    url = "https://financialmodelingprep.com/api/v4/earning_call_transcript"
    params = {
        "symbol": symbol,
        "year": year,
        "quarter": quarter,
        "apikey": api_key,
    }

    response = requests.get(url, params=params, timeout=timeout_seconds)
    if response.status_code == 403:
        raise PermissionError(
            "FMP returned 403 for transcript endpoint. Your plan likely does not include earnings transcript access."
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"FMP transcript request failed: HTTP {response.status_code} - {response.text[:200]}"
        )

    data = response.json()
    date, content = _extract_fmp_content(data)
    if not content:
        return None

    return TranscriptRecord(
        symbol=symbol,
        year=year,
        quarter=quarter,
        date=date,
        content=content,
        source="fmp",
    )


def fetch_transcript_alpha_vantage(
    symbol: str,
    year: int,
    quarter: int,
    api_key: str,
    timeout_seconds: int,
) -> Optional[TranscriptRecord]:
    if not api_key:
        return None

    url = "https://www.alphavantage.co/query"
    params = {
        "function": "EARNINGS_CALL_TRANSCRIPT",
        "symbol": symbol,
        "quarter": f"{year}Q{quarter}",
        "apikey": api_key,
    }

    response = requests.get(url, params=params, timeout=timeout_seconds)
    if response.status_code != 200:
        raise RuntimeError(
            f"Alpha Vantage transcript request failed: HTTP {response.status_code} - {response.text[:200]}"
        )

    data = response.json()
    if isinstance(data, dict):
        transcript = data.get("transcript") or data.get("content")
        if isinstance(transcript, str) and transcript.strip():
            return TranscriptRecord(
                symbol=symbol,
                year=year,
                quarter=quarter,
                date=data.get("callDate") or data.get("date"),
                content=transcript,
                source="alpha_vantage",
            )

    return None


def fetch_last_4_transcripts(symbol: str, settings: Settings) -> Tuple[list[TranscriptRecord], list[str]]:
    warnings: list[str] = []
    transcripts: list[TranscriptRecord] = []
    forbidden_seen = False

    for year, quarter in recent_quarters(symbol, limit=4):
        record: Optional[TranscriptRecord] = None

        try:
            record = fetch_transcript_fmp(
                symbol=symbol,
                year=year,
                quarter=quarter,
                api_key=settings.fmp_api_key,
                timeout_seconds=settings.request_timeout_seconds,
            )
        except PermissionError as exc:
            if not forbidden_seen:
                warnings.append(str(exc))
                forbidden_seen = True
        except Exception as exc:
            warnings.append(f"FMP error for {symbol} {_quarter_label(year, quarter)}: {exc}")

        if record is None:
            try:
                record = fetch_transcript_alpha_vantage(
                    symbol=symbol,
                    year=year,
                    quarter=quarter,
                    api_key=settings.alpha_vantage_api_key,
                    timeout_seconds=settings.request_timeout_seconds,
                )
            except Exception as exc:
                warnings.append(
                    f"Alpha Vantage error for {symbol} {_quarter_label(year, quarter)}: {exc}"
                )

        if record is None:
            warnings.append(f"No transcript for {symbol} {_quarter_label(year, quarter)}")
            continue

        transcripts.append(record)

    return transcripts, warnings


def _find_series_row(
    frame: Optional[pd.DataFrame],
    candidate_names: list[str],
    max_cols: int = 4,
) -> Dict[str, Optional[float]]:
    if frame is None or frame.empty:
        return {}

    for name in candidate_names:
        if name in frame.index:
            row = frame.loc[name]
            if hasattr(row, "iloc"):
                values = row.iloc[:max_cols]
                out: Dict[str, Optional[float]] = {}
                for idx, value in values.items():
                    ts = pd.Timestamp(idx)
                    q = _quarter_from_month(int(ts.month))
                    key = _quarter_label(int(ts.year), q)
                    out[key] = float(value) if pd.notna(value) else None
                return out
    return {}


def _safe_growth(newer: Optional[float], older: Optional[float]) -> Optional[float]:
    if newer is None or older in (None, 0):
        return None
    return ((newer - older) / abs(older)) * 100.0


def fetch_fundamentals(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(symbol)

    info: dict[str, Any] = {}
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    try:
        income_stmt = ticker.quarterly_income_stmt
    except Exception:
        income_stmt = None

    revenue_map = _find_series_row(income_stmt, ["Total Revenue", "Revenue"])
    net_income_map = _find_series_row(income_stmt, ["Net Income", "NetIncome"])

    eps_map: Dict[str, Dict[str, Optional[float]]] = {}
    try:
        earnings = ticker.get_earnings_dates(limit=8)
        if isinstance(earnings, pd.DataFrame) and not earnings.empty:
            past = earnings[earnings.index <= pd.Timestamp.utcnow()]
            for idx, row in past.head(4).iterrows():
                ts = pd.Timestamp(idx)
                label = _quarter_label(int(ts.year), _quarter_from_month(int(ts.month)))
                eps_map[label] = {
                    "reported": float(row["Reported EPS"]) if pd.notna(row.get("Reported EPS")) else None,
                    "estimate": float(row["EPS Estimate"]) if pd.notna(row.get("EPS Estimate")) else None,
                }
    except Exception:
        eps_map = {}

    quarters = sorted(
        set(revenue_map.keys()) | set(net_income_map.keys()) | set(eps_map.keys()),
        reverse=True,
    )[:4]

    snapshots: list[dict[str, Any]] = []
    for q in quarters:
        eps_entry = eps_map.get(q, {})
        snapshots.append(
            {
                "quarter": q,
                "revenue": revenue_map.get(q),
                "net_income": net_income_map.get(q),
                "reported_eps": eps_entry.get("reported"),
                "eps_estimate": eps_entry.get("estimate"),
            }
        )

    revenue_qoq = None
    eps_qoq = None
    if len(snapshots) >= 2:
        revenue_qoq = _safe_growth(snapshots[0].get("revenue"), snapshots[1].get("revenue"))
        eps_qoq = _safe_growth(snapshots[0].get("reported_eps"), snapshots[1].get("reported_eps"))

    return {
        "currency": info.get("currency"),
        "market_cap": info.get("marketCap"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "debt_to_equity": info.get("debtToEquity"),
        "quarterly": snapshots,
        "revenue_qoq_growth_pct": revenue_qoq,
        "eps_qoq_growth_pct": eps_qoq,
    }
