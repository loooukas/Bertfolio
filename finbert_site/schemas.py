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


class AnalysisResponse(BaseModel):
    ticker: str
    transcripts_found: int
    warnings: list[str]
    aggregate_scores: AggregateScores
    fundamentals: FundamentalsSummary
    transcripts: list[TranscriptResult]
