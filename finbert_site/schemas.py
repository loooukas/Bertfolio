"""Pydantic models for API responses."""

from __future__ import annotations

from typing import Literal, Optional

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
    url: str
    subreddit: Optional[str] = None
    created_utc: Optional[int] = None
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


class AnalysisResponse(BaseModel):
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
    news: list[NewsArticle]
    social: list[SocialPost]
    transcripts: list[TranscriptResult]
