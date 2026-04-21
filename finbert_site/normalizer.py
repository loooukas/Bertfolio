"""Transcript normalization and speaker-block analysis."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import json
import re
from statistics import mean
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


def _truncate_block_text(text: str, max_chars: int = 1000) -> str:
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
) -> tuple[dict[int, BlockAiFeatures], list[str]]:
    if settings is None:
        return {}, []
    if not settings.transcript_feature_ai_enabled:
        return {}, []
    if not settings.openai_api_key:
        return {}, []
    if not sections:
        return {}, []

    try:
        system_prompt = load_prompt_template("transcript_feature_classifier_v1.md")
    except Exception as exc:
        return {}, [f"Transcript feature classifier prompt load failed: {exc}"]

    max_blocks = max(1, settings.transcript_feature_ai_max_blocks)
    batch_size = max(1, min(32, settings.transcript_feature_ai_batch_size))
    timeout_seconds = max(5, settings.transcript_feature_ai_timeout_seconds)
    target_sections = sections[:max_blocks]

    model_name = _chat_compatible_model(settings.transcript_feature_ai_model)
    results: dict[int, BlockAiFeatures] = {}
    warnings: list[str] = []

    for start in range(0, len(target_sections), batch_size):
        batch = target_sections[start : start + batch_size]
        payload = {
            "topics": list(_TOPIC_LABELS),
            "blocks": [
                {
                    "index": start + offset,
                    "speaker": section.speaker,
                    "section_type": section.section_type,
                    "text": _truncate_block_text(section.text),
                }
                for offset, section in enumerate(batch)
            ],
        }
        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model_name,
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": json.dumps(payload)},
                    ],
                },
                timeout=timeout_seconds,
            )
            response.raise_for_status()
            raw = response.json()
            choices = raw.get("choices") or []
            if not choices:
                raise ValueError("OpenAI feature classifier returned no choices")
            content = str(choices[0].get("message", {}).get("content") or "").strip()
            if not content:
                raise ValueError("OpenAI feature classifier returned empty content")
            parsed = json.loads(_extract_json_from_text(content))
            items = parsed.get("blocks")
            if not isinstance(items, list):
                raise ValueError("OpenAI feature classifier response missing blocks[]")

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
        except Exception as exc:
            warnings.append(f"OpenAI feature classification failed for batch {start // batch_size + 1}: {exc}")

    return results, warnings


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[.!?])\s+", compact)
    return [p.strip() for p in parts if p.strip()]


def _guess_role(speaker: str) -> str | None:
    lowered = speaker.lower()
    if "operator" in lowered:
        return "operator"
    if "analyst" in lowered:
        return "analyst"
    if any(t in lowered for t in ["ceo", "chief executive", "cfo", "chief financial", "president"]):
        return "management"
    return None


def _detect_section_type(line: str, current: str) -> str:
    lowered = line.lower()
    if "questions and answers" in lowered or lowered.strip() in {"q&a", "question-and-answer"}:
        return "qa"
    if "prepared remarks" in lowered:
        return "prepared_remarks"
    return current


def _speaker_line_match(line: str) -> tuple[str, str] | None:
    m = re.match(r"^([A-Za-z][A-Za-z .,'&()\-/]{1,70}):\s*(.+)$", line)
    if not m:
        return None
    speaker = re.sub(r"\s+", " ", m.group(1)).strip()
    text = m.group(2).strip()
    if len(text) < 2:
        return None
    return speaker, text


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
) -> TranscriptDocument:
    lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    section_type = "other"
    sections: list[TranscriptSectionBlock] = []
    order_idx = 0

    current_speaker = None
    current_role = None
    current_buffer: list[str] = []
    current_section_type = section_type

    def flush_current() -> None:
        nonlocal order_idx, current_speaker, current_role, current_buffer, current_section_type
        if not current_speaker or not current_buffer:
            return
        text = " ".join(current_buffer).strip()
        if not text:
            return
        evidence = _sentences(text)[:2]
        sections.append(
            TranscriptSectionBlock(
                section_type=current_section_type,
                speaker=current_speaker,
                speaker_role=current_role,
                text=text,
                order_index=order_idx,
                evidence_snippets=evidence,
            )
        )
        order_idx += 1
        current_speaker = None
        current_role = None
        current_buffer = []

    for line in lines:
        section_type = _detect_section_type(line, section_type)

        match = _speaker_line_match(line)
        if match:
            flush_current()
            current_speaker = match[0]
            current_role = _guess_role(current_speaker)
            current_section_type = section_type
            current_buffer = [match[1]]
            continue

        if current_speaker:
            current_buffer.append(line)

    flush_current()

    if not sections and lines:
        sections.append(
            TranscriptSectionBlock(
                section_type="other",
                speaker="unknown",
                speaker_role=None,
                text=" ".join(lines[:300]),
                order_index=0,
                evidence_snippets=_sentences(" ".join(lines[:300]))[:2],
            )
        )

    participant_models = [
        TranscriptParticipant(name=p.get("name", "unknown"), role=p.get("role") or None)
        for p in participants[:20]
        if p.get("name")
    ]

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


def _chat_compatible_model(model_name: str) -> str:
    normalized = (model_name or "").strip().lower()
    if normalized.startswith("gpt-5"):
        return "gpt-4o-mini"
    return model_name


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
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": _chat_compatible_model(settings.openai_normalizer_model),
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(input_payload)},
                ],
            },
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices") or []
        if not choices:
            return None, "OpenAI normalization returned no choices."
        content = str(choices[0].get("message", {}).get("content") or "").strip()
        if not content:
            return None, "OpenAI normalization returned empty content."

        parsed = json.loads(_extract_json_from_text(content))
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
    )

    if not _should_try_openai_normalization(deterministic):
        return NormalizationResult(document=deterministic, warnings=[])

    normalized, error = _openai_normalize(deterministic, settings)
    if normalized is not None:
        return NormalizationResult(document=normalized, warnings=[])

    warnings = [error] if error else []
    return NormalizationResult(document=deterministic, warnings=warnings)


def build_speaker_analysis(
    sections: list[TranscriptSectionBlock],
    score_text_fn,
    settings: Settings | None = None,
    classifier_warnings: list[str] | None = None,
) -> list[TranscriptSpeakerAnalysis]:
    results: list[TranscriptSpeakerAnalysis] = []
    ai_features_by_index, ai_warnings = _classify_block_features_with_openai(sections=sections, settings=settings)
    if classifier_warnings is not None and ai_warnings:
        classifier_warnings.extend(ai_warnings)

    ai_weight_base = (
        _clamp_unit(settings.transcript_feature_ai_weight)
        if settings is not None and settings.transcript_feature_ai_enabled
        else 0.0
    )

    for idx, block in enumerate(sections):
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
        risk_density_lex, risk_terms = _weighted_term_density(block.text, _RISK_TERMS)
        specificity_density_lex, specificity_terms = _weighted_term_density(block.text, _SPECIFICITY_TERMS)
        topic_label_lex, topic_score_lex = _topic_label(block.text)

        ai_features = ai_features_by_index.get(idx)
        ai_blend_weight = ai_weight_base * (ai_features.confidence if ai_features is not None else 0.0)

        forward_density = (
            forward_density_lex * (1.0 - ai_blend_weight) + ai_features.forward_density * ai_blend_weight
            if ai_features is not None
            else forward_density_lex
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
        blended_numeric_density = _clamp_unit(numeric_density * 0.65 + specificity_density * 0.35)

        confidence = _clamp(
            42
            + blended_numeric_density * 36
            + specificity_density * 24
            + forward_density * 10
            - hedge_density * 42
            - risk_density * 8,
            0,
            100,
        )
        evasiveness = _clamp(
            20
            + hedge_density * 58
            + (1 - blended_numeric_density) * 16
            + risk_density * 12
            - specificity_density * 8,
            0,
            100,
        )
        specificity = _clamp(24 + blended_numeric_density * 44 + specificity_density * 38 - hedge_density * 12, 0, 100)
        forward_strength = _clamp(18 + forward_density * 82 - hedge_density * 8, 0, 100)
        risk_intensity = _clamp(15 + risk_density * 88 + hedge_density * 8, 0, 100)

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
            "forward_density": round(forward_density, 4),
            "risk_density": round(risk_density, 4),
            "hedge_density": round(hedge_density, 4),
            "topic_score_lex": round(topic_score_lex, 4),
            "ai_blend_weight": round(ai_blend_weight, 4),
            "topic_label_lex": topic_label_lex,
            "matched_terms": {
                "forward": forward_terms[:8],
                "risk": risk_terms[:8],
                "hedge": hedge_terms[:8],
                "specificity": specificity_terms[:8],
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
                section_type=block.section_type,
                sentiment_direction=_clamp(directional, -1.0, 1.0),
                segment_char_count=len(block.text.strip()),
                confidence=round(confidence, 2),
                evasiveness=round(evasiveness, 2),
                specificity=round(specificity, 2),
                forward_looking_strength=round(forward_strength, 2),
                risk_language_intensity=round(risk_intensity, 2),
                topic_label=topic_label,
                evidence_snippets=evidence,
                segment_diagnostics=merged_segment_diagnostics,
            )
        )

    return results


def summarize_transcript_findings(speaker_analysis: list[TranscriptSpeakerAnalysis]) -> tuple[str, list[str], list[str]]:
    if not speaker_analysis:
        return (
            "No transcript blocks were available to summarize.",
            [],
            ["No transcript-derived pressure points were detected due to missing speaker blocks."],
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
        "Transcript analysis highlights communication quality more than directional score. "
        f"Confidence averaged {avg_confidence:.1f}, while evasiveness averaged {avg_evasive:.1f}."
    )

    return summary, takeaways[:5], pressure_points
