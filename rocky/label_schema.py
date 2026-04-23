"""Structured schema for LM Studio teacher labels."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


MetricBand = Literal["very_low", "low", "medium", "high", "very_high"]
DatasetQualityReason = Literal[
    "clean_single_speaker",
    "substantive_content",
    "enough_context_in_block",
    "contains_concrete_evidence",
    "clear_forward_or_risk_language",
    "too_short",
    "procedural_or_admin",
    "operator_or_host_fluff",
    "malformed_or_truncated",
    "mixed_speakers_or_bad_segmentation",
    "too_context_dependent",
    "weak_signal_for_requested_metrics",
]


class TeacherLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confidence_band: MetricBand
    confidence_score: float = Field(ge=0, le=1)

    specificity_band: MetricBand
    specificity_score: float = Field(ge=0, le=1)

    outlook_strength_band: MetricBand
    outlook_strength_score: float = Field(ge=0, le=1)

    directness_band: MetricBand
    directness_score: float = Field(ge=0, le=1)

    risk_intensity_band: MetricBand
    risk_intensity_score: float = Field(ge=0, le=1)

    teacher_confidence: float = Field(ge=0, le=1)

    dataset_quality_band: MetricBand
    dataset_quality_score: float = Field(ge=0, le=1)
    dataset_quality_reasons: list[DatasetQualityReason] = Field(min_length=1, max_length=5)

    evidence_snippets: list[str] = Field(min_length=1, max_length=3)
    notes: str = Field(max_length=300)


TEACHER_LABEL_JSON_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "confidence_band",
        "confidence_score",
        "specificity_band",
        "specificity_score",
        "outlook_strength_band",
        "outlook_strength_score",
        "directness_band",
        "directness_score",
        "risk_intensity_band",
        "risk_intensity_score",
        "teacher_confidence",
        "dataset_quality_band",
        "dataset_quality_score",
        "dataset_quality_reasons",
        "evidence_snippets",
        "notes",
    ],
    "properties": {
        "confidence_band": {
            "type": "string",
            "enum": ["very_low", "low", "medium", "high", "very_high"],
        },
        "confidence_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "specificity_band": {
            "type": "string",
            "enum": ["very_low", "low", "medium", "high", "very_high"],
        },
        "specificity_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "outlook_strength_band": {
            "type": "string",
            "enum": ["very_low", "low", "medium", "high", "very_high"],
        },
        "outlook_strength_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "directness_band": {
            "type": "string",
            "enum": ["very_low", "low", "medium", "high", "very_high"],
        },
        "directness_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "risk_intensity_band": {
            "type": "string",
            "enum": ["very_low", "low", "medium", "high", "very_high"],
        },
        "risk_intensity_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "teacher_confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "dataset_quality_band": {
            "type": "string",
            "enum": ["very_low", "low", "medium", "high", "very_high"],
        },
        "dataset_quality_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "dataset_quality_reasons": {
            "type": "array",
            "minItems": 1,
            "maxItems": 5,
            "items": {
                "type": "string",
                "enum": [
                    "clean_single_speaker",
                    "substantive_content",
                    "enough_context_in_block",
                    "contains_concrete_evidence",
                    "clear_forward_or_risk_language",
                    "too_short",
                    "procedural_or_admin",
                    "operator_or_host_fluff",
                    "malformed_or_truncated",
                    "mixed_speakers_or_bad_segmentation",
                    "too_context_dependent",
                    "weak_signal_for_requested_metrics",
                ],
            },
        },
        "evidence_snippets": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 400,
            },
        },
        "notes": {
            "type": "string",
            "maxLength": 300,
        },
    },
}


def validate_teacher_label(payload: dict) -> dict:
    return TeacherLabel.model_validate(payload).model_dump()

