"""OpenAI web-search prototype for Motley Fool transcript link discovery."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import html as html_lib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

load_dotenv()

DEFAULT_OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_OPENAI_SEARCH_MODEL = os.getenv("OPENAI_SEARCH_MODEL", "gpt-5-mini")
DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_OPENAI_RETRY_ATTEMPTS = int(os.getenv("OPENAI_RETRY_ATTEMPTS", "3"))
DEFAULT_TRANSCRIPT_INPUT_MAX_CHARS = int(os.getenv("TRANSCRIPT_INPUT_MAX_CHARS", "120000"))
DEFAULT_OPENAI_CONNECT_TIMEOUT_SECONDS = float(os.getenv("OPENAI_CONNECT_TIMEOUT_SECONDS", "10"))
DEFAULT_OPENAI_READ_TIMEOUT_CAP_SECONDS = float(os.getenv("OPENAI_READ_TIMEOUT_CAP_SECONDS", "50"))
DEFAULT_OPENAI_TRANSPORT_RETRIES = int(os.getenv("OPENAI_TRANSPORT_RETRIES", "0"))
DEFAULT_TRANSCRIPT_SEGMENT_CHARS = int(os.getenv("TRANSCRIPT_SEGMENT_CHARS", "12000"))
DEFAULT_SCRAPE_CACHE_DIR = os.getenv("MOTLEY_SCRAPE_CACHE_DIR", "output/openai_motley_cache")
DEFAULT_SCRAPE_CACHE_MODE = os.getenv("MOTLEY_SCRAPE_CACHE_MODE", "refresh")

_TITLE_QUARTER_PATTERNS = (
    re.compile(r"\bQ([1-4])\s+(20\d{2})\b", flags=re.IGNORECASE),
    re.compile(r"\b(20\d{2})\s+Q([1-4])\b", flags=re.IGNORECASE),
)
_URL_QUARTER_PATTERN = re.compile(r"-q([1-4])-(20\d{2})-earnings-call-transcript", flags=re.IGNORECASE)
_URL_DATE_PATTERN = re.compile(r"/earnings/call-transcripts/(\d{4})/(\d{2})/(\d{2})/")
_SPEAKER_LINE_PATTERN = re.compile(r"^([A-Za-z][A-Za-z .,'&()\-/]{1,90}):\s*(.+)$")
_PLAUSIBLE_PERSON_NAME_PATTERN = re.compile(r"^[A-Z][A-Za-z.'\-]+(?: [A-Z][A-Za-z.'\-]+){0,5}$")

_TRANSCRIPT_END_MARKERS = {
    "read next",
    "stocks mentioned",
    "premium investing services",
    "motley fool stock advisor's latest pick",
    "this article is a transcript",
    "the motley fool has positions",
    "the motley fool has a disclosure policy",
    "terms of use",
    "about the motley fool",
    "need a quote from a motley fool analyst",
    "this conference call transcript",
}

_TRANSCRIPT_START_MARKERS = {
    "full conference call transcript",
    "prepared remarks",
    "questions and answers",
    "q&a",
}

_QA_TRANSITION_MARKERS = (
    "questions and answers",
    "q&a",
    "we'll now move over to q and a",
    "we'll now move to q and a",
    "let's open the call to questions",
    "let's open the line for questions",
    "open the call to questions",
    "open the line for questions",
    "may we have the first question",
    "we ask that you limit yourself",
    "first question",
    "next question",
    "our next question",
    "question comes from",
)
_ANALYST_QUESTION_HINTS = (
    "i have two",
    "i have one",
    "i have a question",
    "my question",
    "thanks for taking",
    "thank you for taking",
    "can you comment",
    "could you comment",
    "help us understand",
)

_SECTION_TYPE_VALUES = {"prepared_remarks", "qa", "other"}
_GENERIC_SPEAKER_LABELS = {
    "operator",
    "analyst",
    "management",
    "unknown",
    "unidentified speaker",
    "unidentified analyst",
    "participant",
}
_BAD_SPEAKER_LABELS = {
    "greetings",
    "hello",
    "hi",
    "thanks",
    "thank you",
    "good afternoon",
    "good morning",
}
_COMPANY_TOKEN_STOPWORDS = {
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "company",
    "co",
    "class",
    "common",
    "stock",
    "holding",
    "holdings",
    "group",
    "global",
    "limited",
    "ltd",
    "plc",
    "sa",
    "nv",
    "the",
    "and",
    "of",
}
_TRANSCRIPT_HEADING_PATTERN = re.compile(
    r"^(full conference call transcript|prepared remarks|questions and answers|q&a)\s*[:\-–—]?\s*$",
    flags=re.IGNORECASE,
)

_PARTICIPANT_STOP_MARKERS = {
    "takeaways",
    "risks",
    "summary",
    "industry glossary",
    "full conference call transcript",
}

_REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
}


def _build_openai_http_session() -> requests.Session:
    transport_retries = max(0, DEFAULT_OPENAI_TRANSPORT_RETRIES)
    retry = Retry(
        total=transport_retries,
        connect=transport_retries,
        read=transport_retries,
        backoff_factor=0.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["POST"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=16, pool_maxsize=16)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_OPENAI_HTTP_SESSION = _build_openai_http_session()


@dataclass(frozen=True)
class MotleyTranscriptCandidate:
    title: str
    url: str
    published_date: str
    source: str
    year: Optional[int]
    quarter: Optional[int]
    quality_score: float


class TranscriptExtractionError(RuntimeError):
    def __init__(self, message: str, *, scrape_method: str, diagnostics: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.scrape_method = scrape_method
        self.diagnostics = diagnostics or {}


def _normalize_ticker(ticker: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9.-]", "", ticker.strip().upper())
    return cleaned


def _safe_filename_component(value: str, fallback: str = "item", max_len: int = 80) -> str:
    raw = re.sub(r"[^A-Za-z0-9._-]+", "-", (value or "").strip())
    raw = raw.strip("-._")
    if not raw:
        raw = fallback
    return raw[:max_len]


def _build_scrape_cache_key(ticker: str, quarter: str, url: str) -> str:
    normalized = _normalize_url(url) or url
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return f"{_normalize_ticker(ticker)}::{quarter or 'unknown'}::{digest}"


def _resolve_scrape_cache_path(cache_dir: str, ticker: str, quarter: str, url: str, published_date: str) -> Path:
    root = Path(cache_dir)
    symbol = _normalize_ticker(ticker) or "UNKNOWN"
    quarter_safe = _safe_filename_component(quarter or "unknown-quarter", fallback="unknown-quarter")
    date_safe = _safe_filename_component(published_date or "unknown-date", fallback="unknown-date")
    slug = _safe_filename_component(urlparse(url).path.rstrip("/").split("/")[-1], fallback="transcript")
    key = _build_scrape_cache_key(symbol, quarter, url).split("::")[-1]
    filename = f"{symbol}_{quarter_safe}_{date_safe}_{slug}_{key}.json"
    return root / symbol / filename


def _build_debug_artifact_root(debug_dir: str, ticker: str, quarter: str, url: str, published_date: str) -> Path:
    root = Path(debug_dir)
    symbol = _normalize_ticker(ticker) or "UNKNOWN"
    quarter_safe = _safe_filename_component(quarter or "unknown-quarter", fallback="unknown-quarter")
    date_safe = _safe_filename_component(published_date or "unknown-date", fallback="unknown-date")
    slug = _safe_filename_component(urlparse(url).path.rstrip("/").split("/")[-1], fallback="transcript")
    key = _build_scrape_cache_key(symbol, quarter, url).split("::")[-1]
    return root / symbol / f"{symbol}_{quarter_safe}_{date_safe}_{slug}_{key}"


def _write_debug_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_debug_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _looks_like_plausible_speaker_label(label: str) -> bool:
    cleaned = re.sub(r"\s+", " ", str(label or "").strip())
    if not cleaned:
        return False
    lowered = cleaned.lower()
    if lowered in _GENERIC_SPEAKER_LABELS:
        return True
    if lowered in _BAD_SPEAKER_LABELS:
        return False
    if any(ch.isdigit() for ch in cleaned):
        return False
    if len(cleaned) > 80:
        return False
    if ":" in cleaned:
        return False
    if _PLAUSIBLE_PERSON_NAME_PATTERN.fullmatch(cleaned):
        return True
    return False


def _sanitize_section_role(value: str) -> Optional[str]:
    role = str(value or "").strip().lower()
    if not role:
        return None
    if role in {"operator", "analyst", "management"}:
        return role
    return None


def _default_logger(message: str) -> None:
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"[openai-motley-search {timestamp}] {message}", file=sys.stderr, flush=True)


def _speaker_line_match(line: str) -> Optional[tuple[str, str]]:
    match = _SPEAKER_LINE_PATTERN.match(line.strip())
    if not match:
        return None
    speaker = re.sub(r"\s+", " ", match.group(1)).strip()
    spoken = match.group(2).strip()
    if len(spoken) < 2:
        return None
    return speaker, spoken


def _is_transcript_heading_line(line: str) -> Optional[str]:
    normalized = re.sub(r"\s+", " ", line.strip())
    if not normalized:
        return None
    match = _TRANSCRIPT_HEADING_PATTERN.match(normalized)
    if not match:
        return None
    return match.group(1).lower()


def _guess_speaker_role(speaker: str) -> Optional[str]:
    lowered = speaker.lower()
    if "operator" in lowered:
        return "operator"
    if "analyst" in lowered:
        return "analyst"
    if any(token in lowered for token in ("ceo", "cfo", "chief", "president", "investor relations")):
        return "management"
    return None


def _detect_section_type(line: str, current: str) -> str:
    heading = _is_transcript_heading_line(line)
    if heading in {"questions and answers", "q&a"}:
        return "qa"
    if heading == "prepared remarks":
        return "prepared_remarks"
    return current


def _extract_text_lines(container: BeautifulSoup) -> list[str]:
    lines: list[str] = []
    for node in container.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        text = node.get_text(" ", strip=True)
        if not text:
            continue
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            lines.append(text)

    compact: list[str] = []
    last = ""
    for line in lines:
        if line == last:
            continue
        compact.append(line)
        last = line
    return compact


def _extract_article_body_from_jsonld(soup: BeautifulSoup) -> list[str]:
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except Exception:
            continue

        candidates: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            candidates = [payload]
        elif isinstance(payload, list):
            candidates = [item for item in payload if isinstance(item, dict)]

        for node in candidates:
            article_body = node.get("articleBody")
            if not isinstance(article_body, str) or not article_body.strip():
                continue
            lines = [line.strip() for line in article_body.splitlines() if line.strip()]
            if lines:
                return lines
    return []


def _extract_text_lines_relaxed(container: BeautifulSoup) -> list[str]:
    text = container.get_text("\n", strip=True)
    if not text:
        return []
    lines: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)

    compact: list[str] = []
    seen: set[str] = set()
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        compact.append(line)
    return compact


def _decode_unicode_escapes(value: str) -> str:
    def _replace(match: re.Match[str]) -> str:
        try:
            return chr(int(match.group(1), 16))
        except Exception:
            return match.group(0)

    return re.sub(r"\\u([0-9a-fA-F]{4})", _replace, value)


def _decode_script_blob(raw: str) -> str:
    text = raw
    text = text.replace("\\n", "\n").replace("\\r", "\n").replace("\\t", " ")
    text = text.replace("\\/", "/")
    text = _decode_unicode_escapes(text)
    text = html_lib.unescape(text)
    return text


def _extract_text_lines_from_script_payloads(soup: BeautifulSoup) -> list[str]:
    def _collect_string_values(node: Any) -> list[str]:
        values: list[str] = []
        if isinstance(node, str):
            values.append(node)
        elif isinstance(node, list):
            for item in node:
                values.extend(_collect_string_values(item))
        elif isinstance(node, dict):
            for value in node.values():
                values.extend(_collect_string_values(value))
        return values

    collected: list[str] = []
    for script in soup.find_all("script"):
        raw = script.string or script.get_text(" ", strip=False)
        if not raw:
            continue
        if "Full Conference Call Transcript" not in raw and "Call participants" not in raw:
            continue

        decoded = _decode_script_blob(raw)

        parsed_json: Any = None
        try:
            parsed_json = json.loads(raw)
        except Exception:
            parsed_json = None

        text_blobs: list[str] = []
        if parsed_json is not None:
            text_blobs.extend(_collect_string_values(parsed_json))
        text_blobs.append(decoded)

        for blob in text_blobs:
            decoded_blob = _decode_script_blob(blob)
            text = BeautifulSoup(decoded_blob, "html.parser").get_text("\n", strip=True)
            if not text:
                continue
            for line_raw in text.splitlines():
                line = re.sub(r"\s+", " ", line_raw).strip()
                if line:
                    collected.append(line)

    compact: list[str] = []
    seen: set[str] = set()
    for line in collected:
        if line in seen:
            continue
        seen.add(line)
        compact.append(line)
    return compact


def _split_name_role(left: str, right: str) -> tuple[str, str]:
    role_tokens = {"officer", "director", "president", "chief", "ceo", "cfo", "investor relations"}
    left_l = left.lower()
    right_l = right.lower()

    left_looks_role = any(token in left_l for token in role_tokens)
    right_looks_role = any(token in right_l for token in role_tokens)

    if left_looks_role and not right_looks_role:
        return right, left
    return left, right


def _extract_participants_from_lines(lines: list[str]) -> list[dict[str, str]]:
    start_idx = None
    for i, line in enumerate(lines):
        if line.lower().strip() == "call participants":
            start_idx = i + 1
            break
    if start_idx is None:
        return []

    out: list[dict[str, str]] = []
    for line in lines[start_idx : start_idx + 60]:
        lowered = line.lower().strip()
        if lowered in _PARTICIPANT_STOP_MARKERS:
            break
        if len(line) < 3:
            continue

        cleaned = line.strip("• ").strip()
        if not cleaned:
            continue

        left = ""
        right = ""
        if "—" in cleaned:
            left, right = [part.strip() for part in cleaned.split("—", 1)]
        elif " - " in cleaned:
            left, right = [part.strip() for part in cleaned.split(" - ", 1)]
        elif "," in cleaned:
            left, right = [part.strip() for part in cleaned.split(",", 1)]

        if left and right:
            name, role = _split_name_role(left, right)
        else:
            name, role = cleaned, ""

        if not name:
            continue
        out.append({"name": name, "role": role})

    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in out:
        key = f"{item.get('name', '').lower()}::{item.get('role', '').lower()}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:30]


def _find_repeated_speaker_start(lines: list[str], window: int = 25) -> Optional[int]:
    speaker_points: list[tuple[int, str]] = []
    for idx, line in enumerate(lines):
        match = _speaker_line_match(line)
        if not match:
            continue
        speaker_points.append((idx, match[0]))

    if len(speaker_points) < 2:
        return None

    for idx, _ in speaker_points:
        in_window = [(i, name) for i, name in speaker_points if idx <= i <= idx + window]
        if len(in_window) < 2:
            continue
        names = {name for _, name in in_window}
        if len(names) >= 2:
            return idx
    return None


def _extract_transcript_lines_with_diagnostics(lines: list[str]) -> tuple[list[str], dict[str, Any]]:
    start_idx = None
    start_marker = None
    start_reason = None
    for i, line in enumerate(lines):
        marker = _is_transcript_heading_line(line)
        if marker:
            start_idx = i + (1 if marker == "full conference call transcript" else 0)
            start_marker = marker
            start_reason = "marker"
            break

    if start_idx is None:
        repeated_idx = _find_repeated_speaker_start(lines)
        if repeated_idx is not None:
            start_idx = repeated_idx
            start_reason = "repeated_speaker"

    if start_idx is None:
        for i, line in enumerate(lines):
            if _speaker_line_match(line):
                start_idx = i
                start_reason = "single_speaker_fallback"
                break

    if start_idx is None:
        return [], {
            "start_found": False,
            "start_reason": "not_found",
            "start_marker": None,
            "start_index": None,
            "stop_marker": None,
            "stop_index": None,
            "source_line_count": len(lines),
            "transcript_line_count": 0,
        }

    stop_idx = len(lines)
    stop_marker = None
    for i in range(start_idx + 1, len(lines)):
        lowered = lines[i].lower()
        marker = next((m for m in _TRANSCRIPT_END_MARKERS if m in lowered), None)
        if marker:
            stop_idx = i
            stop_marker = marker
            break

    transcript_lines = lines[start_idx:stop_idx]
    return transcript_lines, {
        "start_found": True,
        "start_reason": start_reason,
        "start_marker": start_marker,
        "start_index": start_idx,
        "stop_marker": stop_marker,
        "stop_index": stop_idx if stop_marker else None,
        "source_line_count": len(lines),
        "transcript_line_count": len(transcript_lines),
    }


def _extract_transcript_lines(lines: list[str]) -> list[str]:
    transcript_lines, _ = _extract_transcript_lines_with_diagnostics(lines)
    return transcript_lines


def _build_speaker_sections(transcript_lines: list[str]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    section_type = "other"
    order_idx = 0

    current_speaker: Optional[str] = None
    current_role: Optional[str] = None
    current_type = section_type
    current_buffer: list[str] = []

    def flush_current() -> None:
        nonlocal order_idx, current_speaker, current_role, current_type, current_buffer
        if not current_speaker or not current_buffer:
            return
        text = " ".join(current_buffer).strip()
        if not text:
            return
        sections.append(
            {
                "speaker": current_speaker,
                "speaker_role": current_role,
                "section_type": current_type,
                "order_index": order_idx,
                "text": text,
            }
        )
        order_idx += 1
        current_speaker = None
        current_role = None
        current_buffer = []

    for line in transcript_lines:
        section_type = _detect_section_type(line, section_type)
        match = _speaker_line_match(line)
        if match:
            flush_current()
            current_speaker = match[0]
            current_role = _guess_speaker_role(current_speaker)
            current_type = section_type
            current_buffer = [match[1]]
            continue

        if current_speaker:
            current_buffer.append(line)

    flush_current()

    if not sections and transcript_lines:
        sections.append(
            {
                "speaker": "unknown",
                "speaker_role": None,
                "section_type": "other",
                "order_index": 0,
                "text": " ".join(transcript_lines[:300]),
            }
        )

    return sections


def _looks_like_operator_question_transition(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _QA_TRANSITION_MARKERS)


def _looks_like_analyst_question(text: str) -> bool:
    lowered = text.lower()
    if "?" in text:
        return True
    return any(marker in lowered for marker in _ANALYST_QUESTION_HINTS)


def _extract_management_participant_names(participants: list[dict[str, str]]) -> set[str]:
    management_role_tokens = (
        "chief",
        "ceo",
        "cfo",
        "president",
        "investor relations",
        "director",
        "vice president",
        "vp",
    )
    management_names: set[str] = set()
    for item in participants:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        role = str(item.get("role") or "").strip().lower()
        if not name or not role:
            continue
        if any(token in role for token in management_role_tokens):
            management_names.add(name.lower())
    return management_names


def _infer_qa_start_index(sections: list[dict[str, Any]]) -> Optional[int]:
    for idx, section in enumerate(sections):
        speaker = str(section.get("speaker") or "").strip().lower()
        role = _sanitize_section_role(section.get("speaker_role"))
        text = str(section.get("text") or "").strip()
        lowered = text.lower()

        if "questions and answers" in lowered or re.search(r"\bq\s*&\s*a\b", lowered):
            return idx
        if (speaker == "operator" or role == "operator") and _looks_like_operator_question_transition(text):
            return idx

    for idx, section in enumerate(sections):
        speaker = str(section.get("speaker") or "").strip().lower()
        if not speaker or speaker in {"unknown", "operator"}:
            continue
        text = str(section.get("text") or "").strip()
        if idx >= 2 and _looks_like_analyst_question(text):
            return max(0, idx - 1)

    return None


def _enrich_speaker_sections(
    sections: list[dict[str, Any]],
    *,
    participants: Optional[list[dict[str, str]]] = None,
) -> list[dict[str, Any]]:
    if not sections:
        return sections

    enriched = [dict(section) for section in sections]
    participants = participants or []
    management_names = _extract_management_participant_names(participants)
    qa_start = _infer_qa_start_index(enriched)

    # Speakers before the Q&A transition are almost always management on earnings calls.
    for idx, section in enumerate(enriched):
        if qa_start is not None and idx >= qa_start:
            break
        speaker = str(section.get("speaker") or "").strip()
        if not speaker:
            continue
        speaker_lower = speaker.lower()
        if speaker_lower in {"unknown", "operator"}:
            continue
        management_names.add(speaker_lower)

    if not management_names:
        for section in enriched:
            speaker = str(section.get("speaker") or "").strip()
            if not speaker:
                continue
            speaker_lower = speaker.lower()
            if speaker_lower in {"unknown", "operator"}:
                continue
            management_names.add(speaker_lower)
            if len(management_names) >= 2:
                break

    for idx, section in enumerate(enriched):
        speaker = str(section.get("speaker") or "").strip()
        speaker_lower = speaker.lower()
        text = str(section.get("text") or "").strip()

        role = _sanitize_section_role(section.get("speaker_role"))
        if role is None:
            inferred_role: Optional[str] = None
            if "operator" in speaker_lower:
                inferred_role = "operator"
            elif speaker_lower in management_names:
                inferred_role = "management"
            elif qa_start is not None and idx >= qa_start:
                if _looks_like_analyst_question(text):
                    inferred_role = "analyst"
                elif idx > 0:
                    prev_speaker = str(enriched[idx - 1].get("speaker") or "").strip().lower()
                    if prev_speaker == "operator":
                        inferred_role = "analyst"
            elif speaker_lower and speaker_lower not in {"unknown"}:
                inferred_role = "management"
            role = _sanitize_section_role(inferred_role)
        section["speaker_role"] = role

        section_type = str(section.get("section_type") or "other").strip().lower()
        if section_type not in _SECTION_TYPE_VALUES:
            section_type = "other"
        if section_type == "other":
            if qa_start is None:
                section_type = "prepared_remarks"
            else:
                section_type = "qa" if idx >= qa_start else "prepared_remarks"
        section["section_type"] = section_type

    return enriched


def _presentable_participant_role(role: Optional[str]) -> str:
    if role == "operator":
        return "Operator"
    if role == "analyst":
        return "Analyst"
    if role == "management":
        return "Management"
    return ""


def _merge_participants_with_speaker_sections(
    participants: list[dict[str, str]],
    sections: list[dict[str, Any]],
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    by_name: dict[str, int] = {}

    def upsert(name: str, role: str) -> None:
        clean_name = str(name or "").strip()
        clean_role = str(role or "").strip()
        if not clean_name:
            return
        key = clean_name.lower()
        if key in by_name:
            idx = by_name[key]
            if not merged[idx].get("role") and clean_role:
                merged[idx]["role"] = clean_role
            return
        by_name[key] = len(merged)
        merged.append({"name": clean_name, "role": clean_role})

    for item in participants:
        if not isinstance(item, dict):
            continue
        upsert(str(item.get("name") or ""), str(item.get("role") or ""))

    for section in sections:
        if not isinstance(section, dict):
            continue
        speaker = str(section.get("speaker") or "").strip()
        if not speaker or speaker.lower() == "unknown":
            continue
        role = _presentable_participant_role(_sanitize_section_role(section.get("speaker_role")))
        upsert(speaker, role)

    return merged


def _extract_line_sources(
    *,
    raw_soup: BeautifulSoup,
    sanitized_soup: BeautifulSoup,
) -> list[tuple[str, list[str]]]:
    container = (
        sanitized_soup.select_one("article")
        or sanitized_soup.select_one("main")
        or sanitized_soup.select_one("div[class*='article']")
        or sanitized_soup.body
    )
    if container is None:
        return []

    sources: list[tuple[str, list[str]]] = []
    sources.append(("semantic_dom", _extract_text_lines(container)))
    sources.append(("jsonld_article_body", _extract_article_body_from_jsonld(raw_soup)))
    sources.append(("script_payload", _extract_text_lines_from_script_payloads(raw_soup)))
    if sanitized_soup.body is not None:
        sources.append(("relaxed_body", _extract_text_lines_relaxed(sanitized_soup.body)))
    return sources


def _parse_transcript_from_html(
    *,
    html: str,
    scrape_method: str,
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _: None)
    raw_soup = BeautifulSoup(html, "html.parser")
    sanitized_soup = BeautifulSoup(html, "html.parser")
    for node in sanitized_soup(["script", "style", "noscript", "svg", "button", "form", "header", "footer", "nav"]):
        node.decompose()

    line_sources = _extract_line_sources(raw_soup=raw_soup, sanitized_soup=sanitized_soup)
    if not line_sources:
        raise TranscriptExtractionError(
            "No content container found for transcript page.",
            scrape_method=scrape_method,
            diagnostics={"line_sources": []},
        )

    attempts: list[dict[str, Any]] = []
    had_any_lines = False

    for source_name, lines in line_sources:
        log(f"scrape: {scrape_method} source '{source_name}' yielded {len(lines)} lines")
        marker_detection = {
            "start_found": False,
            "start_reason": "not_checked",
            "start_marker": None,
            "start_index": None,
            "stop_marker": None,
            "stop_index": None,
            "source_line_count": len(lines),
            "transcript_line_count": 0,
        }
        if lines:
            had_any_lines = True
            transcript_lines, marker_detection = _extract_transcript_lines_with_diagnostics(lines)
            if transcript_lines:
                participants = _extract_participants_from_lines(lines)
                speaker_sections = _build_speaker_sections(transcript_lines)
                speaker_sections = _enrich_speaker_sections(speaker_sections, participants=participants)
                participants = _merge_participants_with_speaker_sections(participants, speaker_sections)
                speaker_names = [section["speaker"] for section in speaker_sections if section.get("speaker")]
                speaker_unique = sorted({name for name in speaker_names if name})
                return {
                    "participants": participants,
                    "speaker_sections": speaker_sections,
                    "speaker_count": len(speaker_unique),
                    "speakers": speaker_unique,
                    "section_count": len(speaker_sections),
                    "transcript_line_count": len(transcript_lines),
                    "transcript_char_count": len("\n".join(transcript_lines)),
                    "scrape_method": scrape_method,
                    "line_source": source_name,
                    "marker_detection": {**marker_detection, "line_source": source_name},
                    "line_count": {
                        "source_line_count": len(lines),
                        "transcript_line_count": len(transcript_lines),
                    },
                    "section_parse_method": "regex",
                    "raw_text": "\n".join(transcript_lines),
                }

        attempts.append(
            {
                "line_source": source_name,
                "line_count": len(lines),
                "marker_detection": marker_detection,
            }
        )

    if not had_any_lines:
        raise TranscriptExtractionError(
            "No text lines found in transcript page.",
            scrape_method=scrape_method,
            diagnostics={"line_sources": attempts},
        )

    raise TranscriptExtractionError(
        "Transcript section markers were not found on page.",
        scrape_method=scrape_method,
        diagnostics={"line_sources": attempts},
    )


def _render_playwright_snapshot(url: str, timeout_seconds: int) -> tuple[str, str]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - environment-dependent
        raise RuntimeError(
            "Playwright is not installed. Install optional browser fallback with "
            "`pip install playwright` and `python -m playwright install chromium`."
        ) from exc

    try:  # pragma: no cover - browser runtime is environment-dependent
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=_REQUEST_HEADERS["User-Agent"])
            page.goto(url, wait_until="domcontentloaded", timeout=int(timeout_seconds * 1000))
            page.wait_for_timeout(1500)
            html = page.content()
            visible_text = page.evaluate(
                """() => {
                    const selectors = [
                      '#article-body-transcript',
                      '[id*="transcript"]',
                      'article',
                      'main',
                    ];
                    for (const sel of selectors) {
                      const el = document.querySelector(sel);
                      if (el && el.innerText && el.innerText.trim().length > 200) {
                        return el.innerText;
                      }
                    }
                    return (document.body && document.body.innerText) ? document.body.innerText : '';
                }"""
            )
            browser.close()
            return html, str(visible_text or "")
    except Exception as exc:
        raise RuntimeError(f"Playwright render failed: {exc}") from exc


def _render_html_with_playwright(url: str, timeout_seconds: int) -> str:
    html, _ = _render_playwright_snapshot(url=url, timeout_seconds=timeout_seconds)
    return html


def _fetch_transcript_sections(
    *,
    url: str,
    ticker: str,
    quarter: str,
    title: str,
    published_date: str,
    timeout_seconds: int,
    openai_api_key: str = "",
    openai_model: str = DEFAULT_OPENAI_SEARCH_MODEL,
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL,
    openai_retry_attempts: int = DEFAULT_OPENAI_RETRY_ATTEMPTS,
    debug_openai_io: bool = False,
    debug_openai_io_max_chars: int = 2000,
    debug_openai_dir: str = "",
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _: None)
    log(f"scrape: fetching {url}")

    response = requests.get(url, headers=_REQUEST_HEADERS, timeout=timeout_seconds)
    response.raise_for_status()
    html = response.text

    browser_html: Optional[str] = None
    browser_visible_text: Optional[str] = None
    browser_error: Optional[str] = None
    try:
        browser_html, browser_visible_text = _render_playwright_snapshot(url=url, timeout_seconds=timeout_seconds)
        log("scrape: browser render captured for page text extraction")
    except Exception as exc:
        browser_error = str(exc)
        log(f"scrape: browser render unavailable ({exc}); continuing with static HTML text")

    source_input = _build_source_first_llm_input(
        static_html=html,
        browser_html=browser_html,
        browser_visible_text=browser_visible_text,
    )
    transcript_text = str(source_input.get("text") or "").strip()
    source_label = f"{source_input.get('input_source')}:{source_input.get('input_source_detail')}"
    scrape_method = "browser" if str(source_input.get("input_source") or "").startswith("browser") else "static"
    debug_artifact_root: Optional[Path] = None
    if debug_openai_dir:
        debug_artifact_root = _build_debug_artifact_root(
            debug_dir=debug_openai_dir,
            ticker=ticker,
            quarter=quarter,
            url=url,
            published_date=published_date,
        )
        try:
            _write_debug_text(debug_artifact_root / "page_source_selected_input.txt", transcript_text)
            _write_debug_json(debug_artifact_root / "page_source_input_diagnostics.json", source_input)
            if browser_error:
                _write_debug_text(debug_artifact_root / "browser_error.txt", browser_error)
            log(f"scrape: wrote debug page-input artifacts to {debug_artifact_root}")
        except Exception as exc:
            log(f"scrape: failed writing debug page-input artifacts ({exc})")

    if not transcript_text:
        message = "No transcript-like page text was extracted for OpenAI structuring."
        if browser_error:
            message = f"{message} Browser fallback unavailable: {browser_error}"
        error_scrape_method = "browser" if browser_error else scrape_method
        raise TranscriptExtractionError(
            message,
            scrape_method=error_scrape_method,
            diagnostics={
                "line_source": source_label,
                "llm_input_diagnostics": source_input,
                "browser_error": browser_error,
            },
        )

    log(
        "scrape: page text prepared "
        f"(source={source_label}, chars={source_input.get('input_char_count')}, "
        f"speaker_lines={source_input.get('input_speaker_line_count')})"
    )

    openai_error: Optional[str] = None
    if openai_api_key:
        try:
            log("scrape: structuring page text with OpenAI")
            structured = _structure_transcript_with_openai(
                api_key=openai_api_key,
                model=openai_model,
                base_url=openai_base_url,
                timeout_seconds=timeout_seconds,
                retry_attempts=max(openai_retry_attempts, 1),
                ticker=ticker,
                quarter=quarter,
                title=title,
                url=url,
                published_date=published_date,
                transcript_text=transcript_text,
                log_fn=log_fn,
                debug_io=debug_openai_io,
                debug_io_max_chars=debug_openai_io_max_chars,
                debug_artifact_root=debug_artifact_root,
            )
            return {
                "quarter": quarter,
                "title": title,
                "url": url,
                "published_date": published_date,
                **structured,
                "scrape_method": scrape_method,
                "line_source": source_label,
                "marker_detection": source_input.get("marker_detection") or {},
                "line_count": {
                    "source_line_count": int(source_input.get("input_line_count") or 0),
                    "transcript_line_count": int(structured.get("transcript_line_count") or 0),
                    "input_char_count": int(source_input.get("input_char_count") or 0),
                },
                "section_parse_method": "openai_page_text",
                "section_parse_reason": "page_text_structured_by_openai",
                "llm_input_diagnostics": source_input,
                "llm_input_preview": transcript_text[:2000],
            }
        except Exception as exc:
            openai_error = str(exc)
            log(f"scrape: OpenAI structuring failed ({exc}); trying regex fallback on extracted page text")

    parsed_from_text = _parse_speaker_sections_from_text(transcript_text)
    low_quality, low_quality_reason = _is_low_quality_speaker_parse(parsed_from_text)
    if low_quality:
        diagnostics: dict[str, Any] = {
            "low_quality_reason": low_quality_reason,
            "line_source": source_label,
            "line_count": parsed_from_text.get("line_count"),
            "marker_detection": parsed_from_text.get("marker_detection"),
            "llm_input_diagnostics": source_input,
            "llm_input_preview": transcript_text[:2000],
        }
        if openai_error:
            diagnostics["openai_error"] = openai_error
        if browser_error:
            diagnostics["browser_error"] = browser_error
        message = "Unable to produce high-quality speaker sections from page text."
        if browser_error:
            message = f"{message} Browser fallback unavailable: {browser_error}"
        error_scrape_method = "browser" if browser_error else scrape_method
        raise TranscriptExtractionError(
            message,
            scrape_method=error_scrape_method,
            diagnostics=diagnostics,
        )

    parsed_from_text["section_parse_reason"] = (
        "openai_unavailable_or_failed" if openai_error else "openai_not_requested"
    )
    return {
        "quarter": quarter,
        "title": title,
        "url": url,
        "published_date": published_date,
        **parsed_from_text,
        "scrape_method": scrape_method,
        "line_source": source_label,
        "line_count": {
            **(parsed_from_text.get("line_count") or {}),
            "input_char_count": int(source_input.get("input_char_count") or 0),
        },
        "llm_input_diagnostics": source_input,
        "llm_input_preview": transcript_text[:2000],
    }


def _select_most_recent_candidates(report: dict[str, Any], count: int) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    seen: set[str] = set()
    target_count = max(count, 1)

    found_links = report.get("found_transcript_links")
    if isinstance(found_links, list):
        for row in found_links:
            if not isinstance(row, dict):
                continue
            url = str(row.get("url") or "").strip()
            if not url:
                continue
            normalized = _normalize_url(url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            selected.append(
                {
                    "quarter": str(row.get("quarter") or ""),
                    "title": str(row.get("title") or ""),
                    "url": normalized,
                    "published_date": str(row.get("published_date") or _date_from_motley_url(normalized)),
                }
            )
            if len(selected) >= target_count:
                return selected

    # Only fallback to candidate_pool if no quarter-resolved links were found.
    if selected:
        return selected

    pool = report.get("candidate_pool")
    if not isinstance(pool, list):
        return selected

    for row in pool:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        normalized = _normalize_url(url)
        if not normalized or normalized in seen:
            continue
        quality_raw = row.get("quality_score")
        quality = float(quality_raw) if isinstance(quality_raw, (int, float)) else 10.0
        if isinstance(quality_raw, (int, float)) and quality < 8.0:
            continue
        seen.add(normalized)
        selected.append(
            {
                "quarter": str(row.get("quarter") or ""),
                "title": str(row.get("title") or ""),
                "url": normalized,
                "published_date": str(row.get("published_date") or _date_from_motley_url(normalized)),
            }
        )
        if len(selected) >= target_count:
            break
    return selected


def _quarter_from_month(month: int) -> int:
    return ((month - 1) // 3) + 1


def _quarter_label(year: int, quarter: int) -> str:
    return f"{year}-Q{quarter}"


def _decrement_quarter(year: int, quarter: int) -> tuple[int, int]:
    if quarter > 1:
        return year, quarter - 1
    return year - 1, 4


def _quarter_window(anchor_year: int, anchor_quarter: int, count: int) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    year = anchor_year
    quarter = anchor_quarter
    for _ in range(max(0, count)):
        out.append((year, quarter))
        year, quarter = _decrement_quarter(year, quarter)
    return out


def _safe_parse_date(raw: str) -> Optional[datetime]:
    if not raw:
        return None

    value = raw.strip()
    if not value:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            parsed = datetime.strptime(value, fmt)
            if parsed.tzinfo is not None:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
    except ValueError:
        return None


def _date_from_motley_url(url: str) -> str:
    match = _URL_DATE_PATTERN.search(url)
    if not match:
        return ""
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def infer_year_quarter(title: str, url: str, published_date: str) -> tuple[Optional[int], Optional[int]]:
    for pattern in _TITLE_QUARTER_PATTERNS:
        match = pattern.search(title)
        if not match:
            continue
        if pattern is _TITLE_QUARTER_PATTERNS[0]:
            quarter = int(match.group(1))
            year = int(match.group(2))
        else:
            year = int(match.group(1))
            quarter = int(match.group(2))
        return year, quarter

    slug_match = _URL_QUARTER_PATTERN.search(url)
    if slug_match:
        quarter = int(slug_match.group(1))
        year = int(slug_match.group(2))
        return year, quarter

    date_guess = _safe_parse_date(published_date or _date_from_motley_url(url))
    if date_guess is not None:
        return date_guess.year, _quarter_from_month(date_guess.month)

    return None, None


def _normalize_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""

    if raw.startswith("/"):
        raw = f"https://www.fool.com{raw}"
    elif raw.startswith("//"):
        raw = f"https:{raw}"
    elif raw.startswith("http://"):
        raw = "https://" + raw[len("http://") :]

    parsed = urlparse(raw)
    if not parsed.scheme or not parsed.netloc:
        return ""

    path = parsed.path or "/"
    if not path.endswith("/"):
        path = f"{path}/"
    sanitized = parsed._replace(query="", fragment="", path=path)
    return urlunparse(sanitized)


def _is_motley_transcript_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower().strip()
    if host.startswith("www."):
        host = host[4:]
    if host != "fool.com":
        return False
    return "/earnings/call-transcripts/" in parsed.path.lower()


def _candidate_has_explicit_ticker(ticker: str, title: str, url: str) -> bool:
    ticker_upper = ticker.upper()
    ticker_lower = ticker.lower()
    title_upper = title.upper()
    url_lower = url.lower()
    return bool(
        re.search(rf"\({re.escape(ticker_upper)}\)", title_upper)
        or re.search(rf"\b{re.escape(ticker_upper)}\b", title_upper)
        or f"-{ticker_lower}-" in url_lower
    )


def _extract_company_tokens_from_candidate(ticker: str, title: str, url: str) -> set[str]:
    ticker_lower = ticker.lower()
    tokens: set[str] = set()

    slug = urlparse(url).path.rstrip("/").split("/")[-1].replace(".aspx", "")
    slug_parts = [part.lower() for part in slug.split("-") if part]
    for part in slug_parts:
        if part == ticker_lower:
            continue
        if part in {"earnings", "call", "transcript", "conference"}:
            break
        if re.fullmatch(r"q[1-4]", part):
            break
        if re.fullmatch(r"20\d{2}", part):
            break
        if not re.fullmatch(r"[a-z]{3,}", part):
            continue
        if part in _COMPANY_TOKEN_STOPWORDS:
            continue
        tokens.add(part)

    for part in re.findall(r"[A-Za-z]{3,}", title.lower()):
        if part == ticker_lower:
            continue
        if part in _COMPANY_TOKEN_STOPWORDS:
            continue
        if part in {"earnings", "call", "transcript", "conference"}:
            continue
        tokens.add(part)
        if len(tokens) >= 8:
            break

    return tokens


def _candidate_matches_company_tokens(title: str, url: str, company_tokens: set[str]) -> bool:
    if not company_tokens:
        return False
    title_lower = title.lower()
    url_lower = url.lower()
    for token in company_tokens:
        if re.search(rf"\b{re.escape(token)}\b", title_lower):
            return True
        if re.search(rf"(^|[-/]){re.escape(token)}($|[-/.])", url_lower):
            return True
    return False


def _score_candidate(ticker: str, title: str, url: str) -> float:
    title_upper = title.upper()
    title_lower = title.lower()
    ticker_upper = ticker.upper()
    ticker_lower = ticker.lower()

    score = 0.0
    if re.search(rf"\({re.escape(ticker_upper)}\)", title_upper):
        score += 8.0
    if re.search(rf"\b{re.escape(ticker_upper)}\b", title_upper):
        score += 4.0
    if f"-{ticker_lower}-" in url.lower():
        score += 4.0
    if "earnings call transcript" in title_lower:
        score += 2.0
    elif "earnings transcript" in title_lower:
        score += 1.0

    return score


def _build_response_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "ticker": {"type": "string"},
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "url": {"type": "string"},
                        "published_date": {"type": "string"},
                        "source": {"type": "string"},
                    },
                    "required": ["title", "url", "published_date", "source"],
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["ticker", "candidates", "notes"],
    }


def _build_transcript_structure_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "participants": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                    },
                    "required": ["name", "role"],
                },
            },
            "speaker_sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "speaker": {"type": "string"},
                        "speaker_role": {"type": "string"},
                        "section_type": {"type": "string"},
                        "order_index": {"type": "integer"},
                        "text": {"type": "string"},
                    },
                    "required": ["speaker", "speaker_role", "section_type", "order_index", "text"],
                },
            },
            "notes": {"type": "string"},
        },
        "required": ["participants", "speaker_sections", "notes"],
    }


def _build_search_prompt(ticker: str, max_candidates: int) -> str:
    return (
        "Use web search to find Motley Fool earnings call transcript pages for the stock ticker "
        f"{ticker}.\n"
        "Focus on URLs under /earnings/call-transcripts/ on www.fool.com.\n"
        f"Find at least {max_candidates} likely transcript pages if available, newest first.\n"
        "The tool sources are the main output we will parse."
    )


def _build_transcript_structure_prompt(
    *,
    ticker: str,
    quarter: str,
    title: str,
    url: str,
    published_date: str,
    transcript_text: str,
    segment_index: int = 0,
    segment_count: int = 1,
) -> str:
    segment_header = ""
    if segment_count > 1:
        segment_header = (
            f"Segment: {segment_index + 1} of {segment_count}.\n"
            "Return sections only for this segment.\n"
            "order_index should start at 0 for this segment.\n"
        )
    return (
        "Convert the provided earnings-call transcript content into structured JSON with speaker-by-speaker sections.\n"
        "Do not summarize. Preserve what each speaker said as faithfully as possible.\n"
        "Treat each `Speaker: ...` switch in the input as a hard boundary for speaker_sections.\n"
        "Do not merge multiple speakers into one section.\n"
        "Each time the transcript switches speakers, create a new speaker_sections item.\n"
        "If text includes escaped JSON/Next.js script wrappers, recover the human-readable transcript first.\n"
        "Use section_type values: prepared_remarks, qa, or other.\n"
        "Each speaker_sections.text value should contain only what that speaker said in this segment.\n"
        "Never return an empty speaker_sections array unless the segment truly has no speaker lines.\n\n"
        f"{segment_header}"
        f"Ticker: {ticker}\n"
        f"Quarter: {quarter}\n"
        f"Title: {title}\n"
        f"Published Date: {published_date}\n"
        f"URL: {url}\n\n"
        "Transcript Content:\n"
        f"{transcript_text}"
    )


def _build_tool(tool_type: str) -> dict[str, Any]:
    if tool_type == "web_search":
        return {
            "type": "web_search",
            "search_context_size": "high",
            "filters": {
                "allowed_domains": ["www.fool.com"],
            },
            "user_location": {
                "type": "approximate",
                "country": "US",
            },
        }
    if tool_type == "web_search_preview":
        return {
            "type": "web_search_preview",
            "search_context_size": "high",
            "user_location": {
                "type": "approximate",
                "country": "US",
            },
        }
    raise ValueError(f"Unsupported web-search tool type: {tool_type}")


def _build_request_payload(
    *,
    model: str,
    ticker: str,
    max_candidates: int,
    tool_type: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "max_output_tokens": 800,
        "tool_choice": "required",
        "input": _build_search_prompt(ticker=ticker, max_candidates=max_candidates),
        "tools": [_build_tool(tool_type)],
        "include": ["web_search_call.action.sources"],
    }


def _extract_error_message(response: requests.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text.strip() or f"HTTP {response.status_code}"

    error = payload.get("error")
    if isinstance(error, dict):
        msg = str(error.get("message") or "").strip()
        if msg:
            return msg

    return json.dumps(payload)[:400]


def _openai_post_responses(
    *,
    base_url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_seconds: int,
) -> requests.Response:
    read_timeout = min(float(timeout_seconds), DEFAULT_OPENAI_READ_TIMEOUT_CAP_SECONDS)
    if read_timeout <= 0:
        read_timeout = DEFAULT_OPENAI_READ_TIMEOUT_CAP_SECONDS

    response = _OPENAI_HTTP_SESSION.post(
        f"{base_url.rstrip('/')}/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Connection": "close",
        },
        json=payload,
        timeout=(DEFAULT_OPENAI_CONNECT_TIMEOUT_SECONDS, read_timeout),
    )
    return response


def _extract_structured_output(response_payload: dict[str, Any]) -> dict[str, Any]:
    def _parse_text_blob(blob: str) -> dict[str, Any]:
        text = blob.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?", "", text).strip()
            text = re.sub(r"```$", "", text).strip()
        return json.loads(text)

    parsed = response_payload.get("output_parsed")
    if isinstance(parsed, dict):
        return parsed

    output_text = response_payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return _parse_text_blob(output_text)

    for output_item in response_payload.get("output", []) or []:
        if not isinstance(output_item, dict):
            continue
        content = output_item.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            text_value = block.get("text")
            if isinstance(text_value, str) and text_value.strip():
                return _parse_text_blob(text_value)
            if isinstance(text_value, dict):
                maybe = text_value.get("value") or text_value.get("text")
                if isinstance(maybe, str) and maybe.strip():
                    return _parse_text_blob(maybe)

    raise RuntimeError("OpenAI response did not include parseable structured JSON output.")


def _is_retryable_openai_request_error(exc: Exception) -> bool:
    message = str(exc).lower()
    non_retry_connectivity_markers = (
        "failed to establish a new connection",
        "nodename nor servname provided",
        "name or service not known",
        "temporary failure in name resolution",
        "no route to host",
    )
    if any(marker in message for marker in non_retry_connectivity_markers):
        return False
    return True


def _is_retryable_openai_structuring_error(exc: Exception) -> bool:
    if not _is_retryable_openai_request_error(exc):
        return False
    if isinstance(exc, json.JSONDecodeError):
        return False

    message = str(exc).lower()
    non_retry_markers = (
        "unterminated string",
        "expecting value",
        "expecting property name enclosed in double quotes",
        "extra data",
        "parseable structured json output",
    )
    if any(marker in message for marker in non_retry_markers):
        return False

    return True


def _candidate_title_from_url(url: str, ticker: str) -> str:
    parsed = urlparse(url)
    slug = parsed.path.rstrip("/").split("/")[-1]
    slug = slug.replace(".aspx", "")
    if not slug:
        return f"{ticker} Earnings Call Transcript"

    words = [w for w in slug.split("-") if w]
    if not words:
        return f"{ticker} Earnings Call Transcript"

    title_words: list[str] = []
    for word in words:
        upper = word.upper()
        if re.fullmatch(r"q[1-4]", word, flags=re.IGNORECASE):
            title_words.append(upper)
        elif re.fullmatch(r"20\d{2}", word):
            title_words.append(word)
        elif word.lower() == ticker.lower():
            title_words.append(ticker.upper())
        else:
            title_words.append(word.capitalize())

    title = " ".join(title_words)
    if "earnings call transcript" not in title.lower():
        title = f"{title} Earnings Call Transcript".strip()
    return title


def _fallback_candidates_from_sources(
    *,
    ticker: str,
    response_payload: dict[str, Any],
    max_candidates: int,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for url in _extract_sources(response_payload):
        if not _is_motley_transcript_url(url):
            continue
        out.append(
            {
                "title": _candidate_title_from_url(url=url, ticker=ticker),
                "url": url,
                "published_date": _date_from_motley_url(url),
                "source": "web_search_source_fallback",
            }
        )
        if len(out) >= max_candidates:
            break
    return out


def _normalize_participants(raw_participants: Any) -> list[dict[str, str]]:
    if not isinstance(raw_participants, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw_participants:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        role = str(item.get("role") or "").strip()
        if not name:
            continue
        key = f"{name.lower()}::{role.lower()}"
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "role": role})
    return out


def _normalize_speaker_sections(raw_sections: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_sections, list):
        return []

    normalized: list[dict[str, Any]] = []
    for i, item in enumerate(raw_sections):
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or "").strip() or "unknown"
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        speaker_role_raw = item.get("speaker_role")
        speaker_role = _sanitize_section_role(speaker_role_raw) if isinstance(speaker_role_raw, str) else None
        section_type = str(item.get("section_type") or "other").strip().lower()
        if section_type not in _SECTION_TYPE_VALUES:
            section_type = "other"
        order_value = item.get("order_index")
        order_index = order_value if isinstance(order_value, int) else i

        normalized.append(
            {
                "speaker": speaker,
                "speaker_role": speaker_role,
                "section_type": section_type,
                "order_index": order_index,
                "text": text,
            }
        )

    normalized.sort(key=lambda row: row.get("order_index", 0))
    for idx, row in enumerate(normalized):
        row["order_index"] = idx
    return normalized


def _is_low_quality_speaker_parse(parsed: dict[str, Any]) -> tuple[bool, str]:
    sections = parsed.get("speaker_sections")
    if not isinstance(sections, list) or not sections:
        return True, "no_sections"

    unknown_sections = 0
    suspicious_content = False
    for section in sections:
        if not isinstance(section, dict):
            continue
        speaker = str(section.get("speaker") or "").strip().lower()
        if speaker in {"", "unknown"}:
            unknown_sections += 1
        text = str(section.get("text") or "")
        if "self.__next_f.push" in text or '\\"children\\":' in text or "\\u003c" in text:
            suspicious_content = True

    if suspicious_content:
        return True, "script_wrapped_text"
    if len(sections) == 1 and unknown_sections == 1:
        return True, "single_unknown_section"
    if unknown_sections == len(sections):
        return True, "all_unknown_speakers"
    return False, ""


def _extract_transcript_text_for_llm(parsed: dict[str, Any], max_chars: int = 50000) -> str:
    sections = parsed.get("speaker_sections")
    if isinstance(sections, list) and sections:
        joined = "\n\n".join(str(section.get("text") or "").strip() for section in sections if isinstance(section, dict))
    else:
        joined = ""
    text = joined.strip()
    if not text:
        text = str(parsed.get("raw_text") or "")
    if len(text) > max_chars:
        return text[:max_chars]
    return text


def _extract_focus_html_window(raw_html: str, window_size: int = 140000) -> str:
    if not raw_html:
        return ""
    lowered = raw_html.lower()
    focus_markers = (
        "article-body-transcript",
        "full conference call transcript",
        "call participants",
        "prepared remarks",
        "questions and answers",
    )
    for marker in focus_markers:
        idx = lowered.find(marker)
        if idx >= 0:
            start = max(0, idx - (window_size // 2))
            end = min(len(raw_html), idx + (window_size // 2))
            return raw_html[start:end]
    return raw_html[:window_size]


def _speaker_line_count(text: str, max_lines: int = 3000) -> int:
    count = 0
    for line in text.splitlines()[:max_lines]:
        if _speaker_line_match(line.strip()):
            count += 1
    return count


def _normalize_text_lines(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            out.append(line)
    return out


def _slice_transcript_like_text(text: str) -> tuple[str, bool, dict[str, Any]]:
    lines = _normalize_text_lines(text)
    if not lines:
        return "", False, {"start_found": False, "start_reason": "no_lines"}
    transcript_lines, marker = _extract_transcript_lines_with_diagnostics(lines)
    if transcript_lines and len(transcript_lines) >= 8:
        return "\n".join(transcript_lines), True, marker
    return "\n".join(lines), False, marker


def _score_llm_input_text(text: str) -> float:
    if not text:
        return 0.0
    lowered = text.lower()
    markers = 0
    for token in _TRANSCRIPT_START_MARKERS:
        if token in lowered:
            markers += 1
    if "call participants" in lowered:
        markers += 1
    speaker_lines = _speaker_line_count(text)
    score = float(speaker_lines * 10 + markers * 25 + min(len(text), 50000) / 5000.0)
    if "self.__next_f.push" in lowered:
        score -= 40.0
    if "\\u003c" in lowered:
        score -= 20.0
    nav_noise_tokens = (
        "all services",
        "best stocks to buy",
        "stock advisor",
        "retirement news",
        "best credit cards",
        "premium investing services",
    )
    nav_hits = sum(1 for token in nav_noise_tokens if token in lowered)
    score -= float(nav_hits * 8)
    return score


def _build_source_first_llm_input(
    *,
    static_html: str,
    browser_html: Optional[str] = None,
    browser_visible_text: Optional[str] = None,
    max_chars: int = DEFAULT_TRANSCRIPT_INPUT_MAX_CHARS,
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []

    def _candidate_from_html(source_label: str, html: str) -> None:
        soup = BeautifulSoup(html, "html.parser")
        article = soup.select_one("article") or soup.select_one("main")
        article_text = ""
        if article is not None:
            article_text = article.get_text("\n", strip=True)
        body_text = ""
        if soup.body is not None:
            body_text = soup.body.get_text("\n", strip=True)
        script_payload_text = "\n".join(_extract_text_lines_from_script_payloads(soup))

        sources = [("article_text", article_text), ("body_text", body_text), ("script_payload_text", script_payload_text)]
        transformed_sources: list[tuple[str, str, float, bool, dict[str, Any]]] = []
        for source_name, source_text in sources:
            sliced, slice_found, marker = _slice_transcript_like_text(source_text)
            score = _score_llm_input_text(sliced)
            if slice_found:
                score += 35.0
            transformed_sources.append((source_name, sliced, score, slice_found, marker))

        best_name, best_text, best_score, best_slice_found, best_marker = max(
            transformed_sources,
            key=lambda item: item[2],
        )

        merged = best_text.strip()[:max_chars]
        candidates.append(
            {
                "source": source_label,
                "best_source": best_name,
                "score": round(best_score, 3),
                "text": merged,
                "speaker_line_count": _speaker_line_count(merged),
                "char_count": len(merged),
                "line_count": len(merged.splitlines()),
                "transcript_slice_found": best_slice_found,
                "marker_detection": best_marker,
            }
        )

    _candidate_from_html("static_html", static_html)
    if browser_html:
        _candidate_from_html("browser_html", browser_html)
    if browser_visible_text and browser_visible_text.strip():
        visible_text = browser_visible_text.strip()
        visible_slice, visible_slice_found, marker = _slice_transcript_like_text(visible_text)
        candidate_text = visible_slice if visible_slice else visible_text
        visible_score = _score_llm_input_text(candidate_text)
        if visible_slice_found:
            visible_score += 80.0
        if _speaker_line_count(candidate_text) >= 8:
            visible_score += 40.0
        candidates.append(
            {
                "source": "browser_visible_text",
                "best_source": "inner_text",
                "score": round(visible_score, 3),
                "text": candidate_text[:max_chars],
                "speaker_line_count": _speaker_line_count(candidate_text),
                "char_count": min(len(candidate_text), max_chars),
                "line_count": len(candidate_text.splitlines()),
                "transcript_slice_found": visible_slice_found,
                "marker_detection": marker,
            }
        )

    chosen = max(candidates, key=lambda item: item["score"])
    return {
        "text": chosen["text"],
        "input_source": chosen["source"],
        "input_source_detail": chosen["best_source"],
        "input_char_count": chosen["char_count"],
        "input_speaker_line_count": chosen["speaker_line_count"],
        "input_line_count": chosen["line_count"],
        "marker_detection": chosen.get("marker_detection") or {},
        "input_candidates": [
            {
                "source": item["source"],
                "best_source": item["best_source"],
                "score": item["score"],
                "char_count": item["char_count"],
                "speaker_line_count": item["speaker_line_count"],
                "line_count": item["line_count"],
                "transcript_slice_found": bool(item.get("transcript_slice_found")),
                "marker_detection": item.get("marker_detection") or {},
            }
            for item in candidates
        ],
    }


def _is_low_quality_structured_sections(
    sections: list[dict[str, Any]],
    *,
    min_sections: int = 2,
) -> tuple[bool, str]:
    if not sections:
        return True, "no_sections"
    if len(sections) < max(1, min_sections):
        return True, "too_few_sections"
    unknown_count = sum(1 for section in sections if str(section.get("speaker") or "").strip().lower() in {"", "unknown"})
    implausible_count = 0
    for section in sections:
        speaker = str(section.get("speaker") or "").strip()
        if not _looks_like_plausible_speaker_label(speaker):
            implausible_count += 1
    if unknown_count == len(sections):
        return True, "all_unknown_speakers"
    if unknown_count / max(len(sections), 1) > 0.9:
        return True, "mostly_unknown_speakers"
    if implausible_count / max(len(sections), 1) > 0.25:
        return True, "implausible_speaker_labels"
    return False, ""


def _parse_speaker_sections_from_text(transcript_text: str) -> dict[str, Any]:
    lines = _normalize_text_lines(transcript_text)
    transcript_lines, marker_detection = _extract_transcript_lines_with_diagnostics(lines)
    working_lines = transcript_lines or lines
    participants = _extract_participants_from_lines(lines)
    sections = _build_speaker_sections(working_lines)
    sections = _enrich_speaker_sections(sections, participants=participants)
    participants = _merge_participants_with_speaker_sections(participants, sections)
    speakers = sorted({str(section.get("speaker") or "").strip() for section in sections if section.get("speaker")})
    return {
        "participants": participants,
        "speaker_sections": sections,
        "speaker_count": len(speakers),
        "speakers": speakers,
        "section_count": len(sections),
        "transcript_line_count": len(working_lines),
        "transcript_char_count": len("\n".join(working_lines)),
        "marker_detection": marker_detection,
        "line_count": {
            "source_line_count": len(lines),
            "transcript_line_count": len(working_lines),
        },
        "section_parse_method": "regex_from_page_text",
        "section_parse_reason": "openai_failed",
    }


def _segment_transcript_text(transcript_text: str, max_segment_chars: int = DEFAULT_TRANSCRIPT_SEGMENT_CHARS) -> list[str]:
    if not transcript_text.strip():
        return []

    parsed = _parse_speaker_sections_from_text(transcript_text)
    sections = parsed.get("speaker_sections")
    if not isinstance(sections, list) or not sections:
        return [transcript_text.strip()]

    max_segment_chars = max(4000, max_segment_chars)
    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0

    for section in sections:
        if not isinstance(section, dict):
            continue
        speaker = str(section.get("speaker") or "unknown").strip() or "unknown"
        text = str(section.get("text") or "").strip()
        if not text:
            continue
        block = f"{speaker}: {text}"
        block_len = len(block) + 2
        if current and current_chars + block_len > max_segment_chars:
            chunks.append("\n\n".join(current).strip())
            current = [block]
            current_chars = len(block)
        else:
            current.append(block)
            current_chars += block_len

    if current:
        chunks.append("\n\n".join(current).strip())

    return [chunk for chunk in chunks if chunk]


def _structure_transcript_with_openai(
    *,
    api_key: str,
    model: str,
    base_url: str,
    timeout_seconds: int,
    retry_attempts: int,
    ticker: str,
    quarter: str,
    title: str,
    url: str,
    published_date: str,
    transcript_text: str,
    log_fn: Optional[Callable[[str], None]] = None,
    debug_io: bool = False,
    debug_io_max_chars: int = 2000,
    debug_artifact_root: Optional[Path] = None,
) -> dict[str, Any]:
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for transcript structuring.")

    transcript_text = str(transcript_text or "").strip()
    if not transcript_text:
        raise RuntimeError("Transcript text is empty after extraction.")

    log = log_fn or (lambda _: None)
    retry_attempts = max(1, retry_attempts)
    segments = _segment_transcript_text(transcript_text)
    if not segments:
        raise RuntimeError("Transcript segmentation produced no usable segments.")
    log(f"scrape: OpenAI structuring will process {len(segments)} segment(s)")

    all_participants: list[dict[str, str]] = []
    all_sections: list[dict[str, Any]] = []
    notes: list[str] = []

    for segment_index, segment_text in enumerate(segments):
        payload = {
            "model": model,
            "max_output_tokens": 4500,
            "input": _build_transcript_structure_prompt(
                ticker=ticker,
                quarter=quarter,
                title=title,
                url=url,
                published_date=published_date,
                transcript_text=segment_text,
                segment_index=segment_index,
                segment_count=len(segments),
            ),
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "transcript_speaker_sections",
                    "strict": True,
                    "schema": _build_transcript_structure_schema(),
                }
            },
        }
        if debug_io:
            preview = segment_text[: max(200, debug_io_max_chars)]
            log(
                f"scrape: OpenAI input preview (segment {segment_index + 1}/{len(segments)}): "
                f"{preview}"
            )
        if debug_artifact_root is not None:
            _write_debug_text(
                debug_artifact_root / f"segment_{segment_index + 1:02d}_input.txt",
                segment_text,
            )
            _write_debug_json(
                debug_artifact_root / f"segment_{segment_index + 1:02d}_request_payload.json",
                payload,
            )

        last_exc: Optional[Exception] = None
        segment_structured: Optional[dict[str, Any]] = None
        segment_response_json: Optional[dict[str, Any]] = None
        read_timeout_failures = 0
        for attempt in range(1, retry_attempts + 1):
            try:
                log(
                    "scrape: structuring transcript with OpenAI "
                    f"(segment {segment_index + 1}/{len(segments)}, attempt {attempt}/{retry_attempts})"
                )
                response = _openai_post_responses(
                    base_url=base_url,
                    api_key=api_key,
                    payload=payload,
                    timeout_seconds=timeout_seconds,
                )
                if response.status_code >= 400:
                    raise RuntimeError(_extract_error_message(response))
                segment_response_json = response.json()
                if debug_io:
                    raw_preview = json.dumps(segment_response_json, ensure_ascii=False)[: max(200, debug_io_max_chars)]
                    log(
                        f"scrape: OpenAI raw response preview (segment {segment_index + 1}/{len(segments)}): "
                        f"{raw_preview}"
                    )
                if debug_artifact_root is not None:
                    _write_debug_json(
                        debug_artifact_root / f"segment_{segment_index + 1:02d}_response_raw.json",
                        segment_response_json,
                    )
                segment_structured = _extract_structured_output(segment_response_json)
                if debug_artifact_root is not None:
                    _write_debug_json(
                        debug_artifact_root / f"segment_{segment_index + 1:02d}_response_structured.json",
                        segment_structured,
                    )
                break
            except Exception as exc:
                last_exc = exc
                lowered_exc = str(exc).lower()
                if "read timed out" in lowered_exc:
                    read_timeout_failures += 1
                log(
                    "scrape: OpenAI structuring failed "
                    f"(segment {segment_index + 1}/{len(segments)}, attempt {attempt}): {exc}"
                )
                if not _is_retryable_openai_structuring_error(exc):
                    log(
                        "scrape: OpenAI structuring error is non-retryable; "
                        f"aborting retries for segment {segment_index + 1}"
                    )
                    break
                if read_timeout_failures >= 2:
                    log(
                        "scrape: repeated OpenAI read timeouts; "
                        f"aborting retries for segment {segment_index + 1}"
                    )
                    break
                if attempt < retry_attempts:
                    backoff_seconds = min(4.0, 1.2 * attempt)
                    time.sleep(backoff_seconds)

        if segment_structured is None:
            raise RuntimeError(f"OpenAI transcript structuring failed on segment {segment_index + 1}: {last_exc}")

        participants = _normalize_participants(segment_structured.get("participants"))
        segment_sections = _normalize_speaker_sections(segment_structured.get("speaker_sections"))
        if not segment_sections:
            raise RuntimeError(f"OpenAI transcript structuring returned no speaker sections for segment {segment_index + 1}.")

        low_quality, low_reason = _is_low_quality_structured_sections(segment_sections, min_sections=1)
        if low_quality:
            raise RuntimeError(
                f"OpenAI transcript structuring quality check failed on segment {segment_index + 1}: {low_reason}"
            )

        all_participants.extend(participants)
        all_sections.extend(segment_sections)
        notes.append(str(segment_structured.get("notes") or "").strip())

    normalized_participants = _normalize_participants(all_participants)
    merged_sections = _normalize_speaker_sections(all_sections)
    merged_sections = _enrich_speaker_sections(merged_sections, participants=normalized_participants)
    low_quality, low_reason = _is_low_quality_structured_sections(merged_sections, min_sections=2)
    if low_quality:
        raise RuntimeError(f"OpenAI transcript structuring quality check failed: {low_reason}")

    normalized_participants = _merge_participants_with_speaker_sections(normalized_participants, merged_sections)
    speakers = sorted({str(section.get("speaker") or "").strip() for section in merged_sections if section.get("speaker")})
    return {
        "participants": normalized_participants,
        "speaker_sections": merged_sections,
        "speaker_count": len(speakers),
        "speakers": speakers,
        "section_count": len(merged_sections),
        "transcript_line_count": sum(section["text"].count("\n") + 1 for section in merged_sections),
        "transcript_char_count": len("\n\n".join(section["text"] for section in merged_sections)),
        "section_parse_method": "openai",
        "section_parse_notes": " | ".join(note for note in notes if note),
    }


def _extract_sources(response_payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    def _push(raw_url: Any) -> None:
        if not isinstance(raw_url, str) or not raw_url.strip():
            return
        normalized = _normalize_url(raw_url)
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        urls.append(normalized)

    for output_item in response_payload.get("output", []) or []:
        if not isinstance(output_item, dict):
            continue
        if output_item.get("type") == "web_search_call":
            action = output_item.get("action")
            if isinstance(action, dict):
                sources = action.get("sources")
                if isinstance(sources, list):
                    for source in sources:
                        if not isinstance(source, dict):
                            continue
                        _push(source.get("url"))

        if output_item.get("type") == "message":
            content = output_item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                annotations = block.get("annotations")
                if not isinstance(annotations, list):
                    continue
                for annotation in annotations:
                    if not isinstance(annotation, dict):
                        continue
                    _push(annotation.get("url"))
                    if isinstance(annotation.get("url_citation"), dict):
                        _push(annotation["url_citation"].get("url"))

    return urls


def _dedupe_links(urls: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = _normalize_url(url)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _pick_best_candidate_by_quarter(
    candidates: list[MotleyTranscriptCandidate],
) -> dict[tuple[int, int], MotleyTranscriptCandidate]:
    def _sort_key(candidate: MotleyTranscriptCandidate) -> tuple[float, datetime]:
        parsed_date = _safe_parse_date(candidate.published_date) or _safe_parse_date(_date_from_motley_url(candidate.url))
        fallback = parsed_date or datetime(1970, 1, 1)
        return candidate.quality_score, fallback

    sorted_candidates = sorted(candidates, key=_sort_key, reverse=True)
    by_quarter: dict[tuple[int, int], MotleyTranscriptCandidate] = {}
    for candidate in sorted_candidates:
        if candidate.year is None or candidate.quarter is None:
            continue
        key = (candidate.year, candidate.quarter)
        if key not in by_quarter:
            by_quarter[key] = candidate
    return by_quarter


def _clean_candidates(
    *,
    ticker: str,
    raw_candidates: list[dict[str, Any]],
) -> tuple[list[MotleyTranscriptCandidate], list[str]]:
    staged: list[dict[str, Any]] = []
    warnings: list[str] = []
    seen_urls: set[str] = set()

    for item in raw_candidates:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "").strip()
        url = _normalize_url(str(item.get("url") or ""))
        published_date = str(item.get("published_date") or "").strip()
        source = str(item.get("source") or "").strip()

        if not title or not url:
            continue
        if url in seen_urls:
            continue
        seen_urls.add(url)

        if not _is_motley_transcript_url(url):
            warnings.append(f"Dropped non-transcript URL: {url}")
            continue

        year, quarter = infer_year_quarter(title=title, url=url, published_date=published_date)
        explicit_ticker = _candidate_has_explicit_ticker(ticker=ticker, title=title, url=url)
        base_quality = _score_candidate(ticker=ticker, title=title, url=url)
        staged.append(
            {
                "title": title,
                "url": url,
                "published_date": published_date or _date_from_motley_url(url),
                "source": source,
                "year": year,
                "quarter": quarter,
                "explicit_ticker": explicit_ticker,
                "base_quality": base_quality,
            }
        )

    company_tokens: set[str] = set()
    for row in staged:
        if not bool(row.get("explicit_ticker")):
            continue
        company_tokens.update(
            _extract_company_tokens_from_candidate(
                ticker=ticker,
                title=str(row.get("title") or ""),
                url=str(row.get("url") or ""),
            )
        )

    cleaned: list[MotleyTranscriptCandidate] = []
    for row in staged:
        title = str(row.get("title") or "")
        url = str(row.get("url") or "")
        explicit_ticker = bool(row.get("explicit_ticker"))
        alias_match = _candidate_matches_company_tokens(title=title, url=url, company_tokens=company_tokens)
        if company_tokens and not explicit_ticker and not alias_match:
            warnings.append(f"Dropped likely off-ticker URL: {url}")
            continue

        quality = float(row.get("base_quality") or 0.0)
        if alias_match and not explicit_ticker:
            quality += 6.0

        cleaned.append(
            MotleyTranscriptCandidate(
                title=title,
                url=url,
                published_date=str(row.get("published_date") or ""),
                source=str(row.get("source") or ""),
                year=row.get("year"),
                quarter=row.get("quarter"),
                quality_score=quality,
            )
        )

    cleaned.sort(
        key=lambda c: (
            c.year or 0,
            c.quarter or 0,
            _safe_parse_date(c.published_date) or datetime(1970, 1, 1),
            c.quality_score,
        ),
        reverse=True,
    )
    return cleaned, warnings


def discover_last_quarter_links(
    *,
    ticker: str,
    api_key: str,
    model: str = DEFAULT_OPENAI_SEARCH_MODEL,
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    max_candidates: int = 12,
    target_quarters: int = 4,
    retry_attempts: int = DEFAULT_OPENAI_RETRY_ATTEMPTS,
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _: None)
    symbol = _normalize_ticker(ticker)
    if not symbol:
        raise ValueError("Ticker is empty after normalization.")
    if not api_key:
        raise ValueError("OPENAI_API_KEY is required.")
    if target_quarters <= 0:
        raise ValueError("target_quarters must be >= 1.")

    response_payload: dict[str, Any] | None = None
    selected_tool = ""
    tool_errors: list[str] = []

    log(
        f"{symbol}: starting discovery "
        f"(model={model}, max_candidates={max_candidates}, target_quarters={target_quarters})"
    )

    retry_attempts = max(1, retry_attempts)
    for tool_type in ("web_search", "web_search_preview"):
        payload = _build_request_payload(
            model=model,
            ticker=symbol,
            max_candidates=max_candidates,
            tool_type=tool_type,
        )
        last_exc: Optional[Exception] = None
        for attempt in range(1, retry_attempts + 1):
            try:
                log(f"{symbol}: trying OpenAI tool '{tool_type}' (attempt {attempt}/{retry_attempts})")
                response = _openai_post_responses(
                    base_url=base_url,
                    api_key=api_key,
                    payload=payload,
                    timeout_seconds=timeout_seconds,
                )
                if response.status_code >= 400:
                    raise RuntimeError(_extract_error_message(response))
                response_payload = response.json()
                selected_tool = tool_type
                log(f"{symbol}: OpenAI request succeeded with '{tool_type}'")
                break
            except Exception as exc:
                last_exc = exc
                log(f"{symbol}: tool '{tool_type}' failed on attempt {attempt}: {exc}")
                if not _is_retryable_openai_request_error(exc):
                    log(
                        f"{symbol}: tool '{tool_type}' error is non-retryable; "
                        f"aborting retries for this tool"
                    )
                    break
                if attempt < retry_attempts:
                    backoff_seconds = min(4.0, 1.2 * attempt)
                    log(f"{symbol}: retrying '{tool_type}' after {backoff_seconds:.1f}s")
                    time.sleep(backoff_seconds)

        if response_payload is not None:
            break
        if last_exc is not None:
            tool_errors.append(f"{tool_type}: {last_exc}")

    if response_payload is None:
        raise RuntimeError("OpenAI web-search request failed. " + " | ".join(tool_errors))

    search_sources = _extract_sources(response_payload)
    raw_candidates = _fallback_candidates_from_sources(
        ticker=symbol,
        response_payload=response_payload,
        max_candidates=max_candidates,
    )
    structured_notes = (
        "Candidates derived from OpenAI web_search sources "
        f"(sources={len(search_sources)}, candidates={len(raw_candidates)})."
    )
    if raw_candidates:
        log(f"{symbol}: built {len(raw_candidates)} raw candidates from web-search sources")
    else:
        # Last-resort fallback: try to parse any structured output if sources were empty.
        try:
            structured = _extract_structured_output(response_payload)
            structured_candidates = structured.get("candidates")
            if isinstance(structured_candidates, list):
                raw_candidates = [item for item in structured_candidates if isinstance(item, dict)]
                structured_notes = (
                    "No web_search source URLs were returned; "
                    f"used {len(raw_candidates)} candidates from structured model output."
                )
                log(f"{symbol}: source URLs were empty; used structured candidates={len(raw_candidates)}")
        except Exception as exc:
            structured_notes = (
                "No web_search source URLs were returned and structured candidate parsing failed "
                f"({exc})."
            )
            log(f"{symbol}: discovery produced no parseable source URLs or structured candidates")

    cleaned_candidates, clean_warnings = _clean_candidates(
        ticker=symbol,
        raw_candidates=[item for item in raw_candidates if isinstance(item, dict)],
    )
    if not search_sources:
        clean_warnings.append("No web_search source URLs returned by OpenAI for discovery.")
    log(
        f"{symbol}: accepted {len(cleaned_candidates)} candidate URLs after Motley filter "
        f"(warnings={len(clean_warnings)})"
    )
    quarter_map = _pick_best_candidate_by_quarter(cleaned_candidates)

    if quarter_map:
        anchor_year, anchor_quarter = sorted(quarter_map.keys(), reverse=True)[0]
    else:
        now = date.today()
        anchor_year = now.year
        anchor_quarter = _quarter_from_month(now.month)

    window = _quarter_window(anchor_year=anchor_year, anchor_quarter=anchor_quarter, count=target_quarters)
    requested = [_quarter_label(year, quarter) for year, quarter in window]

    quarter_rows: list[dict[str, Any]] = []
    found: list[str] = []
    missing: list[str] = []

    for year, quarter in window:
        label = _quarter_label(year, quarter)
        candidate = quarter_map.get((year, quarter))
        if candidate is None:
            missing.append(label)
            quarter_rows.append(
                {
                    "quarter": label,
                    "status": "not_found",
                    "title": "",
                    "url": "",
                    "published_date": "",
                    "source": "",
                }
            )
            continue

        found.append(label)
        quarter_rows.append(
            {
                "quarter": label,
                "status": "found",
                "title": candidate.title,
                "url": candidate.url,
                "published_date": candidate.published_date,
                "source": candidate.source,
            }
        )

    found_transcript_links = [
        {
            "quarter": row["quarter"],
            "title": row["title"],
            "url": row["url"],
        }
        for row in quarter_rows
        if row["status"] == "found" and row["url"]
    ]
    found_links = [item["url"] for item in found_transcript_links]
    all_links = _dedupe_links(found_links + [c.url for c in cleaned_candidates] + search_sources)
    log(
        f"{symbol}: quarter results found={len(found)} missing={len(missing)} "
        f"links={len(all_links)} search_sources={len(search_sources)}"
    )

    return {
        "ticker": symbol,
        "as_of_date": date.today().isoformat(),
        "openai_model": model,
        "openai_search_tool": selected_tool,
        "requested_quarters": requested,
        "found_quarters": found,
        "missing_quarters": missing,
        "quarters": quarter_rows,
        "raw_candidate_count": len(raw_candidates),
        "accepted_candidate_count": len(cleaned_candidates),
        "found_transcript_links": found_transcript_links,
        "links": all_links,
        "candidate_pool": [
            {
                "quarter": _quarter_label(c.year, c.quarter) if c.year and c.quarter else "",
                "title": c.title,
                "url": c.url,
                "published_date": c.published_date,
                "quality_score": round(c.quality_score, 3),
            }
            for c in cleaned_candidates
        ],
        "search_sources": search_sources,
        "warnings": clean_warnings,
        "notes": structured_notes,
    }


def scrape_recent_transcripts_for_report(
    *,
    report: dict[str, Any],
    scrape_count: int,
    timeout_seconds: int,
    api_key: str = "",
    model: str = DEFAULT_OPENAI_SEARCH_MODEL,
    base_url: str = DEFAULT_OPENAI_BASE_URL,
    retry_attempts: int = DEFAULT_OPENAI_RETRY_ATTEMPTS,
    cache_mode: str = DEFAULT_SCRAPE_CACHE_MODE,
    cache_dir: str = DEFAULT_SCRAPE_CACHE_DIR,
    debug_openai_io: bool = False,
    debug_openai_io_max_chars: int = 2000,
    debug_openai_dir: str = "",
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _: None)
    ticker = str(report.get("ticker") or "")
    selected = _select_most_recent_candidates(report, scrape_count)
    cache_mode = (cache_mode or DEFAULT_SCRAPE_CACHE_MODE).strip().lower()
    if cache_mode not in {"refresh", "use", "off"}:
        cache_mode = DEFAULT_SCRAPE_CACHE_MODE
    log(
        f"{ticker}: selected {len(selected)} recent transcript links for scraping "
        f"(cache_mode={cache_mode})"
    )

    scraped: list[dict[str, Any]] = []
    scrape_errors: list[dict[str, Any]] = []
    for item in selected:
        url = item["url"]
        quarter = item["quarter"]
        title = item["title"]
        published_date = item["published_date"]
        cache_key = _build_scrape_cache_key(ticker, quarter, url)
        cache_path = _resolve_scrape_cache_path(
            cache_dir=cache_dir,
            ticker=ticker,
            quarter=quarter,
            url=url,
            published_date=published_date,
        )

        if cache_mode == "use" and cache_path.exists():
            try:
                cached_payload = json.loads(cache_path.read_text(encoding="utf-8"))
                if isinstance(cached_payload, dict):
                    cached_payload = {
                        **cached_payload,
                        "from_cache": True,
                        "cache_key": cache_key,
                        "cache_file": str(cache_path),
                    }
                    scraped.append(cached_payload)
                    log(f"{ticker}: loaded {quarter or 'unknown-quarter'} from cache ({cache_path})")
                    continue
            except Exception as cache_read_exc:
                log(f"{ticker}: cache read failed for {quarter or 'unknown-quarter'} ({cache_read_exc}); refetching")

        try:
            payload = _fetch_transcript_sections(
                url=url,
                ticker=ticker,
                quarter=quarter,
                title=title,
                published_date=published_date,
                timeout_seconds=timeout_seconds,
                openai_api_key=api_key,
                openai_model=model,
                openai_base_url=base_url,
                openai_retry_attempts=retry_attempts,
                debug_openai_io=debug_openai_io,
                debug_openai_io_max_chars=debug_openai_io_max_chars,
                debug_openai_dir=debug_openai_dir,
                log_fn=log_fn,
            )
            payload = {
                **payload,
                "from_cache": False,
                "cache_key": cache_key,
                "cache_file": str(cache_path),
            }
            if cache_mode in {"refresh", "use"}:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
                log(f"{ticker}: cached {quarter or 'unknown-quarter'} -> {cache_path}")
            scraped.append(payload)
            log(
                f"{ticker}: scraped {quarter or 'unknown-quarter'} "
                f"(sections={payload['section_count']}, speakers={payload['speaker_count']})"
            )
        except Exception as exc:
            error_payload: dict[str, Any] = {
                "quarter": quarter,
                "url": url,
                "error": str(exc),
                "cache_key": cache_key,
                "cache_file": str(cache_path),
            }
            if isinstance(exc, TranscriptExtractionError):
                error_payload["scrape_method"] = exc.scrape_method
                if exc.diagnostics:
                    error_payload["diagnostics"] = exc.diagnostics
            scrape_errors.append(error_payload)
            log(f"{ticker}: scrape failed for {quarter or 'unknown-quarter'} ({exc})")

    return {
        "selected_recent_links": selected,
        "scraped_transcripts": scraped,
        "scraped_count": len(scraped),
        "scrape_errors": scrape_errors,
    }


def _build_html_report(output: dict[str, Any]) -> str:
    def esc(value: Any) -> str:
        return html_lib.escape(str(value if value is not None else ""))

    generated_at = esc(output.get("generated_at", ""))
    model = esc(output.get("model", ""))
    results = output.get("results")
    if not isinstance(results, list):
        results = []

    chunks: list[str] = []
    chunks.append(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>OpenAI Motley Transcript Report</title>"
        "<style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,Helvetica,Arial,sans-serif;"
        "margin:20px;background:#f6f7f9;color:#111827}"
        ".meta{margin-bottom:16px;padding:12px;border:1px solid #d1d5db;background:#fff;border-radius:8px}"
        ".ticker{margin-bottom:18px;padding:14px;border:1px solid #d1d5db;background:#fff;border-radius:10px}"
        ".ticker h2{margin:0 0 10px 0;font-size:20px}"
        ".summary{font-size:13px;color:#374151;margin-bottom:10px}"
        ".error{background:#fee2e2;border:1px solid #fecaca;color:#991b1b;padding:10px;border-radius:6px}"
        ".transcript{margin:12px 0;padding:10px;border:1px solid #e5e7eb;border-radius:8px;background:#fafafa}"
        ".transcript h3{margin:0 0 8px 0;font-size:16px}"
        ".participants{font-size:13px;margin:6px 0 10px 0;color:#1f2937}"
        ".section{border-top:1px solid #e5e7eb;padding-top:8px;margin-top:8px}"
        ".section:first-child{border-top:none;padding-top:0;margin-top:0}"
        ".section .head{font-size:12px;color:#374151;margin-bottom:4px}"
        ".section .text{white-space:pre-wrap;font-size:13px;line-height:1.45}"
        ".mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}"
        "</style></head><body>"
    )
    chunks.append(f"<div class='meta'><div><strong>Generated:</strong> {generated_at}</div><div><strong>Model:</strong> {model}</div></div>")

    for result in results:
        if not isinstance(result, dict):
            continue
        ticker = esc(result.get("ticker", "UNKNOWN"))
        chunks.append(f"<section class='ticker'><h2>{ticker}</h2>")
        if result.get("error"):
            chunks.append(f"<div class='error'>{esc(result.get('error'))}</div></section>")
            continue
        found = len(result.get("found_quarters") or [])
        missing = len(result.get("missing_quarters") or [])
        scraped_count = int(result.get("scraped_count") or 0)
        chunks.append(
            f"<div class='summary'>found_quarters={found} | missing_quarters={missing} | scraped_count={scraped_count}</div>"
        )
        scraped = result.get("scraped_transcripts")
        if not isinstance(scraped, list) or not scraped:
            chunks.append("<div class='summary'>No scraped transcripts in this result.</div>")
        else:
            for transcript in scraped:
                if not isinstance(transcript, dict):
                    continue
                t_title = esc(transcript.get("title", ""))
                t_quarter = esc(transcript.get("quarter", ""))
                t_date = esc(transcript.get("published_date", ""))
                t_url = esc(transcript.get("url", ""))
                parse_method = esc(transcript.get("section_parse_method", ""))
                scrape_method = esc(transcript.get("scrape_method", ""))
                chunks.append(
                    "<article class='transcript'>"
                    f"<h3>{t_quarter} - {t_title}</h3>"
                    f"<div class='summary'>date={t_date} | parse={parse_method} | scrape={scrape_method}</div>"
                    f"<div class='mono'>{t_url}</div>"
                )
                participants = transcript.get("participants")
                if isinstance(participants, list) and participants:
                    pbits: list[str] = []
                    for p in participants:
                        if not isinstance(p, dict):
                            continue
                        pname = esc(p.get("name", ""))
                        prole = esc(p.get("role", ""))
                        if prole:
                            pbits.append(f"{pname} ({prole})")
                        else:
                            pbits.append(pname)
                    if pbits:
                        chunks.append(f"<div class='participants'><strong>Participants:</strong> {'; '.join(pbits)}</div>")
                sections = transcript.get("speaker_sections")
                if isinstance(sections, list):
                    for section in sections:
                        if not isinstance(section, dict):
                            continue
                        speaker = esc(section.get("speaker", "unknown"))
                        role = esc(section.get("speaker_role", ""))
                        section_type = esc(section.get("section_type", "other"))
                        order_index = esc(section.get("order_index", ""))
                        text = esc(section.get("text", ""))
                        chunks.append(
                            "<div class='section'>"
                            f"<div class='head'><strong>{speaker}</strong> "
                            f"{'(' + role + ')' if role else ''} | type={section_type} | order={order_index}</div>"
                            f"<div class='text'>{text}</div>"
                            "</div>"
                        )
                chunks.append("</article>")
        errors = result.get("scrape_errors")
        if isinstance(errors, list) and errors:
            chunks.append("<div class='summary'><strong>Scrape Errors</strong></div>")
            for err in errors:
                if not isinstance(err, dict):
                    continue
                chunks.append(
                    "<div class='error'>"
                    f"{esc(err.get('quarter', ''))}: {esc(err.get('error', ''))}<br>"
                    f"<span class='mono'>{esc(err.get('url', ''))}</span>"
                    "</div>"
                )
        chunks.append("</section>")

    chunks.append("</body></html>")
    return "".join(chunks)


def run_cli(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="OpenAI web-search test script for Motley Fool transcript link discovery."
    )
    parser.add_argument("tickers", nargs="+", help="One or more stock tickers, e.g. AAPL MSFT NVDA")
    parser.add_argument("--model", default=DEFAULT_OPENAI_SEARCH_MODEL, help="OpenAI model name")
    parser.add_argument("--base-url", default=DEFAULT_OPENAI_BASE_URL, help="OpenAI API base URL")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Request timeout in seconds")
    parser.add_argument(
        "--openai-retries",
        type=int,
        default=DEFAULT_OPENAI_RETRY_ATTEMPTS,
        help="Retry attempts per OpenAI web-search tool call",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=12,
        help="Maximum candidate URLs to request from OpenAI before quarter reduction",
    )
    parser.add_argument(
        "--quarters",
        type=int,
        default=4,
        help="How many consecutive quarters to return",
    )
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""), help="OpenAI API key override")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--verbose", action="store_true", help="Print progress logs to stderr")
    parser.add_argument(
        "--scrape",
        action="store_true",
        help="After link discovery, fetch and parse most recent transcript pages into speaker sections",
    )
    parser.add_argument(
        "--scrape-count",
        type=int,
        default=4,
        help="How many most-recent transcript links to scrape per ticker when --scrape is set",
    )
    parser.add_argument(
        "--cache-mode",
        choices=["refresh", "use", "off"],
        default=DEFAULT_SCRAPE_CACHE_MODE if DEFAULT_SCRAPE_CACHE_MODE in {"refresh", "use", "off"} else "refresh",
        help=(
            "Cache behavior for scraped transcript JSON: "
            "'refresh' (default) always refetch and overwrite cache, "
            "'use' reads cache when available, 'off' disables cache read/write."
        ),
    )
    parser.add_argument(
        "--cache-dir",
        default=DEFAULT_SCRAPE_CACHE_DIR,
        help="Directory for transcript scrape cache files.",
    )
    parser.add_argument(
        "--debug-openai-io",
        action="store_true",
        help="Print OpenAI transcript-structuring input/output previews in verbose logs.",
    )
    parser.add_argument(
        "--debug-openai-io-max-chars",
        type=int,
        default=2000,
        help="Max characters for terminal previews when --debug-openai-io is enabled.",
    )
    parser.add_argument(
        "--debug-openai-dir",
        default="",
        help="Optional directory to write full OpenAI transcript structuring artifacts (input/response JSON).",
    )
    parser.add_argument(
        "--html-report",
        default="",
        help="Optional output path for a simple HTML view of the final JSON results.",
    )

    args = parser.parse_args(argv)
    if not args.api_key:
        print(
            json.dumps({"error": "OPENAI_API_KEY is missing. Set it in env or pass --api-key."}),
            file=sys.stderr,
        )
        return 2

    reports: list[dict[str, Any]] = []
    had_error = False
    interrupted = False
    log_fn = _default_logger if args.verbose else None

    if args.verbose:
        _default_logger(
            f"Starting run for {len(args.tickers)} ticker(s): {', '.join(args.tickers)} "
            f"(model={args.model}, timeout={args.timeout}s, retries={max(args.openai_retries, 1)}, "
            f"cache_mode={args.cache_mode})"
        )

    for ticker in args.tickers:
        try:
            if args.verbose:
                _default_logger(f"{ticker}: dispatching discovery")
            report = discover_last_quarter_links(
                ticker=ticker,
                api_key=args.api_key,
                model=args.model,
                base_url=args.base_url,
                timeout_seconds=args.timeout,
                max_candidates=args.max_candidates,
                target_quarters=args.quarters,
                retry_attempts=max(args.openai_retries, 1),
                log_fn=log_fn,
            )
            if args.scrape and "error" not in report:
                if args.verbose:
                    _default_logger(f"{ticker}: scraping most recent {max(args.scrape_count, 1)} transcript links")
                scrape_payload = scrape_recent_transcripts_for_report(
                    report=report,
                    scrape_count=max(args.scrape_count, 1),
                    timeout_seconds=args.timeout,
                    api_key=args.api_key,
                    model=args.model,
                    base_url=args.base_url,
                    retry_attempts=max(args.openai_retries, 1),
                    cache_mode=args.cache_mode,
                    cache_dir=args.cache_dir,
                    debug_openai_io=args.debug_openai_io,
                    debug_openai_io_max_chars=max(args.debug_openai_io_max_chars, 200),
                    debug_openai_dir=args.debug_openai_dir,
                    log_fn=log_fn,
                )
                report = {**report, **scrape_payload}
            reports.append(report)
            if args.verbose:
                _default_logger(
                    f"{ticker}: done (found={len(report.get('found_quarters', []))}, "
                    f"links={len(report.get('links', []))})"
                )
        except KeyboardInterrupt:
            interrupted = True
            had_error = True
            if args.verbose:
                _default_logger(f"{ticker}: interrupted by user; returning partial results")
            reports.append(
                {
                    "ticker": _normalize_ticker(ticker),
                    "error": "Interrupted by user.",
                }
            )
            break
        except Exception as exc:
            had_error = True
            if args.verbose:
                _default_logger(f"{ticker}: failed ({exc})")
            reports.append(
                {
                    "ticker": _normalize_ticker(ticker),
                    "error": str(exc),
                }
            )

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "model": args.model,
        "results": reports,
    }
    if interrupted:
        output["interrupted"] = True

    if args.pretty:
        print(json.dumps(output, indent=2))
    else:
        print(json.dumps(output))

    if args.html_report:
        html_path = Path(args.html_report)
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(_build_html_report(output), encoding="utf-8")
        if args.verbose:
            _default_logger(f"HTML report written: {html_path}")

    if args.verbose:
        _default_logger(f"Run complete (had_error={had_error})")

    if interrupted:
        return 130
    return 1 if had_error else 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
