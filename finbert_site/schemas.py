"""Pydantic models for API responses."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SentimentBreakdown(BaseModel):
    positive: float
    negative: float
    neutral: float
    directional_score: float
    label: str


class TranscriptResult(BaseModel):
    year: int
    quarter: int
    date: Optional[str] = None
    source: str
    sentiment: SentimentBreakdown
    confidence_score: float = Field(ge=0, le=100)
    outlook_score: float = Field(ge=0, le=100)
    evasiveness_score: float = Field(ge=0, le=100)
    bullish_signals: list[str]
    bearish_signals: list[str]
    evasive_signals: list[str]
    decision_relevant_quotes: list[str]


class FundamentalsSnapshot(BaseModel):
    quarter: str
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    reported_eps: Optional[float] = None
    eps_estimate: Optional[float] = None


class FundamentalsSummary(BaseModel):
    currency: Optional[str] = None
    market_cap: Optional[float] = None
    trailing_pe: Optional[float] = None
    forward_pe: Optional[float] = None
    debt_to_equity: Optional[float] = None
    beta: Optional[float] = None
    enterprise_value: Optional[float] = None
    total_debt: Optional[float] = None
    total_cash: Optional[float] = None
    current_ratio: Optional[float] = None
    quick_ratio: Optional[float] = None
    return_on_equity: Optional[float] = None
    operating_margin: Optional[float] = None
    free_cashflow: Optional[float] = None
    quarterly: list[FundamentalsSnapshot]
    revenue_qoq_growth_pct: Optional[float] = None
    eps_qoq_growth_pct: Optional[float] = None


class AggregateScores(BaseModel):
    company_strength_score: float = Field(ge=0, le=100)
    outlook_score: float = Field(ge=0, le=100)
    confidence_score: float = Field(ge=0, le=100)
    evasiveness_score: float = Field(ge=0, le=100)
    sentiment_label: Literal[
        "strongly_bullish",
        "cautiously_bullish",
        "mixed",
        "cautiously_bearish",
        "strongly_bearish",
    ]


class NewsArticle(BaseModel):
    title: str
    summary: str
    url: str
    source: Optional[str] = None
    time_published: Optional[str] = None
    sentiment_score: float
    sentiment_label: str


class NewsSummary(BaseModel):
    article_count: int
    avg_sentiment_score: float
    sentiment_label: str


class SocialPost(BaseModel):
    source: str
    title: str
    body: str
    excerpt: Optional[str] = None
    url: str
    subreddit: Optional[str] = None
    created_utc: Optional[int] = None
    relevance_score: float = Field(ge=0)
    sentiment_score: float
    sentiment_label: str


class SocialSummary(BaseModel):
    post_count: int
    avg_sentiment_score: float
    sentiment_label: str


class AnalystSignal(BaseModel):
    name: Literal["transcript", "fundamentals", "news", "social"]
    stance: Literal["bullish", "bearish", "mixed"]
    signal_score: float = Field(ge=-1, le=1)
    confidence_score: float = Field(ge=0, le=100)
    key_points: list[str]
    evidence: list[str]


class ResearchDebate(BaseModel):
    bullish_points: list[str]
    bearish_points: list[str]
    discussion_summary: str
    buy_evidence_score: float = Field(ge=0, le=100)
    sell_evidence_score: float = Field(ge=0, le=100)


class TraderProposal(BaseModel):
    action: Literal["buy", "sell", "hold"]
    conviction_score: float = Field(ge=0, le=100)
    thesis: str
    horizon: str


class RiskView(BaseModel):
    profile: Literal["aggressive", "neutral", "conservative"]
    recommendation: str
    max_position_pct: float = Field(ge=0, le=100)


class RiskManagementSummary(BaseModel):
    views: list[RiskView]
    consensus: str


class ManagerDecision(BaseModel):
    action: Literal["approve_buy", "approve_sell", "hold"]
    rationale: list[str]
    execution_plan: list[str]


class WorkflowStage(BaseModel):
    key: str
    title: str
    status: Literal["completed", "partial", "skipped"]
    detail: str


class RunSummary(BaseModel):
    ticker: str
    overall_label: str
    overall_score: float
    transcripts_found: int
    news_count: int
    social_count: int


class TranscriptQuarterStatus(BaseModel):
    quarter: str
    status: Literal["found", "not_found", "error"]
    detail: Optional[str] = None


class TranscriptHealth(BaseModel):
    requested_quarters: list[str]
    found_quarters: list[str]
    missing_quarters: list[str]
    errors: list[str]
    outcomes: list[TranscriptQuarterStatus]


class DataHealth(BaseModel):
    transcripts: TranscriptHealth
    warnings_compact: list[str]


class ReportKPI(BaseModel):
    label: str
    value: str


class ReportTable(BaseModel):
    title: str
    columns: list[str]
    rows: list[list[str]]


class ReportTab(BaseModel):
    id: str
    title: str
    markdown: str
    kpis: list[ReportKPI]
    tables: list[ReportTable]


class PriceVolumePoint(BaseModel):
    date: str
    close: float
    volume: float


class SentimentTimelinePoint(BaseModel):
    date: str
    news: float
    social: float
    blended: float


class FundamentalsTrendPoint(BaseModel):
    quarter: str
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    eps: Optional[float] = None
    eps_estimate: Optional[float] = None


class ChartsPayload(BaseModel):
    price_volume: list[PriceVolumePoint]
    sentiment_timeline: list[SentimentTimelinePoint]
    fundamentals_trend: list[FundamentalsTrendPoint]


class CopyDictionary(BaseModel):
    app_title: str
    app_subtitle: str
    section_labels: dict[str, str]
    ui_labels: dict[str, str]
    empty_states: dict[str, str]
    headings: dict[str, str] = Field(default_factory=dict)
    microcopy: dict[str, str] = Field(default_factory=dict)


class CompactMetric(BaseModel):
    key: str
    label: str
    value: str


class OverviewSection(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    stance_label: str
    executive_summary: str
    key_takeaways: list[str]
    metrics: list[CompactMetric]


class TranscriptParticipant(BaseModel):
    name: str
    role: Optional[str] = None


class TranscriptSectionBlock(BaseModel):
    section_type: Literal["prepared_remarks", "qa", "other"]
    speaker: str
    speaker_role: Optional[str] = None
    text: str
    order_index: int
    evidence_snippets: list[str]


class TranscriptSpeakerAnalysis(BaseModel):
    speaker: str
    section_type: Literal["prepared_remarks", "qa", "other"]
    sentiment_direction: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=100)
    evasiveness: float = Field(ge=0, le=100)
    specificity: float = Field(ge=0, le=100)
    forward_looking_strength: float = Field(ge=0, le=100)
    risk_language_intensity: float = Field(ge=0, le=100)
    topic_label: str
    evidence_snippets: list[str]
    segment_diagnostics: Optional[dict[str, Any]] = None


class TranscriptDocument(BaseModel):
    ticker: str
    company_name: Optional[str] = None
    source: str
    source_url: Optional[str] = None
    title: Optional[str] = None
    published_date: Optional[str] = None
    has_full_transcript: bool
    extraction_confidence: float = Field(ge=0, le=1)
    parsing_warnings: list[str]
    participants: list[TranscriptParticipant]
    sections: list[TranscriptSectionBlock]
    key_quotes: list[str]
    normalization_mode: Literal["openai", "deterministic_degraded"]


class TranscriptSectionPayload(BaseModel):
    availability: Literal["available", "partial", "missing"]
    transcript_count_requested: int
    transcript_count_found: int
    latest_summary: str
    prepared_vs_qa_note: str
    speaker_analysis: list[TranscriptSpeakerAnalysis]
    key_quotes: list[str]
    qa_pressure_points: list[str]
    transcripts: list[TranscriptDocument]
    speaker_confidence_profile: list[dict[str, Any]]
    chart_enabled: bool
    sparse_note: Optional[str] = None


class MarketReactionSection(BaseModel):
    balance_summary: str
    news_count: int
    social_count: int
    news_items: list[NewsArticle]
    social_items: list[SocialPost]
    chart_enabled: bool
    sparse_note: Optional[str] = None


class FundamentalsWorkspaceSection(BaseModel):
    operating_context: str
    metrics: list[CompactMetric]
    table: list[FundamentalsSnapshot]
    trend_series: list[FundamentalsTrendPoint]
    chart_enabled: bool
    sparse_note: Optional[str] = None


class TranscriptDiscoveryAudit(BaseModel):
    pages_scanned: int
    candidates_total: int
    transcript_like_count: int
    match_filtered_count: int
    selected_count: int
    discarded_near_matches: list[str]
    fetch_failures: list[str]
    playwright_fallback_used: bool


class DataAuditSection(BaseModel):
    transcript_discovery: TranscriptDiscoveryAudit
    source_counts: dict[str, int]
    dedupe_counts: dict[str, int]
    parsing_warnings: list[str]
    missing_items: list[str]
    normalization_mode: Literal["openai", "deterministic_degraded"]
    warnings: list[str]
    confidence_note: str


class AnalysisResponse(BaseModel):
    analysis_version: str
    ui_copy: CopyDictionary
    overview: OverviewSection
    transcript: TranscriptSectionPayload
    market_reaction: MarketReactionSection
    fundamentals_workspace: FundamentalsWorkspaceSection
    data_audit: DataAuditSection
    ticker: str
    transcripts_found: int
    overall_sentiment_score: float
    overall_sentiment_label: str
    warnings: list[str]
    aggregate_scores: AggregateScores
    fundamentals: FundamentalsSummary
    news_summary: NewsSummary
    social_summary: SocialSummary
    analyst_team: list[AnalystSignal]
    research_team: ResearchDebate
    trader_plan: TraderProposal
    risk_management: RiskManagementSummary
    manager_decision: ManagerDecision
    workflow: list[WorkflowStage]
    run_summary: RunSummary
    data_health: DataHealth
    report_tabs: list[ReportTab]
    charts: ChartsPayload
    news: list[NewsArticle]
    social: list[SocialPost]
    transcripts: list[TranscriptResult]
