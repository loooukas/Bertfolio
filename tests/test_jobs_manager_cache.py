from __future__ import annotations

import time
from pathlib import Path

from finbert_site.analysis_cache import load_cached_analysis, write_cached_analysis
from finbert_site.jobs import AnalyzeJobManager
from finbert_site.settings import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        use_cache=True,
        analysis_result_cache_dir=str(tmp_path / "analysis_cache"),
    )


def _wait_for_terminal_job(
    manager: AnalyzeJobManager,
    job_id: str,
    *,
    timeout_seconds: float = 5.0,
) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        payload = manager.get_job(job_id, include_result=True)
        if payload and payload.get("status") in {"completed", "failed"}:
            return payload
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for job {job_id} to complete")


def test_job_manager_uses_cached_report_when_enabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    write_cached_analysis(
        cache_dir=settings.analysis_result_cache_dir,
        ticker="AAPL",
        result={"ticker": "AAPL", "analysis_version": "cached-v1", "cached": True},
    )

    manager = AnalyzeJobManager(settings=settings, max_workers=1)
    called = {"count": 0}

    def _analysis_fn(**kwargs):
        called["count"] += 1
        raise AssertionError("analysis_fn should not run on cache hit")

    queued = manager.create_job(
        ticker="AAPL",
        analysis_fn=_analysis_fn,
        runtime_overrides={"use_cache": True},
    )
    completed = _wait_for_terminal_job(manager, queued["job_id"])

    assert completed["status"] == "completed"
    assert completed["result"]["cached"] is True
    assert called["count"] == 0


def test_job_manager_overwrites_cached_report_when_cache_disabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    write_cached_analysis(
        cache_dir=settings.analysis_result_cache_dir,
        ticker="AAPL",
        result={"ticker": "AAPL", "analysis_version": "cached-old", "cached": True},
    )

    manager = AnalyzeJobManager(settings=settings, max_workers=1)

    def _analysis_fn(**kwargs):
        return {"ticker": "AAPL", "analysis_version": "fresh-v2", "cached": False}

    queued = manager.create_job(
        ticker="AAPL",
        analysis_fn=_analysis_fn,
        runtime_overrides={"use_cache": False},
    )
    completed = _wait_for_terminal_job(manager, queued["job_id"])

    assert completed["status"] == "completed"
    assert completed["result"]["analysis_version"] == "fresh-v2"
    assert completed["result"]["cached"] is False
    assert load_cached_analysis(cache_dir=settings.analysis_result_cache_dir, ticker="AAPL") == completed["result"]


def test_job_manager_writes_cache_on_miss_when_cache_enabled(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    manager = AnalyzeJobManager(settings=settings, max_workers=1)

    def _analysis_fn(**kwargs):
        return {"ticker": "MSFT", "analysis_version": "fresh-v1", "cached": False}

    queued = manager.create_job(
        ticker="MSFT",
        analysis_fn=_analysis_fn,
        runtime_overrides={"use_cache": True},
    )
    completed = _wait_for_terminal_job(manager, queued["job_id"])

    assert completed["status"] == "completed"
    assert completed["result"]["analysis_version"] == "fresh-v1"
    assert load_cached_analysis(cache_dir=settings.analysis_result_cache_dir, ticker="MSFT") == completed["result"]

