"""FastAPI entrypoint for the local bertfolio earnings analyzer site."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
import re
from statistics import mean
from typing import Any, Optional

from .analysis import (
    _aggregate_scores,
    _analyst_signal,
    _clamp_unit,
    _exclude_operator_rows,
    _fundamentals_blended_signal,
    _fundamentals_growth_signal,
    _label_from_sentiment_score,
    _management_only_rows,
    _normalize_speaker_role,
    _resolve_score_weights,
    _resolve_transcript_component,
    _stance_from_score,
    build_analysis,
    build_sentiment_snapshot,
    summarize_transcript_findings,
)
from .analysis_cache import (
    delete_cached_analysis,
    list_cached_analysis_summaries,
    load_cached_analysis,
    load_cached_analysis_envelope,
    write_cached_analysis,
)
from .jobs import AnalyzeJobManager
from .schemas import FundamentalsSummary, TranscriptSpeakerAnalysis
from .settings import Settings, settings


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    try:
        yield
    except asyncio.CancelledError:
        # Uvicorn reload + Ctrl+C can cancel lifespan receive during shutdown.
        # Swallow this expected cancellation to avoid noisy traceback logs.
        return


app = FastAPI(title="Bertfolio", version="0.4.0", lifespan=_app_lifespan)

job_manager = AnalyzeJobManager(settings=settings)

_OVERRIDABLE_SETTING_KEYS: tuple[str, ...] = (
    "news_limit",
    "news_pool_size",
    "news_lookback_days",
    "social_limit",
    "social_pool_size",
    "social_lookback_days",
    "use_cache",
    "score_weight_transcript",
    "score_weight_fundamentals",
    "score_weight_news",
    "score_weight_social",
    "transcript_internal_model_enabled",
    "transcript_internal_intercept",
    "transcript_internal_weight_sentiment",
    "transcript_internal_weight_confidence",
    "transcript_internal_weight_directness",
    "transcript_internal_weight_outlook_strength",
    "transcript_internal_weight_specificity",
    "transcript_internal_weight_risk_intensity",
    "news_enable_alpha_vantage",
    "news_enable_yahoo_finance",
    "social_enable_reddit",
    "social_enable_stocktwits",
)


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
    transcript_internal_model_enabled: Optional[bool] = None
    transcript_internal_intercept: Optional[float] = Field(default=None, ge=-5, le=5)
    transcript_internal_weight_sentiment: Optional[float] = Field(default=None, ge=-5, le=5)
    transcript_internal_weight_confidence: Optional[float] = Field(default=None, ge=-5, le=5)
    transcript_internal_weight_directness: Optional[float] = Field(default=None, ge=-5, le=5)
    transcript_internal_weight_outlook_strength: Optional[float] = Field(default=None, ge=-5, le=5)
    transcript_internal_weight_specificity: Optional[float] = Field(default=None, ge=-5, le=5)
    transcript_internal_weight_risk_intensity: Optional[float] = Field(default=None, ge=-5, le=5)
    news_enable_alpha_vantage: Optional[bool] = None
    news_enable_yahoo_finance: Optional[bool] = None
    social_enable_reddit: Optional[bool] = None
    social_enable_stocktwits: Optional[bool] = None


class AnalyzeJobRequest(BaseModel):
    ticker: str
    runtime_overrides: Optional[AnalyzeRuntimeOverrides] = None


def _safe_float(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_percent(value: Any) -> Optional[float]:
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None
    matched = re.search(r"([+-]?\d+(?:\.\d+)?)\s*%", value)
    if not matched:
        return None
    try:
        return float(matched.group(1))
    except ValueError:
        return None


def _settings_for_runtime_overrides(runtime_overrides: Optional[dict[str, Any]]) -> Settings:
    if not runtime_overrides:
        return settings
    sanitized = {
        key: value
        for key, value in runtime_overrides.items()
        if key in _OVERRIDABLE_SETTING_KEYS
    }
    if not sanitized:
        return settings
    return replace(settings, **sanitized)


def _refresh_cached_result_from_local_data(
    *,
    result: dict[str, Any],
    runtime_overrides: Optional[dict[str, Any]],
) -> dict[str, Any]:
    refreshed = deepcopy(result)
    transcript = refreshed.get("transcript")
    if not isinstance(transcript, dict):
        return refreshed

    speaker_rows_raw = transcript.get("speaker_analysis")
    if not isinstance(speaker_rows_raw, list):
        speaker_rows_raw = []

    transcript_docs = transcript.get("transcripts")
    if not isinstance(transcript_docs, list):
        transcript_docs = []

    section_role_index: dict[tuple[str, str, int, str], str] = {}
    section_role_by_speaker_and_type: dict[tuple[str, str], str] = {}
    role_counts_by_speaker: dict[str, dict[str, int]] = {}

    for transcript_doc in transcript_docs:
        if not isinstance(transcript_doc, dict):
            continue
        source_url = str(transcript_doc.get("source_url") or "").strip()
        sections = transcript_doc.get("sections")
        if not isinstance(sections, list):
            continue
        for section in sections:
            if not isinstance(section, dict):
                continue
            speaker = str(section.get("speaker") or "").strip().lower()
            section_type = str(section.get("section_type") or "").strip()
            role = str(section.get("speaker_role") or "").strip()
            if not speaker or not section_type or not role:
                continue

            order_index_raw = section.get("order_index")
            if isinstance(order_index_raw, int):
                section_role_index[(speaker, section_type, int(order_index_raw), source_url)] = role
                section_role_index[(speaker, section_type, int(order_index_raw), "")] = role
            section_role_by_speaker_and_type[(speaker, section_type)] = role

            normalized_role = _normalize_speaker_role(role)
            if normalized_role in {"analyst", "management"}:
                counts = role_counts_by_speaker.get(speaker, {"analyst": 0, "management": 0})
                counts[normalized_role] += 1
                role_counts_by_speaker[speaker] = counts

    dominant_role_by_speaker: dict[str, str] = {}
    for speaker, counts in role_counts_by_speaker.items():
        if counts["analyst"] == 0 and counts["management"] == 0:
            continue
        dominant_role_by_speaker[speaker] = "analyst" if counts["analyst"] > counts["management"] else "management"

    hydrated_rows: list[TranscriptSpeakerAnalysis] = []
    for raw_row in speaker_rows_raw:
        if not isinstance(raw_row, dict):
            continue
        row = dict(raw_row)
        speaker = str(row.get("speaker") or "").strip().lower()
        section_type = str(row.get("section_type") or "").strip()
        source_url = str(row.get("transcript_source_url") or "").strip()
        order_index_raw = row.get("order_index")
        order_index: Optional[int] = None
        if isinstance(order_index_raw, int):
            order_index = int(order_index_raw)
        elif isinstance(order_index_raw, float) and float(order_index_raw).is_integer():
            order_index = int(order_index_raw)

        if not str(row.get("speaker_role") or "").strip():
            inferred_role = None
            if speaker and section_type and order_index is not None:
                inferred_role = section_role_index.get((speaker, section_type, order_index, source_url))
                if inferred_role is None:
                    inferred_role = section_role_index.get((speaker, section_type, order_index, ""))
            if inferred_role is None and speaker and section_type:
                inferred_role = section_role_by_speaker_and_type.get((speaker, section_type))
            if inferred_role is None and speaker:
                inferred_role = dominant_role_by_speaker.get(speaker)
            if inferred_role:
                row["speaker_role"] = inferred_role

        try:
            hydrated = TranscriptSpeakerAnalysis.model_validate(row)
        except Exception:
            continue
        hydrated_rows.append(hydrated)

    if not hydrated_rows:
        return refreshed

    transcript["speaker_analysis"] = [row.model_dump() for row in hydrated_rows]

    non_operator_rows = _exclude_operator_rows(hydrated_rows)
    management_rows = _management_only_rows(non_operator_rows)

    transcript_direction = mean(row.sentiment_direction for row in management_rows) if management_rows else 0.0
    forward_strength = mean(row.forward_looking_strength for row in management_rows) if management_rows else 45.0
    confidence_score = mean(row.confidence for row in management_rows) if management_rows else 45.0
    evasiveness_score = mean(row.evasiveness for row in management_rows) if management_rows else 40.0

    # Keep transcript summary aligned with current management-only company-facing logic.
    if management_rows:
        latest_summary, _, _ = summarize_transcript_findings(management_rows)
    else:
        latest_summary = "Management-labeled transcript metrics are unavailable in this cached run."
    transcript["latest_summary"] = latest_summary

    fundamentals_payload = refreshed.get("fundamentals")
    fundamentals_raw = fundamentals_payload if isinstance(fundamentals_payload, dict) else {}
    if not isinstance(fundamentals_raw.get("quarterly"), list):
        fundamentals_raw["quarterly"] = []
    try:
        fundamentals = FundamentalsSummary.model_validate(fundamentals_raw)
    except Exception:
        fundamentals = FundamentalsSummary(quarterly=[])

    fundamentals_workspace = refreshed.get("fundamentals_workspace")
    analyst_signals = (
        fundamentals_workspace.get("analyst_signals")
        if isinstance(fundamentals_workspace, dict) and isinstance(fundamentals_workspace.get("analyst_signals"), list)
        else []
    )
    recommendation_mean: Optional[float] = None
    target_upside_pct: Optional[float] = None
    for signal in analyst_signals:
        if not isinstance(signal, dict):
            continue
        key = str(signal.get("key") or "").strip().lower()
        value = signal.get("value")
        note = signal.get("note")
        if key == "recommendation_mean":
            recommendation_mean = _safe_float(value)
        elif key == "target_mean":
            target_upside_pct = _parse_percent(note) or _parse_percent(value)

    growth_signal = _fundamentals_growth_signal(
        fundamentals.revenue_qoq_growth_pct,
        fundamentals.eps_qoq_growth_pct,
    )
    analyst_signal = _analyst_signal(recommendation_mean, target_upside_pct)
    fundamentals_signal = _fundamentals_blended_signal(growth_signal, analyst_signal)

    news_summary = refreshed.get("news_summary")
    social_summary = refreshed.get("social_summary")
    market_reaction = refreshed.get("market_reaction")

    news_avg = (
        _safe_float(news_summary.get("avg_sentiment_score"))
        if isinstance(news_summary, dict)
        else None
    )
    social_avg = (
        _safe_float(social_summary.get("avg_sentiment_score"))
        if isinstance(social_summary, dict)
        else None
    )

    if news_avg is None and isinstance(market_reaction, dict):
        news_items = market_reaction.get("news_items")
        if isinstance(news_items, list):
            scores = [
                _safe_float(item.get("sentiment_score"))
                for item in news_items
                if isinstance(item, dict)
            ]
            scores = [score for score in scores if score is not None]
            if scores:
                news_avg = mean(scores)
    if social_avg is None and isinstance(market_reaction, dict):
        social_items = market_reaction.get("social_items")
        if isinstance(social_items, list):
            scores = [
                _safe_float(item.get("sentiment_score"))
                for item in social_items
                if isinstance(item, dict)
            ]
            scores = [score for score in scores if score is not None]
            if scores:
                social_avg = mean(scores)

    news_avg = float(news_avg or 0.0)
    social_avg = float(social_avg or 0.0)

    scoring_settings = _settings_for_runtime_overrides(runtime_overrides)
    score_weights = _resolve_score_weights(scoring_settings)

    transcript_component, _ = _resolve_transcript_component(
        management_speaker_analysis=management_rows,
        settings=scoring_settings,
    )
    overall_score = _clamp_unit(
        transcript_component * score_weights.get("transcript", 0.40)
        + fundamentals_signal * score_weights.get("fundamentals", 0.35)
        + news_avg * score_weights.get("news", 0.15)
        + social_avg * score_weights.get("social", 0.10)
    )
    overall_label = _label_from_sentiment_score(overall_score)

    aggregate = _aggregate_scores(management_rows, fundamentals, news_avg, social_avg)

    refreshed["overall_sentiment_score"] = round(overall_score, 4)
    refreshed["overall_sentiment_label"] = overall_label
    refreshed["aggregate_scores"] = aggregate.model_dump()

    run_summary = refreshed.get("run_summary")
    if isinstance(run_summary, dict):
        run_summary["overall_score"] = round(overall_score, 4)
        run_summary["overall_label"] = _stance_from_score(overall_score)

    overview = refreshed.get("overview")
    if isinstance(overview, dict):
        overview["stance_label"] = _stance_from_score(overall_score)
        coverage_value = f"{int(transcript.get('transcript_count_found') or 0)}/{int(transcript.get('transcript_count_requested') or 0)}"
        replacements = {
            "management_confidence": f"{confidence_score:.1f}",
            "evasiveness": f"{evasiveness_score:.1f}",
            "outlook_strength": f"{forward_strength:.1f}",
            "transcript_coverage": coverage_value,
        }
        metrics = overview.get("metrics")
        if isinstance(metrics, list):
            seen_keys: set[str] = set()
            for metric in metrics:
                if not isinstance(metric, dict):
                    continue
                key = str(metric.get("key") or "").strip()
                if not key:
                    continue
                if key in replacements:
                    metric["value"] = replacements[key]
                    seen_keys.add(key)
            if seen_keys != set(replacements.keys()):
                missing_keys = [key for key in replacements.keys() if key not in seen_keys]
                for key in missing_keys:
                    metrics.append(
                        {
                            "key": key,
                            "label": key.replace("_", " ").title(),
                            "value": replacements[key],
                        }
                    )

    return refreshed


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
    runtime_overrides = envelope.get("runtime_overrides")
    runtime_overrides = runtime_overrides if isinstance(runtime_overrides, dict) else None
    refreshed_result = _refresh_cached_result_from_local_data(
        result=result,
        runtime_overrides=runtime_overrides,
    )

    return {
        "ticker": symbol,
        "updated_at": str(envelope.get("updated_at") or ""),
        "analysis_version": str(envelope.get("analysis_version") or ""),
        "result": refreshed_result,
        "recomputed_from_cached_data": True,
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
