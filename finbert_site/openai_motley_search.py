"""OpenAI web-search prototype for Motley Fool transcript link discovery."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, datetime, timezone
import json
import os
import re
import sys
from typing import Any, Callable, Optional
from urllib.parse import urlparse, urlunparse

from dotenv import load_dotenv
import requests

load_dotenv()

DEFAULT_OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
DEFAULT_OPENAI_SEARCH_MODEL = os.getenv("OPENAI_SEARCH_MODEL", "gpt-5-mini")
DEFAULT_TIMEOUT_SECONDS = 45

_TITLE_QUARTER_PATTERNS = (
    re.compile(r"\bQ([1-4])\s+(20\d{2})\b", flags=re.IGNORECASE),
    re.compile(r"\b(20\d{2})\s+Q([1-4])\b", flags=re.IGNORECASE),
)
_URL_QUARTER_PATTERN = re.compile(r"-q([1-4])-(20\d{2})-earnings-call-transcript", flags=re.IGNORECASE)
_URL_DATE_PATTERN = re.compile(r"/earnings/call-transcripts/(\d{4})/(\d{2})/(\d{2})/")


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

    for tool_type in ("web_search", "web_search_preview"):
        payload = _build_request_payload(
            model=model,
            ticker=symbol,
            max_candidates=max_candidates,
            tool_type=tool_type,
        )
        try:
            log(f"{symbol}: trying OpenAI tool '{tool_type}'")
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
            log(f"{symbol}: tool '{tool_type}' failed: {exc}")
            tool_errors.append(f"{tool_type}: {exc}")

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


def run_cli(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="OpenAI web-search test script for Motley Fool transcript link discovery."
    )
    parser.add_argument("tickers", nargs="+", help="One or more stock tickers, e.g. AAPL MSFT NVDA")
    parser.add_argument("--model", default=DEFAULT_OPENAI_SEARCH_MODEL, help="OpenAI model name")
    parser.add_argument("--base-url", default=DEFAULT_OPENAI_BASE_URL, help="OpenAI API base URL")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SECONDS, help="Request timeout in seconds")
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
            f"(model={args.model}, timeout={args.timeout}s)"
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
                log_fn=log_fn,
            )
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
