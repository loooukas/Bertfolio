"""Student model inference runtime for transcript block communication metrics."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import threading
from typing import Any

from .schemas import TranscriptSectionBlock
from .settings import Settings

BAND_LABELS_FIVE = ("very_low", "low", "medium", "high", "very_high")
BAND_LABELS_THREE = ("low", "medium", "high")
_KNOWN_BANDS = set(BAND_LABELS_FIVE)

BAND_TO_SCORE_100 = {
    "very_low": 10.0,
    "low": 30.0,
    "medium": 50.0,
    "high": 70.0,
    "very_high": 90.0,
}

_DEFAULT_MODEL_DIR_BY_METRIC = {
    "confidence": "output/student_models/confidence_three_band_deberta_v3_base_strict070/model",
    "directness": "output/student_models/directness_three_band_deberta_v3_base_strict070/model",
    "outlook_strength": "output/student_models/outlook_strength_five_band_deberta_v3_base_strict070/model",
    "specificity": "output/student_models/specificity_deberta_v3_base_cpu/model",
    "risk_intensity": "output/student_models/risk_intensity_three_band_deberta_v3_base_strict070/model",
}

_SHORT_ADMIN_HINT_RE = re.compile(
    r"(?:next question|please go ahead|line is open|operator|moderator|opening remarks|closing remarks)",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class StudentMetricPrediction:
    band: str
    score: float
    probabilities: dict[str, float]
    predicted_confidence: float


@dataclass(frozen=True)
class StudentMetricConfig:
    metric: str
    model_dir: str
    enabled: bool
    expected_labels: tuple[str, ...] | None = None


@dataclass
class StudentMetricInferenceResult:
    by_index: dict[int, dict[str, StudentMetricPrediction]]
    metric_errors: dict[str, str]
    warnings: list[str]
    diagnostics: list[str]


@dataclass(frozen=True)
class _ModelBundle:
    tokenizer: Any
    model: Any
    labels: tuple[str, ...]
    device: Any
    model_dir: str


_MODEL_CACHE: dict[tuple[str, str], _ModelBundle] = {}
_MODEL_CACHE_LOCK = threading.Lock()


def score_from_band(band: str) -> float | None:
    return BAND_TO_SCORE_100.get(str(band or "").strip().lower())


def band_from_score(score: float, labels: tuple[str, ...]) -> str:
    label_scores = [(label, score_from_band(label)) for label in labels]
    candidates = [(label, value) for label, value in label_scores if value is not None]
    if not candidates:
        return labels[0] if labels else "medium"
    target = float(score)
    return min(candidates, key=lambda item: abs(item[1] - target))[0]


def student_block_guard_reason(text: str) -> str | None:
    compact = re.sub(r"\s+", " ", str(text or "")).strip()
    if not compact:
        return "missing_text"
    if len(compact) < 24:
        return "text_too_short"
    token_count = len(compact.split())
    if token_count < 6:
        return "too_few_tokens"
    if len(compact) < 180 and _SHORT_ADMIN_HINT_RE.search(compact):
        return "short_admin_or_operator_like"
    return None


def infer_student_metric_blocks(
    *,
    sections: list[TranscriptSectionBlock],
    settings: Settings | None,
) -> StudentMetricInferenceResult:
    result = StudentMetricInferenceResult(by_index={}, metric_errors={}, warnings=[], diagnostics=[])
    if settings is None or not sections:
        return result
    if settings.student_metrics_force_lexical_fallback:
        result.diagnostics.append("student_metrics_force_lexical_fallback=1; skipped student inference.")
        return result

    configs = _metric_configs(settings)
    active = [cfg for cfg in configs if cfg.enabled]
    if not active:
        return result

    usable_inputs: list[tuple[int, str]] = []
    for idx, section in enumerate(sections):
        if student_block_guard_reason(section.text) is None:
            usable_inputs.append((idx, _build_input_text(section)))

    if not usable_inputs:
        result.diagnostics.append("No block rows passed student input quality guardrail.")
        return result

    for cfg in active:
        model_dir = cfg.model_dir.strip()
        if not model_dir:
            result.metric_errors[cfg.metric] = "missing_model_dir"
            result.warnings.append(f"Student metric disabled for {cfg.metric}: model_dir is empty.")
            continue
        if not Path(model_dir).exists():
            result.metric_errors[cfg.metric] = "model_dir_missing"
            result.warnings.append(f"Student metric degraded for {cfg.metric}: model_dir not found ({model_dir}).")
            continue
        try:
            bundle = _get_model_bundle(model_dir=model_dir)
        except Exception as exc:
            result.metric_errors[cfg.metric] = "model_load_failed"
            result.warnings.append(f"Student metric degraded for {cfg.metric}: model load failed ({exc}).")
            continue

        try:
            predictions, label_note = _predict_for_metric(
                bundle=bundle,
                usable_inputs=usable_inputs,
                expected_labels=cfg.expected_labels,
                max_length=max(64, settings.student_metrics_max_length),
                batch_size=max(1, settings.student_metrics_batch_size),
            )
        except Exception as exc:
            result.metric_errors[cfg.metric] = "inference_failed"
            result.warnings.append(f"Student metric degraded for {cfg.metric}: inference failed ({exc}).")
            continue

        if label_note:
            result.diagnostics.append(f"{cfg.metric}: {label_note}")

        for row_idx, pred in predictions.items():
            bucket = result.by_index.setdefault(row_idx, {})
            bucket[cfg.metric] = pred

    return result


def _metric_configs(settings: Settings) -> list[StudentMetricConfig]:
    return [
        StudentMetricConfig(
            metric="confidence",
            enabled=settings.use_student_confidence,
            model_dir=settings.student_model_confidence_dir,
            expected_labels=BAND_LABELS_THREE,
        ),
        StudentMetricConfig(
            metric="directness",
            enabled=settings.use_student_directness,
            model_dir=settings.student_model_directness_dir,
            expected_labels=BAND_LABELS_THREE,
        ),
        StudentMetricConfig(
            metric="outlook_strength",
            enabled=settings.use_student_outlook_strength,
            model_dir=settings.student_model_outlook_strength_dir,
            expected_labels=BAND_LABELS_FIVE,
        ),
        StudentMetricConfig(
            metric="specificity",
            enabled=settings.use_student_specificity or settings.student_metrics_specificity_blend_enabled,
            model_dir=settings.student_model_specificity_dir,
            expected_labels=None,
        ),
        StudentMetricConfig(
            metric="risk_intensity",
            enabled=settings.use_student_risk_intensity,
            model_dir=settings.student_model_risk_intensity_dir,
            expected_labels=None,
        ),
    ]


def _build_input_text(section: TranscriptSectionBlock) -> str:
    role = re.sub(r"\s+", " ", str(section.speaker_role or "unknown")).strip().lower() or "unknown"
    section_type = re.sub(r"\s+", " ", str(section.section_type or "other")).strip().lower() or "other"
    text = re.sub(r"\s+", " ", str(section.text or "")).strip()
    return f"[ROLE={role}] [SECTION={section_type}] {text}".strip()


def _normalize_band(label: str) -> str:
    return re.sub(r"\s+", "_", str(label or "").strip().lower())


def _resolve_device():
    import torch

    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _get_model_bundle(*, model_dir: str) -> _ModelBundle:
    device = _resolve_device()
    cache_key = (str(Path(model_dir).resolve()), str(device))
    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached

    tokenizer = _load_tokenizer(model_dir)

    from transformers import AutoModelForSequenceClassification

    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.to(device)
    model.eval()

    labels = _extract_labels_from_config(model)
    bundle = _ModelBundle(
        tokenizer=tokenizer,
        model=model,
        labels=labels,
        device=device,
        model_dir=model_dir,
    )
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE[cache_key] = bundle
    return bundle


def _load_tokenizer(model_dir: str) -> Any:
    from transformers import AutoTokenizer

    try:
        return AutoTokenizer.from_pretrained(model_dir, use_fast=True, fix_mistral_regex=True)
    except TypeError:
        try:
            return AutoTokenizer.from_pretrained(model_dir, use_fast=True)
        except Exception:
            pass
    except Exception:
        pass

    try:
        return AutoTokenizer.from_pretrained(model_dir, use_fast=False, fix_mistral_regex=True)
    except TypeError:
        try:
            return AutoTokenizer.from_pretrained(model_dir, use_fast=False)
        except Exception:
            pass
    except Exception:
        pass

    if "deberta-v3" in model_dir.lower() or "deberta-v2" in model_dir.lower():
        try:
            import sentencepiece  # noqa: F401
            from transformers.models.deberta_v2.tokenization_deberta_v2 import DebertaV2Tokenizer

            return DebertaV2Tokenizer.from_pretrained(model_dir)
        except Exception as exc:
            raise RuntimeError(
                "Tokenizer load failed and DeBERTa fallback requires sentencepiece."
            ) from exc

    raise RuntimeError(f"Tokenizer load failed for {model_dir}")


def _extract_labels_from_config(model: Any) -> tuple[str, ...]:
    id2label = getattr(model.config, "id2label", None)
    if isinstance(id2label, dict) and id2label:
        parsed: list[tuple[int, str]] = []
        for key, value in id2label.items():
            try:
                idx = int(key)
            except Exception:
                continue
            parsed.append((idx, _normalize_band(str(value))))
        parsed.sort(key=lambda item: item[0])
        labels = tuple(value for _, value in parsed if value)
        if labels:
            return labels
    num_labels = int(getattr(model.config, "num_labels", 0))
    if num_labels <= 0:
        raise RuntimeError("Unable to infer model labels from config.")
    return tuple(f"class_{idx}" for idx in range(num_labels))


def _predict_for_metric(
    *,
    bundle: _ModelBundle,
    usable_inputs: list[tuple[int, str]],
    expected_labels: tuple[str, ...] | None,
    max_length: int,
    batch_size: int,
) -> tuple[dict[int, StudentMetricPrediction], str]:
    import torch

    remapped_labels, note = _coerce_labels(bundle.labels, expected_labels)
    text_by_index = {idx: text for idx, text in usable_inputs}
    ordered_indices = list(text_by_index.keys())
    ordered_texts = [text_by_index[idx] for idx in ordered_indices]

    predictions: dict[int, StudentMetricPrediction] = {}
    with torch.no_grad():
        for start in range(0, len(ordered_texts), batch_size):
            end = min(start + batch_size, len(ordered_texts))
            batch_texts = ordered_texts[start:end]
            batch_indices = ordered_indices[start:end]
            encoded = bundle.tokenizer(
                batch_texts,
                truncation=True,
                max_length=max_length,
                padding=True,
                return_tensors="pt",
            )
            encoded = {key: value.to(bundle.device) for key, value in encoded.items()}
            outputs = bundle.model(**encoded)
            probs = torch.softmax(outputs.logits.detach().cpu(), dim=1)
            pred_ids = torch.argmax(probs, dim=1)
            for local_idx, row_idx in enumerate(batch_indices):
                prob_values = probs[local_idx].tolist()
                pred_id = int(pred_ids[local_idx].item())
                band = remapped_labels[pred_id]
                score = score_from_band(band)
                if score is None:
                    continue
                predictions[row_idx] = StudentMetricPrediction(
                    band=band,
                    score=float(score),
                    probabilities={label: float(prob_values[idx]) for idx, label in enumerate(remapped_labels)},
                    predicted_confidence=float(max(prob_values)),
                )
    return predictions, note


def _coerce_labels(
    labels: tuple[str, ...],
    expected_labels: tuple[str, ...] | None,
) -> tuple[tuple[str, ...], str]:
    normalized = tuple(_normalize_band(label) for label in labels)
    if expected_labels is not None:
        expected = tuple(_normalize_band(label) for label in expected_labels)
        if normalized == expected:
            return expected, ""
        if len(normalized) == len(expected) and all(label not in _KNOWN_BANDS for label in normalized):
            return expected, f"unexpected_labels={list(normalized)} remapped_positionally={list(expected)}"
        raise RuntimeError(
            f"Model labels {list(normalized)} do not match expected labels {list(expected)}."
        )

    if all(label in _KNOWN_BANDS for label in normalized):
        return normalized, ""
    if len(normalized) == 3:
        return BAND_LABELS_THREE, f"unexpected_labels={list(normalized)} remapped_positionally={list(BAND_LABELS_THREE)}"
    if len(normalized) == 5:
        return BAND_LABELS_FIVE, f"unexpected_labels={list(normalized)} remapped_positionally={list(BAND_LABELS_FIVE)}"
    raise RuntimeError(f"Unsupported model label set: {list(normalized)}")


def default_model_dir_for_metric(metric: str) -> str:
    return _DEFAULT_MODEL_DIR_BY_METRIC.get(metric, "")
