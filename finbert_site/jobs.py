"""In-memory async job manager for analysis runs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import uuid
from typing import Any, Callable, Optional

from .progress import RunProgressTracker
from .settings import Settings


@dataclass
class AnalyzeJob:
    job_id: str
    ticker: str
    created_at: float
    updated_at: float
    status: str
    progress: dict[str, Any]
    result: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class AnalyzeJobManager:
    """Simple in-memory job store with background execution."""

    def __init__(self, *, settings: Settings, ttl_seconds: int = 900, max_workers: int = 2) -> None:
        self.settings = settings
        self.ttl_seconds = max(120, int(ttl_seconds))
        self._lock = threading.RLock()
        self._jobs: dict[str, AnalyzeJob] = {}
        self._executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers)))

    def _now(self) -> float:
        return time.time()

    def _iso(self, ts: float) -> str:
        return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()

    def _cleanup_locked(self) -> None:
        now = self._now()
        stale_ids = [
            job_id
            for job_id, job in self._jobs.items()
            if job.status in {"completed", "failed"} and (now - job.updated_at) > self.ttl_seconds
        ]
        for job_id in stale_ids:
            self._jobs.pop(job_id, None)

    def _job_payload(self, job: AnalyzeJob, *, include_result: bool = False) -> dict[str, Any]:
        payload = {
            "job_id": job.job_id,
            "ticker": job.ticker,
            "status": job.status,
            "created_at": self._iso(job.created_at),
            "updated_at": self._iso(job.updated_at),
            "progress": job.progress,
            "error": job.error,
        }
        if include_result:
            payload["result"] = job.result
        return payload

    def _on_progress(self, job_id: str, snapshot: dict[str, Any]) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.progress = snapshot
            job.updated_at = self._now()

    def _run_job(
        self,
        *,
        job_id: str,
        ticker: str,
        tracker: RunProgressTracker,
        analysis_fn: Callable[..., Any],
    ) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.status = "running"
            job.updated_at = self._now()

        tracker.mark_running()
        try:
            result = analysis_fn(ticker=ticker, settings=self.settings, progress=tracker, run_id=job_id)
            serialized = result.model_dump() if hasattr(result, "model_dump") else result
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "completed"
                job.result = serialized
                job.error = None
                job.updated_at = self._now()
            tracker.mark_completed()
        except Exception as exc:
            error_message = str(exc)
            with self._lock:
                job = self._jobs.get(job_id)
                if job is None:
                    return
                job.status = "failed"
                job.error = error_message
                job.updated_at = self._now()
            tracker.mark_failed(error_message)

    def create_job(self, *, ticker: str, analysis_fn: Callable[..., Any]) -> dict[str, Any]:
        job_id = uuid.uuid4().hex[:12]
        created = self._now()
        tracker = RunProgressTracker(
            run_id=job_id,
            ticker=ticker,
            on_update=lambda snapshot: self._on_progress(job_id, snapshot),
        )
        job = AnalyzeJob(
            job_id=job_id,
            ticker=ticker,
            created_at=created,
            updated_at=created,
            status="queued",
            progress=tracker.snapshot(),
        )
        with self._lock:
            self._cleanup_locked()
            self._jobs[job_id] = job
        self._executor.submit(
            self._run_job,
            job_id=job_id,
            ticker=ticker,
            tracker=tracker,
            analysis_fn=analysis_fn,
        )
        return self._job_payload(job)

    def get_job(self, job_id: str, *, include_result: bool = False) -> Optional[dict[str, Any]]:
        with self._lock:
            self._cleanup_locked()
            job = self._jobs.get(job_id)
            if job is None:
                return None
            return self._job_payload(job, include_result=include_result)

