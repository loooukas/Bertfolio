"""Persistent cache helpers for full analysis report payloads."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any, Optional


def _cache_path(cache_dir: str, ticker: str) -> Path:
    symbol = (ticker or "").strip().upper() or "UNKNOWN"
    return Path(cache_dir) / f"{symbol}.json"


def _parse_cache_envelope(path: Path) -> Optional[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def load_cached_analysis_envelope(*, cache_dir: str, ticker: str) -> Optional[dict[str, Any]]:
    path = _cache_path(cache_dir, ticker)
    if not path.exists():
        return None
    return _parse_cache_envelope(path)


def load_cached_analysis(*, cache_dir: str, ticker: str) -> Optional[dict[str, Any]]:
    payload = load_cached_analysis_envelope(cache_dir=cache_dir, ticker=ticker)
    if payload is None:
        return None
    result = payload.get("result")
    if not isinstance(result, dict):
        return None
    return result


def write_cached_analysis(
    *,
    cache_dir: str,
    ticker: str,
    result: dict[str, Any],
    runtime_overrides: Optional[dict[str, Any]] = None,
) -> Path:
    path = _cache_path(cache_dir, ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    envelope = {
        "ticker": (ticker or "").strip().upper(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "analysis_version": str(result.get("analysis_version") or ""),
        "runtime_overrides": dict(runtime_overrides or {}),
        "result": result,
    }
    path.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def delete_cached_analysis(*, cache_dir: str, ticker: str) -> bool:
    path = _cache_path(cache_dir, ticker)
    if not path.exists():
        return False
    try:
        path.unlink()
        return True
    except Exception:
        return False


def _quarter_from_date(raw: Any) -> Optional[str]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except Exception:
        return None
    quarter = ((dt.month - 1) // 3) + 1
    return f"Q{quarter} {dt.year}"


def _quarter_from_title(raw: Any) -> Optional[str]:
    if not isinstance(raw, str) or not raw.strip():
        return None
    matched = re.search(r"\bQ([1-4])\s*(?:FY)?\s*(20\d{2})\b", raw, re.IGNORECASE)
    if not matched:
        return None
    return f"Q{matched.group(1)} {matched.group(2)}"


def _transcript_labels_from_result(result: dict[str, Any]) -> list[str]:
    transcript = result.get("transcript")
    if not isinstance(transcript, dict):
        return []

    labels: list[str] = []
    quarter_status = transcript.get("quarter_status")
    if isinstance(quarter_status, list):
        for item in quarter_status:
            if not isinstance(item, dict):
                continue
            if str(item.get("status", "")).lower() != "found":
                continue
            quarter = str(item.get("quarter", "")).strip()
            if quarter:
                labels.append(quarter.replace("-", " "))

    if labels:
        return sorted(set(labels))

    docs = transcript.get("transcripts")
    if isinstance(docs, list):
        for item in docs:
            if not isinstance(item, dict):
                continue
            quarter = _quarter_from_title(item.get("title")) or _quarter_from_date(item.get("published_date"))
            if quarter:
                labels.append(quarter)

    return sorted(set(labels))


def list_cached_analysis_summaries(*, cache_dir: str) -> list[dict[str, Any]]:
    root = Path(cache_dir)
    if not root.exists():
        return []

    rows: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        payload = _parse_cache_envelope(path)
        if payload is None:
            continue

        result = payload.get("result")
        if not isinstance(result, dict):
            continue

        transcript = result.get("transcript")
        transcript_found = 0
        if isinstance(transcript, dict):
            count_found = transcript.get("transcript_count_found")
            if isinstance(count_found, int):
                transcript_found = count_found
        if transcript_found <= 0:
            top_count = result.get("transcripts_found")
            if isinstance(top_count, int) and top_count > 0:
                transcript_found = top_count

        ticker = str(payload.get("ticker") or "").strip().upper() or path.stem.strip().upper()
        rows.append(
            {
                "ticker": ticker,
                "updated_at": str(payload.get("updated_at") or ""),
                "analysis_version": str(payload.get("analysis_version") or ""),
                "transcripts_found": transcript_found,
                "transcript_labels": _transcript_labels_from_result(result),
            }
        )

    rows.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)
    return rows
