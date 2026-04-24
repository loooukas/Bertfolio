#!/usr/bin/env python3
"""Build one-row-per-earnings-event historical table for score calibration."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass, replace
from datetime import timedelta
import glob
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from finbert_site.normalizer import build_speaker_analysis
from finbert_site.providers import (
    enrich_fundamentals_with_alpha_validation,
    fetch_fundamentals,
    fetch_news_multi_source,
    fetch_social_multi_source,
)
from finbert_site.schemas import TranscriptSectionBlock
from finbert_site.settings import Settings
from scripts.score_calibration_utils import (
    ProgressBar,
    clamp,
    compute_event_window,
    date_to_str,
    ensure_dir,
    fetch_close_series,
    fetch_close_series_with_diagnostics,
    mean_or_none,
    parse_date,
    read_structured_records,
    safe_float,
    write_json,
)

DEFAULT_NORMALIZED_DIR = "output/teacher_dataset_kaggle_v2/normalized_transcripts"
DEFAULT_ANALYSIS_CACHE_GLOB = "output/analysis_cache/*.json"
DEFAULT_OUTPUT_DIR = "output/score_calibration"
DEFAULT_OUTPUT_FILE = "historical_event_table.csv"

_POSITIVE_FINANCE_TERMS = {
    "beat",
    "beats",
    "growth",
    "improve",
    "improved",
    "strong",
    "strength",
    "upside",
    "momentum",
    "outperform",
    "expansion",
    "record",
    "profit",
    "profitable",
    "confidence",
    "opportunity",
    "resilient",
}
_NEGATIVE_FINANCE_TERMS = {
    "miss",
    "missed",
    "decline",
    "weak",
    "weakness",
    "downside",
    "headwind",
    "risk",
    "pressure",
    "slowdown",
    "uncertain",
    "uncertainty",
    "loss",
    "losses",
    "evasive",
    "challenging",
}
_DATE_FROM_URL_RE = re.compile(r"/earnings/call-transcripts/(\d{4})/(\d{2})/(\d{2})/")


@dataclass
class EventRow:
    ticker: str
    company_name: Optional[str]
    event_date: Optional[str]
    quarter_label: Optional[str]
    transcript_source_url: Optional[str]
    transcript_id: str
    transcript_coverage: Optional[float]
    management_confidence: Optional[float]
    management_directness: Optional[float]
    management_outlook_strength: Optional[float]
    management_specificity: Optional[float]
    management_risk_intensity: Optional[float]
    transcript_sentiment_directional_score: Optional[float]
    management_block_count: int
    analyst_block_count: int
    qa_block_count: int
    prepared_remarks_block_count: int
    fundamentals_signal: Optional[float] = None
    news_signal: Optional[float] = None
    social_signal: Optional[float] = None
    current_handset_overall_score: Optional[float] = None
    current_handset_transcript_score: Optional[float] = None
    fundamentals_revenue_qoq_growth_pct: Optional[float] = None
    fundamentals_eps_qoq_growth_pct: Optional[float] = None
    news_count_snapshot: Optional[float] = None
    social_count_snapshot: Optional[float] = None
    component_source: Optional[str] = None
    close_t_minus_1: Optional[float] = None
    close_t: Optional[float] = None
    close_t_plus_1: Optional[float] = None
    close_t_plus_3: Optional[float] = None
    close_t_plus_5: Optional[float] = None
    stock_return_1d: Optional[float] = None
    stock_return_3d: Optional[float] = None
    stock_return_5d: Optional[float] = None
    benchmark_t_minus_1: Optional[float] = None
    benchmark_t: Optional[float] = None
    benchmark_t_plus_1: Optional[float] = None
    benchmark_t_plus_3: Optional[float] = None
    benchmark_t_plus_5: Optional[float] = None
    benchmark_return_1d: Optional[float] = None
    benchmark_return_3d: Optional[float] = None
    benchmark_return_5d: Optional[float] = None
    abnormal_return_1d: Optional[float] = None
    abnormal_return_3d: Optional[float] = None
    abnormal_return_5d: Optional[float] = None
    binary_abnormal_up_1d: Optional[int] = None
    binary_abnormal_up_3d: Optional[int] = None
    binary_abnormal_up_5d: Optional[int] = None
    aligned_trading_date: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class ComponentFeatureLookup:
    def __init__(self) -> None:
        self.by_transcript_id: dict[str, dict[str, Any]] = {}
        self.by_source_url: dict[str, dict[str, Any]] = {}
        self.by_ticker_date: dict[tuple[str, str], dict[str, Any]] = {}
        self.by_ticker_quarter: dict[tuple[str, str], dict[str, Any]] = {}
        self.by_ticker: dict[str, dict[str, Any]] = {}

    def add(self, *, source: str, row: dict[str, Any]) -> None:
        payload = dict(row)
        payload["component_source"] = source
        transcript_id = str(payload.get("transcript_id") or "").strip()
        source_url = str(payload.get("transcript_source_url") or "").strip()
        ticker = str(payload.get("ticker") or "").upper().strip()
        event_date = str(payload.get("event_date") or "").strip()
        quarter_label = str(payload.get("quarter_label") or "").strip()

        if transcript_id:
            self.by_transcript_id[transcript_id] = payload
        if source_url:
            self.by_source_url[source_url] = payload
        if ticker and event_date:
            self.by_ticker_date[(ticker, event_date)] = payload
        if ticker and quarter_label:
            self.by_ticker_quarter[(ticker, quarter_label)] = payload
        if ticker:
            self.by_ticker[ticker] = payload

    def lookup(
        self,
        *,
        ticker: str,
        event_date: Optional[str],
        quarter_label: Optional[str],
        transcript_id: str,
        transcript_source_url: Optional[str],
    ) -> Optional[dict[str, Any]]:
        symbol = ticker.upper().strip()
        src_url = (transcript_source_url or "").strip()

        if transcript_id and transcript_id in self.by_transcript_id:
            return dict(self.by_transcript_id[transcript_id])
        if src_url and src_url in self.by_source_url:
            return dict(self.by_source_url[src_url])
        if event_date and (symbol, event_date) in self.by_ticker_date:
            return dict(self.by_ticker_date[(symbol, event_date)])
        if quarter_label and (symbol, quarter_label) in self.by_ticker_quarter:
            return dict(self.by_ticker_quarter[(symbol, quarter_label)])
        if symbol in self.by_ticker:
            return dict(self.by_ticker[symbol])
        return None


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build historical earnings-event table for score calibration.")
    parser.add_argument("--normalized-transcripts-dir", default=DEFAULT_NORMALIZED_DIR)
    parser.add_argument("--normalized-transcript-glob", default="*/*.json")
    parser.add_argument("--analysis-cache-glob", default=DEFAULT_ANALYSIS_CACHE_GLOB)
    parser.add_argument("--component-features-input", help="Optional CSV/JSON/JSONL component feature rows.")
    parser.add_argument(
        "--component-source",
        choices=["none", "analysis_cache", "live_current", "analysis_cache_then_live"],
        default="analysis_cache_then_live",
        help="How fundamentals/news/social component features are sourced.",
    )
    parser.add_argument("--benchmark-ticker", default="SPY")
    parser.add_argument(
        "--event-alignment-mode",
        choices=["on_or_next_trading_day", "next_trading_day"],
        default="on_or_next_trading_day",
    )
    parser.add_argument("--start-date", help="Filter events on/after YYYY-MM-DD.")
    parser.add_argument("--end-date", help="Filter events on/before YYYY-MM-DD.")
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument(
        "--sentiment-mode",
        choices=["lexical", "finbert", "neutral"],
        default="lexical",
        help="Sentiment function for transcript directional scores when re-scoring blocks.",
    )
    parser.add_argument(
        "--transcript-metric-mode",
        choices=["fast_recompute", "site_default"],
        default="fast_recompute",
        help=(
            "Transcript metric mode: "
            "fast_recompute disables student/AI extras for speed; "
            "site_default uses current site Settings exactly."
        ),
    )
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--no-progress", action="store_true", default=False, help="Disable terminal progress bars.")
    return parser.parse_args(argv)


def _normalize_role(value: Optional[str]) -> str:
    lowered = (value or "").strip().lower()
    if lowered in {"management", "executive"}:
        return "management"
    if lowered in {"analyst", "research"}:
        return "analyst"
    if lowered in {"operator", "moderator", "host"}:
        return "operator"
    return lowered


def _find_event_date(document: dict[str, Any], transcript_id: str, quarter_label: Optional[str]) -> Optional[date]:
    explicit = parse_date(document.get("published_date"))
    if explicit is not None:
        return explicit

    source_url = str(document.get("source_url") or "")
    if source_url:
        match = _DATE_FROM_URL_RE.search(source_url)
        if match:
            inferred = parse_date(f"{match.group(1)}-{match.group(2)}-{match.group(3)}")
            if inferred is not None:
                return inferred

    if quarter_label and re.match(r"^\d{4}-Q[1-4]$", quarter_label):
        year = int(quarter_label[:4])
        quarter = int(quarter_label[-1])
        month = quarter * 3
        return parse_date(f"{year:04d}-{month:02d}-15")

    match = re.search(r"_(\d{4})q([1-4])_", transcript_id.lower())
    if match:
        year = int(match.group(1))
        quarter = int(match.group(2))
        month = quarter * 3
        return parse_date(f"{year:04d}-{month:02d}-15")

    return None


def _extract_sections(document: dict[str, Any]) -> list[TranscriptSectionBlock]:
    out: list[TranscriptSectionBlock] = []
    for idx, raw in enumerate(document.get("sections") or []):
        if not isinstance(raw, dict):
            continue
        payload = dict(raw)
        if "order_index" not in payload:
            payload["order_index"] = idx
        if "evidence_snippets" not in payload:
            payload["evidence_snippets"] = []
        try:
            out.append(TranscriptSectionBlock.model_validate(payload))
        except Exception:
            continue
    return out


def _build_lexical_sentiment_fn() -> Callable[[str], dict[str, float | str]]:
    def score(text: str) -> dict[str, float | str]:
        lowered = re.sub(r"[^a-z0-9\s]", " ", str(text or "").lower())
        tokens = [tok for tok in lowered.split() if tok]
        if not tokens:
            return {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0,
                "directional_score": 0.0,
                "label": "mixed",
            }
        pos_hits = sum(1 for tok in tokens if tok in _POSITIVE_FINANCE_TERMS)
        neg_hits = sum(1 for tok in tokens if tok in _NEGATIVE_FINANCE_TERMS)
        directional = (pos_hits - neg_hits) / max(3.0, (pos_hits + neg_hits + 3.0))
        directional = clamp(float(directional), -1.0, 1.0)
        positive = max(0.0, directional)
        negative = max(0.0, -directional)
        neutral = max(0.0, 1.0 - abs(directional))
        label = "bullish" if directional > 0.12 else "bearish" if directional < -0.12 else "mixed"
        return {
            "positive": positive,
            "negative": negative,
            "neutral": neutral,
            "directional_score": directional,
            "label": label,
        }

    return score


def _build_neutral_sentiment_fn() -> Callable[[str], dict[str, float | str]]:
    def score(_text: str) -> dict[str, float | str]:
        return {
            "positive": 0.0,
            "negative": 0.0,
            "neutral": 1.0,
            "directional_score": 0.0,
            "label": "mixed",
        }

    return score


def _build_finbert_sentiment_fn(settings: Settings) -> Callable[[str], dict[str, float | str]]:
    from finbert_site.finbert_model import get_engine

    engine = get_engine(settings.finbert_model_name)

    def score(text: str) -> dict[str, float | str]:
        return engine.score_text(text)

    return score


def _choose_sentiment_fn(mode: str, settings: Settings) -> Callable[[str], dict[str, float | str]]:
    if mode == "neutral":
        return _build_neutral_sentiment_fn()
    if mode == "finbert":
        try:
            return _build_finbert_sentiment_fn(settings)
        except Exception as exc:
            print(f"[event-table] FinBERT sentiment unavailable ({exc}); falling back to lexical.")
            return _build_lexical_sentiment_fn()
    return _build_lexical_sentiment_fn()


def _component_fields_from_analysis_result(result: dict[str, Any]) -> dict[str, Any]:
    analyst_signals: dict[str, float] = {}
    for row in result.get("analyst_team") or []:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip().lower()
        score = safe_float(row.get("signal_score"))
        if name and score is not None:
            analyst_signals[name] = float(score)

    fundamentals = result.get("fundamentals") or {}
    news_summary = result.get("news_summary") or {}
    social_summary = result.get("social_summary") or {}

    return {
        "fundamentals_signal": analyst_signals.get("fundamentals"),
        "news_signal": analyst_signals.get("news"),
        "social_signal": analyst_signals.get("social"),
        "current_handset_overall_score": safe_float(result.get("overall_sentiment_score")),
        "fundamentals_revenue_qoq_growth_pct": safe_float(fundamentals.get("revenue_qoq_growth_pct")),
        "fundamentals_eps_qoq_growth_pct": safe_float(fundamentals.get("eps_qoq_growth_pct")),
        "news_count_snapshot": safe_float(news_summary.get("article_count")),
        "social_count_snapshot": safe_float(social_summary.get("post_count")),
        "analysis_transcript_signal_fallback": analyst_signals.get("transcript"),
    }


def _load_analysis_cache_lookup(glob_pattern: str) -> ComponentFeatureLookup:
    lookup = ComponentFeatureLookup()
    paths = sorted(glob.glob(glob_pattern))
    if not paths:
        return lookup

    for path_str in paths:
        path = Path(path_str)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue

        result = payload.get("result") if isinstance(payload, dict) and isinstance(payload.get("result"), dict) else payload
        if not isinstance(result, dict):
            continue

        ticker = str(result.get("ticker") or payload.get("ticker") or "").upper().strip()
        if not ticker:
            continue

        base = _component_fields_from_analysis_result(result)
        transcript_docs = ((result.get("transcript") or {}).get("transcripts") or []) if isinstance(result.get("transcript"), dict) else []
        transcript_rows = result.get("transcripts") or []

        if isinstance(transcript_rows, list) and transcript_rows:
            for idx, transcript_row in enumerate(transcript_rows):
                if not isinstance(transcript_row, dict):
                    continue
                transcript_signal = safe_float(((transcript_row.get("sentiment") or {}).get("directional_score")))
                year = safe_float(transcript_row.get("year"))
                quarter = safe_float(transcript_row.get("quarter"))
                quarter_label = None
                if year is not None and quarter is not None:
                    quarter_label = f"{int(year):04d}-Q{int(quarter)}"

                event_date = str(transcript_row.get("date") or "").strip() or None
                source_url = None
                if idx < len(transcript_docs) and isinstance(transcript_docs[idx], dict):
                    source_url = str(transcript_docs[idx].get("source_url") or "").strip() or None

                merged = {
                    "ticker": ticker,
                    "event_date": event_date,
                    "quarter_label": quarter_label,
                    "transcript_source_url": source_url,
                    "current_handset_transcript_score": (
                        transcript_signal if transcript_signal is not None else base.get("analysis_transcript_signal_fallback")
                    ),
                    **base,
                }
                lookup.add(source="analysis_cache", row=merged)
        else:
            lookup.add(
                source="analysis_cache",
                row={
                    "ticker": ticker,
                    **base,
                    "current_handset_transcript_score": base.get("analysis_transcript_signal_fallback"),
                },
            )

    return lookup


def _coerce_component_payload(raw: dict[str, Any]) -> dict[str, Any]:
    out = dict(raw)
    for key in [
        "fundamentals_signal",
        "news_signal",
        "social_signal",
        "current_handset_overall_score",
        "current_handset_transcript_score",
        "fundamentals_revenue_qoq_growth_pct",
        "fundamentals_eps_qoq_growth_pct",
        "news_count_snapshot",
        "social_count_snapshot",
    ]:
        out[key] = safe_float(out.get(key))

    out["ticker"] = str(out.get("ticker") or "").upper().strip() or None
    out["event_date"] = str(out.get("event_date") or "").strip() or None
    out["quarter_label"] = str(out.get("quarter_label") or "").strip() or None
    out["transcript_id"] = str(out.get("transcript_id") or "").strip() or None
    out["transcript_source_url"] = str(out.get("transcript_source_url") or "").strip() or None
    return out


def _load_external_component_lookup(path_str: Optional[str]) -> ComponentFeatureLookup:
    lookup = ComponentFeatureLookup()
    if not path_str:
        return lookup

    path = Path(path_str)
    if not path.exists():
        raise RuntimeError(f"Component feature input not found: {path}")

    for raw in read_structured_records(path):
        payload = _coerce_component_payload(raw)
        lookup.add(source="external_component_file", row=payload)
    return lookup


class LiveComponentFetcher:
    def __init__(self, settings: Settings, sentiment_fn: Callable[[str], dict[str, float | str]]) -> None:
        self.settings = settings
        self.sentiment_fn = sentiment_fn
        self.cache: dict[str, dict[str, Any]] = {}
        self.diag_cache: dict[str, dict[str, Any]] = {}

    def fetch(self, ticker: str, company_name: Optional[str]) -> dict[str, Any]:
        payload, _diag = self.fetch_with_diagnostics(ticker=ticker, company_name=company_name)
        return payload

    def fetch_with_diagnostics(self, ticker: str, company_name: Optional[str]) -> tuple[dict[str, Any], dict[str, Any]]:
        symbol = ticker.upper().strip()
        if symbol in self.cache and symbol in self.diag_cache:
            return dict(self.cache[symbol]), dict(self.diag_cache[symbol])

        diagnostics: dict[str, Any] = {
            "ticker": symbol,
            "fundamentals": {"status": "not_attempted"},
            "news": {"status": "not_attempted"},
            "social": {"status": "not_attempted"},
        }

        fundamentals: dict[str, Any] = {}
        fundamentals_validation: dict[str, Any] = {}
        try:
            fundamentals_raw = fetch_fundamentals(symbol)
            fundamentals, fundamentals_validation = enrich_fundamentals_with_alpha_validation(
                symbol=symbol,
                settings=self.settings,
                yahoo_payload=fundamentals_raw,
            )
            diagnostics["fundamentals"] = {
                "status": "ok",
                "alpha_source_used": bool(fundamentals_validation.get("alpha_source_used", False)),
                "mismatch_count": int(len(fundamentals_validation.get("mismatches") or [])),
                "notes": [str(item) for item in (fundamentals_validation.get("notes") or [])[:5]],
            }
        except Exception as exc:
            fundamentals = {}
            fundamentals_validation = {}
            diagnostics["fundamentals"] = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }

        rev_qoq = safe_float(fundamentals.get("revenue_qoq_growth_pct"))
        eps_qoq = safe_float(fundamentals.get("eps_qoq_growth_pct"))
        fundamentals_signal = None
        if rev_qoq is not None or eps_qoq is not None:
            rev = float(rev_qoq or 0.0)
            eps = float(eps_qoq or 0.0)
            fundamentals_signal = clamp(((rev * 0.55 + eps * 0.45) / 50.0), -1.0, 1.0)

        news_signal = None
        social_signal = None
        news_count = 0
        social_count = 0

        try:
            news, warnings, audit = fetch_news_multi_source(
                symbol,
                self.settings,
                company_name=company_name,
                enable_alpha=self.settings.news_enable_alpha_vantage,
                enable_yahoo=self.settings.news_enable_yahoo_finance,
            )
            news_values = [safe_float(getattr(item, "sentiment_score", None)) for item in news]
            news_signal = mean_or_none(news_values)
            news_count = len(news)
            diagnostics["news"] = {
                "status": "ok",
                "records": int(len(news)),
                "warnings": [str(item) for item in warnings[:5]],
                "fetched_pool": int(getattr(audit, "fetched_pool", 0)),
                "parsed_records": int(getattr(audit, "parsed_records", 0)),
                "normalized_records": int(getattr(audit, "normalized_records", 0)),
            }
        except Exception as exc:
            news_signal = None
            diagnostics["news"] = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }

        try:
            social, warnings, audit = fetch_social_multi_source(
                symbol,
                self.settings,
                company_name=company_name,
                enable_reddit=self.settings.social_enable_reddit,
                enable_stocktwits=self.settings.social_enable_stocktwits,
            )
            social_values: list[Optional[float]] = []
            for item in social:
                text = f"{getattr(item, 'title', '')}. {getattr(item, 'body', '')}"
                scored = self.sentiment_fn(text)
                social_values.append(safe_float(scored.get("directional_score")))
            social_signal = mean_or_none(social_values)
            social_count = len(social)
            diagnostics["social"] = {
                "status": "ok",
                "records": int(len(social)),
                "warnings": [str(item) for item in warnings[:5]],
                "fetched_pool": int(getattr(audit, "fetched_pool", 0)),
                "parsed_records": int(getattr(audit, "parsed_records", 0)),
                "normalized_records": int(getattr(audit, "normalized_records", 0)),
            }
        except Exception as exc:
            social_signal = None
            diagnostics["social"] = {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }

        payload = {
            "fundamentals_signal": fundamentals_signal,
            "news_signal": news_signal,
            "social_signal": social_signal,
            "current_handset_overall_score": None,
            "current_handset_transcript_score": None,
            "fundamentals_revenue_qoq_growth_pct": rev_qoq,
            "fundamentals_eps_qoq_growth_pct": eps_qoq,
            "news_count_snapshot": float(news_count),
            "social_count_snapshot": float(social_count),
            "component_source": "live_current_snapshot",
            "fundamentals_alpha_source_used": bool(fundamentals_validation.get("alpha_source_used", False)),
        }
        self.cache[symbol] = payload
        self.diag_cache[symbol] = diagnostics
        return dict(payload), dict(diagnostics)


def _build_event_rows(
    *,
    args: argparse.Namespace,
    settings: Settings,
    sentiment_fn: Callable[[str], dict[str, float | str]],
    analysis_lookup: ComponentFeatureLookup,
    external_lookup: ComponentFeatureLookup,
    live_fetcher: LiveComponentFetcher,
) -> tuple[list[EventRow], dict[str, dict[str, Any]]]:
    normalized_dir = Path(args.normalized_transcripts_dir)
    if not normalized_dir.exists():
        raise RuntimeError(f"Normalized transcript directory not found: {normalized_dir}")

    if args.transcript_metric_mode == "site_default":
        metric_settings = settings
    else:
        metric_settings = replace(
            settings,
            transcript_feature_ai_enabled=False,
            use_student_confidence=False,
            use_student_directness=False,
            use_student_outlook_strength=False,
            use_student_specificity=False,
            use_student_risk_intensity=False,
            student_metrics_shadow_compare=False,
        )

    paths = sorted(normalized_dir.glob(args.normalized_transcript_glob))
    if args.max_events > 0:
        paths = paths[: int(args.max_events)]

    rows: list[EventRow] = []
    component_fetch_diagnostics: dict[str, dict[str, Any]] = {}
    progress = ProgressBar(total=len(paths), label="Phase1 Event Rows", enabled=not args.no_progress)

    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(payload, dict):
            continue

        document = payload.get("document") if isinstance(payload.get("document"), dict) else payload
        if not isinstance(document, dict):
            continue

        ticker = str(document.get("ticker") or "").upper().strip()
        if not ticker:
            continue

        transcript_id = str(payload.get("transcript_id") or path.stem)
        quarter_label = str(payload.get("quarter") or "").strip() or None
        company_name = str(document.get("company_name") or "").strip() or None
        source_url = str(document.get("source_url") or "").strip() or None

        event_date_obj = _find_event_date(document, transcript_id=transcript_id, quarter_label=quarter_label)
        event_date = date_to_str(event_date_obj) if event_date_obj is not None else None

        sections = _extract_sections(document)
        if not sections:
            continue

        classifier_warnings: list[str] = []
        classifier_diagnostics: list[str] = []
        speaker_rows = build_speaker_analysis(
            sections,
            score_text_fn=sentiment_fn,
            settings=metric_settings,
            classifier_warnings=classifier_warnings,
            classifier_diagnostics=classifier_diagnostics,
        )

        management_rows = [row for row in speaker_rows if _normalize_role(row.speaker_role) == "management"]
        non_operator_blocks = [section for section in sections if _normalize_role(section.speaker_role) != "operator"]

        management_block_count = sum(1 for section in sections if _normalize_role(section.speaker_role) == "management")
        analyst_block_count = sum(1 for section in sections if _normalize_role(section.speaker_role) == "analyst")
        qa_block_count = sum(1 for section in sections if str(section.section_type) == "qa")
        prepared_count = sum(1 for section in sections if str(section.section_type) == "prepared_remarks")

        transcript_coverage = None
        if non_operator_blocks:
            transcript_coverage = len(management_rows) / float(len(non_operator_blocks))

        management_confidence = mean_or_none(row.confidence for row in management_rows)
        management_directness = mean_or_none((100.0 - float(row.evasiveness)) for row in management_rows)
        management_outlook = mean_or_none(row.forward_looking_strength for row in management_rows)
        management_specificity = mean_or_none(row.specificity for row in management_rows)
        management_risk = mean_or_none(row.risk_language_intensity for row in management_rows)
        transcript_sentiment = mean_or_none(row.sentiment_direction for row in management_rows)

        event_row = EventRow(
            ticker=ticker,
            company_name=company_name,
            event_date=event_date,
            quarter_label=quarter_label,
            transcript_source_url=source_url,
            transcript_id=transcript_id,
            transcript_coverage=transcript_coverage,
            management_confidence=management_confidence,
            management_directness=management_directness,
            management_outlook_strength=management_outlook,
            management_specificity=management_specificity,
            management_risk_intensity=management_risk,
            transcript_sentiment_directional_score=transcript_sentiment,
            management_block_count=management_block_count,
            analyst_block_count=analyst_block_count,
            qa_block_count=qa_block_count,
            prepared_remarks_block_count=prepared_count,
            current_handset_transcript_score=transcript_sentiment,
        )

        component_payload: Optional[dict[str, Any]] = None

        external_hit = external_lookup.lookup(
            ticker=ticker,
            event_date=event_date,
            quarter_label=quarter_label,
            transcript_id=transcript_id,
            transcript_source_url=source_url,
        )
        if external_hit is not None:
            component_payload = dict(external_hit)

        if component_payload is None and args.component_source in {"analysis_cache", "analysis_cache_then_live"}:
            analysis_hit = analysis_lookup.lookup(
                ticker=ticker,
                event_date=event_date,
                quarter_label=quarter_label,
                transcript_id=transcript_id,
                transcript_source_url=source_url,
            )
            if analysis_hit is not None:
                component_payload = dict(analysis_hit)

        if component_payload is None and args.component_source in {"live_current", "analysis_cache_then_live"}:
            component_payload, live_diag = live_fetcher.fetch_with_diagnostics(ticker=ticker, company_name=company_name)
            component_fetch_diagnostics[ticker] = live_diag

        if component_payload is not None:
            event_row.fundamentals_signal = safe_float(component_payload.get("fundamentals_signal"))
            event_row.news_signal = safe_float(component_payload.get("news_signal"))
            event_row.social_signal = safe_float(component_payload.get("social_signal"))
            event_row.current_handset_overall_score = safe_float(component_payload.get("current_handset_overall_score"))
            event_row.current_handset_transcript_score = safe_float(
                component_payload.get("current_handset_transcript_score")
            ) or event_row.current_handset_transcript_score
            event_row.fundamentals_revenue_qoq_growth_pct = safe_float(
                component_payload.get("fundamentals_revenue_qoq_growth_pct")
            )
            event_row.fundamentals_eps_qoq_growth_pct = safe_float(
                component_payload.get("fundamentals_eps_qoq_growth_pct")
            )
            event_row.news_count_snapshot = safe_float(component_payload.get("news_count_snapshot"))
            event_row.social_count_snapshot = safe_float(component_payload.get("social_count_snapshot"))
            event_row.component_source = str(component_payload.get("component_source") or "unknown")

            if event_row.current_handset_overall_score is None:
                ts = safe_float(event_row.current_handset_transcript_score)
                fs = safe_float(event_row.fundamentals_signal)
                ns = safe_float(event_row.news_signal)
                ss = safe_float(event_row.social_signal)
                if ts is not None and fs is not None and ns is not None and ss is not None:
                    event_row.current_handset_overall_score = (
                        ts * 0.40 + fs * 0.35 + ns * 0.15 + ss * 0.10
                    )

        rows.append(event_row)
        progress.update(1)

    progress.close()

    return rows, component_fetch_diagnostics


def _apply_event_date_filters(
    rows: list[EventRow],
    *,
    start_date: Optional[date],
    end_date: Optional[date],
) -> list[EventRow]:
    filtered: list[EventRow] = []
    for row in rows:
        if row.event_date is None:
            continue
        event_dt = parse_date(row.event_date)
        if event_dt is None:
            continue
        if start_date is not None and event_dt < start_date:
            continue
        if end_date is not None and event_dt > end_date:
            continue
        filtered.append(row)
    return filtered


def _attach_market_outcomes(
    rows: list[EventRow],
    *,
    benchmark_ticker: str,
    alignment_mode: str,
    show_progress: bool,
) -> dict[str, Any]:
    if not rows:
        return {"ticker_price_diagnostics": {}, "benchmark_price_diagnostics": {}}

    event_dates = [parse_date(row.event_date) for row in rows if row.event_date]
    event_dates = [item for item in event_dates if item is not None]
    if not event_dates:
        return {"ticker_price_diagnostics": {}, "benchmark_price_diagnostics": {}}

    start = min(event_dates) - timedelta(days=30)
    end = max(event_dates) + timedelta(days=30)

    per_ticker: dict[str, pd.Series] = {}
    ticker_price_diag: dict[str, Any] = {}
    tickers = sorted({row.ticker for row in rows})
    fetch_progress = ProgressBar(total=len(tickers), label="Phase1 Prices", enabled=show_progress)
    for ticker in tickers:
        try:
            series, diag = fetch_close_series_with_diagnostics(ticker, start, end)
            per_ticker[ticker] = series
            ticker_price_diag[ticker] = diag
        except Exception:
            per_ticker[ticker] = pd.Series(dtype=float)
            ticker_price_diag[ticker] = {"ticker_requested": ticker, "status": "exception", "attempts": []}
        fetch_progress.update(1)
    fetch_progress.close()

    benchmark_diag: dict[str, Any]
    try:
        benchmark_series, benchmark_diag = fetch_close_series_with_diagnostics(benchmark_ticker, start, end)
    except Exception:
        benchmark_series = pd.Series(dtype=float)
        benchmark_diag = {"ticker_requested": benchmark_ticker, "status": "exception", "attempts": []}

    outcome_progress = ProgressBar(total=len(rows), label="Phase1 Outcomes", enabled=show_progress)
    for row in rows:
        event_dt = parse_date(row.event_date)
        if event_dt is None:
            continue

        stock_series = per_ticker.get(row.ticker, pd.Series(dtype=float))
        stock_window = compute_event_window(stock_series, event_dt, alignment_mode)
        bench_window = compute_event_window(benchmark_series, event_dt, alignment_mode)

        row.aligned_trading_date = stock_window.aligned_trading_date
        row.close_t_minus_1 = stock_window.close_t_minus_1
        row.close_t = stock_window.close_t
        row.close_t_plus_1 = stock_window.close_t_plus_1
        row.close_t_plus_3 = stock_window.close_t_plus_3
        row.close_t_plus_5 = stock_window.close_t_plus_5
        row.stock_return_1d = stock_window.return_1d
        row.stock_return_3d = stock_window.return_3d
        row.stock_return_5d = stock_window.return_5d

        row.benchmark_t_minus_1 = bench_window.close_t_minus_1
        row.benchmark_t = bench_window.close_t
        row.benchmark_t_plus_1 = bench_window.close_t_plus_1
        row.benchmark_t_plus_3 = bench_window.close_t_plus_3
        row.benchmark_t_plus_5 = bench_window.close_t_plus_5
        row.benchmark_return_1d = bench_window.return_1d
        row.benchmark_return_3d = bench_window.return_3d
        row.benchmark_return_5d = bench_window.return_5d

        if row.stock_return_1d is not None and row.benchmark_return_1d is not None:
            row.abnormal_return_1d = row.stock_return_1d - row.benchmark_return_1d
            row.binary_abnormal_up_1d = int(row.abnormal_return_1d > 0)
        if row.stock_return_3d is not None and row.benchmark_return_3d is not None:
            row.abnormal_return_3d = row.stock_return_3d - row.benchmark_return_3d
            row.binary_abnormal_up_3d = int(row.abnormal_return_3d > 0)
        if row.stock_return_5d is not None and row.benchmark_return_5d is not None:
            row.abnormal_return_5d = row.stock_return_5d - row.benchmark_return_5d
            row.binary_abnormal_up_5d = int(row.abnormal_return_5d > 0)
        outcome_progress.update(1)
    outcome_progress.close()
    return {
        "ticker_price_diagnostics": ticker_price_diag,
        "benchmark_price_diagnostics": benchmark_diag,
    }


def _summary_payload(rows: list[EventRow], args: argparse.Namespace) -> dict[str, Any]:
    frame = pd.DataFrame([row.to_dict() for row in rows]) if rows else pd.DataFrame()
    if frame.empty:
        return {
            "events": 0,
            "tickers": 0,
            "assumptions": [],
        }

    missing_rates: dict[str, float] = {}
    for col in [
        "management_confidence",
        "management_directness",
        "management_outlook_strength",
        "management_specificity",
        "management_risk_intensity",
        "transcript_sentiment_directional_score",
        "fundamentals_signal",
        "news_signal",
        "social_signal",
        "abnormal_return_1d",
        "abnormal_return_3d",
        "abnormal_return_5d",
    ]:
        if col in frame.columns:
            missing_rates[col] = float(frame[col].isna().mean())

    event_dates = pd.to_datetime(frame["event_date"], errors="coerce")
    event_dates = event_dates.dropna()

    assumptions = [
        "Event alignment uses transcript published_date, then Motley URL date, then quarter midpoint fallback.",
        "Returns are post-event close-to-close: t->t+1, t->t+3, t->t+5.",
        f"Alignment mode: {args.event_alignment_mode}.",
        f"Benchmark ticker: {args.benchmark_ticker}.",
        "When component_source=live_current_snapshot, fundamentals/news/social are current snapshots and not event-time as-of values.",
    ]

    return {
        "events": int(len(frame)),
        "tickers": int(frame["ticker"].nunique()),
        "date_min": date_to_str(event_dates.min().date()) if not event_dates.empty else None,
        "date_max": date_to_str(event_dates.max().date()) if not event_dates.empty else None,
        "component_source_counts": Counter(frame["component_source"].fillna("missing").tolist()),
        "missing_rate": missing_rates,
        "top_tickers": frame["ticker"].value_counts().head(20).to_dict(),
        "assumptions": assumptions,
    }


def _failure_payload(
    rows: list[EventRow],
    price_diag: dict[str, Any],
    benchmark_ticker: str,
    component_diag: Optional[dict[str, dict[str, Any]]] = None,
) -> dict[str, Any]:
    frame = pd.DataFrame([row.to_dict() for row in rows]) if rows else pd.DataFrame()
    if frame.empty:
        return {
            "rows": 0,
            "missing_abnormal_return_3d_rows": 0,
            "missing_by_ticker": {},
            "ticker_price_diagnostics": {},
            "benchmark_ticker": benchmark_ticker,
            "benchmark_price_diagnostics": {},
            "component_missing_rows": 0,
            "component_missing_by_ticker": {},
            "component_fetch_diagnostics": {},
        }

    missing = frame.loc[frame["abnormal_return_3d"].isna()].copy()
    missing_counts = missing["ticker"].value_counts().to_dict() if not missing.empty else {}

    ticker_diag_all = (price_diag or {}).get("ticker_price_diagnostics") or {}
    ticker_diag_subset = {
        ticker: ticker_diag_all.get(ticker)
        for ticker in sorted(missing_counts.keys())
    }

    component_diag_all = component_diag or {}
    component_missing = frame.loc[
        frame["fundamentals_signal"].isna() & frame["news_signal"].isna() & frame["social_signal"].isna()
    ].copy()
    component_missing_counts = component_missing["ticker"].value_counts().to_dict() if not component_missing.empty else {}
    component_diag_subset = {
        ticker: component_diag_all.get(ticker)
        for ticker in sorted(component_missing_counts.keys())
        if ticker in component_diag_all
    }

    return {
        "rows": int(len(frame)),
        "missing_abnormal_return_3d_rows": int(len(missing)),
        "missing_by_ticker": missing_counts,
        "ticker_price_diagnostics": ticker_diag_subset,
        "benchmark_ticker": benchmark_ticker,
        "benchmark_price_diagnostics": (price_diag or {}).get("benchmark_price_diagnostics") or {},
        "component_missing_rows": int(len(component_missing)),
        "component_missing_by_ticker": component_missing_counts,
        "component_fetch_diagnostics": component_diag_subset,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    start_date = parse_date(args.start_date) if args.start_date else None
    end_date = parse_date(args.end_date) if args.end_date else None

    settings = Settings()
    sentiment_fn = _choose_sentiment_fn(args.sentiment_mode, settings)

    print("[event-table] Loading component lookups...")
    analysis_lookup = _load_analysis_cache_lookup(args.analysis_cache_glob)
    external_lookup = _load_external_component_lookup(args.component_features_input)
    live_fetcher = LiveComponentFetcher(settings=settings, sentiment_fn=sentiment_fn)

    print("[event-table] Building event rows from normalized transcripts...")
    rows, component_diag = _build_event_rows(
        args=args,
        settings=settings,
        sentiment_fn=sentiment_fn,
        analysis_lookup=analysis_lookup,
        external_lookup=external_lookup,
        live_fetcher=live_fetcher,
    )
    print(f"[event-table] Candidate rows before date filter: {len(rows)}")

    rows = _apply_event_date_filters(rows, start_date=start_date, end_date=end_date)
    print(f"[event-table] Rows after date filter: {len(rows)}")

    print("[event-table] Attaching price/benchmark outcomes...")
    benchmark_ticker = str(args.benchmark_ticker).upper()
    price_diag = _attach_market_outcomes(
        rows,
        benchmark_ticker=benchmark_ticker,
        alignment_mode=args.event_alignment_mode,
        show_progress=not args.no_progress,
    )

    out_dir = Path(args.output_dir)
    ensure_dir(out_dir)
    output_path = out_dir / args.output_file
    summary_path = out_dir / "event_table_summary.json"
    failures_path = out_dir / "event_table_failures.json"

    frame = pd.DataFrame([row.to_dict() for row in rows])
    if not frame.empty:
        frame = frame.sort_values(["event_date", "ticker", "transcript_id"], ascending=[True, True, True]).reset_index(drop=True)

    frame.to_csv(output_path, index=False)
    summary = _summary_payload(rows, args)
    write_json(summary_path, summary)
    failures = _failure_payload(
        rows,
        price_diag=price_diag,
        benchmark_ticker=benchmark_ticker,
        component_diag=component_diag,
    )
    write_json(failures_path, failures)

    print(f"[event-table] Wrote {len(frame)} rows -> {output_path}")
    print(f"[event-table] Wrote summary -> {summary_path}")
    print(f"[event-table] Wrote failure diagnostics -> {failures_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
