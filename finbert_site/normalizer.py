"""Transcript normalization and speaker-block analysis."""

from __future__ import annotations

from dataclasses import dataclass
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

_FORWARD_TERMS = {
    "guidance",
    "next quarter",
    "full year",
    "outlook",
    "expect",
    "forecast",
    "pipeline",
}

_RISK_TERMS = {
    "headwind",
    "pressure",
    "uncertain",
    "volatility",
    "risk",
    "challenging",
    "softness",
    "downturn",
}

_HEDGE_TERMS = {
    "may",
    "might",
    "could",
    "assuming",
    "we believe",
    "we think",
    "not going to comment",
    "cannot comment",
    "too early",
}

_TOPIC_KEYWORDS = {
    "demand": {"demand", "orders", "bookings", "backlog"},
    "margins": {"margin", "gross margin", "operating margin", "profitability"},
    "guidance": {"guidance", "outlook", "expect", "forecast"},
    "capex": {"capex", "investment", "datacenter", "infrastructure"},
    "costs": {"cost", "expense", "opex", "efficiency"},
}


@dataclass
class NormalizationResult:
    document: TranscriptDocument
    warnings: list[str]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


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


def _term_density(text: str, terms: set[str]) -> float:
    lowered = text.lower()
    if not lowered.strip():
        return 0.0
    hits = sum(1 for term in terms if term in lowered)
    return hits / max(len(terms), 1)


def _topic_label(text: str) -> str:
    lowered = text.lower()
    best_topic = "general"
    best_hits = 0
    for topic, keywords in _TOPIC_KEYWORDS.items():
        hits = sum(1 for kw in keywords if kw in lowered)
        if hits > best_hits:
            best_hits = hits
            best_topic = topic
    return best_topic


def build_speaker_analysis(
    sections: list[TranscriptSectionBlock],
    score_text_fn,
) -> list[TranscriptSpeakerAnalysis]:
    results: list[TranscriptSpeakerAnalysis] = []

    for block in sections:
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
        hedge_density = _term_density(block.text, _HEDGE_TERMS)
        forward_density = _term_density(block.text, _FORWARD_TERMS)
        risk_density = _term_density(block.text, _RISK_TERMS)

        confidence = _clamp(48 + numeric_density * 45 - hedge_density * 35, 0, 100)
        evasiveness = _clamp(25 + hedge_density * 60 + (1 - numeric_density) * 20, 0, 100)
        specificity = _clamp(30 + numeric_density * 60, 0, 100)
        forward_strength = _clamp(25 + forward_density * 80, 0, 100)
        risk_intensity = _clamp(20 + risk_density * 90, 0, 100)

        evidence = block.evidence_snippets[:2] if block.evidence_snippets else _sentences(block.text)[:2]
        if segment_diagnostics is not None:
            top_pos = str(segment_diagnostics.get("top_positive_evidence") or "").strip()
            top_neg = str(segment_diagnostics.get("top_negative_evidence") or "").strip()
            merged: list[str] = []
            for item in [top_pos, top_neg, *evidence]:
                if item and item not in merged:
                    merged.append(item)
            evidence = merged[:2] if merged else evidence

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
                topic_label=_topic_label(block.text),
                evidence_snippets=evidence,
                segment_diagnostics=segment_diagnostics,
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
