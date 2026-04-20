"""FastAPI entrypoint for the local FinBERT earnings analyzer site."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .analysis import build_analysis, build_sentiment_snapshot
from .jobs import AnalyzeJobManager
from .settings import settings

app = FastAPI(title="FinBERT Earnings Signals", version="0.4.0")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
job_manager = AnalyzeJobManager(settings=settings)


class AnalyzeJobRequest(BaseModel):
    ticker: str


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
        result = build_analysis(ticker=ticker, settings=settings)
        return result.model_dump()
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
    return job_manager.create_job(ticker=ticker, analysis_fn=build_analysis)


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
