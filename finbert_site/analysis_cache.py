"""Persistent cache helpers for full analysis report payloads."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Optional


def _cache_path(cache_dir: str, ticker: str) -> Path:
    symbol = (ticker or "").strip().upper() or "UNKNOWN"
    return Path(cache_dir) / f"{symbol}.json"


def load_cached_analysis(*, cache_dir: str, ticker: str) -> Optional[dict[str, Any]]:
    path = _cache_path(cache_dir, ticker)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
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

