"""Core analysis pipeline for transcript sentiment, confidence, and multi-stage synthesis."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import re
from statistics import mean
from typing import Any, Optional

from .finbert_model import get_engine
from .providers import (
    TranscriptFetchDiagnostics,
    fetch_fundamentals,
    fetch_last_4_transcripts,
    fetch_news_alpha_vantage,
    fetch_price_volume_history,
    fetch_social_reddit,
)
from .schemas import (
    AggregateScores,
    AnalysisResponse,
    AnalystSignal,
    ChartsPayload,
    DataHealth,
    FundamentalsSnapshot,
    FundamentalsSummary,
    FundamentalsTrendPoint,
    ManagerDecision,
    NewsArticle,
    NewsSummary,
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
    TranscriptHealth,
    TranscriptQuarterStatus,
    TranscriptResult,
    WorkflowStage,
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


def _stance_from_score(score: float) -> str:
    if score >= 0.12:
        return "bullish"
    if score <= -0.12:
        return "bearish"
    return "mixed"


def _pct_text(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}%"


def _float_text(value: Optional[float]) -> str:
    if value is None:
        return "n/a"
    return f"{value:.2f}"


def _fundamentals_signal_score(fundamentals: FundamentalsSummary) -> float:
    rev_growth = _as_percent(fundamentals.revenue_qoq_growth_pct)
    eps_growth = _as_percent(fundamentals.eps_qoq_growth_pct)
    combined = (rev_growth * 0.55) + (eps_growth * 0.45)
    return _clamp_unit(combined / 50.0)


def _build_fundamentals_key_points(fundamentals: FundamentalsSummary) -> list[str]:
    points = [
        f"Revenue QoQ growth: {_pct_text(fundamentals.revenue_qoq_growth_pct)}",
        f"EPS QoQ growth: {_pct_text(fundamentals.eps_qoq_growth_pct)}",
        f"Trailing PE: {_float_text(fundamentals.trailing_pe)} | Forward PE: {_float_text(fundamentals.forward_pe)}",
    ]
    if fundamentals.debt_to_equity is not None:
        points.append(f"Debt/Equity: {fundamentals.debt_to_equity:.2f}")
    return points


def _top_items_by_score(
    scored_text: list[tuple[float, str]],
    positive: bool,
    limit: int = 3,
) -> list[str]:
    filtered = [row for row in scored_text if row[1].strip()]
    if not filtered:
        return []
    ranked = sorted(filtered, key=lambda x: x[0], reverse=positive)
    return [text for _, text in ranked[:limit]]


def _aggregate_scores(
    transcript_results: list[TranscriptResult],
    fundamentals: FundamentalsSummary,
    news_avg_sentiment: float,
    social_avg_sentiment: float,
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
    news_boost = news_avg_sentiment * 12.0
    social_boost = social_avg_sentiment * 8.0

    strength = _clamp(55 + (avg_directional * 35) + fundamentals_boost + news_boost + social_boost)

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
    social_avg_sentiment: float,
) -> tuple[float, str]:
    transcript_component = (
        mean(t.sentiment.directional_score for t in transcript_results)
        if transcript_results
        else 0.0
    )

    fundamentals_component = _fundamentals_signal_score(fundamentals)

    if transcript_results:
        score = (
            (transcript_component * 0.45)
            + (news_avg_sentiment * 0.25)
            + (social_avg_sentiment * 0.15)
            + (fundamentals_component * 0.15)
        )
    else:
        score = (
            (news_avg_sentiment * 0.45)
            + (social_avg_sentiment * 0.25)
            + (fundamentals_component * 0.30)
        )

    normalized = _clamp_unit(score)
    return round(normalized, 4), _label_from_sentiment_score(normalized)


def _build_workflow(
    transcripts_found: int,
    news_count: int,
    social_count: int,
    decision_action: str,
) -> list[WorkflowStage]:
    ingestion_ready = transcripts_found + news_count + social_count
    ingestion_status = "completed" if ingestion_ready >= 2 else "partial"

    return [
        WorkflowStage(
            key="analyst_ingestion",
            title="Analyst Ingestion",
            status=ingestion_status,
            detail=f"Transcripts {transcripts_found}, news {news_count}, social posts {social_count}",
        ),
        WorkflowStage(
            key="research_team",
            title="Research Team Debate",
            status="completed",
            detail="Bull and bear evidence synthesized from analyst outputs.",
        ),
        WorkflowStage(
            key="trader_proposal",
            title="Trader Proposal",
            status="completed",
            detail="Trader generated a directional plan from combined evidence.",
        ),
        WorkflowStage(
            key="risk_management",
            title="Risk Management",
            status="completed",
            detail="Risk team produced aggressive/neutral/conservative constraints.",
        ),
        WorkflowStage(
            key="manager_decision",
            title="Manager Decision",
            status="completed" if decision_action != "hold" else "partial",
            detail="Final execution decision applied with controls.",
        ),
    ]


def _parse_news_datetime(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    try:
        if "T" in raw:
            dt = datetime.strptime(raw, "%Y%m%dT%H%M%S")
            return dt.strftime("%Y-%m-%d")
        dt = datetime.fromisoformat(raw)
        return dt.strftime("%Y-%m-%d")
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

    points: list[SentimentTimelinePoint] = []
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

        points.append(
            SentimentTimelinePoint(
                date=day,
                news=round(news_avg, 4),
                social=round(social_avg, 4),
                blended=round(blended, 4),
            )
        )

    return points


def _build_report_tabs(
    symbol: str,
    overall_score: float,
    overall_label: str,
    aggregate: AggregateScores,
    analyst_team: list[AnalystSignal],
    research_team: ResearchDebate,
    trader_plan: TraderProposal,
    risk_management: RiskManagementSummary,
    manager_decision: ManagerDecision,
    data_health: DataHealth,
) -> list[ReportTab]:
    analyst_rows = [
        [
            report.name,
            report.stance,
            f"{report.signal_score:+.3f}",
            f"{report.confidence_score:.1f}",
        ]
        for report in analyst_team
    ]

    summary_table = ReportTable(
        title="Core KPI",
        columns=["Metric", "Value"],
        rows=[
            ["Overall sentiment", f"{overall_label} ({overall_score:+.4f})"],
            ["Company strength", f"{aggregate.company_strength_score:.2f}"],
            ["Outlook", f"{aggregate.outlook_score:.2f}"],
            ["Confidence", f"{aggregate.confidence_score:.2f}"],
            ["Evasiveness", f"{aggregate.evasiveness_score:.2f}"],
        ],
    )

    analyst_table = ReportTable(
        title="Analyst Signal Matrix",
        columns=["Analyst", "Stance", "Signal", "Confidence"],
        rows=analyst_rows,
    )

    research_table = ReportTable(
        title="Debate Scores",
        columns=["Measure", "Value"],
        rows=[
            ["Buy evidence", f"{research_team.buy_evidence_score:.2f}"],
            ["Sell evidence", f"{research_team.sell_evidence_score:.2f}"],
        ],
    )

    trader_table = ReportTable(
        title="Trader Decision",
        columns=["Field", "Value"],
        rows=[
            ["Action", trader_plan.action.upper()],
            ["Conviction", f"{trader_plan.conviction_score:.2f}"],
            ["Horizon", trader_plan.horizon],
            ["Thesis", trader_plan.thesis],
        ],
    )

    risk_rows = [
        [view.profile, f"{view.max_position_pct:.1f}%", view.recommendation]
        for view in risk_management.views
    ]
    risk_rows.append(["manager_action", manager_decision.action, " | ".join(manager_decision.rationale)])

    risk_table = ReportTable(
        title="Risk + Final Verdict",
        columns=["Role", "Constraint", "Detail"],
        rows=risk_rows,
    )

    health_rows = [
        [o.quarter, o.status, o.detail or ""]
        for o in data_health.transcripts.outcomes
    ]
    health_table = ReportTable(
        title="Transcript Retrieval Outcomes",
        columns=["Quarter", "Status", "Detail"],
        rows=health_rows,
    )

    tabs = [
        ReportTab(
            id="summary",
            title="Summary",
            markdown=(
                f"# {symbol} Summary\n\n"
                f"Overall stance: **{overall_label}** (`{overall_score:+.4f}`)\n\n"
                f"Key orientation:\n"
                f"- Strength: {aggregate.company_strength_score:.2f}\n"
                f"- Outlook: {aggregate.outlook_score:.2f}\n"
                f"- Confidence: {aggregate.confidence_score:.2f}\n"
                f"- Evasiveness: {aggregate.evasiveness_score:.2f}\n\n"
                "Deterministic KPI values are in the table below."
            ),
            kpis=[
                ReportKPI(label="overall", value=f"{overall_label} ({overall_score:+.4f})"),
                ReportKPI(label="strength", value=f"{aggregate.company_strength_score:.2f}"),
                ReportKPI(label="outlook", value=f"{aggregate.outlook_score:.2f}"),
            ],
            tables=[summary_table],
        ),
        ReportTab(
            id="analyst",
            title="Analyst Reports",
            markdown=(
                "# Analyst Signal Matrix\n\n"
                "Structured matrix values are in the table below.\n\n"
                + "\n".join(
                    [f"## {r.name.title()} Analyst\n- " + "\n- ".join(r.key_points[:4]) for r in analyst_team]
                )
            ),
            kpis=[
                ReportKPI(label="analysts", value=str(len(analyst_team))),
            ],
            tables=[analyst_table],
        ),
        ReportTab(
            id="research",
            title="Research Debate",
            markdown=(
                "# Research Debate\n\n"
                f"{research_team.discussion_summary}\n\n"
                "Debate score breakdown is in the table below.\n\n"
                "## Bullish points\n- "
                + "\n- ".join(research_team.bullish_points)
                + "\n\n## Bearish points\n- "
                + "\n- ".join(research_team.bearish_points)
            ),
            kpis=[
                ReportKPI(label="buy evidence", value=f"{research_team.buy_evidence_score:.2f}"),
                ReportKPI(label="sell evidence", value=f"{research_team.sell_evidence_score:.2f}"),
            ],
            tables=[research_table],
        ),
        ReportTab(
            id="trader",
            title="Trader Plan",
            markdown="# Trader Plan\n\nDecision rows are shown in the table below.",
            kpis=[
                ReportKPI(label="action", value=trader_plan.action.upper()),
                ReportKPI(label="conviction", value=f"{trader_plan.conviction_score:.2f}"),
            ],
            tables=[trader_table],
        ),
        ReportTab(
            id="risk_manager",
            title="Risk + Final Verdict",
            markdown=(
                "# Risk + Final Verdict\n\n"
                f"Consensus: {risk_management.consensus}\n\n"
                "Risk constraints and final verdict are in the table below.\n\n"
                "## Execution plan\n- "
                + "\n- ".join(manager_decision.execution_plan)
            ),
            kpis=[
                ReportKPI(label="decision", value=manager_decision.action.upper()),
                ReportKPI(label="risk views", value=str(len(risk_management.views))),
            ],
            tables=[risk_table],
        ),
        ReportTab(
            id="data_health",
            title="Data Health",
            markdown=(
                "# Data Health\n\n"
                f"Requested transcript quarters: {len(data_health.transcripts.requested_quarters)}\n\n"
                f"Found: {len(data_health.transcripts.found_quarters)}\n"
                f"Missing: {len(data_health.transcripts.missing_quarters)}\n"
                f"Errors: {len(data_health.transcripts.errors)}\n\n"
                + "Per-quarter outcomes are in the table below.\n\n## Compact warnings\n- "
                + "\n- ".join(data_health.warnings_compact)
            ),
            kpis=[
                ReportKPI(label="transcripts found", value=str(len(data_health.transcripts.found_quarters))),
                ReportKPI(label="transcripts missing", value=str(len(data_health.transcripts.missing_quarters))),
            ],
            tables=[health_table],
        ),
    ]

    return tabs


def _compact_warnings(warnings: list[str], diagnostics: TranscriptFetchDiagnostics) -> list[str]:
    out: list[str] = []

    if diagnostics.requested_quarters:
        out.append(
            f"Transcripts {len(diagnostics.found_quarters)}/{len(diagnostics.requested_quarters)} found."
        )

    if diagnostics.errors:
        out.append(f"Transcript retrieval errors: {len(diagnostics.errors)}")

    for warning in warnings[:4]:
        out.append(warning)

    if not out:
        out.append("No critical data health warnings.")

    return out


def build_analysis(ticker: str, settings: Settings) -> AnalysisResponse:
    symbol = _normalize_ticker(ticker)

    transcripts, transcript_warnings, transcript_diagnostics = fetch_last_4_transcripts(symbol, settings)
    news_records, news_warnings = fetch_news_alpha_vantage(symbol, settings, limit=12)
    social_records, social_warnings = fetch_social_reddit(symbol, settings, limit=12)
    warnings = transcript_warnings + news_warnings + social_warnings

    if not transcripts and not news_records and not social_records:
        warnings.append("No transcript, news, or social records were available for this query.")

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

    engine = (
        get_engine(settings.finbert_model_name)
        if (transcripts or news_records or social_records)
        else None
    )

    news: list[NewsArticle] = []
    news_scored_text: list[tuple[float, str]] = []
    for item in news_records:
        text = f"{item.title}. {item.summary}".strip()
        if engine is not None and text:
            scored = engine.score_text(text)
            directional = float(scored["directional_score"])
        else:
            directional = float(item.sentiment_score)

        stance = _stance_from_score(directional)
        news.append(
            NewsArticle(
                title=item.title,
                summary=item.summary,
                url=item.url,
                source=item.source,
                time_published=item.time_published,
                sentiment_score=round(directional, 4),
                sentiment_label=stance,
            )
        )
        news_scored_text.append((directional, item.title))

    news_avg_sentiment = mean(item.sentiment_score for item in news) if news else 0.0
    news_summary = NewsSummary(
        article_count=len(news),
        avg_sentiment_score=round(news_avg_sentiment, 4),
        sentiment_label=_stance_from_score(news_avg_sentiment),
    )

    social: list[SocialPost] = []
    social_scored_text: list[tuple[float, str]] = []
    for item in social_records:
        text = f"{item.title}. {item.body}".strip()
        if engine is not None and text:
            scored = engine.score_text(text)
            directional = float(scored["directional_score"])
        else:
            directional = 0.0

        stance = _stance_from_score(directional)
        social.append(
            SocialPost(
                source=item.source,
                title=item.title,
                body=item.body,
                url=item.url,
                subreddit=item.subreddit,
                created_utc=item.created_utc,
                relevance_score=round(item.relevance_score, 3),
                sentiment_score=round(directional, 4),
                sentiment_label=stance,
            )
        )
        social_scored_text.append((directional, f"r/{item.subreddit or 'unknown'}: {item.title}"))

    social_avg_sentiment = mean(item.sentiment_score for item in social) if social else 0.0
    social_summary = SocialSummary(
        post_count=len(social),
        avg_sentiment_score=round(social_avg_sentiment, 4),
        sentiment_label=_stance_from_score(social_avg_sentiment),
    )

    transcript_results: list[TranscriptResult] = []
    transcript_directionals: list[float] = []

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

        directional = round(float(sentiment_raw["directional_score"]), 4)
        transcript_directionals.append(directional)

        transcript_results.append(
            TranscriptResult(
                year=transcript.year,
                quarter=transcript.quarter,
                date=transcript.date,
                source=transcript.source,
                sentiment=SentimentBreakdown(
                    positive=round(float(sentiment_raw["positive"]), 4),
                    negative=round(float(sentiment_raw["negative"]), 4),
                    neutral=round(float(sentiment_raw["neutral"]), 4),
                    directional_score=directional,
                    label=_stance_from_score(directional),
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

    aggregate = _aggregate_scores(
        transcript_results,
        fundamentals,
        news_avg_sentiment,
        social_avg_sentiment,
    )
    overall_score, overall_label = _compute_overall_sentiment(
        transcript_results,
        fundamentals,
        news_avg_sentiment,
        social_avg_sentiment,
    )

    transcript_signal = mean(transcript_directionals) if transcript_directionals else 0.0
    transcript_confidence = (
        mean(t.confidence_score for t in transcript_results) if transcript_results else 40.0
    )
    transcript_bull = [signal for t in transcript_results for signal in t.bullish_signals][:3]
    transcript_bear = [signal for t in transcript_results for signal in t.bearish_signals][:3]
    transcript_quotes = [quote for t in transcript_results for quote in t.decision_relevant_quotes][:4]

    fundamentals_signal = _fundamentals_signal_score(fundamentals)
    fundamentals_points = _build_fundamentals_key_points(fundamentals)

    analyst_team = [
        AnalystSignal(
            name="transcript",
            stance=_stance_from_score(transcript_signal),
            signal_score=round(transcript_signal, 4),
            confidence_score=round(_clamp(transcript_confidence), 2),
            key_points=[
                f"Bullish cues: {len(transcript_bull)} | Bearish cues: {len(transcript_bear)}",
                f"Outlook score (avg): {_float_text(mean(t.outlook_score for t in transcript_results) if transcript_results else 50.0)}",
                f"Evasiveness score (avg): {_float_text(mean(t.evasiveness_score for t in transcript_results) if transcript_results else 35.0)}",
            ],
            evidence=(transcript_quotes or ["No transcript quotes available."]),
        ),
        AnalystSignal(
            name="fundamentals",
            stance=_stance_from_score(fundamentals_signal),
            signal_score=round(fundamentals_signal, 4),
            confidence_score=round(_clamp(45 + len(fundamentals.quarterly) * 12), 2),
            key_points=fundamentals_points,
            evidence=[
                (
                    f"{q.quarter}: revenue={_float_text(q.revenue)}, EPS={_float_text(q.reported_eps)}, "
                    f"EPS est={_float_text(q.eps_estimate)}"
                )
                for q in fundamentals.quarterly[:3]
            ]
            or ["No recent fundamentals snapshots available."],
        ),
        AnalystSignal(
            name="news",
            stance=_stance_from_score(news_avg_sentiment),
            signal_score=round(news_avg_sentiment, 4),
            confidence_score=round(_clamp(35 + len(news) * 5), 2),
            key_points=[
                f"Articles analyzed: {len(news)}",
                f"Average FinBERT directional score: {news_avg_sentiment:.3f}",
                f"Dominant stance: {_stance_from_score(news_avg_sentiment)}",
            ],
            evidence=(
                _top_items_by_score(news_scored_text, positive=True, limit=2)
                + _top_items_by_score(news_scored_text, positive=False, limit=2)
            )
            or ["No news evidence available."],
        ),
        AnalystSignal(
            name="social",
            stance=_stance_from_score(social_avg_sentiment),
            signal_score=round(social_avg_sentiment, 4),
            confidence_score=round(_clamp(30 + len(social) * 6), 2),
            key_points=[
                f"Posts analyzed: {len(social)}",
                f"Average FinBERT directional score: {social_avg_sentiment:.3f}",
                f"Top relevance score: {max((p.relevance_score for p in social), default=0):.2f}",
            ],
            evidence=(
                _top_items_by_score(social_scored_text, positive=True, limit=2)
                + _top_items_by_score(social_scored_text, positive=False, limit=2)
            )
            or ["No social evidence available."],
        ),
    ]

    combined_signal = round(
        (
            transcript_signal * 0.40
            + fundamentals_signal * 0.20
            + news_avg_sentiment * 0.25
            + social_avg_sentiment * 0.15
        ),
        4,
    )

    bullish_points = [
        f"{report.name.title()}: {report.key_points[0]}"
        for report in analyst_team
        if report.signal_score > 0.05
    ]
    bearish_points = [
        f"{report.name.title()}: {report.key_points[0]}"
        for report in analyst_team
        if report.signal_score < -0.05
    ]

    if not bullish_points:
        bullish_points = ["No strong bullish cluster detected across current modules."]
    if not bearish_points:
        bearish_points = ["No strong bearish cluster detected across current modules."]

    buy_evidence_score = _clamp(50 + (combined_signal * 45) + (len(bullish_points) * 4) - (len(bearish_points) * 2))
    sell_evidence_score = _clamp(50 - (combined_signal * 45) + (len(bearish_points) * 4) - (len(bullish_points) * 2))

    research_team = ResearchDebate(
        bullish_points=bullish_points[:5],
        bearish_points=bearish_points[:5],
        discussion_summary=(
            f"Composite signal is {combined_signal:+.3f}. "
            f"Buy evidence {buy_evidence_score:.1f} vs sell evidence {sell_evidence_score:.1f}."
        ),
        buy_evidence_score=round(buy_evidence_score, 2),
        sell_evidence_score=round(sell_evidence_score, 2),
    )

    if combined_signal >= 0.20:
        trader_action = "buy"
    elif combined_signal <= -0.20:
        trader_action = "sell"
    else:
        trader_action = "hold"

    conviction = _clamp(abs(combined_signal) * 100 + (abs(buy_evidence_score - sell_evidence_score) * 0.25))
    trader_plan = TraderProposal(
        action=trader_action,
        conviction_score=round(conviction, 2),
        thesis=(
            f"Trader leans {trader_action.upper()} from blended analyst signal ({combined_signal:+.3f}) "
            "after reconciling fundamentals, news, social, and transcript sentiment."
        ),
        horizon="1-4 weeks",
    )

    disagreement = _clamp(100 - abs(buy_evidence_score - sell_evidence_score))
    aggressive_size = 35.0 if trader_action != "hold" else 15.0
    neutral_size = 20.0 if trader_action != "hold" else 10.0
    conservative_size = 10.0 if trader_action != "hold" else 5.0

    risk_views = [
        RiskView(
            profile="aggressive",
            recommendation=(
                f"Allow up to {aggressive_size:.0f}% position if momentum confirms and stop-loss discipline is enforced."
            ),
            max_position_pct=aggressive_size,
        ),
        RiskView(
            profile="neutral",
            recommendation=(
                f"Cap initial allocation near {neutral_size:.0f}% and scale only if evidence spread widens."
            ),
            max_position_pct=neutral_size,
        ),
        RiskView(
            profile="conservative",
            recommendation=(
                f"Limit to {conservative_size:.0f}% unless macro and earnings signals align for multiple cycles."
            ),
            max_position_pct=conservative_size,
        ),
    ]

    if conviction < 55 or disagreement > 55:
        risk_consensus = "High disagreement or low conviction: default to reduced risk posture."
        manager_action = "hold"
    elif trader_action == "buy":
        risk_consensus = "Evidence favors controlled long exposure with staged entries."
        manager_action = "approve_buy"
    elif trader_action == "sell":
        risk_consensus = "Evidence favors controlled de-risking with staged exits."
        manager_action = "approve_sell"
    else:
        risk_consensus = "Balanced evidence: hold and wait for clearer directional setup."
        manager_action = "hold"

    risk_management = RiskManagementSummary(views=risk_views, consensus=risk_consensus)

    if manager_action == "approve_buy":
        execution_plan = [
            "Enter in 2-3 tranches near support to reduce timing risk.",
            "Use neutral-risk sizing as base allocation and scale only on confirming catalysts.",
            "Place invalidation stop below the most recent structural support.",
        ]
    elif manager_action == "approve_sell":
        execution_plan = [
            "Reduce exposure in staged clips to avoid liquidity shock.",
            "Prioritize trimming into strength while preserving optionality.",
            "Keep a re-entry trigger list tied to earnings and guidance revisions.",
        ]
    else:
        execution_plan = [
            "No trade execution now; monitor incoming news and next transcript cycle.",
            "Track spread between buy/sell evidence until conviction exceeds threshold.",
            "Re-run analysis after major catalyst events.",
        ]

    manager_decision = ManagerDecision(
        action=manager_action,
        rationale=[
            f"Trader action: {trader_action}",
            f"Conviction score: {conviction:.1f}",
            f"Debate spread: {abs(buy_evidence_score - sell_evidence_score):.1f}",
            risk_consensus,
        ],
        execution_plan=execution_plan,
    )

    workflow = _build_workflow(
        transcripts_found=len(transcript_results),
        news_count=len(news),
        social_count=len(social),
        decision_action=manager_action,
    )

    compact_warnings = _compact_warnings(warnings, transcript_diagnostics)

    data_health = DataHealth(
        transcripts=TranscriptHealth(
            requested_quarters=transcript_diagnostics.requested_quarters,
            found_quarters=transcript_diagnostics.found_quarters,
            missing_quarters=transcript_diagnostics.missing_quarters,
            errors=transcript_diagnostics.errors,
            outcomes=[
                TranscriptQuarterStatus(
                    quarter=o.quarter,
                    status=o.status,
                    detail=o.detail,
                )
                for o in transcript_diagnostics.outcomes
            ],
        ),
        warnings_compact=compact_warnings,
    )

    run_summary = RunSummary(
        ticker=symbol,
        overall_label=overall_label,
        overall_score=overall_score,
        transcripts_found=len(transcript_results),
        news_count=len(news),
        social_count=len(social),
    )

    price_history = fetch_price_volume_history(symbol, period="3mo")

    charts = ChartsPayload(
        price_volume=[
            PriceVolumePoint(date=p.date, close=round(p.close, 4), volume=round(p.volume, 2))
            for p in price_history
        ],
        sentiment_timeline=_build_sentiment_timeline(news, social),
        fundamentals_trend=[
            FundamentalsTrendPoint(
                quarter=q.quarter,
                revenue=q.revenue,
                net_income=q.net_income,
                eps=q.reported_eps,
            )
            for q in reversed(fundamentals.quarterly)
        ],
    )

    report_tabs = _build_report_tabs(
        symbol=symbol,
        overall_score=overall_score,
        overall_label=overall_label,
        aggregate=aggregate,
        analyst_team=analyst_team,
        research_team=research_team,
        trader_plan=trader_plan,
        risk_management=risk_management,
        manager_decision=manager_decision,
        data_health=data_health,
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
