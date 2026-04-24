from __future__ import annotations

from finbert_site.normalizer import build_speaker_analysis
from finbert_site.schemas import TranscriptSectionBlock
from finbert_site.settings import Settings
from finbert_site.student_metrics import StudentMetricInferenceResult, StudentMetricPrediction


def _section(text: str) -> TranscriptSectionBlock:
    return TranscriptSectionBlock(
        section_type="prepared_remarks",
        speaker="Management Speaker",
        speaker_role="management",
        text=text,
        order_index=0,
        evidence_snippets=[],
    )


def _score_text(text: str) -> dict[str, float]:
    return {
        "positive": 0.6,
        "negative": 0.2,
        "neutral": 0.2,
        "directional_score": 0.4,
        "label": "mixed",
    }


def test_student_primary_metrics_are_selected(monkeypatch) -> None:
    monkeypatch.setattr(
        "finbert_site.normalizer.infer_student_metric_blocks",
        lambda *, sections, settings: StudentMetricInferenceResult(
            by_index={
                0: {
                    "confidence": StudentMetricPrediction(
                        band="high",
                        score=70.0,
                        probabilities={"low": 0.05, "medium": 0.15, "high": 0.8},
                        predicted_confidence=0.8,
                    ),
                    "directness": StudentMetricPrediction(
                        band="medium",
                        score=50.0,
                        probabilities={"low": 0.1, "medium": 0.7, "high": 0.2},
                        predicted_confidence=0.7,
                    ),
                    "outlook_strength": StudentMetricPrediction(
                        band="very_high",
                        score=90.0,
                        probabilities={
                            "very_low": 0.01,
                            "low": 0.02,
                            "medium": 0.05,
                            "high": 0.12,
                            "very_high": 0.8,
                        },
                        predicted_confidence=0.8,
                    ),
                }
            },
            metric_errors={},
            warnings=[],
            diagnostics=[],
        ),
    )

    settings = Settings(
        use_student_confidence=True,
        use_student_directness=True,
        use_student_outlook_strength=True,
        use_student_specificity=False,
        use_student_risk_intensity=False,
        student_metrics_shadow_compare=True,
    )
    row = build_speaker_analysis([_section("We continue to expect strong demand and margin expansion.")], _score_text, settings=settings)[0]

    assert row.confidence == 70.0
    assert row.forward_looking_strength == 90.0
    assert row.evasiveness == 50.0

    diagnostics = row.segment_diagnostics or {}
    feature = diagnostics.get("feature_diagnostics") if isinstance(diagnostics, dict) else {}
    debug = feature.get("metric_source_debug") if isinstance(feature, dict) else {}
    assert debug["confidence"]["source"] == "student_primary"
    assert debug["directness"]["source"] == "student_primary"
    assert debug["outlook_strength"]["source"] == "student_primary"
    assert debug["specificity"]["source"] == "lexical_primary"
    assert debug["risk_intensity"]["source"] == "lexical_primary"


def test_force_lexical_fallback_overrides_student(monkeypatch) -> None:
    monkeypatch.setattr(
        "finbert_site.normalizer.infer_student_metric_blocks",
        lambda *, sections, settings: StudentMetricInferenceResult(
            by_index={
                0: {
                    "confidence": StudentMetricPrediction(
                        band="high",
                        score=70.0,
                        probabilities={"low": 0.05, "medium": 0.15, "high": 0.8},
                        predicted_confidence=0.8,
                    )
                }
            },
            metric_errors={},
            warnings=[],
            diagnostics=[],
        ),
    )

    settings = Settings(
        use_student_confidence=True,
        use_student_directness=False,
        use_student_outlook_strength=False,
        use_student_specificity=False,
        use_student_risk_intensity=False,
        student_metrics_force_lexical_fallback=True,
        student_metrics_shadow_compare=True,
    )

    row = build_speaker_analysis([_section("Strong execution with measured optimism.")], _score_text, settings=settings)[0]
    diagnostics = row.segment_diagnostics or {}
    feature = diagnostics.get("feature_diagnostics") if isinstance(diagnostics, dict) else {}
    debug = feature.get("metric_source_debug") if isinstance(feature, dict) else {}

    assert debug["confidence"]["source"] == "lexical_fallback"
    assert debug["confidence"]["fallback_reason"] == "forced_lexical_fallback"
    assert row.confidence != 70.0


def test_specificity_experimental_blend(monkeypatch) -> None:
    monkeypatch.setattr(
        "finbert_site.normalizer.infer_student_metric_blocks",
        lambda *, sections, settings: StudentMetricInferenceResult(
            by_index={
                0: {
                    "specificity": StudentMetricPrediction(
                        band="high",
                        score=70.0,
                        probabilities={"low": 0.1, "medium": 0.2, "high": 0.7},
                        predicted_confidence=0.7,
                    )
                }
            },
            metric_errors={},
            warnings=[],
            diagnostics=[],
        ),
    )

    settings = Settings(
        use_student_confidence=False,
        use_student_directness=False,
        use_student_outlook_strength=False,
        use_student_specificity=True,
        use_student_risk_intensity=False,
        student_metrics_specificity_blend_enabled=True,
        student_metrics_specificity_blend_weight=0.35,
        student_metrics_shadow_compare=True,
    )

    row = build_speaker_analysis([_section("Revenue increased 12% year over year with margin up 80 basis points.")], _score_text, settings=settings)[0]
    diagnostics = row.segment_diagnostics or {}
    feature = diagnostics.get("feature_diagnostics") if isinstance(diagnostics, dict) else {}
    debug = feature.get("metric_source_debug") if isinstance(feature, dict) else {}

    lexical_score = float(debug["specificity"]["lexical_score"])
    assert debug["specificity"]["source"] == "lexical_primary"
    assert debug["specificity"]["blend_mode"] == "specificity_experimental_lexical_student"
    assert min(lexical_score, 70.0) <= row.specificity <= max(lexical_score, 70.0)
