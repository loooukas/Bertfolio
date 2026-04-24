from __future__ import annotations

from pathlib import Path

from finbert_site.schemas import TranscriptSectionBlock
from finbert_site.settings import Settings
from finbert_site.student_metrics import (
    StudentMetricPrediction,
    _ModelBundle,
    infer_student_metric_blocks,
)


def _section(text: str) -> TranscriptSectionBlock:
    return TranscriptSectionBlock(
        section_type="prepared_remarks",
        speaker="Test Speaker",
        speaker_role="management",
        text=text,
        order_index=0,
        evidence_snippets=[],
    )


def test_infer_student_metric_blocks_handles_model_load_failure(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "confidence_model"
    model_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        use_student_confidence=True,
        use_student_directness=False,
        use_student_outlook_strength=False,
        use_student_specificity=False,
        use_student_risk_intensity=False,
        student_model_confidence_dir=str(model_dir),
    )

    def _fail_loader(*, model_dir: str):
        raise RuntimeError(f"cannot load {model_dir}")

    monkeypatch.setattr("finbert_site.student_metrics._get_model_bundle", _fail_loader)

    out = infer_student_metric_blocks(sections=[_section("Demand remained strong and margins improved.")], settings=settings)

    assert out.by_index == {}
    assert out.metric_errors.get("confidence") == "model_load_failed"
    assert any("model load failed" in warning.lower() for warning in out.warnings)


def test_infer_student_metric_blocks_returns_predictions(monkeypatch, tmp_path: Path) -> None:
    model_dir = tmp_path / "confidence_model"
    model_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        use_student_confidence=True,
        use_student_directness=False,
        use_student_outlook_strength=False,
        use_student_specificity=False,
        use_student_risk_intensity=False,
        student_model_confidence_dir=str(model_dir),
    )

    dummy_bundle = _ModelBundle(
        tokenizer=object(),
        model=object(),
        labels=("low", "medium", "high"),
        device="cpu",
        model_dir=str(model_dir),
    )

    monkeypatch.setattr("finbert_site.student_metrics._get_model_bundle", lambda *, model_dir: dummy_bundle)

    def _predict(
        *,
        bundle: _ModelBundle,
        usable_inputs,
        expected_labels,
        max_length: int,
        batch_size: int,
    ):
        assert expected_labels == ("low", "medium", "high")
        assert max_length > 0
        assert batch_size > 0
        assert usable_inputs
        idx = usable_inputs[0][0]
        return (
            {
                idx: StudentMetricPrediction(
                    band="high",
                    score=70.0,
                    probabilities={"low": 0.1, "medium": 0.2, "high": 0.7},
                    predicted_confidence=0.7,
                )
            },
            "",
        )

    monkeypatch.setattr("finbert_site.student_metrics._predict_for_metric", _predict)

    out = infer_student_metric_blocks(sections=[_section("We expect sustained growth in the back half.")], settings=settings)

    assert out.metric_errors == {}
    assert 0 in out.by_index
    assert out.by_index[0]["confidence"].band == "high"
    assert out.by_index[0]["confidence"].score == 70.0
