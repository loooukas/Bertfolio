"""Transcript normalization and speaker-block analysis."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import lru_cache
import json
import math
import re
from statistics import mean
import time
from typing import Any

import requests

from .prompt_loader import load_prompt_template
from .schemas import (
    TranscriptDocument,
    TranscriptParticipant,
    TranscriptSectionBlock,
    TranscriptSpeakerAnalysis,
)
from .settings import Settings
from .student_metrics import (
    BAND_LABELS_FIVE,
    BAND_LABELS_THREE,
    StudentMetricPrediction,
    band_from_score,
    infer_student_metric_blocks,
    student_block_guard_reason,
)

_LEXICON_MAX_HITS_PER_TERM = 3
_TOPIC_GENERAL_THRESHOLD = 0.03

_FORWARD_TERMS = {
    "guidance": 1.0,
    "outlook": 1.0,
    "expect": 0.8,
    "expects": 0.8,
    "expected": 0.8,
    "forecast": 1.0,
    "projection": 0.9,
    "project": 0.8,
    "target": 0.9,
    "targets": 0.9,
    "next quarter": 1.3,
    "next year": 1.2,
    "full year": 1.1,
    "fiscal year": 1.0,
    "pipeline": 0.9,
    "visibility": 0.8,
    "momentum": 0.8,
    "ramp": 0.9,
    "roadmap": 1.0,
    "launch": 0.8,
    "expansion": 0.8,
    "growth": 0.7,
    "long term": 1.0,
    "medium term": 0.9,
    "near term": 0.8,
    "we see": 0.7,
    "we anticipate": 1.0,
    "tailwind": 0.9,
    "upside": 0.8,
    "catalyst": 0.7,
    "back half": 0.8,
    "second half": 0.8,
}

_RISK_TERMS = {
    "risk": 0.8,
    "risks": 0.8,
    "headwind": 1.0,
    "headwinds": 1.0,
    "pressure": 0.9,
    "pressures": 0.9,
    "uncertain": 1.0,
    "uncertainty": 1.0,
    "volatile": 0.9,
    "volatility": 0.9,
    "challenging": 0.8,
    "softness": 1.0,
    "downturn": 1.0,
    "recession": 1.1,
    "slowdown": 1.0,
    "constraint": 0.8,
    "constraints": 0.8,
    "supply constraint": 1.0,
    "geopolitical": 1.0,
    "tariff": 1.0,
    "regulatory": 0.8,
    "litigation": 1.0,
    "lawsuit": 1.0,
    "cybersecurity": 0.8,
    "security incident": 1.0,
    "execution risk": 1.1,
    "foreign exchange": 0.9,
    "fx": 0.7,
    "inflation": 0.9,
    "deflation": 0.8,
    "pricing pressure": 1.1,
    "inventory correction": 1.2,
    "demand destruction": 1.3,
    "credit risk": 1.1,
    "default": 0.9,
    "defaults": 0.9,
    "churn": 1.0,
    "attrition": 0.8,
    "impairment": 1.0,
    "write-down": 1.0,
    "writeoff": 1.0,
    "deceleration": 1.0,
    "delay": 0.8,
    "delays": 0.8,
    "disruption": 1.0,
}

_HEDGE_TERMS = {
    "may": 0.8,
    "might": 0.9,
    "could": 0.8,
    "assuming": 1.0,
    "subject to": 1.1,
    "we believe": 0.9,
    "we think": 0.9,
    "we feel": 0.8,
    "it depends": 1.0,
    "not going to comment": 1.2,
    "cannot comment": 1.2,
    "can't comment": 1.2,
    "too early": 1.1,
    "early to say": 1.1,
    "hard to predict": 1.2,
    "limited visibility": 1.2,
    "no guarantee": 1.3,
    "unclear": 1.0,
    "approximately": 0.7,
    "roughly": 0.7,
    "around": 0.6,
    "about": 0.5,
    "potentially": 0.9,
    "probably": 0.8,
    "likely": 0.6,
    "to the extent": 1.0,
    "at this time": 0.8,
    "not yet": 0.8,
    "we'll see": 1.1,
    "remains to be seen": 1.3,
    "where appropriate": 1.0,
    "opportunistically": 0.9,
    "at a high level": 1.1,
    "directionally": 1.0,
}

_SPECIFICITY_TERMS = {
    "basis points": 1.2,
    "bps": 1.2,
    "percent": 0.6,
    "million": 0.9,
    "billion": 0.9,
    "trillion": 0.9,
    "guidance range": 1.1,
    "range": 0.6,
    "contract": 0.8,
    "contracts": 0.8,
    "customer": 0.8,
    "customers": 0.8,
    "units": 0.8,
    "utilization": 0.9,
    "gross margin": 1.0,
    "operating margin": 1.0,
    "free cash flow": 1.0,
    "opex": 0.8,
    "capex": 0.8,
    "eps": 0.8,
    "revenue": 0.8,
    "backlog": 0.9,
    "bookings": 0.9,
    "inventory days": 1.0,
    "headcount": 0.8,
    "market share": 1.0,
    "roi": 0.9,
}

_FORWARD_COUNTER_TERMS = {
    "headwind": 1.0,
    "headwinds": 1.0,
    "uncertain": 1.0,
    "uncertainty": 1.0,
    "pressure": 0.9,
    "pressures": 0.9,
    "slowdown": 1.0,
    "softness": 1.0,
    "volatility": 1.0,
    "challenging": 0.9,
    "timing dependent": 1.0,
    "not committed": 1.1,
}

_CONFIDENCE_TERMS = {
    "on track": 1.0,
    "executed": 1.0,
    "delivered": 1.0,
    "visibility": 0.9,
    "disciplined": 0.8,
    "consistent": 0.8,
    "repeatable": 0.9,
    "raising guidance": 1.2,
    "raise guidance": 1.2,
    "confident": 0.9,
    "committed": 0.9,
}

_CONFIDENCE_COUNTER_TERMS = {
    "unclear": 1.0,
    "uncertain": 1.1,
    "too early": 1.2,
    "cannot comment": 1.3,
    "can't comment": 1.3,
    "not prepared": 1.1,
    "limited visibility": 1.2,
    "remains to be seen": 1.3,
    "we'll see": 1.2,
}

_SPECIFICITY_COUNTER_TERMS = {
    "various": 0.8,
    "several": 0.8,
    "many": 0.7,
    "some": 0.6,
    "kind of": 1.0,
    "sort of": 1.0,
    "at a high level": 1.2,
    "directionally": 1.0,
    "broadly": 0.9,
    "roughly": 0.9,
    "approximately": 0.8,
}

_DIRECTNESS_TERMS = {
    "specifically": 1.0,
    "to be clear": 1.1,
    "exactly": 1.0,
    "we will": 0.9,
    "we did": 0.8,
    "we have": 0.8,
    "the number is": 1.2,
    "guidance is": 1.0,
    "we can commit": 1.2,
}

_TOPIC_KEYWORDS = {
    "demand": {
        "demand": 1.2,
        "orders": 1.2,
        "bookings": 1.1,
        "backlog": 1.2,
        "sell-through": 1.0,
        "sell through": 1.0,
        "consumption": 0.8,
    },
    "margins": {
        "margin": 1.1,
        "gross margin": 1.3,
        "operating margin": 1.3,
        "profitability": 1.0,
        "mix": 0.6,
        "incremental margin": 1.0,
    },
    "guidance": {
        "guidance": 1.3,
        "outlook": 1.2,
        "expect": 0.9,
        "forecast": 1.1,
        "next quarter": 1.1,
        "full year": 1.1,
    },
    "capex": {
        "capex": 1.3,
        "investment": 0.9,
        "infrastructure": 1.0,
        "capacity": 1.0,
        "datacenter": 1.1,
        "data center": 1.1,
    },
    "costs": {
        "cost": 1.0,
        "costs": 1.0,
        "expense": 1.0,
        "expenses": 1.0,
        "opex": 1.1,
        "efficiency": 0.9,
        "productivity": 0.8,
        "restructuring": 0.9,
    },
    "pricing": {
        "pricing": 1.2,
        "price": 0.9,
        "discount": 0.9,
        "asp": 1.0,
        "average selling price": 1.0,
        "promotion": 0.7,
    },
    "competition": {
        "competition": 1.2,
        "competitive": 1.0,
        "share": 0.8,
        "market share": 1.1,
        "rival": 1.0,
        "peer": 0.8,
    },
    "regulation": {
        "regulation": 1.2,
        "regulatory": 1.1,
        "compliance": 1.0,
        "antitrust": 1.2,
        "policy": 0.8,
        "tariff": 0.9,
        "export control": 1.2,
    },
    "ai": {
        "ai": 0.9,
        "artificial intelligence": 1.2,
        "machine learning": 1.0,
        "genai": 1.0,
        "inference": 1.0,
        "training": 1.0,
        "model": 0.7,
        "gpu": 0.8,
        "accelerator": 0.8,
    },
    "macro": {
        "macro": 1.0,
        "consumer": 0.7,
        "enterprise demand": 0.9,
        "recession": 1.0,
        "inflation": 1.0,
        "fx": 0.8,
        "foreign exchange": 1.0,
        "interest rate": 1.0,
    },
    "supply_chain": {
        "supply": 0.8,
        "supply chain": 1.2,
        "inventory": 1.0,
        "lead time": 1.0,
        "constraint": 0.9,
        "manufacturing": 0.8,
    },
    "cashflow": {
        "cash flow": 1.2,
        "free cash flow": 1.2,
        "working capital": 1.1,
        "balance sheet": 1.0,
        "debt": 0.9,
        "liquidity": 0.9,
        "buyback": 0.9,
    },
}

_TOPIC_LABELS = tuple(_TOPIC_KEYWORDS.keys()) + ("general",)


@dataclass(frozen=True)
class BlockAiFeatures:
    forward_density: float
    risk_density: float
    hedge_density: float
    specificity_density: float
    topic_label: str
    confidence: float


@dataclass
class NormalizationResult:
    document: TranscriptDocument
    warnings: list[str]


@dataclass
class _NameSignature:
    raw: str
    key: str
    tokens: list[str]
    first: str
    last: str


@dataclass
class _CanonicalSpeakerRecord:
    canonical_name: str
    signature: _NameSignature
    aliases: set[str]
    source_priority: int


@dataclass
class _DeterministicBlock:
    speaker_raw: str
    speaker: str
    text: str
    order_index: int
    base_state: str
    question_like: bool = False
    routing_like: bool = False
    closing_like: bool = False
    section_type: str = "other"
    speaker_role: str | None = None


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _clamp_unit(value: float) -> float:
    return _clamp(value, 0.0, 1.0)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


@lru_cache(maxsize=512)
def _compile_phrase_regex(term: str) -> re.Pattern[str]:
    escaped = re.escape(term.lower())
    if re.search(r"\s|[/\-]", term):
        pattern = rf"(?<!\w){escaped}(?!\w)"
    else:
        pattern = rf"\b{escaped}\b"
    return re.compile(pattern, flags=re.IGNORECASE)


def _weighted_term_density(text: str, terms: dict[str, float]) -> tuple[float, list[str]]:
    lowered = text.lower().strip()
    if not lowered or not terms:
        return 0.0, []

    max_hits = _LEXICON_MAX_HITS_PER_TERM
    matched_weight = 0.0
    total_weight = 0.0
    matched_terms: list[str] = []
    for term, weight in terms.items():
        safe_weight = max(0.0, float(weight))
        if safe_weight <= 0:
            continue
        total_weight += safe_weight * max_hits
        hits = len(_compile_phrase_regex(term).findall(lowered))
        if hits <= 0:
            continue
        matched_weight += safe_weight * min(hits, max_hits)
        matched_terms.append(term)

    if total_weight <= 0:
        return 0.0, []
    return _clamp_unit(matched_weight / total_weight), matched_terms


def _net_density(positive_density: float, counter_density: float, counter_weight: float) -> float:
    return _clamp_unit(positive_density - max(0.0, counter_weight) * counter_density)


def _smoothed_percent(net_density: float, smoothing: float) -> float:
    # Convert unit density into a stable 0-100 signal with bounded curvature.
    curve = 1.9 + max(0.0, min(1.0, smoothing)) * 2.6
    mapped = 0.5 + 0.5 * math.tanh(_clamp(net_density, -1.0, 1.0) * curve)
    return _clamp(mapped * 100.0, 0.0, 100.0)


def _topic_label(text: str) -> tuple[str, float]:
    best_topic = "general"
    best_score = 0.0
    for topic, lexicon in _TOPIC_KEYWORDS.items():
        density, _ = _weighted_term_density(text, lexicon)
        if density > best_score:
            best_score = density
            best_topic = topic
    if best_score < _TOPIC_GENERAL_THRESHOLD:
        return "general", best_score
    return best_topic, best_score


def _truncate_block_text(text: str, max_chars: int = 700) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    if len(compact) <= max_chars:
        return compact
    head_chars = int(max_chars * 0.75)
    tail_chars = max_chars - head_chars - 5
    return f"{compact[:head_chars]} ... {compact[-tail_chars:]}"


def _classify_block_features_with_openai(
    *,
    sections: list[TranscriptSectionBlock],
    settings: Settings | None,
) -> tuple[dict[int, BlockAiFeatures], list[str], list[str]]:
    if settings is None:
        return {}, [], []
    if not settings.transcript_feature_ai_enabled:
        return {}, [], []
    if not settings.openai_api_key:
        return {}, [], []
    if not sections:
        return {}, [], []

    try:
        system_prompt = load_prompt_template("transcript_feature_classifier_v1.md")
    except Exception as exc:
        return {}, [f"OpenAI feature classification degraded: prompt load failed ({exc})."], []

    max_blocks = max(1, settings.transcript_feature_ai_max_blocks)
    configured_batch = max(1, min(32, settings.transcript_feature_ai_batch_size))
    min_batch_size = max(1, min(configured_batch, settings.transcript_feature_ai_min_batch_size))
    timeout_seconds = max(5, settings.transcript_feature_ai_timeout_seconds)
    target_sections = sections[:max_blocks]
    model_resolution_warning: str | None = None

    try:
        model_name, model_resolution_warning = _resolve_structured_chat_model(
            settings.transcript_feature_ai_model,
            purpose="OpenAI feature classifier",
        )
    except Exception as exc:
        return {}, [f"OpenAI feature classification degraded: {exc}"], []

    response_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "blocks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "index": {"type": "integer"},
                        "forward_density": {"type": "number"},
                        "risk_density": {"type": "number"},
                        "hedge_density": {"type": "number"},
                        "specificity_density": {"type": "number"},
                        "topic_label": {"type": "string", "enum": list(_TOPIC_LABELS)},
                        "confidence": {"type": "number"},
                    },
                    "required": [
                        "index",
                        "forward_density",
                        "risk_density",
                        "hedge_density",
                        "specificity_density",
                        "topic_label",
                        "confidence",
                    ],
                },
            }
        },
        "required": ["blocks"],
    }

    results: dict[int, BlockAiFeatures] = {}
    warnings: list[str] = []
    diagnostics: list[str] = []
    failed_batches = 0
    failed_blocks = 0
    if model_resolution_warning:
        diagnostics.append(model_resolution_warning)

    cursor = 0
    batch_number = 0
    while cursor < len(target_sections):
        batch_number += 1
        remaining = len(target_sections) - cursor
        attempt_batch_size = min(configured_batch, remaining)
        parsed: dict[str, Any] | None = None
        final_error = ""

        while attempt_batch_size >= min_batch_size:
            batch = target_sections[cursor : cursor + attempt_batch_size]
            payload = {
                "topics": list(_TOPIC_LABELS),
                "blocks": [
                    {
                        "index": cursor + offset,
                        "speaker": section.speaker,
                        "section_type": section.section_type,
                        "text": _truncate_block_text(section.text),
                    }
                    for offset, section in enumerate(batch)
                ],
            }
            parsed, error = _post_structured_chat_completion(
                api_key=settings.openai_api_key,
                model_name=model_name,
                system_prompt=system_prompt,
                user_payload=payload,
                response_schema_name="transcript_block_features_v1",
                response_schema=response_schema,
                timeout_seconds=timeout_seconds,
                retries=settings.openai_request_retries,
                backoff_seconds=settings.openai_retry_backoff_seconds,
            )
            if parsed is not None:
                break

            final_error = str(error or "unknown_error")
            if attempt_batch_size > min_batch_size:
                next_batch_size = max(min_batch_size, attempt_batch_size // 2)
                diagnostics.append(
                    f"batch={batch_number} reduced_size={attempt_batch_size}->{next_batch_size} error={final_error}"
                )
                attempt_batch_size = next_batch_size
                continue
            break

        if parsed is None:
            failed_batches += 1
            failed_blocks += attempt_batch_size
            diagnostics.append(
                f"batch={batch_number} failed_size={attempt_batch_size} error={final_error or 'unknown_error'}"
            )
            cursor += attempt_batch_size
            continue

        items = parsed.get("blocks")
        if not isinstance(items, list):
            failed_batches += 1
            failed_blocks += attempt_batch_size
            diagnostics.append(f"batch={batch_number} invalid_schema=missing_blocks_array")
            cursor += attempt_batch_size
            continue

        for item in items:
            if not isinstance(item, dict):
                continue
            idx = int(_safe_float(item.get("index"), -1))
            if idx < 0 or idx >= len(sections):
                continue
            topic_label = str(item.get("topic_label") or "general").strip().lower()
            if topic_label not in _TOPIC_LABELS:
                topic_label = "general"
            results[idx] = BlockAiFeatures(
                forward_density=_clamp_unit(_safe_float(item.get("forward_density"), 0.0)),
                risk_density=_clamp_unit(_safe_float(item.get("risk_density"), 0.0)),
                hedge_density=_clamp_unit(_safe_float(item.get("hedge_density"), 0.0)),
                specificity_density=_clamp_unit(_safe_float(item.get("specificity_density"), 0.0)),
                topic_label=topic_label,
                confidence=_clamp_unit(_safe_float(item.get("confidence"), 0.5)),
            )
        cursor += attempt_batch_size

    if failed_batches > 0:
        total_blocks = max(1, len(target_sections))
        fallback_ratio = failed_blocks / total_blocks
        degradation_message = (
            "OpenAI feature classification degraded: "
            f"{failed_batches} batches failed after retries; lexical fallback used for {failed_blocks} blocks."
        )
        if fallback_ratio <= 0.08 and failed_blocks <= 3:
            diagnostics.append(f"minor_fallback: {degradation_message}")
        else:
            warnings.append(degradation_message)

    return results, warnings, diagnostics


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[.!?])\s+", compact)
    return [p.strip() for p in parts if p.strip()]


def _should_skip_metric_scoring_for_fluff_block(block: TranscriptSectionBlock) -> bool:
    compact = re.sub(r"\s+", " ", str(block.text or "")).strip()
    if not compact:
        return True
    word_count = len(re.findall(r"\b\w+\b", compact))
    if word_count < 7 and "operator" in compact.lower():
        return True
    return False


_ROLE_OPERATOR = "operator"
_ROLE_ANALYST = "analyst"
_ROLE_MANAGEMENT = "management"
_ROLE_HOST_IR = "host_ir"
_ROLE_UNKNOWN = "unknown"
_SECTION_PREPARED = "prepared_remarks"
_SECTION_QA = "qa"
_SECTION_OTHER = "other"

_OPERATOR_NAME_TOKENS = ("operator", "moderator")
_HOST_IR_TITLE_TOKENS = (
    "investor relations",
    "investor relation",
    "ir",
    "head of ir",
    "vp, ir",
    "vp ir",
)
_MANAGEMENT_TITLE_TOKENS = (
    "chief",
    "ceo",
    "cfo",
    "coo",
    "cao",
    "cto",
    "chairman",
    "chairwoman",
    "president",
    "executive",
    "founder",
    "vice president",
    "svp",
    "evp",
    "treasurer",
    "director",
)
_ANALYST_TITLE_TOKENS = ("analyst", "research", "equity research")

_QA_TRANSITION_MARKERS = (
    "first question",
    "next question",
    "our next question",
    "final question",
    "line is open",
    "please go ahead",
    "we will now take questions",
    "we are now ready for questions",
    "open the line",
    "open it up for questions",
    "poll for questions",
    "unmute yourself",
)
_QA_CLOSING_MARKERS = (
    "all the time we have for q&a",
    "all the time we have for questions",
    "this concludes the question-and-answer session",
    "this concludes today",
    "before we conclude",
    "closing remarks",
    "thank you for joining",
    "that concludes today's conference call",
)
_ANALYST_QUESTION_HINTS = (
    "thanks for taking my question",
    "my question is",
    "quick follow-up",
    "quick follow up",
    "can you",
    "could you",
    "how should we think about",
    "what is",
    "what are",
    "do you expect",
    "would you",
    "why",
    "when",
)
_HEADING_QA_PATTERN = re.compile(r"^\s*(q\s*&\s*a|question(?:s)?\s*(?:and|&)\s*answer(?:s)?)\s*$", flags=re.IGNORECASE)
_HEADING_PREPARED_PATTERN = re.compile(r"^\s*prepared remarks\s*$", flags=re.IGNORECASE)
_HEADING_CLOSING_PATTERN = re.compile(r"^\s*closing remarks?\s*$", flags=re.IGNORECASE)
_SPEAKER_LINE_PATTERN = re.compile(r"^([A-Za-z][A-Za-z .,'&()\-/]{1,80}):\s*(.+)$")

_NAME_PREFIX_TOKENS = {"mr", "mrs", "ms", "dr", "sir", "prof"}
_NAME_SUFFIX_TOKENS = {"jr", "sr", "ii", "iii", "iv", "v", "phd", "cfa", "mba", "md"}
_NON_PERSON_LABEL_KEYS = {
    "operator",
    "moderator",
    "host",
    "unknown",
    "unidentified speaker",
}
_GENERIC_BOILERPLATE_MARKERS = (
    "forward-looking statements",
    "safe harbor",
    "copyright",
    "transcript by",
)


def _normalize_name_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").strip().lower()).strip()


def _speaker_line_match(line: str) -> tuple[str, str] | None:
    match = _SPEAKER_LINE_PATTERN.match(line.strip())
    if not match:
        return None
    speaker = re.sub(r"\s+", " ", match.group(1)).strip()
    spoken = match.group(2).strip()
    if len(spoken) < 2:
        return None
    return speaker, spoken


def _looks_like_heading(line: str, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.match(line.strip()))


def _normalize_person_tokens(value: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9\s]", " ", (value or "").lower())
    tokens = [token for token in normalized.split() if token]
    if not tokens:
        return []

    while tokens and tokens[0] in _NAME_PREFIX_TOKENS:
        tokens = tokens[1:]
    while tokens and tokens[-1] in _NAME_SUFFIX_TOKENS:
        tokens = tokens[:-1]
    return tokens


def _name_signature(value: str) -> _NameSignature | None:
    raw = re.sub(r"\s+", " ", (value or "").strip())
    if not raw:
        return None
    key = _normalize_name_key(raw)
    if not key:
        return None
    tokens = _normalize_person_tokens(raw)
    if not tokens:
        return None
    first = tokens[0]
    last = tokens[-1]
    return _NameSignature(raw=raw, key=key, tokens=tokens, first=first, last=last)


def _is_non_person_speaker_label(name: str) -> bool:
    key = _normalize_name_key(name)
    if not key:
        return True
    if key in _NON_PERSON_LABEL_KEYS:
        return True
    return any(token in key for token in _OPERATOR_NAME_TOKENS)


def _signature_alias_keys(signature: _NameSignature) -> set[str]:
    keys = {signature.key}
    if signature.first and signature.last:
        keys.add(f"{signature.first} {signature.last}")
    return {key for key in keys if key}


def _name_quality_score(name: str, source_priority: int) -> tuple[int, int, int]:
    signature = _name_signature(name)
    token_count = len(signature.tokens) if signature else 0
    return (source_priority, token_count, len(name))


def _merge_confidence(signature: _NameSignature, other: _NameSignature) -> float:
    if signature.last != other.last:
        return 0.0
    first_ratio = SequenceMatcher(None, signature.first, other.first).ratio()
    if first_ratio < 0.88:
        return 0.0
    full_ratio = SequenceMatcher(None, signature.key, other.key).ratio()
    if signature.first == other.first and signature.last == other.last:
        return max(0.95, full_ratio)
    return (0.6 * first_ratio) + (0.4 * full_ratio)


def _best_record_match(
    signature: _NameSignature,
    records: list[_CanonicalSpeakerRecord],
) -> tuple[int | None, float]:
    best_idx: int | None = None
    best_score = 0.0
    for idx, record in enumerate(records):
        score = _merge_confidence(signature, record.signature)
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx, best_score


def _apply_alias_map_entry(
    alias_key_to_index: dict[str, int],
    ambiguous_aliases: set[str],
    alias_key: str,
    index: int,
) -> None:
    existing = alias_key_to_index.get(alias_key)
    if existing is None:
        if alias_key not in ambiguous_aliases:
            alias_key_to_index[alias_key] = index
        return
    if existing == index:
        return
    ambiguous_aliases.add(alias_key)
    alias_key_to_index.pop(alias_key, None)


def _canonicalize_speaker_names(
    *,
    participants: list[dict[str, str]],
    management_roster: list[dict[str, str]] | None,
    observed_speakers: list[str],
) -> dict[str, str]:
    records: list[_CanonicalSpeakerRecord] = []
    alias_key_to_index: dict[str, int] = {}
    ambiguous_aliases: set[str] = set()

    def upsert_name(name: str, *, source_priority: int) -> None:
        signature = _name_signature(name)
        if signature is None:
            return
        if _is_non_person_speaker_label(signature.raw):
            return

        direct_idx = alias_key_to_index.get(signature.key)
        if direct_idx is not None:
            record = records[direct_idx]
            record.aliases.add(signature.key)
            if _name_quality_score(signature.raw, source_priority) > _name_quality_score(
                record.canonical_name, record.source_priority
            ):
                record.canonical_name = signature.raw
                record.signature = signature
                record.source_priority = source_priority
            return

        best_idx, best_score = _best_record_match(signature, records)
        if best_idx is not None and best_score >= 0.92:
            record = records[best_idx]
            record.aliases.add(signature.key)
            if _name_quality_score(signature.raw, source_priority) > _name_quality_score(
                record.canonical_name, record.source_priority
            ):
                record.canonical_name = signature.raw
                record.signature = signature
                record.source_priority = source_priority
            target_idx = best_idx
        else:
            target_idx = len(records)
            records.append(
                _CanonicalSpeakerRecord(
                    canonical_name=signature.raw,
                    signature=signature,
                    aliases={signature.key},
                    source_priority=source_priority,
                )
            )

        record = records[target_idx]
        for alias in _signature_alias_keys(signature):
            _apply_alias_map_entry(alias_key_to_index, ambiguous_aliases, alias, target_idx)
            record.aliases.add(alias)

    for participant in participants:
        name = str(participant.get("name") or "").strip()
        if name:
            upsert_name(name, source_priority=3)

    for officer in management_roster or []:
        name = str(officer.get("name") or "").strip()
        if name:
            upsert_name(name, source_priority=2)

    for speaker in observed_speakers:
        if speaker:
            upsert_name(speaker, source_priority=1)

    out: dict[str, str] = {}
    for record in records:
        for alias in record.aliases:
            if alias and alias not in ambiguous_aliases:
                out[alias] = record.canonical_name
    return out


def _role_from_participant_title(value: str | None) -> str | None:
    lowered = (value or "").strip().lower()
    if not lowered:
        return None
    if any(token in lowered for token in _OPERATOR_NAME_TOKENS):
        return _ROLE_OPERATOR
    if any(token in lowered for token in _HOST_IR_TITLE_TOKENS):
        return _ROLE_HOST_IR
    if any(token in lowered for token in _ANALYST_TITLE_TOKENS):
        return _ROLE_ANALYST
    if any(token in lowered for token in _MANAGEMENT_TITLE_TOKENS):
        return _ROLE_MANAGEMENT
    return None


def _role_hint_from_speaker_name(speaker: str) -> str | None:
    lowered = (speaker or "").strip().lower()
    if not lowered:
        return None
    if any(token in lowered for token in _OPERATOR_NAME_TOKENS):
        return _ROLE_OPERATOR
    if "investor relations" in lowered:
        return _ROLE_HOST_IR
    if "analyst" in lowered:
        return _ROLE_ANALYST
    if any(token in lowered for token in ("ceo", "cfo", "chief", "president")):
        return _ROLE_MANAGEMENT
    return None


def _looks_like_operator_or_host_routing(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _QA_TRANSITION_MARKERS)


def _looks_like_qa_closing(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _QA_CLOSING_MARKERS)


def _looks_like_question_text(text: str) -> bool:
    lowered = text.lower()
    if "?" in text:
        return True
    return any(marker in lowered for marker in _ANALYST_QUESTION_HINTS)


def _looks_like_long_remark_with_trailing_transition(text: str) -> bool:
    lowered = text.lower()
    positions = [lowered.rfind(marker) for marker in _QA_TRANSITION_MARKERS if marker in lowered]
    if not positions:
        return False
    trailing_pos = max(positions)
    appears_trailing = trailing_pos >= int(len(lowered) * 0.6)
    word_count = len(re.findall(r"\b\w+\b", text))
    sentence_count = len(re.findall(r"[.!?]", text))
    return appears_trailing and word_count >= 80 and sentence_count >= 4


def _is_management_roster_title(title: str | None) -> bool:
    lowered = (title or "").strip().lower()
    if not lowered:
        return False
    if any(token in lowered for token in _OPERATOR_NAME_TOKENS):
        return False
    if any(token in lowered for token in _ANALYST_TITLE_TOKENS):
        return False
    if any(token in lowered for token in _HOST_IR_TITLE_TOKENS):
        return False
    return any(token in lowered for token in _MANAGEMENT_TITLE_TOKENS)


def _is_boilerplate_block(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _GENERIC_BOILERPLATE_MARKERS)


def _infer_qa_start_index(
    blocks: list[_DeterministicBlock],
    speaker_role_hints: dict[str, str],
    management_name_keys: set[str],
) -> int | None:
    for idx, block in enumerate(blocks):
        if block.base_state == _SECTION_QA:
            return idx
        if block.routing_like:
            if _looks_like_long_remark_with_trailing_transition(block.text):
                continue
            return idx

    for idx, block in enumerate(blocks):
        speaker_key = _normalize_name_key(block.speaker)
        hinted = speaker_role_hints.get(speaker_key)
        if block.question_like and hinted not in {_ROLE_MANAGEMENT, _ROLE_OPERATOR, _ROLE_HOST_IR}:
            if speaker_key not in management_name_keys:
                return idx
    return None


def _infer_qa_end_index(blocks: list[_DeterministicBlock], qa_start: int | None) -> int | None:
    if qa_start is None:
        return None
    for idx in range(qa_start, len(blocks)):
        if _looks_like_qa_closing(blocks[idx].text):
            return idx
    return None


def _resolve_speaker_roles(
    blocks: list[_DeterministicBlock],
    speaker_role_hints: dict[str, str],
    management_name_keys: set[str],
    qa_start: int | None,
) -> dict[str, str]:
    speaker_stats: dict[str, dict[str, int]] = defaultdict(
        lambda: {
            "prepared_blocks": 0,
            "qa_blocks": 0,
            "question_blocks": 0,
            "routing_blocks": 0,
            "answer_blocks": 0,
        }
    )
    for block in blocks:
        stats = speaker_stats[block.speaker]
        if block.section_type == _SECTION_PREPARED:
            stats["prepared_blocks"] += 1
        if block.section_type == _SECTION_QA:
            stats["qa_blocks"] += 1
        if block.question_like:
            stats["question_blocks"] += 1
        if block.routing_like:
            stats["routing_blocks"] += 1

    for idx, block in enumerate(blocks):
        if idx == 0 or block.section_type != _SECTION_QA or block.question_like:
            continue
        previous = blocks[idx - 1]
        if previous.section_type == _SECTION_QA and previous.question_like and previous.speaker != block.speaker:
            speaker_stats[block.speaker]["answer_blocks"] += 1

    resolved: dict[str, str] = {}
    for speaker, stats in speaker_stats.items():
        speaker_key = _normalize_name_key(speaker)
        name_hint = _role_hint_from_speaker_name(speaker)
        explicit_hint = speaker_role_hints.get(speaker_key) or name_hint
        if explicit_hint == _ROLE_OPERATOR:
            resolved[speaker] = _ROLE_OPERATOR
            continue

        scores: dict[str, float] = defaultdict(float)
        if explicit_hint == _ROLE_HOST_IR:
            scores[_ROLE_HOST_IR] += 5.0
        elif explicit_hint == _ROLE_MANAGEMENT:
            scores[_ROLE_MANAGEMENT] += 5.0
        elif explicit_hint == _ROLE_ANALYST:
            scores[_ROLE_ANALYST] += 5.0

        if speaker_key in management_name_keys:
            scores[_ROLE_MANAGEMENT] += 4.0
        if stats["routing_blocks"] > 0:
            if explicit_hint == _ROLE_MANAGEMENT and stats["answer_blocks"] > 0:
                scores[_ROLE_MANAGEMENT] += 1.0
            else:
                scores[_ROLE_HOST_IR] += 3.5
        if stats["question_blocks"] > 0:
            scores[_ROLE_ANALYST] += 2.5
        if stats["answer_blocks"] > 0:
            scores[_ROLE_MANAGEMENT] += 2.5
        if stats["prepared_blocks"] > 0 and stats["question_blocks"] == 0:
            scores[_ROLE_MANAGEMENT] += 1.5
        if qa_start is not None and stats["qa_blocks"] > 0 and stats["question_blocks"] == stats["qa_blocks"]:
            scores[_ROLE_ANALYST] += 1.0

        if not scores:
            resolved[speaker] = _ROLE_UNKNOWN
            continue

        role_order = {
            _ROLE_OPERATOR: 5,
            _ROLE_HOST_IR: 4,
            _ROLE_MANAGEMENT: 3,
            _ROLE_ANALYST: 2,
            _ROLE_UNKNOWN: 1,
        }
        ranked = sorted(scores.items(), key=lambda item: (item[1], role_order.get(item[0], 0)), reverse=True)
        best_role, best_score = ranked[0]
        if best_score < 2.0:
            resolved[speaker] = _ROLE_UNKNOWN
            continue
        resolved[speaker] = best_role
    return resolved


def _canonicalize_participants_for_output(
    participants: list[dict[str, str]],
    alias_to_canonical: dict[str, str],
    blocks: list[_DeterministicBlock],
) -> list[TranscriptParticipant]:
    visible_speakers = {block.speaker for block in blocks}
    merged: dict[str, str] = {}
    for participant in participants:
        name = str(participant.get("name") or "").strip()
        if not name:
            continue
        canonical = alias_to_canonical.get(_normalize_name_key(name), name)
        role = str(participant.get("role") or "").strip()
        if canonical in merged:
            if len(role) > len(merged[canonical]):
                merged[canonical] = role
        else:
            merged[canonical] = role

    out: list[TranscriptParticipant] = []
    for canonical_name, role in sorted(merged.items(), key=lambda item: item[0]):
        if canonical_name not in visible_speakers and len(out) >= 20:
            continue
        out.append(TranscriptParticipant(name=canonical_name, role=role or None))
    return out[:40]


def deterministic_document_from_text(
    *,
    ticker: str,
    company_name: str | None,
    source: str,
    source_url: str | None,
    title: str | None,
    published_date: str | None,
    content: str,
    extraction_confidence: float,
    parsing_warnings: list[str],
    participants: list[dict[str, str]],
    management_roster: list[dict[str, str]] | None = None,
) -> TranscriptDocument:
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    parsed_blocks: list[_DeterministicBlock] = []
    current_speaker: str | None = None
    current_buffer: list[str] = []
    current_state = "intro"
    current_block_state = _SECTION_PREPARED
    order_idx = 0

    def flush_current() -> None:
        nonlocal order_idx, current_speaker, current_buffer, current_block_state
        if not current_speaker or not current_buffer:
            return
        text = " ".join(current_buffer).strip()
        if not text:
            return
        parsed_blocks.append(
            _DeterministicBlock(
                speaker_raw=current_speaker,
                speaker=current_speaker,
                text=text,
                order_index=order_idx,
                base_state=current_block_state,
                question_like=_looks_like_question_text(text),
                routing_like=_looks_like_operator_or_host_routing(text),
                closing_like=_looks_like_qa_closing(text),
            )
        )
        order_idx += 1
        current_speaker = None
        current_buffer = []

    for line in lines:
        if _looks_like_heading(line, _HEADING_PREPARED_PATTERN):
            current_state = _SECTION_PREPARED
            continue
        if _looks_like_heading(line, _HEADING_QA_PATTERN):
            current_state = _SECTION_QA
            continue
        if _looks_like_heading(line, _HEADING_CLOSING_PATTERN):
            current_state = "closing"
            continue

        match = _speaker_line_match(line)
        if match:
            flush_current()
            current_speaker = match[0]
            if current_state == _SECTION_QA:
                current_block_state = _SECTION_QA
            elif current_state in {"intro", _SECTION_PREPARED}:
                current_block_state = _SECTION_PREPARED
            else:
                current_block_state = _SECTION_OTHER
            current_buffer = [match[1]]
            continue

        if current_speaker:
            current_buffer.append(line)

    flush_current()

    if not parsed_blocks and lines:
        parsed_blocks.append(
            _DeterministicBlock(
                speaker_raw="unknown",
                speaker="unknown",
                text=" ".join(lines[:300]),
                order_index=0,
                base_state=_SECTION_OTHER,
            )
        )

    alias_to_canonical = _canonicalize_speaker_names(
        participants=participants,
        management_roster=management_roster,
        observed_speakers=[block.speaker for block in parsed_blocks],
    )
    for block in parsed_blocks:
        key = _normalize_name_key(block.speaker_raw)
        if _is_non_person_speaker_label(block.speaker_raw):
            lowered = key.lower()
            block.speaker = "Operator" if "operator" in lowered else ("Moderator" if "moderator" in lowered else block.speaker_raw)
        else:
            block.speaker = alias_to_canonical.get(key, block.speaker_raw)

    speaker_role_hints: dict[str, str] = {}
    management_name_keys: set[str] = set()
    for participant in participants:
        name = str(participant.get("name") or "").strip()
        if not name:
            continue
        canonical = alias_to_canonical.get(_normalize_name_key(name), name)
        role_hint = _role_from_participant_title(str(participant.get("role") or ""))
        key = _normalize_name_key(canonical)
        if role_hint:
            speaker_role_hints[key] = role_hint
        if role_hint == _ROLE_MANAGEMENT:
            management_name_keys.add(key)

    for officer in management_roster or []:
        name = str(officer.get("name") or "").strip()
        title = str(officer.get("title") or "")
        if not name:
            continue
        canonical = alias_to_canonical.get(_normalize_name_key(name), name)
        key = _normalize_name_key(canonical)
        if _is_management_roster_title(title):
            management_name_keys.add(key)
            speaker_role_hints.setdefault(key, _ROLE_MANAGEMENT)

    for block in parsed_blocks:
        key = _normalize_name_key(block.speaker)
        role_hint = _role_hint_from_speaker_name(block.speaker)
        if role_hint and key not in speaker_role_hints:
            speaker_role_hints[key] = role_hint

    qa_start = _infer_qa_start_index(parsed_blocks, speaker_role_hints, management_name_keys)
    qa_end = _infer_qa_end_index(parsed_blocks, qa_start)

    for block in parsed_blocks:
        if qa_start is not None:
            if block.order_index < qa_start:
                block.section_type = _SECTION_PREPARED if not _is_boilerplate_block(block.text) else _SECTION_OTHER
            elif qa_end is not None and block.order_index > qa_end:
                block.section_type = _SECTION_OTHER
            elif block.closing_like:
                block.section_type = _SECTION_OTHER
            else:
                block.section_type = _SECTION_QA
        else:
            if block.base_state == _SECTION_OTHER or _is_boilerplate_block(block.text):
                block.section_type = _SECTION_OTHER
            else:
                block.section_type = _SECTION_PREPARED

    resolved_roles = _resolve_speaker_roles(parsed_blocks, speaker_role_hints, management_name_keys, qa_start)

    sections: list[TranscriptSectionBlock] = []
    for block in parsed_blocks:
        role = resolved_roles.get(block.speaker, _ROLE_UNKNOWN)
        role_out: str | None = None if role == _ROLE_UNKNOWN else role
        sections.append(
            TranscriptSectionBlock(
                section_type=block.section_type if block.section_type in {_SECTION_PREPARED, _SECTION_QA, _SECTION_OTHER} else _SECTION_OTHER,
                speaker=block.speaker,
                speaker_role=role_out,
                text=block.text,
                order_index=block.order_index,
                evidence_snippets=_sentences(block.text)[:2],
            )
        )

    participant_models = _canonicalize_participants_for_output(participants, alias_to_canonical, parsed_blocks)

    key_quotes: list[str] = []
    for section in sections:
        for sentence in _sentences(section.text):
            if len(sentence) >= 70:
                key_quotes.append(sentence)
            if len(key_quotes) >= 6:
                break
        if len(key_quotes) >= 6:
            break

    return TranscriptDocument(
        ticker=ticker,
        company_name=company_name,
        source=source,
        source_url=source_url,
        title=title,
        published_date=published_date,
        has_full_transcript=len(sections) >= 2,
        extraction_confidence=_clamp(extraction_confidence, 0.0, 1.0),
        parsing_warnings=parsing_warnings,
        participants=participant_models,
        sections=sections,
        key_quotes=key_quotes,
        normalization_mode="deterministic_degraded",
    )


def _extract_json_from_text(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?", "", content).strip()
        content = re.sub(r"```$", "", content).strip()
    return content


def _resolve_structured_chat_model(model_name: str, *, purpose: str) -> tuple[str, str | None]:
    configured = (model_name or "").strip()
    if not configured:
        raise ValueError(f"{purpose}: model is not configured.")
    lowered = configured.lower()
    if lowered.startswith("gpt-5"):
        fallback_model = "gpt-4o-mini"
        return (
            fallback_model,
            (
                f"{purpose}: model '{configured}' is not allowed for this chat.completions structured-output path. "
                f"Auto-falling back to '{fallback_model}'."
            ),
        )
    return configured, None


def _summarize_openai_http_error(response: requests.Response) -> str:
    detail = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                code = str(error.get("code") or "").strip()
                message = str(error.get("message") or "").strip()
                if code and message:
                    detail = f"{code}: {message}"
                elif message:
                    detail = message
    except Exception:
        pass
    if not detail:
        detail = re.sub(r"\s+", " ", str(response.text or "")).strip()[:360]
    if detail:
        return f"HTTP {response.status_code}: {detail}"
    return f"HTTP {response.status_code}"


def _structured_response_format(schema_name: str, schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema_name,
            "strict": True,
            "schema": schema,
        },
    }


def _post_structured_chat_completion(
    *,
    api_key: str,
    model_name: str,
    system_prompt: str,
    user_payload: dict[str, Any],
    response_schema_name: str,
    response_schema: dict[str, Any],
    timeout_seconds: float,
    retries: int,
    backoff_seconds: float,
) -> tuple[dict[str, Any] | None, str | None]:
    timeout = max(5.0, float(timeout_seconds))
    max_retries = max(0, int(retries))
    backoff = max(0.25, float(backoff_seconds))
    last_error = ""

    for attempt in range(max_retries + 1):
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "temperature": 0,
                    "response_format": _structured_response_format(response_schema_name, response_schema),
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(user_payload)},
                    ],
                },
                timeout=timeout,
            )
            if response.status_code >= 400:
                raise RuntimeError(_summarize_openai_http_error(response))
            payload = response.json()
            choices = payload.get("choices") or []
            if not choices:
                raise ValueError("OpenAI response returned no choices.")
            content = str(choices[0].get("message", {}).get("content") or "").strip()
            if not content:
                raise ValueError("OpenAI response returned empty content.")
            parsed = json.loads(_extract_json_from_text(content))
            if not isinstance(parsed, dict):
                raise ValueError("OpenAI response returned non-object JSON payload.")
            return parsed, None
        except Exception as exc:
            last_error = str(exc).strip() or exc.__class__.__name__
            if attempt >= max_retries:
                break
            time.sleep(backoff * (2 ** attempt))

    return None, last_error or "Unknown OpenAI failure."


def _openai_normalize(
    deterministic_document: TranscriptDocument,
    settings: Settings,
) -> tuple[TranscriptDocument | None, str | None]:
    if not settings.openai_api_key:
        return None, "OPENAI_API_KEY missing; using deterministic transcript normalization."

    try:
        system_prompt = load_prompt_template("normalizer_v1.md")
    except Exception as exc:
        return None, f"Prompt template load failed: {exc}"

    input_payload = {
        "transcript": deterministic_document.model_dump(),
    }

    try:
        model_name, model_resolution_warning = _resolve_structured_chat_model(
            settings.openai_normalizer_model,
            purpose="OpenAI normalizer",
        )
        if model_resolution_warning:
            input_payload["model_resolution_warning"] = model_resolution_warning
        parsed, error = _post_structured_chat_completion(
            api_key=settings.openai_api_key,
            model_name=model_name,
            system_prompt=system_prompt,
            user_payload=input_payload,
            response_schema_name="transcript_document_v1",
            response_schema=TranscriptDocument.model_json_schema(),
            timeout_seconds=settings.request_timeout_seconds,
            retries=settings.openai_request_retries,
            backoff_seconds=settings.openai_retry_backoff_seconds,
        )
        if parsed is None:
            return None, f"OpenAI normalization failed after retries: {error}"
        normalized = TranscriptDocument.model_validate(
            {
                **parsed,
                "normalization_mode": "openai",
            }
        )
        return normalized, None
    except Exception as exc:
        return None, f"OpenAI normalization failed: {exc}"


def _should_try_openai_normalization(document: TranscriptDocument) -> bool:
    section_count = len(document.sections)
    if section_count <= 2:
        return True

    if document.extraction_confidence < 0.55:
        return True

    sparse_warning = any(
        token in warning.lower()
        for warning in document.parsing_warnings
        for token in ("sparse", "empty", "could not")
    )
    if sparse_warning:
        return True

    unknown_speaker_count = sum(1 for section in document.sections if section.speaker.strip().lower() in {"", "unknown"})
    if section_count > 0 and (unknown_speaker_count / section_count) >= 0.35:
        return True

    unknown_role_count = sum(1 for section in document.sections if not (section.speaker_role or "").strip())
    if section_count > 0 and (unknown_role_count / section_count) >= 0.5:
        return True

    other_count = sum(1 for section in document.sections if section.section_type == _SECTION_OTHER)
    if section_count > 0 and (other_count / section_count) >= 0.75:
        return True

    return False


def normalize_transcript_document(
    *,
    ticker: str,
    company_name: str | None,
    source: str,
    source_url: str | None,
    title: str | None,
    published_date: str | None,
    content: str,
    extraction_confidence: float,
    parsing_warnings: list[str],
    participants: list[dict[str, str]],
    management_roster: list[dict[str, str]] | None,
    settings: Settings,
) -> NormalizationResult:
    deterministic = deterministic_document_from_text(
        ticker=ticker,
        company_name=company_name,
        source=source,
        source_url=source_url,
        title=title,
        published_date=published_date,
        content=content,
        extraction_confidence=extraction_confidence,
        parsing_warnings=parsing_warnings,
        participants=participants,
        management_roster=management_roster,
    )

    if not _should_try_openai_normalization(deterministic):
        return NormalizationResult(document=deterministic, warnings=[])

    normalized, error = _openai_normalize(deterministic, settings)
    if normalized is not None:
        return NormalizationResult(document=normalized, warnings=[])

    warnings = [error] if error else []
    return NormalizationResult(document=deterministic, warnings=warnings)


def _metric_band_labels(metric: str) -> tuple[str, ...]:
    if metric in {"confidence", "directness"}:
        return BAND_LABELS_THREE
    if metric == "outlook_strength":
        return BAND_LABELS_FIVE
    return BAND_LABELS_FIVE


def _resolve_metric_selection(
    *,
    metric: str,
    lexical_score: float,
    student_prediction: StudentMetricPrediction | None,
    student_enabled: bool,
    student_primary: bool,
    force_lexical_fallback: bool,
    shadow_compare: bool,
    guard_reason: str | None,
    fallback_error: str | None,
    blend_enabled: bool = False,
    blend_weight: float = 0.35,
) -> tuple[float, str, dict[str, Any]]:
    labels = _metric_band_labels(metric)
    lexical_score = _clamp(lexical_score, 0.0, 100.0)
    lexical_band = band_from_score(lexical_score, labels)

    final_score = lexical_score
    final_band = lexical_band
    source = "lexical_primary"
    fallback_reason: str | None = None
    blend_applied = False

    if student_enabled:
        if force_lexical_fallback:
            source = "lexical_fallback" if student_primary else "lexical_primary"
            fallback_reason = "forced_lexical_fallback"
        elif guard_reason:
            source = "lexical_fallback" if student_primary else "lexical_primary"
            fallback_reason = guard_reason
        elif fallback_error:
            source = "lexical_fallback" if student_primary else "lexical_primary"
            fallback_reason = fallback_error
        elif student_prediction is None:
            source = "lexical_fallback" if student_primary else "lexical_primary"
            fallback_reason = "student_prediction_missing"
        else:
            if blend_enabled:
                safe_weight = _clamp(blend_weight, 0.0, 1.0)
                final_score = _clamp(
                    lexical_score * (1.0 - safe_weight) + student_prediction.score * safe_weight,
                    0.0,
                    100.0,
                )
                final_band = band_from_score(final_score, labels)
                source = "lexical_primary"
                blend_applied = True
            elif student_primary:
                final_score = _clamp(student_prediction.score, 0.0, 100.0)
                final_band = student_prediction.band
                source = "student_primary"
            else:
                source = "lexical_primary"

    debug: dict[str, Any] = {
        "source": source,
        "final_band": final_band,
        "final_score": round(final_score, 2),
    }
    if shadow_compare:
        debug["lexical_score"] = round(lexical_score, 2)
        debug["lexical_band"] = lexical_band
        debug["student_band"] = student_prediction.band if student_prediction is not None else None
        debug["student_score"] = (
            round(float(student_prediction.score), 2) if student_prediction is not None else None
        )
        debug["student_probabilities"] = student_prediction.probabilities if student_prediction is not None else None
        debug["student_predicted_confidence"] = (
            round(float(student_prediction.predicted_confidence), 4) if student_prediction is not None else None
        )
    if fallback_reason:
        debug["fallback_reason"] = fallback_reason
    if blend_applied:
        debug["blend_mode"] = "specificity_experimental_lexical_student"
        debug["blend_weight_student"] = round(_clamp(blend_weight, 0.0, 1.0), 4)
    return final_score, final_band, debug


def build_speaker_analysis(
    sections: list[TranscriptSectionBlock],
    score_text_fn,
    settings: Settings | None = None,
    classifier_warnings: list[str] | None = None,
    classifier_diagnostics: list[str] | None = None,
) -> list[TranscriptSpeakerAnalysis]:
    results: list[TranscriptSpeakerAnalysis] = []
    ai_features_by_index, ai_warnings, ai_diagnostics = _classify_block_features_with_openai(
        sections=sections,
        settings=settings,
    )
    if classifier_warnings is not None and ai_warnings:
        classifier_warnings.extend(ai_warnings)
    if classifier_diagnostics is not None and ai_diagnostics:
        classifier_diagnostics.extend(ai_diagnostics)

    ai_weight_base = (
        _clamp_unit(settings.transcript_feature_ai_weight)
        if settings is not None and settings.transcript_feature_ai_enabled
        else 0.0
    )
    student_inference = infer_student_metric_blocks(sections=sections, settings=settings)
    if classifier_warnings is not None and student_inference.warnings:
        classifier_warnings.extend(student_inference.warnings)
    if classifier_diagnostics is not None and student_inference.diagnostics:
        classifier_diagnostics.extend(student_inference.diagnostics)

    use_student_confidence = bool(settings.use_student_confidence) if settings is not None else False
    use_student_directness = bool(settings.use_student_directness) if settings is not None else False
    use_student_outlook_strength = bool(settings.use_student_outlook_strength) if settings is not None else False
    use_student_specificity = bool(settings.use_student_specificity) if settings is not None else False
    use_student_risk_intensity = bool(settings.use_student_risk_intensity) if settings is not None else False
    force_lexical_fallback = bool(settings.student_metrics_force_lexical_fallback) if settings is not None else False
    shadow_compare = bool(settings.student_metrics_shadow_compare) if settings is not None else False
    specificity_blend_enabled = (
        bool(settings.student_metrics_specificity_blend_enabled) and use_student_specificity
        if settings is not None
        else False
    )
    specificity_blend_weight = (
        _clamp(float(settings.student_metrics_specificity_blend_weight), 0.0, 1.0) if settings is not None else 0.35
    )
    skipped_fluff_blocks = 0

    for idx, block in enumerate(sections):
        if _should_skip_metric_scoring_for_fluff_block(block):
            skipped_fluff_blocks += 1
            continue
        score = score_text_fn(block.text)
        directional = float(score.get("directional_score", 0.0))
        segment_diagnostics = score.get("segment_diagnostics") if isinstance(score, dict) else None
        if not isinstance(segment_diagnostics, dict):
            segment_diagnostics = None

        sentence_list = _sentences(block.text)
        numeric_density = (
            sum(1 for sentence in sentence_list if re.search(r"\d", sentence)) / len(sentence_list)
            if sentence_list
            else 0.0
        )
        hedge_density_lex, hedge_terms = _weighted_term_density(block.text, _HEDGE_TERMS)
        forward_density_lex, forward_terms = _weighted_term_density(block.text, _FORWARD_TERMS)
        forward_counter_density_lex, forward_counter_terms = _weighted_term_density(block.text, _FORWARD_COUNTER_TERMS)
        risk_density_lex, risk_terms = _weighted_term_density(block.text, _RISK_TERMS)
        confidence_density_lex, confidence_terms = _weighted_term_density(block.text, _CONFIDENCE_TERMS)
        confidence_counter_density_lex, confidence_counter_terms = _weighted_term_density(
            block.text,
            _CONFIDENCE_COUNTER_TERMS,
        )
        specificity_density_lex, specificity_terms = _weighted_term_density(block.text, _SPECIFICITY_TERMS)
        specificity_counter_density_lex, specificity_counter_terms = _weighted_term_density(
            block.text,
            _SPECIFICITY_COUNTER_TERMS,
        )
        directness_density_lex, directness_terms = _weighted_term_density(block.text, _DIRECTNESS_TERMS)
        topic_label_lex, topic_score_lex = _topic_label(block.text)

        ai_features = ai_features_by_index.get(idx)
        ai_blend_weight = ai_weight_base * (ai_features.confidence if ai_features is not None else 0.0)
        counter_weight = (
            max(0.0, float(getattr(settings, "transcript_feature_counter_weight", 0.65)))
            if settings is not None
            else 0.65
        )
        smoothing = (
            _clamp(float(getattr(settings, "transcript_feature_density_smoothing", 0.35)), 0.0, 1.0)
            if settings is not None
            else 0.35
        )

        forward_density = (
            forward_density_lex * (1.0 - ai_blend_weight) + ai_features.forward_density * ai_blend_weight
            if ai_features is not None
            else forward_density_lex
        )
        forward_counter_density = (
            forward_counter_density_lex * (1.0 - ai_blend_weight) + ai_features.risk_density * ai_blend_weight
            if ai_features is not None
            else forward_counter_density_lex
        )
        risk_density = (
            risk_density_lex * (1.0 - ai_blend_weight) + ai_features.risk_density * ai_blend_weight
            if ai_features is not None
            else risk_density_lex
        )
        hedge_density = (
            hedge_density_lex * (1.0 - ai_blend_weight) + ai_features.hedge_density * ai_blend_weight
            if ai_features is not None
            else hedge_density_lex
        )
        specificity_density = (
            specificity_density_lex * (1.0 - ai_blend_weight) + ai_features.specificity_density * ai_blend_weight
            if ai_features is not None
            else specificity_density_lex
        )
        confidence_density = (
            confidence_density_lex * (1.0 - ai_blend_weight) + ai_features.specificity_density * ai_blend_weight
            if ai_features is not None
            else confidence_density_lex
        )
        confidence_counter_density = (
            confidence_counter_density_lex * (1.0 - ai_blend_weight) + ai_features.hedge_density * ai_blend_weight
            if ai_features is not None
            else confidence_counter_density_lex
        )
        specificity_counter_density = (
            specificity_counter_density_lex * (1.0 - ai_blend_weight) + ai_features.hedge_density * ai_blend_weight
            if ai_features is not None
            else specificity_counter_density_lex
        )
        directness_density = (
            directness_density_lex * (1.0 - ai_blend_weight) + ai_features.specificity_density * ai_blend_weight
            if ai_features is not None
            else directness_density_lex
        )
        blended_numeric_density = _clamp_unit(numeric_density * 0.65 + specificity_density * 0.35)

        outlook_net = _net_density(forward_density, forward_counter_density, counter_weight)
        confidence_net = _net_density(
            confidence_density + specificity_density * 0.25 + forward_density * 0.15,
            confidence_counter_density + hedge_density * 0.35 + risk_density * 0.2,
            counter_weight,
        )
        specificity_net = _net_density(
            specificity_density + blended_numeric_density * 0.25,
            specificity_counter_density,
            counter_weight,
        )
        evasiveness_net = _net_density(
            hedge_density + risk_density * 0.25,
            directness_density + specificity_density * 0.15,
            counter_weight,
        )
        risk_net = _net_density(risk_density, directness_density * 0.3, max(0.25, counter_weight * 0.45))

        confidence_component = _smoothed_percent(confidence_net, smoothing)
        evasiveness_component = _smoothed_percent(evasiveness_net, smoothing)
        specificity_component = _smoothed_percent(specificity_net, smoothing)
        outlook_component = _smoothed_percent(outlook_net, smoothing)
        risk_component = _smoothed_percent(risk_net, smoothing)

        confidence = _clamp(
            14
            + confidence_component * 0.68
            + specificity_component * 0.14
            + blended_numeric_density * 14
            - evasiveness_component * 0.10,
            0,
            100,
        )
        evasiveness = _clamp(
            10
            + evasiveness_component * 0.72
            + (1 - blended_numeric_density) * 14
            + risk_component * 0.08
            - specificity_component * 0.10,
            0,
            100,
        )
        specificity = _clamp(
            14
            + specificity_component * 0.72
            + blended_numeric_density * 18
            - evasiveness_component * 0.12,
            0,
            100,
        )
        forward_strength = _clamp(
            12
            + outlook_component * 0.78
            - evasiveness_component * 0.10,
            0,
            100,
        )
        risk_intensity = _clamp(
            10
            + risk_component * 0.80
            + evasiveness_component * 0.08,
            0,
            100,
        )
        lexical_directness = _clamp(100.0 - evasiveness, 0.0, 100.0)

        student_predictions = student_inference.by_index.get(idx, {})
        student_guard_reason = student_block_guard_reason(block.text)

        confidence_value, confidence_band, confidence_debug = _resolve_metric_selection(
            metric="confidence",
            lexical_score=confidence,
            student_prediction=student_predictions.get("confidence"),
            student_enabled=use_student_confidence,
            student_primary=True,
            force_lexical_fallback=force_lexical_fallback,
            shadow_compare=shadow_compare,
            guard_reason=student_guard_reason if use_student_confidence else None,
            fallback_error=student_inference.metric_errors.get("confidence") if use_student_confidence else None,
        )
        directness_value, directness_band, directness_debug = _resolve_metric_selection(
            metric="directness",
            lexical_score=lexical_directness,
            student_prediction=student_predictions.get("directness"),
            student_enabled=use_student_directness,
            student_primary=True,
            force_lexical_fallback=force_lexical_fallback,
            shadow_compare=shadow_compare,
            guard_reason=student_guard_reason if use_student_directness else None,
            fallback_error=student_inference.metric_errors.get("directness") if use_student_directness else None,
        )
        outlook_value, outlook_band, outlook_debug = _resolve_metric_selection(
            metric="outlook_strength",
            lexical_score=forward_strength,
            student_prediction=student_predictions.get("outlook_strength"),
            student_enabled=use_student_outlook_strength,
            student_primary=True,
            force_lexical_fallback=force_lexical_fallback,
            shadow_compare=shadow_compare,
            guard_reason=student_guard_reason if use_student_outlook_strength else None,
            fallback_error=(
                student_inference.metric_errors.get("outlook_strength") if use_student_outlook_strength else None
            ),
        )
        specificity_value, specificity_band, specificity_debug = _resolve_metric_selection(
            metric="specificity",
            lexical_score=specificity,
            student_prediction=student_predictions.get("specificity"),
            student_enabled=use_student_specificity or specificity_blend_enabled,
            student_primary=use_student_specificity and not specificity_blend_enabled,
            force_lexical_fallback=force_lexical_fallback,
            shadow_compare=shadow_compare,
            guard_reason=student_guard_reason if (use_student_specificity or specificity_blend_enabled) else None,
            fallback_error=(
                student_inference.metric_errors.get("specificity")
                if (use_student_specificity or specificity_blend_enabled)
                else None
            ),
            blend_enabled=specificity_blend_enabled,
            blend_weight=specificity_blend_weight,
        )
        risk_value, risk_band, risk_debug = _resolve_metric_selection(
            metric="risk_intensity",
            lexical_score=risk_intensity,
            student_prediction=student_predictions.get("risk_intensity"),
            student_enabled=use_student_risk_intensity,
            student_primary=use_student_risk_intensity,
            force_lexical_fallback=force_lexical_fallback,
            shadow_compare=shadow_compare,
            guard_reason=student_guard_reason if use_student_risk_intensity else None,
            fallback_error=(
                student_inference.metric_errors.get("risk_intensity") if use_student_risk_intensity else None
            ),
        )

        if directness_debug.get("source") == "student_primary":
            evasiveness_value = _clamp(100.0 - directness_value, 0.0, 100.0)
            evasiveness_source = "student_primary"
            evasiveness_fallback_reason = None
        else:
            evasiveness_value = evasiveness
            evasiveness_source = directness_debug.get("source", "lexical_primary")
            evasiveness_fallback_reason = directness_debug.get("fallback_reason")
        evasiveness_debug: dict[str, Any] = {
            "source": evasiveness_source,
            "final_band": band_from_score(evasiveness_value, BAND_LABELS_FIVE),
            "final_score": round(evasiveness_value, 2),
            "derived_from": "inverse_of_directness",
            "directness_source": directness_debug.get("source", "lexical_primary"),
        }
        if shadow_compare:
            evasiveness_debug["lexical_score"] = round(evasiveness, 2)
            evasiveness_debug["lexical_band"] = band_from_score(evasiveness, BAND_LABELS_FIVE)
            evasiveness_debug["inverse_directness_score"] = round(_clamp(100.0 - directness_value, 0.0, 100.0), 2)
        if evasiveness_fallback_reason:
            evasiveness_debug["fallback_reason"] = str(evasiveness_fallback_reason)

        topic_label = topic_label_lex
        if ai_features is not None and ai_features.topic_label != "general" and ai_blend_weight >= 0.2:
            topic_label = ai_features.topic_label

        evidence = block.evidence_snippets[:2] if block.evidence_snippets else _sentences(block.text)[:2]
        if segment_diagnostics is not None:
            top_pos = str(segment_diagnostics.get("top_positive_evidence") or "").strip()
            top_neg = str(segment_diagnostics.get("top_negative_evidence") or "").strip()
            merged: list[str] = []
            for item in [top_pos, top_neg, *evidence]:
                if item and item not in merged:
                    merged.append(item)
            evidence = merged[:2] if merged else evidence

        feature_diagnostics = {
            "method": "hybrid_lexical_plus_ai" if ai_features is not None else "lexical_weighted",
            "numeric_density": round(numeric_density, 4),
            "specificity_density": round(specificity_density, 4),
            "specificity_counter_density": round(specificity_counter_density, 4),
            "forward_density": round(forward_density, 4),
            "forward_counter_density": round(forward_counter_density, 4),
            "risk_density": round(risk_density, 4),
            "hedge_density": round(hedge_density, 4),
            "directness_density": round(directness_density, 4),
            "counter_weight": round(counter_weight, 4),
            "density_smoothing": round(smoothing, 4),
            "outlook_net_density": round(outlook_net, 4),
            "confidence_net_density": round(confidence_net, 4),
            "specificity_net_density": round(specificity_net, 4),
            "evasiveness_net_density": round(evasiveness_net, 4),
            "topic_score_lex": round(topic_score_lex, 4),
            "ai_blend_weight": round(ai_blend_weight, 4),
            "topic_label_lex": topic_label_lex,
            "matched_terms": {
                "forward": forward_terms[:8],
                "forward_counter": forward_counter_terms[:8],
                "risk": risk_terms[:8],
                "hedge": hedge_terms[:8],
                "confidence": confidence_terms[:8],
                "confidence_counter": confidence_counter_terms[:8],
                "specificity": specificity_terms[:8],
                "specificity_counter": specificity_counter_terms[:8],
                "directness": directness_terms[:8],
            },
            "metric_source_debug": {
                "confidence": confidence_debug,
                "directness": directness_debug,
                "outlook_strength": outlook_debug,
                "specificity": specificity_debug,
                "risk_intensity": risk_debug,
                "evasiveness": evasiveness_debug,
            },
            "metric_band_debug": {
                "confidence": confidence_band,
                "directness": directness_band,
                "outlook_strength": outlook_band,
                "specificity": specificity_band,
                "risk_intensity": risk_band,
                "evasiveness": evasiveness_debug["final_band"],
            },
        }
        if ai_features is not None:
            feature_diagnostics["ai"] = {
                "confidence": round(ai_features.confidence, 4),
                "topic_label": ai_features.topic_label,
                "forward_density": round(ai_features.forward_density, 4),
                "risk_density": round(ai_features.risk_density, 4),
                "hedge_density": round(ai_features.hedge_density, 4),
                "specificity_density": round(ai_features.specificity_density, 4),
            }

        merged_segment_diagnostics = dict(segment_diagnostics or {})
        merged_segment_diagnostics["feature_diagnostics"] = feature_diagnostics

        results.append(
            TranscriptSpeakerAnalysis(
                speaker=block.speaker,
                speaker_role=block.speaker_role,
                section_type=block.section_type,
                order_index=block.order_index,
                sentiment_direction=_clamp(directional, -1.0, 1.0),
                segment_char_count=len(block.text.strip()),
                confidence=round(confidence_value, 2),
                evasiveness=round(evasiveness_value, 2),
                specificity=round(specificity_value, 2),
                forward_looking_strength=round(outlook_value, 2),
                risk_language_intensity=round(risk_value, 2),
                topic_label=topic_label,
                evidence_snippets=evidence,
                segment_diagnostics=merged_segment_diagnostics,
            )
        )

    if classifier_diagnostics is not None and skipped_fluff_blocks > 0:
        classifier_diagnostics.append(
            f"Skipped {skipped_fluff_blocks} block(s) from sentiment/metric scoring due to short operator fluff rule."
        )

    return results


def summarize_transcript_findings(speaker_analysis: list[TranscriptSpeakerAnalysis]) -> tuple[str, list[str], list[str]]:
    if not speaker_analysis:
        return (
            "No management speaker blocks were available to summarize communication quality.",
            [],
            ["No management pressure points were detected due to missing management speaker blocks."],
        )

    avg_confidence = mean(item.confidence for item in speaker_analysis)
    avg_evasive = mean(item.evasiveness for item in speaker_analysis)

    sorted_forward = sorted(speaker_analysis, key=lambda s: s.forward_looking_strength, reverse=True)
    sorted_evasive = sorted(speaker_analysis, key=lambda s: s.evasiveness, reverse=True)

    takeaways = [
        f"Average management confidence across speaker turns is {avg_confidence:.1f}.",
        f"Average evasiveness across speaker turns is {avg_evasive:.1f}.",
    ]

    if sorted_forward:
        takeaways.append(
            f"Strongest forward-looking language appears in {sorted_forward[0].speaker} ({sorted_forward[0].topic_label})."
        )

    pressure_points = [
        f"{item.speaker}: evasiveness {item.evasiveness:.1f} in {item.topic_label}."
        for item in sorted_evasive[:4]
    ]

    summary = (
        "Management transcript analysis highlights communication quality more than directional score. "
        f"Confidence averaged {avg_confidence:.1f}, while evasiveness averaged {avg_evasive:.1f}."
    )

    return summary, takeaways[:5], pressure_points
