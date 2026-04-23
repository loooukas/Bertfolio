"""Shared helpers for the rocky teacher-labeling pipeline."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any, Iterable


DEFAULT_BOOTSTRAP_TICKERS = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "GOOGL",
    "META",
    "TSLA",
    "AMD",
    "AVGO",
    "INTC",
    "CRM",
    "ORCL",
    "ADBE",
    "QCOM",
    "NFLX",
    "COST",
    "WMT",
    "HD",
    "MCD",
    "PEP",
    "KO",
    "JNJ",
    "PFE",
    "UNH",
    "MRK",
    "V",
    "MA",
    "JPM",
    "BAC",
    "GS",
    "XOM",
    "CVX",
    "COP",
    "CAT",
    "GE",
    "BA",
]

_TICKER_SANITIZE_RE = re.compile(r"[^A-Za-z0-9.-]+")
_WORD_RE = re.compile(r"\b\w+\b")


def iso_now_utc() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def append_jsonl(path: Path, row: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False))
        fh.write("\n")


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def normalize_ticker(value: str) -> str:
    cleaned = _TICKER_SANITIZE_RE.sub("", str(value or "").strip().upper())
    return cleaned


def parse_ticker_inputs(*, inline_tickers: list[str] | None, tickers_file: str | None) -> list[str]:
    raw: list[str] = []

    for token in inline_tickers or []:
        for chunk in str(token).split(","):
            cleaned = normalize_ticker(chunk)
            if cleaned:
                raw.append(cleaned)

    if tickers_file:
        path = Path(tickers_file)
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for chunk in line.split(","):
                cleaned = normalize_ticker(chunk)
                if cleaned:
                    raw.append(cleaned)

    if not raw:
        raw = list(DEFAULT_BOOTSTRAP_TICKERS)

    seen: set[str] = set()
    ordered: list[str] = []
    for ticker in raw:
        if ticker in seen:
            continue
        seen.add(ticker)
        ordered.append(ticker)
    return ordered


def quarter_label(year: int | None, quarter: int | None) -> str | None:
    if year is None or quarter is None:
        return None
    if quarter not in {1, 2, 3, 4}:
        return None
    return f"{int(year)}-Q{int(quarter)}"


def build_transcript_id(
    *,
    ticker: str,
    year: int | None,
    quarter: int | None,
    published_date: str | None,
    source_url: str | None,
    title: str | None,
    ordinal_hint: int,
) -> str:
    quarter_part = quarter_label(year, quarter) or "unknown-quarter"
    basis = "|".join(
        [
            ticker,
            quarter_part,
            str(published_date or ""),
            str(source_url or ""),
            str(title or ""),
            str(ordinal_hint),
        ]
    )
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:12]
    compact_quarter = quarter_part.replace("-", "").lower()
    return f"{ticker}_{compact_quarter}_{digest}"


def build_sample_id(*, transcript_id: str, order_index: int) -> str:
    return f"{transcript_id}::b{int(order_index):04d}"


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def count_words(value: str) -> int:
    return len(_WORD_RE.findall(str(value or "")))


def load_existing_sample_ids(path: Path) -> set[str]:
    out: set[str] = set()
    for row in iter_jsonl(path):
        sample_id = row.get("sample_id")
        if isinstance(sample_id, str) and sample_id:
            out.add(sample_id)
    return out

