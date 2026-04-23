from __future__ import annotations

import pytest

from rocky.label_schema import validate_teacher_label


def test_validate_teacher_label_accepts_expected_payload() -> None:
    payload = {
        "confidence_band": "medium",
        "confidence_score": 0.55,
        "specificity_band": "high",
        "specificity_score": 0.81,
        "outlook_strength_band": "medium",
        "outlook_strength_score": 0.62,
        "directness_band": "medium",
        "directness_score": 0.58,
        "risk_intensity_band": "low",
        "risk_intensity_score": 0.28,
        "teacher_confidence": 0.74,
        "dataset_quality_band": "high",
        "dataset_quality_score": 0.85,
        "dataset_quality_reasons": ["clean_single_speaker", "substantive_content"],
        "evidence_snippets": ["We continue to expect strong demand."],
        "notes": "Concise management guidance block with concrete outlook language.",
    }
    validated = validate_teacher_label(payload)
    assert validated["dataset_quality_band"] == "high"


def test_validate_teacher_label_rejects_unknown_reason() -> None:
    payload = {
        "confidence_band": "medium",
        "confidence_score": 0.55,
        "specificity_band": "high",
        "specificity_score": 0.81,
        "outlook_strength_band": "medium",
        "outlook_strength_score": 0.62,
        "directness_band": "medium",
        "directness_score": 0.58,
        "risk_intensity_band": "low",
        "risk_intensity_score": 0.28,
        "teacher_confidence": 0.74,
        "dataset_quality_band": "high",
        "dataset_quality_score": 0.85,
        "dataset_quality_reasons": ["not_a_real_reason"],
        "evidence_snippets": ["Evidence snippet."],
        "notes": "Invalid reason should fail validation.",
    }
    with pytest.raises(Exception):
        validate_teacher_label(payload)
