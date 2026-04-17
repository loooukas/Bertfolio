"""External data providers for Alpha Vantage transcripts/news and fundamentals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
import time
from typing import Any, Dict, Optional, Tuple

import pandas as pd
import requests
import yfinance as yf

from .settings import Settings

_LAST_ALPHA_REQUEST_TS = 0.0
_ALPHA_MIN_INTERVAL_SEC = 1.1

_FINANCE_TERMS = {
    "stock",
    "shares",
    "earnings",
    "eps",
    "revenue",
    "guidance",
    "valuation",
    "market cap",
    "dividend",
    "buyback",
    "analyst",
    "quarter",
}

_FINANCE_SUBREDDIT_WEIGHTS = {
    "stocks": 2.5,
    "investing": 2.5,
    "wallstreetbets": 2.0,
    "stockmarket": 2.0,
    "options": 1.5,
    "securityanalysis": 2.5,
    "valueinvesting": 2.5,
}


@dataclass
class TranscriptRecord:
    symbol: str
    year: int
    quarter: int
    date: Optional[str]
    content: str
    source: str


@dataclass
class TranscriptFetchOutcome:
    quarter: str
    status: str
    detail: Optional[str] = None


@dataclass
class TranscriptFetchDiagnostics:
    requested_quarters: list[str]
    found_quarters: list[str]
    missing_quarters: list[str]
    errors: list[str]
    outcomes: list[TranscriptFetchOutcome]


@dataclass
class NewsRecord:
    title: str
    summary: str
    url: str
    source: Optional[str]
    time_published: Optional[str]
    sentiment_score: float
    sentiment_label: str


@dataclass
class SocialRecord:
    source: str
    title: str
    body: str
    url: str
    subreddit: Optional[str]
    created_utc: Optional[int]
    relevance_score: float


@dataclass
class PriceVolumeRecord:
    date: str
    close: float
    volume: float


def _quarter_from_month(month: int) -> int:
    return ((month - 1) // 3) + 1


def _quarter_label(year: int, quarter: int) -> str:
    return f"{year}-Q{quarter}"


def _quarter_tuple_from_label(label: str) -> tuple[int, int]:
    year_part, q_part = label.split("-Q")
    return int(year_part), int(q_part)


def _alpha_get(params: Dict[str, str], timeout_seconds: int) -> Dict[str, Any]:
    global _LAST_ALPHA_REQUEST_TS

    now = time.monotonic()
    elapsed = now - _LAST_ALPHA_REQUEST_TS
    if elapsed < _ALPHA_MIN_INTERVAL_SEC:
        time.sleep(_ALPHA_MIN_INTERVAL_SEC - elapsed)

    url = "https://www.alphavantage.co/query"
    response = requests.get(url, params=params, timeout=timeout_seconds)
    _LAST_ALPHA_REQUEST_TS = time.monotonic()
    if response.status_code != 200:
        raise RuntimeError(
            f"Alpha Vantage request failed: HTTP {response.status_code} - {response.text[:200]}"
        )

    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Alpha Vantage returned a non-JSON object.")

    if payload.get("Error Message"):
        raise RuntimeError(str(payload.get("Error Message")))
    if payload.get("Information"):
        raise RuntimeError(str(payload.get("Information")))
    if payload.get("Note"):
        raise RuntimeError(str(payload.get("Note")))

    return payload


def transcript_candidate_quarters(symbol: str, limit: int = 12) -> list[str]:
    ticker = yf.Ticker(symbol)
    labels: list[str] = []

    try:
        earnings_dates = ticker.get_earnings_dates(limit=max(12, limit + 4))
    except Exception:
        earnings_dates = None

    if isinstance(earnings_dates, pd.DataFrame) and not earnings_dates.empty:
        now = pd.Timestamp.utcnow()
        for idx in earnings_dates.index:
            ts = pd.Timestamp(idx).tz_localize(None)
            if ts > now.tz_localize(None):
                continue
            label = _quarter_label(int(ts.year), _quarter_from_month(int(ts.month)))
            if label not in labels:
                labels.append(label)
            if len(labels) >= limit:
                break

    if len(labels) < limit:
        now = datetime.now(timezone.utc)
        year = now.year
        quarter = _quarter_from_month(now.month)
        while len(labels) < limit:
            label = _quarter_label(year, quarter)
            if label not in labels:
                labels.append(label)
            quarter -= 1
            if quarter == 0:
                quarter = 4
                year -= 1

    return labels[:limit]


def fetch_transcript_alpha_vantage(
    symbol: str,
    year: int,
    quarter: int,
    api_key: str,
    timeout_seconds: int,
) -> Optional[TranscriptRecord]:
    if not api_key:
        return None

    payload = _alpha_get(
        {
            "function": "EARNINGS_CALL_TRANSCRIPT",
            "symbol": symbol,
            "quarter": f"{year}Q{quarter}",
            "apikey": api_key,
        },
        timeout_seconds,
    )

    transcript = payload.get("transcript") or payload.get("content")
    if not isinstance(transcript, str) or not transcript.strip():
        return None

    return TranscriptRecord(
        symbol=symbol,
        year=year,
        quarter=quarter,
        date=payload.get("callDate") or payload.get("date"),
        content=transcript,
        source="alpha_vantage",
    )


def fetch_last_4_transcripts(
    symbol: str,
    settings: Settings,
) -> Tuple[list[TranscriptRecord], list[str], TranscriptFetchDiagnostics]:
    warnings: list[str] = []
    transcripts: list[TranscriptRecord] = []

    if not settings.alpha_vantage_api_key:
        diagnostics = TranscriptFetchDiagnostics(
            requested_quarters=[],
            found_quarters=[],
            missing_quarters=[],
            errors=["ALPHAVANTAGE_API_KEY is missing in .env"],
            outcomes=[],
        )
        return [], ["ALPHAVANTAGE_API_KEY is missing in .env"], diagnostics

    candidate_labels = transcript_candidate_quarters(symbol, limit=12)
    outcomes: list[TranscriptFetchOutcome] = []

    for label in candidate_labels:
        if len(transcripts) >= 4:
            break

        year, quarter = _quarter_tuple_from_label(label)
        try:
            record = fetch_transcript_alpha_vantage(
                symbol=symbol,
                year=year,
                quarter=quarter,
                api_key=settings.alpha_vantage_api_key,
                timeout_seconds=settings.request_timeout_seconds,
            )
            if record is None:
                outcomes.append(TranscriptFetchOutcome(quarter=label, status="not_found"))
                continue

            transcripts.append(record)
            outcomes.append(TranscriptFetchOutcome(quarter=label, status="found"))
        except Exception as exc:
            detail = str(exc)
            warnings.append(f"Alpha Vantage transcript error for {symbol} {label}: {detail}")
            outcomes.append(TranscriptFetchOutcome(quarter=label, status="error", detail=detail))

    found_quarters = [o.quarter for o in outcomes if o.status == "found"]
    missing_quarters = [o.quarter for o in outcomes if o.status == "not_found"]
    errors = [f"{o.quarter}: {o.detail}" for o in outcomes if o.status == "error" and o.detail]

    if not transcripts and not errors:
        warnings.append(f"No transcript payload returned for {symbol} in scanned quarters.")

    diagnostics = TranscriptFetchDiagnostics(
        requested_quarters=[o.quarter for o in outcomes],
        found_quarters=found_quarters,
        missing_quarters=missing_quarters,
        errors=errors,
        outcomes=outcomes,
    )

    return transcripts, warnings, diagnostics


def _parse_news_score(raw: Any) -> float:
    try:
        return float(raw)
    except Exception:
        return 0.0


def fetch_news_alpha_vantage(symbol: str, settings: Settings, limit: int = 12) -> Tuple[list[NewsRecord], list[str]]:
    warnings: list[str] = []

    if not settings.alpha_vantage_api_key:
        return [], ["ALPHAVANTAGE_API_KEY is missing in .env"]

    try:
        payload = _alpha_get(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "sort": "LATEST",
                "limit": str(limit),
                "apikey": settings.alpha_vantage_api_key,
            },
            settings.request_timeout_seconds,
        )
    except Exception as exc:
        return [], [f"Alpha Vantage news error for {symbol}: {exc}"]

    feed = payload.get("feed")
    if not isinstance(feed, list):
        return [], [f"No Alpha Vantage news feed available for {symbol}"]

    results: list[NewsRecord] = []
    for item in feed[:limit]:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "Untitled")
        summary = str(item.get("summary") or "")
        url = str(item.get("url") or "")
        if not url:
            continue

        score = _parse_news_score(item.get("overall_sentiment_score"))
        label = str(item.get("overall_sentiment_label") or "neutral")

        results.append(
            NewsRecord(
                title=title,
                summary=summary,
                url=url,
                source=item.get("source"),
                time_published=item.get("time_published"),
                sentiment_score=score,
                sentiment_label=label,
            )
        )

    if not results:
        warnings.append(f"No Alpha Vantage news items returned for {symbol}")

    return results, warnings


def _finance_relevance_score(
    symbol: str,
    title: str,
    body: str,
    subreddit: Optional[str],
) -> float:
    text = f"{title} {body}".lower()
    symbol_l = symbol.lower()

    score = 0.0

    score += 3.0 * len(re.findall(rf"\b{re.escape(symbol_l)}\b", text))
    score += 2.0 * text.count(f"${symbol_l}")

    for term in _FINANCE_TERMS:
        if term in text:
            score += 0.4

    if subreddit:
        score += _FINANCE_SUBREDDIT_WEIGHTS.get(subreddit.lower(), 0.0)

    return score


def fetch_social_reddit(symbol: str, settings: Settings, limit: int = 12) -> Tuple[list[SocialRecord], list[str]]:
    warnings: list[str] = []
    query = f"${symbol} OR {symbol} stock"
    endpoint = "https://www.reddit.com/search.json"

    try:
        response = requests.get(
            endpoint,
            params={
                "q": query,
                "sort": "new",
                "limit": str(max(limit * 2, 24)),
                "type": "link",
                "t": "week",
            },
            headers={"User-Agent": "finbert-local-analyzer/0.3"},
            timeout=settings.request_timeout_seconds,
        )
        if response.status_code != 200:
            return [], [f"Reddit social feed error for {symbol}: HTTP {response.status_code}"]

        payload = response.json()
        data = payload.get("data", {})
        children = data.get("children", [])
        if not isinstance(children, list):
            return [], [f"No Reddit social posts available for {symbol}"]

        records: list[SocialRecord] = []
        for child in children:
            post = child.get("data", {}) if isinstance(child, dict) else {}
            title = str(post.get("title") or "").strip()
            body = str(post.get("selftext") or "").strip()
            permalink = str(post.get("permalink") or "").strip()
            subreddit = str(post.get("subreddit") or "").strip() or None

            if not title:
                continue

            url = f"https://www.reddit.com{permalink}" if permalink else "https://www.reddit.com"
            relevance = _finance_relevance_score(symbol, title, body, subreddit)

            records.append(
                SocialRecord(
                    source="reddit",
                    title=title,
                    body=body,
                    url=url,
                    subreddit=subreddit,
                    created_utc=int(post.get("created_utc")) if post.get("created_utc") else None,
                    relevance_score=relevance,
                )
            )

        records.sort(key=lambda r: r.relevance_score, reverse=True)

        if not records:
            warnings.append(f"No Reddit posts found for {symbol} in the recent window.")

        return records[:limit], warnings
    except Exception as exc:
        return [], [f"Reddit social feed error for {symbol}: {exc}"]


def fetch_price_volume_history(symbol: str, period: str = "3mo") -> list[PriceVolumeRecord]:
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period=period)
        if not isinstance(history, pd.DataFrame) or history.empty:
            return []

        out: list[PriceVolumeRecord] = []
        for idx, row in history.iterrows():
            try:
                ts = pd.Timestamp(idx)
                out.append(
                    PriceVolumeRecord(
                        date=ts.strftime("%Y-%m-%d"),
                        close=float(row.get("Close") or 0.0),
                        volume=float(row.get("Volume") or 0.0),
                    )
                )
            except Exception:
                continue
        return out
    except Exception:
        return []


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
