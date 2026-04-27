"""Run-level progress tracking and structured logging utilities."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import logging
import threading
import time
from typing import Any, Callable, Optional


STAGE_DEFINITIONS: list[dict[str, Any]] = [
    {"key": "news_fetch", "label": "News Fetch", "weight": 8},
    {"key": "social_fetch", "label": "Social Fetch", "weight": 7},
    {"key": "news_sentiment_scoring", "label": "News Sentiment Scoring", "weight": 7},
    {"key": "social_sentiment_scoring", "label": "Social Sentiment Scoring", "weight": 6},
    {"key": "fundamentals_fetch", "label": "Fundamentals Fetch", "weight": 9},
    {"key": "fundamentals_validation", "label": "Fundamentals Validation", "weight": 8},
    {"key": "transcript_discovery_scrape", "label": "Transcript Discovery + Scrape", "weight": 16},
    {"key": "transcript_normalization", "label": "Transcript Normalization", "weight": 14},
    {"key": "transcript_sentiment_speaker_scoring", "label": "Transcript Sentiment + Speaker Scoring", "weight": 17},
    {"key": "data_audit_report_assembly", "label": "Data Audit / Report Assembly", "weight": 8},
]


@dataclass
class StageState:
    key: str
    label: str
    weight: float
    status: str = "pending"
    progress: float = 0.0
    message: str = ""
    subtask: str = ""
    started_at: Optional[float] = None
    ended_at: Optional[float] = None


class RunProgressTracker:
    """Tracks weighted stage progress and emits structured log events."""

    def __init__(
        self,
        *,
        run_id: str,
        ticker: str,
        on_update: Optional[Callable[[dict[str, Any]], None]] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.run_id = run_id
        self.ticker = ticker
        self.on_update = on_update
        self.logger = logger or logging.getLogger("finbert.run")
        self._lock = threading.RLock()
        self._created_at = time.time()
        self._status = "queued"
        self._messages: deque[dict[str, Any]] = deque(maxlen=80)
        self._stages: dict[str, StageState] = {
            row["key"]: StageState(
                key=str(row["key"]),
                label=str(row["label"]),
                weight=float(row["weight"]),
            )
            for row in STAGE_DEFINITIONS
        }
        self._log(event="run_queued", message="Analysis job queued.")
        self._notify()

    def _iso(self, ts: Optional[float] = None) -> str:
        stamp = ts if ts is not None else time.time()
        return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()

    def _message_entry(self, *, level: str, message: str, stage: str = "", subtask: str = "") -> dict[str, Any]:
        return {
            "time": self._iso(),
            "level": level,
            "stage": stage,
            "subtask": subtask,
            "message": message,
        }

    def _log(self, *, event: str, message: str, stage: str = "", subtask: str = "", **fields: Any) -> None:
        payload = {
            "event": event,
            "run_id": self.run_id,
            "ticker": self.ticker,
            "stage": stage,
            "subtask": subtask,
            "message": message,
            "time": self._iso(),
        }
        payload.update(fields)
        self.logger.info(json.dumps(payload, ensure_ascii=True))
        self._messages.append(self._message_entry(level="info", message=message, stage=stage, subtask=subtask))

    def _weighted_percent_locked(self) -> float:
        total_weight = sum(stage.weight for stage in self._stages.values()) or 1.0
        completed = sum(stage.weight * max(0.0, min(1.0, stage.progress)) for stage in self._stages.values())
        return max(0.0, min(100.0, (completed / total_weight) * 100.0))

    def _active_stage_locked(self) -> str:
        loading = [stage.key for stage in self._stages.values() if stage.status == "loading"]
        if loading:
            return loading[0]
        done = [stage.key for stage in self._stages.values() if stage.status == "done"]
        if len(done) == len(self._stages):
            return ""
        for row in STAGE_DEFINITIONS:
            key = str(row["key"])
            if self._stages[key].status != "done":
                return key
        return ""

    def _snapshot_locked(self) -> dict[str, Any]:
        percent = self._weighted_percent_locked()
        active_stage = self._active_stage_locked()
        active_subtask = self._stages[active_stage].subtask if active_stage else ""
        return {
            "run_id": self.run_id,
            "ticker": self.ticker,
            "status": self._status,
            "percent": round(percent, 2),
            "active_stage": active_stage,
            "active_subtask": active_subtask,
            "updated_at": self._iso(),
            "stages": [
                {
                    "key": stage.key,
                    "label": stage.label,
                    "status": stage.status,
                    "progress": round(max(0.0, min(1.0, stage.progress)), 4),
                    "message": stage.message,
                    "subtask": stage.subtask,
                    "duration_ms": (
                        int(((stage.ended_at or time.time()) - stage.started_at) * 1000)
                        if stage.started_at
                        else None
                    ),
                }
                for stage in [self._stages[str(row["key"])] for row in STAGE_DEFINITIONS]
            ],
            "messages": list(self._messages),
        }

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._snapshot_locked()

    def _notify(self) -> None:
        if self.on_update is None:
            return
        try:
            self.on_update(self.snapshot())
        except Exception:
            # Progress callbacks must never break analysis execution.
            pass

    def mark_running(self, message: str = "Analysis job started.") -> None:
        with self._lock:
            self._status = "running"
            self._log(event="run_started", message=message)
        self._notify()

    def start_stage(self, stage_key: str, *, message: str, subtask: str = "") -> None:
        with self._lock:
            stage = self._stages.get(stage_key)
            if stage is None:
                return
            stage.status = "loading"
            stage.progress = max(stage.progress, 0.02)
            stage.started_at = stage.started_at or time.time()
            stage.message = message
            stage.subtask = subtask
            self._log(event="stage_started", stage=stage_key, subtask=subtask, message=message)
        self._notify()

    def update_stage(
        self,
        stage_key: str,
        *,
        progress: float,
        message: str,
        subtask: str = "",
    ) -> None:
        with self._lock:
            stage = self._stages.get(stage_key)
            if stage is None:
                return
            stage.status = "loading"
            stage.started_at = stage.started_at or time.time()
            stage.progress = max(stage.progress, max(0.0, min(0.99, progress)))
            stage.message = message
            stage.subtask = subtask
            self._log(
                event="stage_progress",
                stage=stage_key,
                subtask=subtask,
                message=message,
                stage_progress=round(stage.progress, 4),
                overall_percent=round(self._weighted_percent_locked(), 2),
            )
        self._notify()

    def complete_stage(self, stage_key: str, *, message: str) -> None:
        with self._lock:
            stage = self._stages.get(stage_key)
            if stage is None:
                return
            stage.status = "done"
            stage.progress = 1.0
            stage.subtask = ""
            stage.message = message
            stage.started_at = stage.started_at or time.time()
            stage.ended_at = time.time()
            self._log(
                event="stage_completed",
                stage=stage_key,
                message=message,
                duration_ms=int((stage.ended_at - stage.started_at) * 1000),
            )
        self._notify()

    def fail_stage(self, stage_key: str, *, message: str) -> None:
        with self._lock:
            stage = self._stages.get(stage_key)
            if stage is None:
                return
            stage.status = "error"
            stage.progress = max(stage.progress, 0.0)
            stage.message = message
            stage.ended_at = time.time()
            self._log(event="stage_failed", stage=stage_key, message=message)
        self._notify()

    def mark_completed(self, message: str = "Analysis completed.") -> None:
        with self._lock:
            self._status = "completed"
            self._log(
                event="run_completed",
                message=message,
                total_duration_ms=int((time.time() - self._created_at) * 1000),
            )
        self._notify()

    def mark_failed(self, message: str) -> None:
        with self._lock:
            self._status = "failed"
            self._log(
                event="run_failed",
                message=message,
                total_duration_ms=int((time.time() - self._created_at) * 1000),
            )
        self._notify()
