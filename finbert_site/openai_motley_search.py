"""OpenAI web-search prototype for Motley Fool transcript link discovery."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
import re
import sys
import time
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests

load_dotenv()

DEFAULT_OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_OPENAI_SEARCH_MODEL = os.getenv("OPENAI_SEARCH_MODEL", "gpt-5-mini")
DEFAULT_TIMEOUT_SECONDS = 45
DEFAULT_OPENAI_RETRY_ATTEMPTS = int(os.getenv("OPENAI_RETRY_ATTEMPTS", "3"))

_TITLE_QUARTER_PATTERNS = (
    re.compile(r"\bQ([1-4])\s+(20\d{2})\b", flags=re.IGNORECASE),
    re.compile(r"\b(20\d{2})\s+Q([1-4])\b", flags=re.IGNORECASE),
)
_URL_QUARTER_PATTERN = re.compile(r"-q([1-4])-(20\d{2})-earnings-call-transcript", flags=re.IGNORECASE)
_URL_DATE_PATTERN = re.compile(r"/earnings/call-transcripts/(\d{4})/(\d{2})/(\d{2})/")
_SPEAKER_LINE_PATTERN = re.compile(r"^([A-Za-z][A-Za-z .,'&()\-/]{1,90}):\s*(.+)$")

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
}

_TRANSCRIPT_START_MARKERS = {
    "full conference call transcript",
    "prepared remarks",
    "questions and answers",
    "q&a",
}

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


@dataclass(frozen=True)
class MotleyTranscriptCandidate:
    title: str
    url: str
    published_date: str
    source: str
    year: Optional[int]
    quarter: Optional[int]
    quality_score: float


def _normalize_ticker(ticker: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9.-]", "", ticker.strip().upper())
    return cleaned


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
    lowered = line.lower().strip()
    if "questions and answers" in lowered or lowered in {"q&a", "question-and-answer"}:
        return "qa"
    if "prepared remarks" in lowered:
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

        decoded = raw.replace("\\n", "\n").replace("\\u2014", "—").replace("\\u2019", "'")

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
            text = BeautifulSoup(blob, "html.parser").get_text("\n", strip=True)
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


def _extract_transcript_lines(lines: list[str]) -> list[str]:
    start_idx = None
    for i, line in enumerate(lines):
        lowered = line.lower()
        if any(marker in lowered for marker in _TRANSCRIPT_START_MARKERS):
            start_idx = i + (1 if "full conference call transcript" in lowered else 0)
            break
        if _speaker_line_match(line):
            start_idx = i
            break

    if start_idx is None:
        return []

    stop_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        lowered = lines[i].lower()
        if any(marker in lowered for marker in _TRANSCRIPT_END_MARKERS):
            stop_idx = i
            break

    return lines[start_idx:stop_idx]


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


def _fetch_transcript_sections(
    *,
    url: str,
    quarter: str,
    title: str,
    published_date: str,
    timeout_seconds: int,
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _: None)
    log(f"scrape: fetching {url}")

    response = requests.get(url, headers=_REQUEST_HEADERS, timeout=timeout_seconds)
    response.raise_for_status()
    html = response.text

    raw_soup = BeautifulSoup(html, "html.parser")
    soup = BeautifulSoup(html, "html.parser")
    for node in soup(["script", "style", "noscript", "svg", "button", "form", "header", "footer", "nav"]):
        node.decompose()

    container = (
        soup.select_one("article")
        or soup.select_one("main")
        or soup.select_one("div[class*='article']")
        or soup.body
    )
    if container is None:
        raise RuntimeError("No content container found for transcript page.")

    lines = _extract_text_lines(container)
    if not lines:
        log("scrape: strict tag extraction produced 0 lines; trying relaxed extraction")
        lines = _extract_text_lines_relaxed(container)
    if not lines and soup.body is not None:
        log("scrape: relaxed container extraction produced 0 lines; trying page body")
        lines = _extract_text_lines_relaxed(soup.body)
    if not lines:
        log("scrape: body extraction produced 0 lines; trying script payload extraction")
        lines = _extract_text_lines_from_script_payloads(raw_soup)
    if not lines:
        raise RuntimeError("No text lines found in transcript page.")

    participants = _extract_participants_from_lines(lines)
    transcript_lines = _extract_transcript_lines(lines)
    if not transcript_lines:
        raise RuntimeError("Transcript section markers were not found on page.")

    speaker_sections = _build_speaker_sections(transcript_lines)
    speaker_names = [section["speaker"] for section in speaker_sections if section.get("speaker")]
    speaker_unique = sorted({name for name in speaker_names if name})

    return {
        "quarter": quarter,
        "title": title,
        "url": url,
        "published_date": published_date,
        "participants": participants,
        "speaker_sections": speaker_sections,
        "speaker_count": len(speaker_unique),
        "speakers": speaker_unique,
        "section_count": len(speaker_sections),
        "transcript_line_count": len(transcript_lines),
        "transcript_char_count": len("\n".join(transcript_lines)),
    }


def _select_most_recent_candidates(report: dict[str, Any], count: int) -> list[dict[str, str]]:
    pool = report.get("candidate_pool")
    if not isinstance(pool, list):
        return []

    selected: list[dict[str, str]] = []
    for row in pool:
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        selected.append(
            {
                "quarter": str(row.get("quarter") or ""),
                "title": str(row.get("title") or ""),
                "url": url,
                "published_date": str(row.get("published_date") or ""),
            }
        )
        if len(selected) >= max(count, 1):
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


def _build_search_prompt(ticker: str, max_candidates: int) -> str:
    return (
        "Find Motley Fool earnings call transcript pages for the stock ticker "
        f"{ticker}.\n"
        "Return only Motley Fool transcript URLs under /earnings/call-transcripts/.\n"
        "Prefer entries where ticker/company match is explicit in title/slug.\n"
        f"Return up to {max_candidates} unique candidates ordered newest to oldest.\n"
        "Use YYYY-MM-DD for published_date when available, otherwise empty string."
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
        "tool_choice": "required",
        "input": _build_search_prompt(ticker=ticker, max_candidates=max_candidates),
        "tools": [_build_tool(tool_type)],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "motley_fool_transcript_candidates",
                "strict": True,
                "schema": _build_response_schema(),
            }
        },
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
    cleaned: list[MotleyTranscriptCandidate] = []
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
        cleaned.append(
            MotleyTranscriptCandidate(
                title=title,
                url=url,
                published_date=published_date or _date_from_motley_url(url),
                source=source,
                year=year,
                quarter=quarter,
                quality_score=_score_candidate(ticker=ticker, title=title, url=url),
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
                response = requests.post(
                    f"{base_url.rstrip('/')}/responses",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=timeout_seconds,
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

    structured = _extract_structured_output(response_payload)
    raw_candidates = structured.get("candidates")
    if not isinstance(raw_candidates, list):
        raw_candidates = []
    log(f"{symbol}: model returned {len(raw_candidates)} raw candidates")

    cleaned_candidates, clean_warnings = _clean_candidates(
        ticker=symbol,
        raw_candidates=[item for item in raw_candidates if isinstance(item, dict)],
    )
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

    search_sources = _extract_sources(response_payload)
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
        "notes": str(structured.get("notes") or ""),
    }


def scrape_recent_transcripts_for_report(
    *,
    report: dict[str, Any],
    scrape_count: int,
    timeout_seconds: int,
    log_fn: Optional[Callable[[str], None]] = None,
) -> dict[str, Any]:
    log = log_fn or (lambda _: None)
    ticker = str(report.get("ticker") or "")
    selected = _select_most_recent_candidates(report, scrape_count)
    log(f"{ticker}: selected {len(selected)} recent transcript links for scraping")

    scraped: list[dict[str, Any]] = []
    scrape_errors: list[dict[str, str]] = []
    for item in selected:
        url = item["url"]
        quarter = item["quarter"]
        title = item["title"]
        published_date = item["published_date"]
        try:
            payload = _fetch_transcript_sections(
                url=url,
                quarter=quarter,
                title=title,
                published_date=published_date,
                timeout_seconds=timeout_seconds,
                log_fn=log_fn,
            )
            scraped.append(payload)
            log(
                f"{ticker}: scraped {quarter or 'unknown-quarter'} "
                f"(sections={payload['section_count']}, speakers={payload['speaker_count']})"
            )
        except Exception as exc:
            scrape_errors.append(
                {
                    "quarter": quarter,
                    "url": url,
                    "error": str(exc),
                }
            )
            log(f"{ticker}: scrape failed for {quarter or 'unknown-quarter'} ({exc})")

    return {
        "selected_recent_links": selected,
        "scraped_transcripts": scraped,
        "scraped_count": len(scraped),
        "scrape_errors": scrape_errors,
    }


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

    args = parser.parse_args(argv)
    if not args.api_key:
        print(
            json.dumps({"error": "OPENAI_API_KEY is missing. Set it in env or pass --api-key."}),
            file=sys.stderr,
        )
        return 2

    reports: list[dict[str, Any]] = []
    had_error = False
    log_fn = _default_logger if args.verbose else None

    if args.verbose:
        _default_logger(
            f"Starting run for {len(args.tickers)} ticker(s): {', '.join(args.tickers)} "
            f"(model={args.model}, timeout={args.timeout}s, retries={max(args.openai_retries, 1)})"
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
                    log_fn=log_fn,
                )
                report = {**report, **scrape_payload}
            reports.append(report)
            if args.verbose:
                _default_logger(
                    f"{ticker}: done (found={len(report.get('found_quarters', []))}, "
                    f"links={len(report.get('links', []))})"
                )
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

    if args.pretty:
        print(json.dumps(output, indent=2))
    else:
        print(json.dumps(output))

    if args.verbose:
        _default_logger(f"Run complete (had_error={had_error})")

    return 1 if had_error else 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
