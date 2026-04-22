"""FastAPI entrypoint for the local FinBERT earnings analyzer site."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import Optional

from .analysis import build_analysis, build_sentiment_snapshot
from .analysis_cache import (
    delete_cached_analysis,
    list_cached_analysis_summaries,
    load_cached_analysis,
    load_cached_analysis_envelope,
    write_cached_analysis,
)
from .jobs import AnalyzeJobManager
from .settings import settings

app = FastAPI(title="FinBERT Earnings Signals", version="0.4.0")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
job_manager = AnalyzeJobManager(settings=settings)


class AnalyzeRuntimeOverrides(BaseModel):
    news_limit: Optional[int] = Field(default=None, ge=10, le=120)
    news_pool_size: Optional[int] = Field(default=None, ge=80, le=1000)
    news_lookback_days: Optional[int] = Field(default=None, ge=3, le=365)
    social_limit: Optional[int] = Field(default=None, ge=10, le=120)
    social_pool_size: Optional[int] = Field(default=None, ge=80, le=1000)
    social_lookback_days: Optional[int] = Field(default=None, ge=3, le=365)
    use_cache: Optional[bool] = None
    score_weight_transcript: Optional[float] = Field(default=None, ge=0, le=100)
    score_weight_fundamentals: Optional[float] = Field(default=None, ge=0, le=100)
    score_weight_news: Optional[float] = Field(default=None, ge=0, le=100)
    score_weight_social: Optional[float] = Field(default=None, ge=0, le=100)
    news_enable_alpha_vantage: Optional[bool] = None
    news_enable_yahoo_finance: Optional[bool] = None
    social_enable_reddit: Optional[bool] = None
    social_enable_stocktwits: Optional[bool] = None


class AnalyzeJobRequest(BaseModel):
    ticker: str
    runtime_overrides: Optional[AnalyzeRuntimeOverrides] = None


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/charts-test", response_class=HTMLResponse)
def charts_test(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("charts_test.html", {"request": request})


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/analyze")
def analyze(ticker: str = Query(..., min_length=1, max_length=12)) -> dict:
    try:
        symbol = ticker.strip().upper()
        if settings.use_cache:
            cached = load_cached_analysis(cache_dir=settings.analysis_result_cache_dir, ticker=symbol)
            if cached is not None:
                return cached
        result = build_analysis(ticker=symbol, settings=settings)
        serialized = result.model_dump()
        write_cached_analysis(
            cache_dir=settings.analysis_result_cache_dir,
            ticker=symbol,
            result=serialized,
        )
        return serialized
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc


@app.post("/api/analyze/jobs")
def create_analyze_job(payload: AnalyzeJobRequest) -> dict:
    ticker = payload.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty.")
    runtime_overrides = (
        payload.runtime_overrides.model_dump(exclude_none=True)
        if payload.runtime_overrides is not None
        else None
    )
    return job_manager.create_job(ticker=ticker, analysis_fn=build_analysis, runtime_overrides=runtime_overrides)


@app.get("/api/analyze/jobs/{job_id}")
def get_analyze_job(job_id: str, include_result: bool = Query(False)) -> dict:
    job = job_manager.get_job(job_id, include_result=include_result)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


@app.get("/api/analyze/jobs/{job_id}/result")
def get_analyze_result(job_id: str) -> dict:
    job = job_manager.get_job(job_id, include_result=True)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job.get("status") != "completed":
        raise HTTPException(status_code=202, detail="Job is not completed yet.")
    return job


@app.get("/api/analyze/snapshot")
def analyze_snapshot(ticker: str = Query(..., min_length=1, max_length=12)) -> dict:
    try:
        return build_sentiment_snapshot(ticker=ticker, settings=settings)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {exc}") from exc


@app.get("/api/cache-runs")
def list_cache_runs() -> dict[str, list[dict]]:
    runs = list_cached_analysis_summaries(cache_dir=settings.analysis_result_cache_dir)
    return {"runs": runs}


@app.get("/api/cache-runs/{ticker}")
def get_cache_run(ticker: str) -> dict:
    symbol = ticker.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty.")

    envelope = load_cached_analysis_envelope(cache_dir=settings.analysis_result_cache_dir, ticker=symbol)
    if envelope is None:
        raise HTTPException(status_code=404, detail=f"No cached run found for {symbol}.")

    result = envelope.get("result")
    if not isinstance(result, dict):
        raise HTTPException(status_code=422, detail=f"Cached run for {symbol} is malformed.")

    return {
        "ticker": symbol,
        "updated_at": str(envelope.get("updated_at") or ""),
        "analysis_version": str(envelope.get("analysis_version") or ""),
        "result": result,
    }


@app.delete("/api/cache-runs/{ticker}")
def delete_cache_run(ticker: str) -> dict[str, object]:
    symbol = ticker.strip().upper()
    if not symbol:
        raise HTTPException(status_code=400, detail="Ticker cannot be empty.")

    deleted = delete_cached_analysis(cache_dir=settings.analysis_result_cache_dir, ticker=symbol)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No cached run found for {symbol}.")

    return {"deleted": True, "ticker": symbol}
