"""Core earnings analysis pipeline for FinBERT Earnings Signals."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import json
import math
import re
from statistics import mean
import time
from typing import Any, Optional

import requests

from .finbert_model import get_engine
from .normalizer import (
    build_speaker_analysis,
    normalize_transcript_document,
    summarize_transcript_findings,
)
from .providers import (
    FeedFetchAudit,
    TranscriptDiscoveryAudit as ProviderTranscriptDiscoveryAudit,
    TranscriptRecord,
    enrich_fundamentals_with_alpha_validation,
    fetch_fundamentals,
    fetch_news_multi_source,
    fetch_price_volume_history,
    fetch_social_multi_source,
)
from .progress import RunProgressTracker
from .schemas import (
    AggregateScores,
    AnalysisResponse,
    AnalystSignal,
    AuditTaskBreakdown,
    ChartsPayload,
    CompactMetric,
    CopyDictionary,
    DataAuditSection,
    DataHealth,
    FundamentalsSnapshot,
    FundamentalsSummary,
    FundamentalsTrendPoint,
    FundamentalsValidationAudit,
    FundamentalsValidationMismatch,
    FundamentalsWorkspaceSection,
    ManagerDecision,
    MarketReactionSection,
    NewsArticle,
    NewsSummary,
    OverviewSection,
    PriceVolumePoint,
    ReportKPI,
    ReportTab,
    ReportTable,
    ResearchDebate,
    RiskManagementSummary,
    RiskView,
    RunSummary,
    SentimentBreakdown,
    SentimentTimelinePoint,
    SocialPost,
    SocialSummary,
    TraderProposal,
    TranscriptDiscoveryAudit,
    TranscriptDocument,
    TranscriptHealth,
    TranscriptQuarterStatus,
    TranscriptResult,
    TranscriptSectionPayload,
    TranscriptSpeakerRollup,
    TranscriptSpeakerAnalysis,
    WorkflowStage,
)
from .settings import Settings
from .transcript_pipeline import fetch_transcripts_for_analysis as fetch_transcripts_motley_fool

ANALYSIS_VERSION = "2026.04-earnings-signals-v1"

FORWARD_LOOKING_MARKERS = {
    "we expect",
    "we believe",
    "we continue to",
    "we now expect",
    "outlook",
    "guidance",
    "next quarter",
    "full year",
}

RISK_LANGUAGE_MARKERS = {
    "headwind",
    "pressure",
    "uncertain",
    "volatility",
    "risk",
    "challenging",
    "softness",
    "downturn",
}

LOW_INFORMATION_QUOTES = {
    "yes",
    "yeah",
    "sure",
    "okay",
    "ok",
    "thank you",
    "thanks",
    "hi",
    "hello",
    "good morning",
    "good afternoon",
}

UI_COPY = CopyDictionary(
    app_title="FinBERT Earnings Signals",
    app_subtitle="Transcript-first earnings intelligence with focused market context and auditability.",
    section_labels={
        "overview": "Overview",
        "transcript": "Transcript",
        "market_reaction": "Market Reaction",
        "fundamentals": "Fundamentals",
        "data_audit": "Data Audit",
    },
    ui_labels={
        "run_analysis": "Run Analysis",
        "ticker": "Ticker",
        "coverage": "Coverage",
        "confidence": "Confidence",
        "missing": "Missing",
        "degraded": "Degraded",
    },
    empty_states={
        "transcript": "No transcript was retrieved for this ticker in the current scan window.",
        "speaker_profile": "Not enough speaker diversity for a useful profile chart.",
        "market_chart": "Not enough timeline depth for a useful sentiment chart.",
        "fundamentals_chart": "Not enough quarterly depth for a useful fundamentals trend chart.",
        "social": "No social items met the quality threshold.",
        "news": "No news items met the quality threshold.",
    },
    headings={
        "hero_kicker": "FinBERT Earnings Signals",
        "overview": "Overview",
        "transcript": "Transcript",
        "market_reaction": "Market Reaction",
        "fundamentals": "Fundamentals",
        "data_audit": "Data Audit",
        "speaker_profile_chart": "Speaker Confidence Profile",
        "speaker_analysis_table": "Speaker Block Analysis",
        "transcript_quotes": "Key Quotes",
        "transcript_pressure": "Q&A Pressure Points",
        "news_feed": "News Feed",
        "social_feed": "Social Feed",
        "fundamentals_chart": "Quarterly Trend",
        "audit_warnings": "Warnings",
        "audit_missing": "Missing / Sparse",
        "audit_dedupe": "Dedupe Stats",
        "audit_failures": "Discovery Failures",
        "audit_discarded": "Discarded Near-Matches",
        "audit_parsing": "Parsing Warnings",
    },
    microcopy={
        "query_note": (
            "Full report loads after all sections finish. "
            "Transcripts: Motley Fool. News: Alpha Vantage + Yahoo Finance. "
            "Social: Reddit + Stocktwits (recency-weighted)."
        ),
        "modal_open_action": "Open in new tab",
        "modal_close_action": "Close",
    },
)


def _neutral_score() -> dict[str, float | str]:
    return {
        "positive": 0.0,
        "negative": 0.0,
        "neutral": 1.0,
        "directional_score": 0.0,
        "label": "mixed",
    }


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _clamp_unit(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _normalize_ticker(ticker: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9.-]", "", ticker.strip().upper())
    if not cleaned:
        raise ValueError("Ticker cannot be empty.")
    return cleaned


def _stance_from_score(score: float) -> str:
    if score >= 0.12:
        return "bullish"
    if score <= -0.12:
        return "bearish"
    return "mixed"


def _label_from_sentiment_score(score: float) -> str:
    if score >= 0.5:
        return "strongly_bullish"
    if score >= 0.15:
        return "cautiously_bullish"
    if score <= -0.5:
        return "strongly_bearish"
    if score <= -0.15:
        return "cautiously_bearish"
    return "mixed"


def _format_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}%"


def _format_float(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _format_ratio(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}x"


def _format_decimal_pct(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:.1f}%"


def _format_signed_unit_pct(value: Optional[float], digits: int = 1) -> str:
    if value is None:
        return "n/a"
    clamped = _clamp_unit(float(value))
    return f"{clamped * 100:+.{digits}f}%"


def _normalize_quote_key(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text.lower())).strip()


def _quote_is_low_information(text: str, *, min_chars: int = 45) -> bool:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if not compact:
        return True
    if len(compact) < min_chars:
        return True
    normalized = _normalize_quote_key(compact)
    if normalized in LOW_INFORMATION_QUOTES:
        return True
    words = [token for token in normalized.split(" ") if token]
    return len(words) < 6


def _deterministic_rank_quote_candidates(
    *,
    speaker_rows: list[TranscriptSpeakerAnalysis],
    docs: list[TranscriptDocument],
    limit: int = 10,
) -> list[str]:
    candidates: list[tuple[float, str]] = []
    seen_keys: set[str] = set()

    for row in speaker_rows:
        snippets = row.evidence_snippets or []
        for snippet in snippets:
            text = re.sub(r"\s+", " ", str(snippet or "")).strip()
            if _quote_is_low_information(text):
                continue
            quote_key = _normalize_quote_key(text)
            if not quote_key or quote_key in seen_keys:
                continue
            seen_keys.add(quote_key)
            score = (
                abs(float(row.sentiment_direction)) * 34
                + float(row.confidence) * 0.28
                + float(row.evasiveness) * 0.24
                + float(row.specificity) * 0.2
                + float(row.forward_looking_strength) * 0.18
                + min(18.0, len(text) / 8)
            )
            candidates.append((score, text))

    for doc in docs:
        for quote in doc.key_quotes:
            text = re.sub(r"\s+", " ", str(quote or "")).strip()
            if _quote_is_low_information(text):
                continue
            quote_key = _normalize_quote_key(text)
            if not quote_key or quote_key in seen_keys:
                continue
            seen_keys.add(quote_key)
            score = 22 + min(14.0, len(text) / 10)
            candidates.append((score, text))

    candidates.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    ranked_quotes = [text for _, text in candidates[: max(limit * 2, limit)]]
    return ranked_quotes[:limit]


def _rerank_quotes_with_openai(
    *,
    candidates: list[str],
    settings: Settings,
    limit: int = 10,
) -> list[str]:
    if not settings.openai_api_key or len(candidates) < 3:
        return candidates[:limit]

    payload = {
        "model": settings.openai_normalizer_model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": (
                    "You rank candidate earnings-call quotes for analyst usefulness. "
                    "Prefer quotes with concrete information, decisions, outlook, risk, or financial detail. "
                    "Avoid filler or greetings. Return strict JSON: {\"quotes\": [\"...\"]}."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "limit": limit,
                        "quotes": candidates[: min(len(candidates), 24)],
                    }
                ),
            },
        ],
    }

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        body = response.json()
        choices = body.get("choices") or []
        if not choices:
            return candidates[:limit]
        raw_content = str(choices[0].get("message", {}).get("content") or "").strip()
        if not raw_content:
            return candidates[:limit]
        normalized_content = raw_content
        if normalized_content.startswith("```"):
            normalized_content = re.sub(r"^```(?:json)?", "", normalized_content).strip()
            normalized_content = re.sub(r"```$", "", normalized_content).strip()
        parsed = json.loads(normalized_content)
        requested = [str(item).strip() for item in parsed.get("quotes") or [] if str(item).strip()]
        if not requested:
            return candidates[:limit]
        candidate_map = {_normalize_quote_key(text): text for text in candidates}
        ranked: list[str] = []
        for item in requested:
            matched = candidate_map.get(_normalize_quote_key(item))
            if matched and matched not in ranked:
                ranked.append(matched)
        if not ranked:
            return candidates[:limit]
        for item in candidates:
            if len(ranked) >= limit:
                break
            if item not in ranked:
                ranked.append(item)
        return ranked[:limit]
    except Exception:
        return candidates[:limit]


def _select_key_quotes(
    *,
    speaker_rows: list[TranscriptSpeakerAnalysis],
    docs: list[TranscriptDocument],
    settings: Settings,
    limit: int = 10,
) -> list[str]:
    ranked = _deterministic_rank_quote_candidates(speaker_rows=speaker_rows, docs=docs, limit=max(limit, 12))
    if not ranked:
        return []
    return _rerank_quotes_with_openai(candidates=ranked, settings=settings, limit=limit)


def _format_market_cap(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    abs_value = abs(value)
    if abs_value >= 1_000_000_000_000:
        return f"${value / 1_000_000_000_000:.2f}T"
    if abs_value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if abs_value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value:,.0f}"


def _score_text(text: str, engine) -> dict[str, float | str]:
    if engine is None or not text.strip():
        return _neutral_score()
    try:
        return engine.score_text(text)
    except Exception:
        return _neutral_score()


def _split_sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[.!?])\s+", compact)
    return [part.strip() for part in parts if part.strip()]


def _hard_wrap_text(text: str, *, target_chars: int, max_chars: int) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    target_chars = max(180, target_chars)
    max_chars = max(target_chars, max_chars)

    chunks: list[str] = []
    start = 0
    text_len = len(compact)
    while start < text_len:
        end = min(text_len, start + max_chars)
        if end < text_len:
            candidate_break = compact.rfind(" ", start + max(80, target_chars // 2), end)
            if candidate_break > start:
                end = candidate_break
        chunk = compact[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_len:
            break
        start = end
    return chunks


def _segment_text_for_finbert(text: str, settings: Settings) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    if len(compact) < 700:
        return [compact]

    target_chars = max(250, settings.transcript_sentiment_segment_chars)
    max_chars = max(target_chars, settings.transcript_sentiment_segment_max)
    min_chars = max(120, min(settings.transcript_sentiment_segment_min, target_chars))
    overlap = max(0, settings.transcript_sentiment_segment_overlap_sentences)

    sentences = _split_sentences(compact)
    if len(sentences) <= 1 or any(len(sentence) > max_chars for sentence in sentences):
        wrapped = _hard_wrap_text(compact, target_chars=target_chars, max_chars=max_chars)
        return wrapped or [compact]

    chunks: list[str] = []
    index = 0
    sentence_count = len(sentences)
    while index < sentence_count:
        start_index = index
        chunk_sentences: list[str] = []
        chunk_chars = 0

        while index < sentence_count:
            sentence = sentences[index]
            add_chars = len(sentence) + (1 if chunk_sentences else 0)
            if chunk_sentences and chunk_chars + add_chars > max_chars:
                break
            if chunk_sentences and chunk_chars >= min_chars and chunk_chars + add_chars > target_chars:
                break
            chunk_sentences.append(sentence)
            chunk_chars += add_chars
            index += 1

        if not chunk_sentences:
            chunk_sentences.append(sentences[index])
            index += 1

        chunk = " ".join(chunk_sentences).strip()
        if chunk:
            chunks.append(chunk)

        if index < sentence_count and overlap > 0:
            index = max(start_index + 1, index - overlap)

    return chunks or [compact]


def _score_text_with_segmentation(text: str, engine, settings: Settings) -> dict[str, float | str | dict[str, Any]]:
    segments = _segment_text_for_finbert(text, settings)
    if not segments:
        return _neutral_score()
    if len(segments) == 1:
        return _score_text(segments[0], engine)

    rows: list[dict[str, Any]] = []
    for idx, segment in enumerate(segments):
        score = _score_text(segment, engine)
        directional = _clamp_unit(float(score.get("directional_score", 0.0)))
        positive = max(0.0, float(score.get("positive", 0.0)))
        negative = max(0.0, float(score.get("negative", 0.0)))
        neutral = max(0.0, float(score.get("neutral", 0.0)))
        probs_sorted = sorted([positive, negative, neutral], reverse=True)
        confidence_proxy = probs_sorted[0] - probs_sorted[1] if len(probs_sorted) >= 2 else 0.0

        char_count = len(segment)
        weight = min(2.5, math.sqrt(max(1.0, char_count / 100.0)))
        rows.append(
            {
                "segment_index": idx,
                "text": segment,
                "char_count": char_count,
                "weight": weight,
                "directional_score": directional,
                "positive": positive,
                "negative": negative,
                "neutral": neutral,
                "confidence_proxy": confidence_proxy,
                "kept": True,
            }
        )

    kept_rows = list(rows)
    if len(rows) >= 8:
        trim_n = max(1, int(len(rows) * 0.1))
        sorted_by_direction = sorted(rows, key=lambda item: float(item["directional_score"]))
        drop_ids = {id(item) for item in sorted_by_direction[:trim_n] + sorted_by_direction[-trim_n:]}
        kept_rows = [row for row in rows if id(row) not in drop_ids]
        for row in rows:
            row["kept"] = id(row) not in drop_ids
        if not kept_rows:
            kept_rows = list(rows)
            for row in rows:
                row["kept"] = True

    total_weight = sum(float(row["weight"]) for row in kept_rows) or 1.0

    def _wavg(key: str) -> float:
        return sum(float(row[key]) * float(row["weight"]) for row in kept_rows) / total_weight

    agg_directional = _clamp_unit(_wavg("directional_score"))
    agg_positive = max(0.0, _wavg("positive"))
    agg_negative = max(0.0, _wavg("negative"))
    agg_neutral = max(0.0, _wavg("neutral"))
    prob_sum = agg_positive + agg_negative + agg_neutral
    if prob_sum > 0:
        agg_positive /= prob_sum
        agg_negative /= prob_sum
        agg_neutral /= prob_sum
    else:
        agg_positive, agg_negative, agg_neutral = 0.0, 0.0, 1.0

    top_positive = max(kept_rows, key=lambda row: float(row["directional_score"]))
    top_negative = min(kept_rows, key=lambda row: float(row["directional_score"]))
    top_positive_sentence = _split_sentences(str(top_positive["text"]))
    top_negative_sentence = _split_sentences(str(top_negative["text"]))

    segment_diagnostics: dict[str, Any] = {
        "segmented": True,
        "segment_count": len(rows),
        "kept_segment_count": len(kept_rows),
        "aggregation_method": "weighted_trimmed_mean",
        "trim_fraction": 0.1 if len(rows) >= 8 else 0.0,
        "target_chars": settings.transcript_sentiment_segment_chars,
        "max_chars": settings.transcript_sentiment_segment_max,
        "min_chars": settings.transcript_sentiment_segment_min,
        "overlap_sentences": settings.transcript_sentiment_segment_overlap_sentences,
        "top_positive_evidence": top_positive_sentence[0] if top_positive_sentence else str(top_positive["text"])[:180],
        "top_negative_evidence": top_negative_sentence[0] if top_negative_sentence else str(top_negative["text"])[:180],
        "segments": [
            {
                "segment_index": int(row["segment_index"]),
                "char_count": int(row["char_count"]),
                "directional_score": round(float(row["directional_score"]), 4),
                "confidence_proxy": round(float(row["confidence_proxy"]), 4),
                "weight": round(float(row["weight"]), 4),
                "kept": bool(row["kept"]),
            }
            for row in rows
        ],
    }

    return {
        "positive": round(agg_positive, 4),
        "negative": round(agg_negative, 4),
        "neutral": round(agg_neutral, 4),
        "directional_score": round(agg_directional, 4),
        "label": _stance_from_score(agg_directional),
        "segment_diagnostics": segment_diagnostics,
    }


def _parse_news_datetime(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        if "T" in raw and raw.isdigit() is False:
            dt = datetime.strptime(raw, "%Y%m%dT%H%M%S")
            return dt.strftime("%Y-%m-%d")
        if raw.isdigit() and len(raw) == 8:
            dt = datetime.strptime(raw, "%Y%m%d")
            return dt.strftime("%Y-%m-%d")
        return datetime.fromisoformat(raw).strftime("%Y-%m-%d")
    except Exception:
        return None


def _build_sentiment_timeline(news: list[NewsArticle], social: list[SocialPost]) -> list[SentimentTimelinePoint]:
    buckets: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"news": [], "social": []})

    for item in news:
        day = _parse_news_datetime(item.time_published)
        if day:
            buckets[day]["news"].append(item.sentiment_score)

    for item in social:
        if item.created_utc:
            day = datetime.fromtimestamp(item.created_utc, tz=timezone.utc).strftime("%Y-%m-%d")
            buckets[day]["social"].append(item.sentiment_score)

    timeline: list[SentimentTimelinePoint] = []
    for day in sorted(buckets.keys()):
        news_scores = buckets[day]["news"]
        social_scores = buckets[day]["social"]
        news_avg = mean(news_scores) if news_scores else 0.0
        social_avg = mean(social_scores) if social_scores else 0.0

        blended_values: list[float] = []
        if news_scores:
            blended_values.append(news_avg)
        if social_scores:
            blended_values.append(social_avg)
        blended = mean(blended_values) if blended_values else 0.0

        timeline.append(
            SentimentTimelinePoint(
                date=day,
                news=round(news_avg, 4),
                social=round(social_avg, 4),
                blended=round(blended, 4),
            )
        )

    return timeline


def _score_news_records(news_records: list, engine) -> list[NewsArticle]:
    news: list[NewsArticle] = []
    for item in news_records:
        score = _score_text(f"{item.title}. {item.summary}", engine)
        directional = float(score.get("directional_score", 0.0))
        news.append(
            NewsArticle(
                title=item.title,
                summary=item.summary,
                url=item.url,
                source=item.source,
                time_published=item.time_published,
                sentiment_score=round(directional, 4),
                sentiment_label=_stance_from_score(directional),
            )
        )
    return news


def _score_social_records(social_records: list, engine) -> list[SocialPost]:
    social: list[SocialPost] = []
    for item in social_records:
        score = _score_text(f"{item.title}. {item.body}", engine)
        directional = float(score.get("directional_score", 0.0))
        social.append(
            SocialPost(
                source=item.source,
                title=item.title,
                body=item.body,
                excerpt=item.excerpt,
                url=item.url,
                subreddit=item.subreddit,
                created_utc=item.created_utc,
                relevance_score=round(item.relevance_score, 3),
                sentiment_score=round(directional, 4),
                sentiment_label=_stance_from_score(directional),
            )
        )
    return social


def _build_transcript_quarter_status(raw_records: list[TranscriptRecord]) -> list[str]:
    return [f"{record.year}-Q{record.quarter}" for record in raw_records]


def _is_operator_speaker_name(name: str) -> bool:
    lowered = (name or "").strip().lower()
    return lowered == "operator" or lowered.startswith("operator ")


def _exclude_operator_rows(rows: list[TranscriptSpeakerAnalysis]) -> list[TranscriptSpeakerAnalysis]:
    return [row for row in rows if not _is_operator_speaker_name(row.speaker)]


def _build_speaker_rollup(rows: list[TranscriptSpeakerAnalysis]) -> list[TranscriptSpeakerRollup]:
    by_speaker: dict[str, list[TranscriptSpeakerAnalysis]] = defaultdict(list)
    for row in rows:
        by_speaker[row.speaker].append(row)

    rollups: list[TranscriptSpeakerRollup] = []
    for speaker, items in by_speaker.items():
        topic_counts: dict[str, int] = defaultdict(int)
        for item in items:
            topic_counts[item.topic_label] += 1
        dominant_topic = (
            sorted(topic_counts.items(), key=lambda item: (-item[1], item[0]))[0][0]
            if topic_counts
            else "general"
        )
        rollups.append(
            TranscriptSpeakerRollup(
                speaker=speaker,
                mention_count=len(items),
                avg_sentiment_direction=round(mean(item.sentiment_direction for item in items), 4),
                avg_confidence=round(mean(item.confidence for item in items), 2),
                avg_evasiveness=round(mean(item.evasiveness for item in items), 2),
                dominant_topic=dominant_topic,
            )
        )

    rollups.sort(key=lambda row: (-row.mention_count, row.speaker))
    return rollups


def _compact_warnings(warnings: list[str], found: int, requested: int) -> list[str]:
    compact = [f"Transcripts {found}/{requested} found."]
    compact.extend(warnings[:6])
    return compact[:8]


def _aggregate_scores(
    transcript_speaker_analysis: list[TranscriptSpeakerAnalysis],
    fundamentals: FundamentalsSummary,
    news_avg_sentiment: float,
    social_avg_sentiment: float,
) -> AggregateScores:
    if transcript_speaker_analysis:
        avg_directional = mean(s.sentiment_direction for s in transcript_speaker_analysis)
        avg_outlook = mean(s.forward_looking_strength for s in transcript_speaker_analysis)
        avg_confidence = mean(s.confidence for s in transcript_speaker_analysis)
        avg_evasive = mean(s.evasiveness for s in transcript_speaker_analysis)
    else:
        avg_directional = 0.0
        avg_outlook = 50.0
        avg_confidence = 45.0
        avg_evasive = 40.0

    rev_growth = float(fundamentals.revenue_qoq_growth_pct or 0.0)
    eps_growth = float(fundamentals.eps_qoq_growth_pct or 0.0)

    strength = _clamp(
        52
        + (avg_directional * 32)
        + (news_avg_sentiment * 10)
        + (social_avg_sentiment * 6)
        + (rev_growth * 0.18)
        + (eps_growth * 0.20)
    )

    return AggregateScores(
        company_strength_score=round(strength, 2),
        outlook_score=round(_clamp(avg_outlook), 2),
        confidence_score=round(_clamp(avg_confidence), 2),
        evasiveness_score=round(_clamp(avg_evasive), 2),
        sentiment_label=_label_from_sentiment_score(avg_directional),
    )


def _build_report_tabs(
    overview: OverviewSection,
    transcript_section: TranscriptSectionPayload,
    market_reaction: MarketReactionSection,
    fundamentals_section: FundamentalsWorkspaceSection,
    data_audit: DataAuditSection,
) -> list[ReportTab]:
    overview_table = ReportTable(
        title="Overview Metrics",
        columns=["Metric", "Value"],
        rows=[[m.label, m.value] for m in overview.metrics],
    )

    transcript_table = ReportTable(
        title="Speaker Analysis",
        columns=[
            "Speaker",
            "Section",
            "Sentiment",
            "Confidence",
            "Evasiveness",
            "Topic",
        ],
        rows=[
            [
                s.speaker,
                s.section_type,
                _format_signed_unit_pct(s.sentiment_direction),
                f"{s.confidence:.1f}",
                f"{s.evasiveness:.1f}",
                s.topic_label,
            ]
            for s in transcript_section.speaker_analysis[:30]
        ],
    )

    market_table = ReportTable(
        title="Market Reaction Coverage",
        columns=["Source", "Count"],
        rows=[
            ["News", str(market_reaction.news_count)],
            ["Social", str(market_reaction.social_count)],
        ],
    )

    fundamentals_table = ReportTable(
        title="Fundamentals Snapshot",
        columns=["Quarter", "Revenue", "Net Income", "Reported EPS", "EPS Estimate"],
        rows=[
            [
                row.quarter,
                _format_float(row.revenue),
                _format_float(row.net_income),
                _format_float(row.reported_eps),
                _format_float(row.eps_estimate),
            ]
            for row in fundamentals_section.table
        ],
    )

    audit_table = ReportTable(
        title="Transcript Discovery Audit",
        columns=["Item", "Value"],
        rows=[
            ["Pages scanned", str(data_audit.transcript_discovery.pages_scanned)],
            ["Candidates total", str(data_audit.transcript_discovery.candidates_total)],
            ["Transcript-like titles", str(data_audit.transcript_discovery.transcript_like_count)],
            ["Match-filtered", str(data_audit.transcript_discovery.match_filtered_count)],
            ["Selected", str(data_audit.transcript_discovery.selected_count)],
            ["Normalization", data_audit.normalization_mode],
        ],
    )

    return [
        ReportTab(
            id="overview",
            title="Overview",
            markdown=(
                f"# {overview.ticker} Overview\n\n"
                f"{overview.executive_summary}\n\n"
                "## Key takeaways\n- "
                + "\n- ".join(overview.key_takeaways)
            ),
            kpis=[ReportKPI(label=m.label, value=m.value) for m in overview.metrics],
            tables=[overview_table],
        ),
        ReportTab(
            id="transcript",
            title="Transcript",
            markdown=(
                "# Transcript\n\n"
                f"{transcript_section.latest_summary}\n\n"
                f"Prepared remarks vs Q&A: {transcript_section.prepared_vs_qa_note}\n\n"
                "## Q&A pressure points\n- "
                + "\n- ".join(transcript_section.qa_pressure_points or ["No pressure points were identified."])
            ),
            kpis=[
                ReportKPI(
                    label="coverage",
                    value=f"{transcript_section.transcript_count_found}/{transcript_section.transcript_count_requested}",
                ),
                ReportKPI(label="availability", value=transcript_section.availability),
            ],
            tables=[transcript_table],
        ),
        ReportTab(
            id="market_reaction",
            title="Market Reaction",
            markdown=(
                "# Market Reaction\n\n"
                f"{market_reaction.balance_summary}\n\n"
                f"News items: {market_reaction.news_count} | Social items: {market_reaction.social_count}"
            ),
            kpis=[
                ReportKPI(label="news", value=str(market_reaction.news_count)),
                ReportKPI(label="social", value=str(market_reaction.social_count)),
            ],
            tables=[market_table],
        ),
        ReportTab(
            id="fundamentals",
            title="Fundamentals",
            markdown=(
                "# Fundamentals\n\n"
                f"{fundamentals_section.operating_context}"
            ),
            kpis=[ReportKPI(label=m.label, value=m.value) for m in fundamentals_section.metrics],
            tables=[fundamentals_table],
        ),
        ReportTab(
            id="data_audit",
            title="Data Audit",
            markdown=(
                "# Data Audit\n\n"
                f"Normalization mode: {data_audit.normalization_mode}\n\n"
                "## Warnings\n- "
                + "\n- ".join(data_audit.warnings or ["No warnings."])
            ),
            kpis=[
                ReportKPI(label="normalization", value=data_audit.normalization_mode),
                ReportKPI(label="warnings", value=str(len(data_audit.warnings))),
            ],
            tables=[audit_table],
        ),
    ]


def _workflow_from_sections(transcript_availability: str) -> list[WorkflowStage]:
    transcript_status = "completed" if transcript_availability == "available" else "partial"
    return [
        WorkflowStage(key="overview", title="Overview", status="completed", detail="Run-level summary generated."),
        WorkflowStage(
            key="transcript",
            title="Transcript",
            status=transcript_status,
            detail="Transcript normalization and speaker analysis completed.",
        ),
        WorkflowStage(
            key="market_reaction",
            title="Market Reaction",
            status="completed",
            detail="News and social feeds ranked and curated.",
        ),
        WorkflowStage(
            key="fundamentals",
            title="Fundamentals",
            status="completed",
            detail="Quarterly operating context assembled.",
        ),
        WorkflowStage(
            key="data_audit",
            title="Data Audit",
            status="completed",
            detail="Source coverage and parsing diagnostics assembled.",
        ),
    ]


def _build_legacy_transcript_results(
    normalized_docs: list[TranscriptDocument],
    speaker_analysis_by_url: dict[str, list[TranscriptSpeakerAnalysis]],
) -> list[TranscriptResult]:
    out: list[TranscriptResult] = []
    for doc in normalized_docs:
        analysis_rows = speaker_analysis_by_url.get(doc.source_url or "", [])
        directional = mean(a.sentiment_direction for a in analysis_rows) if analysis_rows else 0.0
        confidence = mean(a.confidence for a in analysis_rows) if analysis_rows else 45.0
        outlook = mean(a.forward_looking_strength for a in analysis_rows) if analysis_rows else 45.0
        evasiveness = mean(a.evasiveness for a in analysis_rows) if analysis_rows else 40.0

        published = doc.published_date or ""
        year = int(published[:4]) if len(published) >= 4 and published[:4].isdigit() else datetime.now().year
        month = int(published[5:7]) if len(published) >= 7 and published[5:7].isdigit() else 1
        quarter = ((month - 1) // 3) + 1

        bullish_signals = [
            row.evidence_snippets[0]
            for row in analysis_rows
            if row.sentiment_direction >= 0.12 and row.evidence_snippets
        ][:4]
        bearish_signals = [
            row.evidence_snippets[0]
            for row in analysis_rows
            if row.sentiment_direction <= -0.12 and row.evidence_snippets
        ][:4]
        evasive_signals = [
            row.evidence_snippets[0]
            for row in analysis_rows
            if row.evasiveness >= 55 and row.evidence_snippets
        ][:4]

        out.append(
            TranscriptResult(
                year=year,
                quarter=quarter,
                date=doc.published_date,
                source=doc.source,
                sentiment=SentimentBreakdown(
                    positive=max(directional, 0),
                    negative=max(-directional, 0),
                    neutral=max(0.0, 1.0 - abs(directional)),
                    directional_score=round(directional, 4),
                    label=_stance_from_score(directional),
                ),
                confidence_score=round(_clamp(confidence), 2),
                outlook_score=round(_clamp(outlook), 2),
                evasiveness_score=round(_clamp(evasiveness), 2),
                bullish_signals=bullish_signals,
                bearish_signals=bearish_signals,
                evasive_signals=evasive_signals,
                decision_relevant_quotes=doc.key_quotes[:4],
            )
        )
    return out


def _build_legacy_fields(
    *,
    aggregate: AggregateScores,
    transcript_results: list[TranscriptResult],
    fundamentals: FundamentalsSummary,
    news: list[NewsArticle],
    social: list[SocialPost],
) -> tuple[list[AnalystSignal], ResearchDebate, TraderProposal, RiskManagementSummary, ManagerDecision]:
    transcript_signal = (
        mean(item.sentiment.directional_score for item in transcript_results)
        if transcript_results
        else 0.0
    )
    news_signal = mean(item.sentiment_score for item in news) if news else 0.0
    social_signal = mean(item.sentiment_score for item in social) if social else 0.0

    fundamentals_signal = _clamp_unit(
        ((fundamentals.revenue_qoq_growth_pct or 0.0) * 0.55 + (fundamentals.eps_qoq_growth_pct or 0.0) * 0.45)
        / 50.0
    )

    analyst_team = [
        AnalystSignal(
            name="transcript",
            stance=_stance_from_score(transcript_signal),
            signal_score=round(transcript_signal, 4),
            confidence_score=round(mean((t.confidence_score for t in transcript_results)), 2)
            if transcript_results
            else 40.0,
            key_points=[
                f"Transcripts analyzed: {len(transcript_results)}",
                f"Average outlook: {mean((t.outlook_score for t in transcript_results)):.1f}" if transcript_results else "Average outlook: n/a",
                f"Average evasiveness: {mean((t.evasiveness_score for t in transcript_results)):.1f}" if transcript_results else "Average evasiveness: n/a",
            ],
            evidence=[quote for t in transcript_results for quote in t.decision_relevant_quotes][:4]
            or ["No transcript quotes available."],
        ),
        AnalystSignal(
            name="fundamentals",
            stance=_stance_from_score(fundamentals_signal),
            signal_score=round(fundamentals_signal, 4),
            confidence_score=round(_clamp(42 + len(fundamentals.quarterly) * 12), 2),
            key_points=[
                f"Revenue QoQ growth: {_format_pct(fundamentals.revenue_qoq_growth_pct)}",
                f"EPS QoQ growth: {_format_pct(fundamentals.eps_qoq_growth_pct)}",
                f"Trailing PE: {_format_float(fundamentals.trailing_pe)} | Forward PE: {_format_float(fundamentals.forward_pe)}",
            ],
            evidence=[
                f"{q.quarter}: revenue={_format_float(q.revenue)}, net_income={_format_float(q.net_income)}"
                for q in fundamentals.quarterly[:3]
            ]
            or ["No recent fundamentals snapshots available."],
        ),
        AnalystSignal(
            name="news",
            stance=_stance_from_score(news_signal),
            signal_score=round(news_signal, 4),
            confidence_score=round(_clamp(30 + len(news) * 4), 2),
            key_points=[
                f"Articles analyzed: {len(news)}",
                f"Average directional score: {news_signal:.3f}",
                f"Dominant stance: {_stance_from_score(news_signal)}",
            ],
            evidence=[item.title for item in news[:4]] or ["No news evidence available."],
        ),
        AnalystSignal(
            name="social",
            stance=_stance_from_score(social_signal),
            signal_score=round(social_signal, 4),
            confidence_score=round(_clamp(30 + len(social) * 4), 2),
            key_points=[
                f"Posts analyzed: {len(social)}",
                f"Average directional score: {social_signal:.3f}",
                f"Top relevance: {max((item.relevance_score for item in social), default=0):.2f}",
            ],
            evidence=[item.title for item in social[:4]] or ["No social evidence available."],
        ),
    ]

    composite = transcript_signal * 0.45 + fundamentals_signal * 0.2 + news_signal * 0.2 + social_signal * 0.15

    research_team = ResearchDebate(
        bullish_points=[f"{a.name}: {a.key_points[0]}" for a in analyst_team if a.signal_score > 0.05]
        or ["No strong bullish cluster detected."],
        bearish_points=[f"{a.name}: {a.key_points[0]}" for a in analyst_team if a.signal_score < -0.05]
        or ["No strong bearish cluster detected."],
        discussion_summary=(
            "Legacy field: directional synthesis retained for compatibility. "
            "Use canonical overview/transcript sections for current UX."
        ),
        buy_evidence_score=round(_clamp(50 + composite * 35), 2),
        sell_evidence_score=round(_clamp(50 - composite * 35), 2),
    )

    trader_plan = TraderProposal(
        action="hold",
        conviction_score=round(_clamp(abs(composite) * 100), 2),
        thesis="Legacy compatibility field. Execution guidance is intentionally suppressed in canonical sections.",
        horizon="n/a",
    )

    risk_management = RiskManagementSummary(
        views=[
            RiskView(profile="aggressive", recommendation="Legacy compatibility field.", max_position_pct=0),
            RiskView(profile="neutral", recommendation="Legacy compatibility field.", max_position_pct=0),
            RiskView(profile="conservative", recommendation="Legacy compatibility field.", max_position_pct=0),
        ],
        consensus="Legacy compatibility field. Use transcript/data audit sections for analysis context.",
    )

    manager_decision = ManagerDecision(
        action="hold",
        rationale=[
            "Legacy compatibility field.",
            f"Aggregate confidence: {aggregate.confidence_score:.1f}",
            f"Aggregate evasiveness: {aggregate.evasiveness_score:.1f}",
        ],
        execution_plan=["Execution guidance removed from canonical interface in this release."],
    )

    return analyst_team, research_team, trader_plan, risk_management, manager_decision


def build_sentiment_snapshot(ticker: str, settings: Settings) -> dict[str, Any]:
    symbol = _normalize_ticker(ticker)
    fundamentals_dict = fetch_fundamentals(symbol)
    company_name = str(fundamentals_dict.get("company_name") or symbol)

    news_records, news_warnings, _news_audit = fetch_news_multi_source(
        symbol,
        settings,
        limit=max(1, settings.news_limit),
        pool_size=max(settings.news_pool_size, settings.news_limit),
        company_name=company_name,
        lookback_days=settings.news_lookback_days,
    )
    social_records, social_warnings, _social_audit = fetch_social_multi_source(
        symbol,
        settings,
        limit=max(1, settings.social_limit),
        pool_size=max(settings.social_pool_size, settings.social_limit),
        company_name=company_name,
        lookback_days=settings.social_lookback_days,
    )

    warnings = news_warnings + social_warnings
    engine = get_engine(settings.finbert_model_name)
    news = _score_news_records(news_records, engine)
    social = _score_social_records(social_records, engine)

    news_avg = mean(n.sentiment_score for n in news) if news else 0.0
    social_avg = mean(s.sentiment_score for s in social) if social else 0.0

    rev_growth = float(fundamentals_dict.get("revenue_qoq_growth_pct") or 0.0)
    eps_growth = float(fundamentals_dict.get("eps_qoq_growth_pct") or 0.0)
    fundamentals_signal = _clamp_unit((rev_growth * 0.55 + eps_growth * 0.45) / 50.0)
    overall_score = _clamp_unit(news_avg * 0.45 + social_avg * 0.2 + fundamentals_signal * 0.35)
    overall_label = _label_from_sentiment_score(overall_score)

    overview = OverviewSection(
        ticker=symbol,
        company_name=company_name,
        stance_label=_stance_from_score(overall_score),
        executive_summary=(
            f"Initial sentiment snapshot for {company_name}: "
            f"news reads {_stance_from_score(news_avg)} ({_format_signed_unit_pct(news_avg)}), "
            f"social reads {_stance_from_score(social_avg)} ({_format_signed_unit_pct(social_avg)}). "
            "Transcript-driven adjustments continue loading."
        ),
        key_takeaways=[
            f"Snapshot captured {len(news)} news items and {len(social)} social posts.",
            f"Fundamentals momentum signal: {_format_signed_unit_pct(fundamentals_signal)}.",
            "Full transcript normalization and speaker analysis are still processing.",
        ],
        metrics=[
            CompactMetric(key="overall_sentiment", label="Snapshot Sentiment", value=_format_signed_unit_pct(overall_score)),
            CompactMetric(key="news_count", label="News Items", value=str(len(news))),
            CompactMetric(key="social_count", label="Social Posts", value=str(len(social))),
            CompactMetric(key="fundamentals_signal", label="Fundamentals Signal", value=_format_signed_unit_pct(fundamentals_signal)),
        ],
    )

    market_reaction = MarketReactionSection(
        balance_summary=(
            f"Snapshot market reaction skews {_stance_from_score(news_avg)} in news "
            f"({_format_signed_unit_pct(news_avg)}) and {_stance_from_score(social_avg)} in social "
            f"({_format_signed_unit_pct(social_avg)})."
        ),
        news_count=len(news),
        social_count=len(social),
        news_items=news,
        social_items=social,
        chart_enabled=False,
        sparse_note="Full timeline rendering waits for complete analysis.",
    )

    return {
        "ticker": symbol,
        "company_name": company_name,
        "overall_sentiment_score": round(overall_score, 4),
        "overall_sentiment_label": overall_label,
        "overview": overview.model_dump(),
        "market_reaction": market_reaction.model_dump(),
        "warnings": warnings,
        "ui_copy": UI_COPY.model_dump(),
    }


def build_analysis(
    ticker: str,
    settings: Settings,
    progress: Optional[RunProgressTracker] = None,
    run_id: Optional[str] = None,
) -> AnalysisResponse:
    task_breakdown: list[AuditTaskBreakdown] = []

    def _record_task(key: str, label: str, start_ts: float, detail: str = "", status: str = "done") -> None:
        duration_ms = int((time.perf_counter() - start_ts) * 1000)
        task_breakdown.append(
            AuditTaskBreakdown(
                key=key,
                label=label,
                status=status if status in {"done", "error", "skipped"} else "done",
                duration_ms=max(0, duration_ms),
                detail=detail,
            )
        )

    if progress is not None:
        progress.start_stage(
            "overview",
            subtask="init",
            message=f"Booting analysis context for {ticker.strip().upper() or ticker}.",
        )
    symbol = _normalize_ticker(ticker)
    if progress is not None:
        progress.complete_stage("overview", message=f"Context initialized for {symbol}.")

    if progress is not None:
        progress.start_stage("market_reaction", subtask="fetch_feeds", message="Fetching news and social feeds.")
    news_fetch_start = time.perf_counter()
    news_records, news_warnings, news_audit = fetch_news_multi_source(
        symbol,
        settings,
        limit=max(1, settings.news_limit),
        pool_size=max(settings.news_pool_size, settings.news_limit),
        company_name=symbol,
        lookback_days=settings.news_lookback_days,
    )
    _record_task("news_fetch", "News Fetch", news_fetch_start, detail=f"{len(news_records)} records.")

    social_fetch_start = time.perf_counter()
    social_records, social_warnings, social_audit = fetch_social_multi_source(
        symbol,
        settings,
        limit=max(1, settings.social_limit),
        pool_size=max(settings.social_pool_size, settings.social_limit),
        company_name=symbol,
        lookback_days=settings.social_lookback_days,
    )
    _record_task("social_fetch", "Social Fetch", social_fetch_start, detail=f"{len(social_records)} records.")

    engine = get_engine(settings.finbert_model_name)

    news_score_start = time.perf_counter()
    news = _score_news_records(news_records, engine)
    _record_task("news_sentiment", "News Sentiment Scoring", news_score_start, detail=f"{len(news)} scored.")

    social_score_start = time.perf_counter()
    social = _score_social_records(social_records, engine)
    _record_task("social_sentiment", "Social Sentiment Scoring", social_score_start, detail=f"{len(social)} scored.")

    if progress is not None:
        progress.update_stage(
            "market_reaction",
            progress=0.8,
            subtask="score_feeds",
            message=f"Scored {len(news)} news and {len(social)} social items.",
        )
        progress.complete_stage("market_reaction", message="Market reaction feeds ranked and scored.")

    news_avg = mean(n.sentiment_score for n in news) if news else 0.0
    social_avg = mean(s.sentiment_score for s in social) if social else 0.0

    news_summary = NewsSummary(
        article_count=len(news),
        avg_sentiment_score=round(news_avg, 4),
        sentiment_label=_stance_from_score(news_avg),
    )
    social_summary = SocialSummary(
        post_count=len(social),
        avg_sentiment_score=round(social_avg, 4),
        sentiment_label=_stance_from_score(social_avg),
    )

    if progress is not None:
        progress.start_stage("fundamentals", subtask="fetch", message="Fetching fundamentals from Yahoo Finance.")
    fundamentals_fetch_start = time.perf_counter()
    fundamentals_dict_raw = fetch_fundamentals(symbol)
    _record_task("fundamentals_fetch", "Fundamentals Fetch", fundamentals_fetch_start)

    company_name = str(fundamentals_dict_raw.get("company_name") or symbol)

    fundamentals_validate_start = time.perf_counter()
    fundamentals_dict, fundamentals_validation_raw = enrich_fundamentals_with_alpha_validation(
        symbol=symbol,
        settings=settings,
        yahoo_payload=fundamentals_dict_raw,
    )
    _record_task(
        "fundamentals_validation",
        "Fundamentals Validation",
        fundamentals_validate_start,
        detail=f"{len(fundamentals_validation_raw.get('mismatches') or [])} mismatches.",
    )

    if progress is not None:
        progress.update_stage(
            "fundamentals",
            progress=0.85,
            subtask="cross_check",
            message="Cross-checked fundamentals against Alpha Vantage.",
        )
        progress.complete_stage("fundamentals", message="Fundamentals metrics assembled.")

    fundamentals = FundamentalsSummary(
        currency=fundamentals_dict.get("currency"),
        market_cap=fundamentals_dict.get("market_cap"),
        trailing_pe=fundamentals_dict.get("trailing_pe"),
        forward_pe=fundamentals_dict.get("forward_pe"),
        debt_to_equity=fundamentals_dict.get("debt_to_equity"),
        beta=fundamentals_dict.get("beta"),
        enterprise_value=fundamentals_dict.get("enterprise_value"),
        total_debt=fundamentals_dict.get("total_debt"),
        total_cash=fundamentals_dict.get("total_cash"),
        current_ratio=fundamentals_dict.get("current_ratio"),
        quick_ratio=fundamentals_dict.get("quick_ratio"),
        return_on_equity=fundamentals_dict.get("return_on_equity"),
        operating_margin=fundamentals_dict.get("operating_margin"),
        free_cashflow=fundamentals_dict.get("free_cashflow"),
        quarterly=[FundamentalsSnapshot(**q) for q in fundamentals_dict.get("quarterly", [])],
        revenue_qoq_growth_pct=fundamentals_dict.get("revenue_qoq_growth_pct"),
        eps_qoq_growth_pct=fundamentals_dict.get("eps_qoq_growth_pct"),
    )

    if progress is not None:
        progress.start_stage("transcript", subtask="discovery_scrape", message="Running transcript discovery and scrape.")
    transcript_fetch_start = time.perf_counter()
    transcript_raw, transcript_warnings, transcript_diagnostics, transcript_discovery = fetch_transcripts_motley_fool(
        symbol=symbol,
        company_name=company_name,
        settings=settings,
        target_count=settings.transcript_target_count,
    )
    _record_task(
        "transcript_fetch",
        "Transcript Discovery + Scrape",
        transcript_fetch_start,
        detail=f"{len(transcript_raw)} transcripts parsed.",
    )

    if progress is not None:
        progress.update_stage(
            "transcript",
            progress=0.35,
            subtask="normalize",
            message=f"Normalizing {len(transcript_raw)} transcript documents.",
        )

    normalized_documents: list[TranscriptDocument] = []
    normalization_warnings: list[str] = []
    speaker_analysis_by_url: dict[str, list[TranscriptSpeakerAnalysis]] = {}
    all_speaker_analysis_raw: list[TranscriptSpeakerAnalysis] = []

    normalize_start = time.perf_counter()
    for idx, record in enumerate(transcript_raw):
        normalized = normalize_transcript_document(
            ticker=symbol,
            company_name=company_name,
            source=record.source,
            source_url=record.source_url,
            title=record.title,
            published_date=record.date,
            content=record.content,
            extraction_confidence=record.extraction_confidence,
            parsing_warnings=record.parsing_warnings,
            participants=record.participants,
            settings=settings,
        )
        normalized_documents.append(normalized.document)
        normalization_warnings.extend(normalized.warnings)
        if progress is not None and transcript_raw:
            progress.update_stage(
                "transcript",
                progress=min(0.35 + ((idx + 1) / max(len(transcript_raw), 1)) * 0.35, 0.75),
                subtask="normalize",
                message=f"Normalized {idx + 1}/{len(transcript_raw)} transcript documents.",
            )
    _record_task(
        "transcript_normalization",
        "Transcript Normalization",
        normalize_start,
        detail=f"{len(normalized_documents)} normalized docs.",
    )

    scoring_start = time.perf_counter()
    for normalized in normalized_documents:
        analysis_rows = build_speaker_analysis(
            normalized.sections,
            lambda text: _score_text_with_segmentation(text, engine, settings),
        )
        filtered_rows = _exclude_operator_rows(analysis_rows)
        speaker_analysis_by_url[normalized.source_url or f"doc-{len(speaker_analysis_by_url)}"] = filtered_rows
        all_speaker_analysis_raw.extend(filtered_rows)
    _record_task(
        "transcript_scoring",
        "Transcript Sentiment + Speaker Scoring",
        scoring_start,
        detail=f"{len(all_speaker_analysis_raw)} speaker blocks.",
    )

    all_speaker_analysis = all_speaker_analysis_raw
    speaker_rollup = _build_speaker_rollup(all_speaker_analysis)

    transcript_summary, transcript_takeaways, pressure_points = summarize_transcript_findings(all_speaker_analysis)

    prepared_count = sum(1 for row in all_speaker_analysis if row.section_type == "prepared_remarks")
    qa_count = sum(1 for row in all_speaker_analysis if row.section_type == "qa")
    prepared_vs_qa_note = f"Prepared remarks blocks: {prepared_count}; Q&A blocks: {qa_count}."

    speaker_confidence_profile = [
        {
            "speaker": row.speaker,
            "mentions": row.mention_count,
            "confidence": round(row.avg_confidence, 2),
            "evasiveness": round(row.avg_evasiveness, 2),
            "sentiment": round(row.avg_sentiment_direction, 4),
        }
        for row in speaker_rollup
    ]

    transcript_availability = "missing"
    if normalized_documents and len(normalized_documents) >= settings.transcript_target_count:
        transcript_availability = "available"
    elif normalized_documents:
        transcript_availability = "partial"

    quarter_status = [
        TranscriptQuarterStatus(quarter=item.quarter, status=item.status, detail=item.detail)
        for item in transcript_diagnostics.outcomes
    ]

    transcript_section = TranscriptSectionPayload(
        availability=transcript_availability,
        transcript_count_requested=settings.transcript_target_count,
        transcript_count_found=len(normalized_documents),
        latest_summary=transcript_summary,
        prepared_vs_qa_note=prepared_vs_qa_note,
        speaker_analysis=all_speaker_analysis,
        key_quotes=_select_key_quotes(
            speaker_rows=all_speaker_analysis,
            docs=normalized_documents,
            settings=settings,
            limit=10,
        ),
        qa_pressure_points=pressure_points,
        transcripts=normalized_documents,
        speaker_confidence_profile=speaker_confidence_profile,
        speaker_rollup=speaker_rollup,
        quarter_status=quarter_status,
        chart_enabled=len(speaker_confidence_profile) >= 2,
        sparse_note=(
            None if len(speaker_confidence_profile) >= 2 else "Not enough speaker diversity for a useful profile chart."
        ),
    )

    if progress is not None:
        progress.update_stage(
            "transcript",
            progress=0.9,
            subtask="summarize",
            message=f"Built transcript summary from {len(all_speaker_analysis)} non-operator speaker blocks.",
        )
        progress.complete_stage("transcript", message="Transcript analysis completed.")

    transcript_direction = mean(row.sentiment_direction for row in all_speaker_analysis) if all_speaker_analysis else 0.0
    forward_strength = mean(row.forward_looking_strength for row in all_speaker_analysis) if all_speaker_analysis else 45.0
    confidence_score = mean(row.confidence for row in all_speaker_analysis) if all_speaker_analysis else 45.0
    evasiveness_score = mean(row.evasiveness for row in all_speaker_analysis) if all_speaker_analysis else 40.0

    rev_growth = float(fundamentals.revenue_qoq_growth_pct or 0.0)
    eps_growth = float(fundamentals.eps_qoq_growth_pct or 0.0)
    fundamentals_signal = _clamp_unit((rev_growth * 0.55 + eps_growth * 0.45) / 50.0)

    if normalized_documents:
        overall_score = _clamp_unit(
            transcript_direction * 0.45
            + news_avg * 0.22
            + social_avg * 0.13
            + fundamentals_signal * 0.20
        )
    else:
        overall_score = _clamp_unit(news_avg * 0.35 + social_avg * 0.2 + fundamentals_signal * 0.45)

    overall_label = _label_from_sentiment_score(overall_score)

    overview_takeaways = transcript_takeaways[:3]
    if len(overview_takeaways) < 6:
        overview_takeaways.extend(
            [
                f"Captured {len(news)} high-relevance news stories in the recent window.",
                f"Captured {len(social)} related social discussions in the recent window.",
                f"Latest revenue QoQ growth is {_format_pct(fundamentals.revenue_qoq_growth_pct)}.",
                f"Most active management speaker: {speaker_rollup[0].speaker if speaker_rollup else 'n/a'}.",
            ]
        )
    overview_takeaways = overview_takeaways[:6]

    overview = OverviewSection(
        ticker=symbol,
        company_name=company_name,
        stance_label=_stance_from_score(overall_score),
        executive_summary=(
            f"{company_name} currently reads as {_stance_from_score(overall_score)} based on transcript tone, "
            f"fundamentals, and near-term market reaction. Transcript coverage is "
            f"{len(normalized_documents)}/{settings.transcript_target_count}; average confidence is "
            f"{confidence_score:.1f} and evasiveness is {evasiveness_score:.1f}."
        ),
        key_takeaways=overview_takeaways,
        metrics=[
            CompactMetric(key="management_confidence", label="Management Confidence", value=f"{confidence_score:.1f}"),
            CompactMetric(key="evasiveness", label="Evasiveness", value=f"{evasiveness_score:.1f}"),
            CompactMetric(key="outlook_strength", label="Outlook Strength", value=f"{forward_strength:.1f}"),
            CompactMetric(
                key="transcript_coverage",
                label="Transcript Coverage",
                value=f"{len(normalized_documents)}/{settings.transcript_target_count}",
            ),
        ],
    )

    sentiment_timeline: list[SentimentTimelinePoint] = []
    market_reaction = MarketReactionSection(
        balance_summary=(
            f"Recent coverage skews {_stance_from_score(news_avg)} in news ({_format_signed_unit_pct(news_avg)}) and "
            f"{_stance_from_score(social_avg)} in social ({_format_signed_unit_pct(social_avg)})."
        ),
        news_count=len(news),
        social_count=len(social),
        news_items=news,
        social_items=social,
        chart_enabled=False,
        sparse_note="Sentiment timeline is intentionally hidden in this view.",
    )

    fundamentals_trend = [
        FundamentalsTrendPoint(
            quarter=item.quarter,
            revenue=item.revenue,
            net_income=item.net_income,
            eps=item.reported_eps,
            eps_estimate=item.eps_estimate,
        )
        for item in reversed(fundamentals.quarterly)
    ]
    fundamentals_chart_enabled = len(fundamentals_trend) >= 3

    fundamentals_workspace = FundamentalsWorkspaceSection(
        operating_context=(
            f"Operating context combines valuation and quarterly momentum. Market cap is {_format_market_cap(fundamentals.market_cap)}. "
            f"Trailing PE is {_format_float(fundamentals.trailing_pe)}, "
            f"forward PE is {_format_float(fundamentals.forward_pe)}, beta is {_format_float(fundamentals.beta)}, "
            f"and debt/equity is {_format_float(fundamentals.debt_to_equity)}. "
            f"Revenue QoQ growth is {_format_pct(fundamentals.revenue_qoq_growth_pct)} and EPS QoQ is {_format_pct(fundamentals.eps_qoq_growth_pct)}."
        ),
        metrics=[
            CompactMetric(key="market_cap", label="Market Cap", value=_format_market_cap(fundamentals.market_cap)),
            CompactMetric(key="trailing_pe", label="Trailing PE", value=_format_float(fundamentals.trailing_pe)),
            CompactMetric(key="forward_pe", label="Forward PE", value=_format_float(fundamentals.forward_pe)),
            CompactMetric(key="beta", label="Beta", value=_format_float(fundamentals.beta)),
            CompactMetric(key="debt_to_equity", label="Debt / Equity", value=_format_float(fundamentals.debt_to_equity)),
            CompactMetric(key="current_ratio", label="Current Ratio", value=_format_ratio(fundamentals.current_ratio)),
            CompactMetric(key="quick_ratio", label="Quick Ratio", value=_format_ratio(fundamentals.quick_ratio)),
            CompactMetric(key="roe", label="Return on Equity", value=_format_decimal_pct(fundamentals.return_on_equity)),
            CompactMetric(key="operating_margin", label="Operating Margin", value=_format_decimal_pct(fundamentals.operating_margin)),
            CompactMetric(key="enterprise_value", label="Enterprise Value", value=_format_market_cap(fundamentals.enterprise_value)),
            CompactMetric(key="total_debt", label="Total Debt", value=_format_market_cap(fundamentals.total_debt)),
            CompactMetric(key="total_cash", label="Total Cash", value=_format_market_cap(fundamentals.total_cash)),
            CompactMetric(key="revenue_qoq", label="Revenue QoQ", value=_format_pct(fundamentals.revenue_qoq_growth_pct)),
            CompactMetric(key="eps_qoq", label="EPS QoQ", value=_format_pct(fundamentals.eps_qoq_growth_pct)),
        ],
        table=fundamentals.quarterly,
        trend_series=fundamentals_trend,
        chart_enabled=fundamentals_chart_enabled,
        sparse_note=None if fundamentals_chart_enabled else UI_COPY.empty_states["fundamentals_chart"],
    )

    warnings = transcript_warnings + news_warnings + social_warnings

    normalization_mode = (
        "openai"
        if normalized_documents and all(doc.normalization_mode == "openai" for doc in normalized_documents)
        else "deterministic_degraded"
    )

    parsing_warnings = [warning for doc in normalized_documents for warning in doc.parsing_warnings]
    parsing_warnings.extend(normalization_warnings)

    missing_items: list[str] = []
    if not normalized_documents:
        missing_items.append("No transcript documents were successfully normalized.")
    if not news:
        missing_items.append("No news records were available after ranking.")
    if not social:
        missing_items.append("No social records were available after ranking.")

    fundamentals_mismatches = [
        FundamentalsValidationMismatch(
            key=str(item.get("key") or ""),
            yahoo_value=item.get("yahoo_value"),
            alpha_value=item.get("alpha_value"),
            relative_diff_pct=item.get("relative_diff_pct"),
            note=item.get("note"),
        )
        for item in (fundamentals_validation_raw.get("mismatches") or [])
        if isinstance(item, dict)
    ]
    fundamentals_validation = FundamentalsValidationAudit(
        yahoo_source_used=bool(fundamentals_validation_raw.get("yahoo_source_used", True)),
        alpha_source_used=bool(fundamentals_validation_raw.get("alpha_source_used", False)),
        compared_fields=[str(item) for item in fundamentals_validation_raw.get("compared_fields") or []],
        mismatches=fundamentals_mismatches,
        notes=[str(item) for item in fundamentals_validation_raw.get("notes") or []],
    )
    if fundamentals_validation.notes:
        warnings.extend([f"Fundamentals validation: {note}" for note in fundamentals_validation.notes[:5]])
    if fundamentals_validation.mismatches:
        warnings.append(
            f"Fundamentals validation found {len(fundamentals_validation.mismatches)} cross-source mismatches."
        )
    if fundamentals_validation.mismatches:
        missing_items.append("Fundamentals cross-check found provider mismatches; review Data Audit details.")

    avg_extraction_confidence = (
        mean(doc.extraction_confidence for doc in normalized_documents)
        if normalized_documents
        else 0.0
    )
    confidence_note = (
        f"Average transcript extraction confidence is {avg_extraction_confidence:.2f}."
        if normalized_documents
        else "No transcript extraction confidence is available for this run."
    )

    if progress is not None:
        progress.start_stage("data_audit", subtask="assemble", message="Assembling data audit details.")

    report_assembly_start = time.perf_counter()
    _record_task("report_assembly", "Report Assembly", report_assembly_start, detail="Sections and tables materialized.")

    slowest_tasks = [
        f"{task.label} ({task.duration_ms}ms)"
        for task in sorted(task_breakdown, key=lambda row: row.duration_ms, reverse=True)[:4]
    ]

    data_audit = DataAuditSection(
        transcript_discovery=TranscriptDiscoveryAudit(
            pages_scanned=transcript_discovery.pages_scanned,
            candidates_total=transcript_discovery.candidates_total,
            transcript_like_count=transcript_discovery.transcript_like_count,
            match_filtered_count=transcript_discovery.match_filtered_count,
            selected_count=transcript_discovery.selected_count,
            discarded_near_matches=transcript_discovery.discarded_near_matches,
            fetch_failures=transcript_discovery.fetch_failures,
            playwright_fallback_used=transcript_discovery.playwright_fallback_used,
        ),
        source_counts={
            "transcripts": len(normalized_documents),
            "news": len(news),
            "social": len(social),
        },
        dedupe_counts={
            "news_pool": news_audit.fetched_pool,
            "news_deduped": news_audit.deduped_pool,
            "social_pool": social_audit.fetched_pool,
            "social_deduped": social_audit.deduped_pool,
        },
        parsing_warnings=parsing_warnings,
        missing_items=missing_items,
        normalization_mode=normalization_mode,
        warnings=warnings,
        confidence_note=confidence_note,
        task_breakdown=task_breakdown,
        slowest_tasks=slowest_tasks,
        fundamentals_validation=fundamentals_validation,
    )

    if progress is not None:
        progress.update_stage(
            "data_audit",
            progress=0.85,
            subtask="finalize",
            message=f"Data audit assembled with {len(task_breakdown)} granular tasks.",
        )
        progress.complete_stage("data_audit", message="Data audit finalized.")

    aggregate = _aggregate_scores(all_speaker_analysis, fundamentals, news_avg, social_avg)

    transcript_results = _build_legacy_transcript_results(normalized_documents, speaker_analysis_by_url)
    analyst_team, research_team, trader_plan, risk_management, manager_decision = _build_legacy_fields(
        aggregate=aggregate,
        transcript_results=transcript_results,
        fundamentals=fundamentals,
        news=news,
        social=social,
    )

    run_summary = RunSummary(
        ticker=symbol,
        overall_label=overall_label,
        overall_score=round(overall_score, 4),
        transcripts_found=len(normalized_documents),
        news_count=len(news),
        social_count=len(social),
    )

    data_health = DataHealth(
        transcripts=TranscriptHealth(
            requested_quarters=transcript_diagnostics.requested_quarters,
            found_quarters=transcript_diagnostics.found_quarters,
            missing_quarters=transcript_diagnostics.missing_quarters,
            errors=transcript_diagnostics.errors,
            outcomes=quarter_status,
        ),
        warnings_compact=_compact_warnings(
            warnings=warnings,
            found=len(normalized_documents),
            requested=settings.transcript_target_count,
        ),
    )

    price_history = fetch_price_volume_history(symbol, period="3mo")
    charts = ChartsPayload(
        price_volume=[
            PriceVolumePoint(date=item.date, close=round(item.close, 4), volume=round(item.volume, 2))
            for item in price_history
        ],
        sentiment_timeline=sentiment_timeline,
        fundamentals_trend=fundamentals_trend,
    )

    report_tabs = _build_report_tabs(
        overview=overview,
        transcript_section=transcript_section,
        market_reaction=market_reaction,
        fundamentals_section=fundamentals_workspace,
        data_audit=data_audit,
    )

    workflow = _workflow_from_sections(transcript_availability)

    return AnalysisResponse(
        analysis_version=ANALYSIS_VERSION,
        ui_copy=UI_COPY,
        overview=overview,
        transcript=transcript_section,
        market_reaction=market_reaction,
        fundamentals_workspace=fundamentals_workspace,
        data_audit=data_audit,
        ticker=symbol,
        transcripts_found=len(normalized_documents),
        overall_sentiment_score=round(overall_score, 4),
        overall_sentiment_label=overall_label,
        warnings=warnings,
        aggregate_scores=aggregate,
        fundamentals=fundamentals,
        news_summary=news_summary,
        social_summary=social_summary,
        analyst_team=analyst_team,
        research_team=research_team,
        trader_plan=trader_plan,
        risk_management=risk_management,
        manager_decision=manager_decision,
        workflow=workflow,
        run_summary=run_summary,
        data_health=data_health,
        report_tabs=report_tabs,
        charts=charts,
        news=news,
        social=social,
        transcripts=transcript_results,
    )
