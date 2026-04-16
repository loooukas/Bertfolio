"""Core analysis pipeline for transcript sentiment, confidence, and fundamentals comparison."""

from __future__ import annotations

import re
from statistics import mean
from typing import Any, Optional

from .finbert_model import get_engine
from .providers import fetch_fundamentals, fetch_last_4_transcripts, fetch_news_alpha_vantage
from .schemas import (
    AggregateScores,
    AnalysisResponse,
    FundamentalsSnapshot,
    FundamentalsSummary,
    NewsArticle,
    NewsSummary,
    SentimentBreakdown,
    TranscriptResult,
)
from .settings import Settings

BULLISH_TERMS = {
    "sequential improvement",
    "share gain",
    "share gains",
    "pipeline expansion",
    "disciplined guidance",
    "bookings strength",
    "better mix",
    "stable backlog",
    "design win",
    "strong demand",
    "margin expansion",
}

BEARISH_TERMS = {
    "moderating demand",
    "elongated sales cycles",
    "macro uncertainty",
    "promotional environment",
    "margin headwind",
    "inventory normalization",
    "customer digestion",
    "pacing issues",
    "weaker demand",
    "softness",
    "headwind",
}

HEDGING_TERMS = {
    "we believe",
    "we expect",
    "we remain confident",
    "as we said",
    "too early",
    "cannot comment",
    "not going to comment",
    "prudently",
    "assuming",
    "could",
    "may",
    "might",
}

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


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


def _clamp_unit(value: float) -> float:
    return max(-1.0, min(1.0, value))


def _normalize_ticker(ticker: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9.-]", "", ticker.strip().upper())
    if not cleaned:
        raise ValueError("Ticker cannot be empty.")
    return cleaned


def _split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if len(p.strip()) >= 20]


def _contains_any(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in keywords)


def _keyword_hits(sentences: list[str], keywords: set[str], limit: int = 6) -> list[str]:
    hits = [s for s in sentences if _contains_any(s, keywords)]
    return hits[:limit]


def _estimate_confidence(sentences: list[str], hedging_hits: int) -> float:
    if not sentences:
        return 40.0
    numeric_density = sum(1 for s in sentences if re.search(r"\d", s)) / len(sentences)
    hedging_density = hedging_hits / len(sentences)
    score = 45 + (numeric_density * 40) - (hedging_density * 35)
    return _clamp(score)


def _estimate_evasiveness(qa_sentences: list[str]) -> tuple[float, list[str]]:
    if not qa_sentences:
        return 35.0, []
    evasive_hits = _keyword_hits(qa_sentences, HEDGING_TERMS, limit=8)
    density = len(evasive_hits) / max(len(qa_sentences), 1)
    return _clamp(30 + density * 80), evasive_hits


def _qa_section(sentences: list[str]) -> list[str]:
    start_idx = None
    for i, sentence in enumerate(sentences):
        lowered = sentence.lower()
        if "question-and-answer" in lowered or "q&a" in lowered:
            start_idx = i
            break
    if start_idx is None:
        return []
    return sentences[start_idx:]


def _pick_quotes(sentence_scores: list[dict[str, Any]], sentiment_key: str, limit: int = 3) -> list[str]:
    ranked = sorted(sentence_scores, key=lambda x: float(x.get(sentiment_key, 0.0)), reverse=True)
    quotes: list[str] = []
    for row in ranked:
        sentence = str(row.get("sentence", "")).strip()
        if len(sentence) < 30:
            continue
        quotes.append(sentence)
        if len(quotes) >= limit:
            break
    return quotes


def _as_percent(value: Optional[float]) -> float:
    if value is None:
        return 0.0
    return float(value)


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


def _aggregate_scores(
    transcript_results: list[TranscriptResult],
    fundamentals: FundamentalsSummary,
    news_avg_sentiment: float,
) -> AggregateScores:
    if transcript_results:
        avg_directional = mean(t.sentiment.directional_score for t in transcript_results)
        avg_outlook = mean(t.outlook_score for t in transcript_results)
        avg_confidence = mean(t.confidence_score for t in transcript_results)
        avg_evasive = mean(t.evasiveness_score for t in transcript_results)
    else:
        avg_directional = 0.0
        avg_outlook = 50.0
        avg_confidence = 50.0
        avg_evasive = 35.0

    rev_growth = _as_percent(fundamentals.revenue_qoq_growth_pct)
    eps_growth = _as_percent(fundamentals.eps_qoq_growth_pct)
    fundamentals_boost = (rev_growth * 0.18) + (eps_growth * 0.24)
    news_boost = news_avg_sentiment * 15.0

    strength = _clamp(55 + (avg_directional * 35) + fundamentals_boost + news_boost)

    return AggregateScores(
        company_strength_score=round(strength, 2),
        outlook_score=round(_clamp(avg_outlook), 2),
        confidence_score=round(_clamp(avg_confidence), 2),
        evasiveness_score=round(_clamp(avg_evasive), 2),
        sentiment_label=_label_from_sentiment_score(avg_directional),
    )


def _compute_overall_sentiment(
    transcript_results: list[TranscriptResult],
    fundamentals: FundamentalsSummary,
    news_avg_sentiment: float,
) -> tuple[float, str]:
    transcript_component = (
        mean(t.sentiment.directional_score for t in transcript_results)
        if transcript_results
        else 0.0
    )

    rev_growth = _as_percent(fundamentals.revenue_qoq_growth_pct)
    eps_growth = _as_percent(fundamentals.eps_qoq_growth_pct)
    fundamentals_component = _clamp_unit(((rev_growth + eps_growth) / 2.0) / 100.0)

    if transcript_results:
        score = (
            (transcript_component * 0.5)
            + (news_avg_sentiment * 0.35)
            + (fundamentals_component * 0.15)
        )
    else:
        score = (news_avg_sentiment * 0.7) + (fundamentals_component * 0.3)

    normalized = _clamp_unit(score)
    return round(normalized, 4), _label_from_sentiment_score(normalized)


def build_analysis(ticker: str, settings: Settings) -> AnalysisResponse:
    symbol = _normalize_ticker(ticker)

    transcripts, transcript_warnings = fetch_last_4_transcripts(symbol, settings)
    news_records, news_warnings = fetch_news_alpha_vantage(symbol, settings, limit=12)
    warnings = transcript_warnings + news_warnings

    if not transcripts and not news_records:
        warnings.append("No Alpha Vantage transcript or news records were available for this query.")

    fundamentals_dict = fetch_fundamentals(symbol)
    fundamentals = FundamentalsSummary(
        currency=fundamentals_dict.get("currency"),
        market_cap=fundamentals_dict.get("market_cap"),
        trailing_pe=fundamentals_dict.get("trailing_pe"),
        forward_pe=fundamentals_dict.get("forward_pe"),
        debt_to_equity=fundamentals_dict.get("debt_to_equity"),
        quarterly=[FundamentalsSnapshot(**q) for q in fundamentals_dict.get("quarterly", [])],
        revenue_qoq_growth_pct=fundamentals_dict.get("revenue_qoq_growth_pct"),
        eps_qoq_growth_pct=fundamentals_dict.get("eps_qoq_growth_pct"),
    )

    news = [
        NewsArticle(
            title=item.title,
            summary=item.summary,
            url=item.url,
            source=item.source,
            time_published=item.time_published,
            sentiment_score=round(item.sentiment_score, 4),
            sentiment_label=item.sentiment_label,
        )
        for item in news_records
    ]

    if news:
        news_avg_sentiment = mean(item.sentiment_score for item in news)
    else:
        news_avg_sentiment = 0.0

    news_summary = NewsSummary(
        article_count=len(news),
        avg_sentiment_score=round(news_avg_sentiment, 4),
        sentiment_label=_label_from_sentiment_score(news_avg_sentiment),
    )

    engine = get_engine(settings.finbert_model_name) if transcripts else None
    transcript_results: list[TranscriptResult] = []

    for transcript in transcripts:
        if engine is None:
            break
        sentences = _split_sentences(transcript.content)
        if len(sentences) > 250:
            sentences = sentences[:250]
            warnings.append(
                f"{symbol} {transcript.year}-Q{transcript.quarter}: capped sentence analysis at 250 for local latency."
            )

        sentiment_raw = engine.score_text(transcript.content)
        sentence_scores = engine.classify_sentences(sentences)

        bullish_hits = _keyword_hits(sentences, BULLISH_TERMS)
        bearish_hits = _keyword_hits(sentences, BEARISH_TERMS)
        qa_sentences = _qa_section(sentences)
        evasiveness_score, evasive_hits = _estimate_evasiveness(qa_sentences)

        forward_sentences = [s for s in sentences if _contains_any(s, FORWARD_LOOKING_MARKERS)]
        if forward_sentences:
            forward_sentiment = engine.score_text(" ".join(forward_sentences))
            outlook_score = _clamp(50 + (forward_sentiment["directional_score"] * 45))
        else:
            outlook_score = _clamp(50 + (sentiment_raw["directional_score"] * 35))

        confidence_score = _estimate_confidence(sentences, len(evasive_hits))

        top_positive_quotes = _pick_quotes(sentence_scores, "positive", limit=2)
        top_negative_quotes = _pick_quotes(sentence_scores, "negative", limit=2)
        quotes = top_positive_quotes + top_negative_quotes

        transcript_results.append(
            TranscriptResult(
                year=transcript.year,
                quarter=transcript.quarter,
                date=transcript.date,
                source=transcript.source,
                sentiment=SentimentBreakdown(
                    positive=round(sentiment_raw["positive"], 4),
                    negative=round(sentiment_raw["negative"], 4),
                    neutral=round(sentiment_raw["neutral"], 4),
                    directional_score=round(sentiment_raw["directional_score"], 4),
                    label=sentiment_raw["label"],
                ),
                confidence_score=round(confidence_score, 2),
                outlook_score=round(outlook_score, 2),
                evasiveness_score=round(evasiveness_score, 2),
                bullish_signals=bullish_hits,
                bearish_signals=bearish_hits,
                evasive_signals=evasive_hits,
                decision_relevant_quotes=quotes,
            )
        )

    aggregate = _aggregate_scores(transcript_results, fundamentals, news_avg_sentiment)
    overall_score, overall_label = _compute_overall_sentiment(
        transcript_results,
        fundamentals,
        news_avg_sentiment,
    )

    return AnalysisResponse(
        ticker=symbol,
        transcripts_found=len(transcript_results),
        overall_sentiment_score=overall_score,
        overall_sentiment_label=overall_label,
        warnings=warnings,
        aggregate_scores=aggregate,
        fundamentals=fundamentals,
        news_summary=news_summary,
        news=news,
        transcripts=transcript_results,
    )
