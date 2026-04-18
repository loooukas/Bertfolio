"""External providers for transcripts, market reaction data, and fundamentals."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
import json
import re
import time
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx
import pandas as pd
import requests
import yfinance as yf

from .settings import Settings

_LAST_ALPHA_REQUEST_TS = 0.0
_ALPHA_MIN_INTERVAL_SEC = 1.1

_FINANCE_TERMS = {
    "stock",
    "shares",
    "earnings",
    "eps",
    "revenue",
    "guidance",
    "valuation",
    "market cap",
    "dividend",
    "buyback",
    "analyst",
    "quarter",
}

_TRANSCRIPT_TITLE_MARKERS = {
    "earnings transcript",
    "earnings call transcript",
    "conference call transcript",
}

_MOTLEY_FOOL_SURFACES = [
    "https://www.fool.com/author/20032/",
]

_TRANSCRIPT_URL_PATTERN = re.compile(
    r"^https://www\.fool\.com/earnings/call-transcripts/\d{4}/\d{2}/\d{2}/[a-z0-9-]+/?$",
    flags=re.IGNORECASE,
)

_FINANCE_SUBREDDIT_WEIGHTS = {
    "stocks": 2.5,
    "investing": 2.5,
    "wallstreetbets": 2.0,
    "stockmarket": 2.0,
    "options": 1.5,
    "securityanalysis": 2.5,
    "valueinvesting": 2.5,
}

_MIN_SOCIAL_RELEVANCE = 1.0
_MIN_NEWS_RELEVANCE = 1.2
_DEFAULT_LOOKBACK_DAYS = 14

_STOP_MARKERS = {
    "read next",
    "stocks mentioned",
    "motley fool returns",
    "our analyst disclosure policy",
    "related articles",
    "join stock advisor",
}

_START_MARKERS = {
    "prepared remarks",
    "questions and answers",
    "full conference call transcript",
    "call participants",
    "date",
}


@dataclass
class TranscriptRecord:
    symbol: str
    year: int
    quarter: int
    date: Optional[str]
    content: str
    source: str
    source_url: Optional[str] = None
    title: Optional[str] = None
    extraction_confidence: float = 0.0
    parsing_warnings: list[str] = field(default_factory=list)
    participants: list[dict[str, str]] = field(default_factory=list)


@dataclass
class TranscriptFetchOutcome:
    quarter: str
    status: str
    detail: Optional[str] = None


@dataclass
class TranscriptFetchDiagnostics:
    requested_quarters: list[str]
    found_quarters: list[str]
    missing_quarters: list[str]
    errors: list[str]
    outcomes: list[TranscriptFetchOutcome]


@dataclass
class TranscriptCandidate:
    title: str
    url: str
    published_date: Optional[str]
    author: Optional[str]
    surface: str
    match_score: float = 0.0


@dataclass
class TranscriptDiscoveryAudit:
    pages_scanned: int
    candidates_total: int
    transcript_like_count: int
    match_filtered_count: int
    selected_count: int
    discarded_near_matches: list[str]
    fetch_failures: list[str]
    playwright_fallback_used: bool


@dataclass
class NewsRecord:
    title: str
    summary: str
    url: str
    source: Optional[str]
    time_published: Optional[str]
    sentiment_score: float
    sentiment_label: str


@dataclass
class SocialRecord:
    source: str
    title: str
    body: str
    excerpt: str
    url: str
    subreddit: Optional[str]
    created_utc: Optional[int]
    relevance_score: float


@dataclass
class PriceVolumeRecord:
    date: str
    close: float
    volume: float


@dataclass
class FeedFetchAudit:
    fetched_pool: int
    deduped_pool: int
    displayed_count: int


def _quarter_from_month(month: int) -> int:
    return ((month - 1) // 3) + 1


def _quarter_label(year: int, quarter: int) -> str:
    return f"{year}-Q{quarter}"


def _quarter_tuple_from_label(label: str) -> tuple[int, int]:
    year_part, q_part = label.split("-Q")
    return int(year_part), int(q_part)


def _normalize_title_key(title: str) -> str:
    lowered = title.lower().strip()
    lowered = re.sub(r"[^a-z0-9\s]", "", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered


def _company_tokens(company_name: Optional[str]) -> list[str]:
    if not company_name:
        return []
    tokens = [t for t in re.split(r"[^a-z0-9]+", company_name.lower()) if len(t) >= 4]
    stop = {"inc", "corp", "ltd", "plc", "group", "company", "holdings"}
    return [token for token in tokens if token not in stop]


def _contains_symbol(text: str, symbol: str) -> bool:
    lowered = text.lower()
    symbol_l = symbol.lower()
    return bool(re.search(rf"\b{re.escape(symbol_l)}\b", lowered)) or (f"${symbol_l}" in lowered)


def _recency_weight(dt: Optional[datetime], lookback_days: int) -> float:
    if not dt:
        return 0.35
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    age_days = max(0.0, (now - dt).total_seconds() / 86400.0)
    if age_days >= lookback_days:
        return 0.0
    return round(1.0 - (age_days / max(float(lookback_days), 1.0)), 4)


def _safe_parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y%m%dT%H%M%S"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _date_from_motley_url(url: str) -> Optional[str]:
    m = re.search(r"/earnings/call-transcripts/(\d{4})/(\d{2})/(\d{2})/", url)
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"


def _is_transcript_title(title: str) -> bool:
    lowered = title.lower()
    return any(marker in lowered for marker in _TRANSCRIPT_TITLE_MARKERS)


def _candidate_match_score(symbol: str, company_name: Optional[str], title: str) -> float:
    title_upper = title.upper()
    title_lower = title.lower()
    symbol_upper = symbol.upper()

    score = 0.0
    if re.search(rf"\({re.escape(symbol_upper)}\)", title_upper):
        score += 100.0
    if re.search(rf"\b{re.escape(symbol_upper)}\b", title_upper):
        score += 60.0

    if company_name:
        name = company_name.lower().strip()
        if name and name in title_lower:
            score += 35.0
        company_tokens = [t for t in re.split(r"[^a-z0-9]+", name) if len(t) >= 4]
        token_hits = sum(1 for tok in company_tokens if tok in title_lower)
        score += float(min(token_hits, 3) * 6)

    if "earnings call transcript" in title_lower:
        score += 12.0
    elif "earnings transcript" in title_lower:
        score += 8.0

    return score


def _alpha_get(params: Dict[str, str], timeout_seconds: int) -> Dict[str, Any]:
    global _LAST_ALPHA_REQUEST_TS

    now = time.monotonic()
    elapsed = now - _LAST_ALPHA_REQUEST_TS
    if elapsed < _ALPHA_MIN_INTERVAL_SEC:
        time.sleep(_ALPHA_MIN_INTERVAL_SEC - elapsed)

    url = "https://www.alphavantage.co/query"
    response = requests.get(url, params=params, timeout=timeout_seconds)
    _LAST_ALPHA_REQUEST_TS = time.monotonic()
    if response.status_code != 200:
        raise RuntimeError(
            f"Alpha Vantage request failed: HTTP {response.status_code} - {response.text[:200]}"
        )

    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("Alpha Vantage returned a non-JSON object.")

    if payload.get("Error Message"):
        raise RuntimeError(str(payload.get("Error Message")))
    if payload.get("Information"):
        raise RuntimeError(str(payload.get("Information")))
    if payload.get("Note"):
        raise RuntimeError(str(payload.get("Note")))

    return payload


def _request_html(url: str, timeout_seconds: int) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    }

    response = requests.get(url, headers=headers, timeout=timeout_seconds)
    if response.status_code == 200 and response.text:
        return response.text

    with httpx.Client(timeout=timeout_seconds, headers=headers, follow_redirects=True) as client:
        fallback = client.get(url)
        fallback.raise_for_status()
        return fallback.text


def _extract_candidate_links(html: str, surface: str) -> list[TranscriptCandidate]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[TranscriptCandidate] = []

    for link in soup.select("a[href*='/earnings/call-transcripts/']"):
        href = str(link.get("href") or "").strip()
        title = link.get_text(" ", strip=True)
        if not href or not title:
            continue

        absolute = urljoin("https://www.fool.com", href)
        if "/earnings/call-transcripts/" not in absolute:
            continue
        if not _TRANSCRIPT_URL_PATTERN.match(absolute):
            continue

        out.append(
            TranscriptCandidate(
                title=title,
                url=absolute,
                published_date=_date_from_motley_url(absolute),
                author="Motley Fool Transcribing" if "/author/20032" in surface else None,
                surface=surface,
            )
        )

    return out


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


def _speaker_line_match(line: str) -> Optional[tuple[str, str]]:
    m = re.match(r"^([A-Za-z][A-Za-z .,'&()\-/]{1,70}):\s*(.+)$", line)
    if not m:
        return None
    speaker = re.sub(r"\s+", " ", m.group(1)).strip()
    spoken = m.group(2).strip()
    if len(spoken) < 2:
        return None
    return speaker, spoken


def _extract_participants(lines: list[str]) -> list[dict[str, str]]:
    start_idx = None
    for i, line in enumerate(lines):
        if "call participants" in line.lower():
            start_idx = i + 1
            break

    if start_idx is None:
        return []

    participants: list[dict[str, str]] = []
    for line in lines[start_idx: start_idx + 40]:
        lowered = line.lower()
        if lowered in _START_MARKERS or "prepared remarks" in lowered or "questions and answers" in lowered:
            break
        if len(line) < 3:
            continue

        if " - " in line:
            name, role = line.split(" - ", 1)
        elif "," in line:
            name, role = line.split(",", 1)
        else:
            name, role = line, ""

        name = name.strip()
        role = role.strip()
        if name:
            participants.append({"name": name, "role": role})

    return participants[:20]


def _extract_transcript_body(html: str) -> tuple[str, list[str], float, list[dict[str, str]]]:
    warnings: list[str] = []
    soup = BeautifulSoup(html, "html.parser")

    for node in soup(["script", "style", "noscript", "svg", "button", "form"]):
        node.decompose()

    container = (
        soup.select_one("article")
        or soup.select_one("main")
        or soup.select_one("div[class*='article']")
        or soup.body
    )

    if container is None:
        return "", ["Transcript parser could not find a content container."], 0.0, []

    lines = _extract_text_lines(container)
    if len(lines) < 8:
        lines_from_json = _extract_article_body_from_jsonld(soup)
        if len(lines_from_json) > len(lines):
            lines = lines_from_json
            warnings.append("Transcript body used JSON-LD fallback extraction.")
    if not lines:
        return "", ["Transcript parser extracted no text lines."], 0.0, []

    start_idx = None
    for i, line in enumerate(lines):
        lowered = line.lower()
        if any(marker in lowered for marker in _START_MARKERS):
            start_idx = i
            break
        if _speaker_line_match(line):
            start_idx = i
            break

    if start_idx is None:
        warnings.append("Transcript start marker not found; using beginning of article body.")
        start_idx = 0

    stop_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        lowered = lines[i].lower()
        if any(marker in lowered for marker in _STOP_MARKERS):
            stop_idx = i
            break

    extracted = lines[start_idx:stop_idx]
    if len(extracted) < 8:
        warnings.append("Transcript extraction appears sparse; content may be incomplete.")

    participants = _extract_participants(extracted)

    has_prepared = any("prepared remarks" in l.lower() for l in extracted)
    has_qa = any("questions and answers" in l.lower() or "q&a" in l.lower() for l in extracted)

    confidence = 0.32
    if start_idx > 0:
        confidence += 0.08
    if stop_idx < len(lines):
        confidence += 0.10
    if has_prepared:
        confidence += 0.18
    if has_qa:
        confidence += 0.18
    if len(extracted) >= 30:
        confidence += 0.14
    confidence = min(1.0, round(confidence, 3))

    body = "\n".join(extracted)
    return body, warnings, confidence, participants


def _infer_year_quarter(title: str, published_date: Optional[str]) -> tuple[int, int]:
    m = re.search(r"\bQ([1-4])\s+(\d{4})\b", title, flags=re.IGNORECASE)
    if m:
        return int(m.group(2)), int(m.group(1))

    date_obj = _safe_parse_date(published_date)
    if date_obj:
        return date_obj.year, _quarter_from_month(date_obj.month)

    now = datetime.now(timezone.utc)
    return now.year, _quarter_from_month(now.month)


def discover_motley_fool_candidates(
    symbol: str,
    company_name: Optional[str],
    settings: Settings,
    max_author_pages: int = 4,
) -> tuple[list[TranscriptCandidate], TranscriptDiscoveryAudit]:
    all_candidates: list[TranscriptCandidate] = []
    failures: list[str] = []
    pages_scanned = 0

    pages: list[tuple[str, str]] = [("author-1", _MOTLEY_FOOL_SURFACES[0])]
    for page in range(2, max_author_pages + 1):
        pages.append((f"author-{page}", f"{_MOTLEY_FOOL_SURFACES[0]}?page={page}"))
    pages.append(("search", f"https://www.fool.com/search/?q={symbol}%20earnings%20call%20transcript"))

    seen_urls: set[str] = set()
    for surface_name, url in pages:
        try:
            html = _request_html(url, settings.request_timeout_seconds)
            pages_scanned += 1
            candidates = _extract_candidate_links(html, surface=url)
            for candidate in candidates:
                if candidate.url in seen_urls:
                    continue
                seen_urls.add(candidate.url)
                all_candidates.append(candidate)
        except Exception as exc:
            failures.append(f"{surface_name}: {exc}")

    transcript_like = [c for c in all_candidates if _is_transcript_title(c.title)]

    for candidate in transcript_like:
        candidate.match_score = _candidate_match_score(symbol, company_name, candidate.title)

    matched = [c for c in transcript_like if c.match_score > 0]
    near_matches = [c for c in transcript_like if c.match_score == 0]

    matched.sort(
        key=lambda c: (
            c.match_score,
            _safe_parse_date(c.published_date) or datetime(1970, 1, 1),
        ),
        reverse=True,
    )

    audit = TranscriptDiscoveryAudit(
        pages_scanned=pages_scanned,
        candidates_total=len(all_candidates),
        transcript_like_count=len(transcript_like),
        match_filtered_count=len(matched),
        selected_count=0,
        discarded_near_matches=[f"{c.title} ({c.url})" for c in near_matches[:25]],
        fetch_failures=failures,
        playwright_fallback_used=False,
    )

    return matched, audit


def fetch_transcripts_motley_fool(
    symbol: str,
    company_name: Optional[str],
    settings: Settings,
    target_count: int = 4,
) -> tuple[list[TranscriptRecord], list[str], TranscriptFetchDiagnostics, TranscriptDiscoveryAudit]:
    warnings: list[str] = []

    candidates, discovery_audit = discover_motley_fool_candidates(symbol, company_name, settings)
    max_attempts = min(len(candidates), max(target_count * 8, target_count))
    selected = candidates[:max_attempts]
    discovery_audit.selected_count = 0

    outcomes: list[TranscriptFetchOutcome] = []
    transcripts: list[TranscriptRecord] = []

    for candidate in selected:
        if len(transcripts) >= target_count:
            break
        quarter_label = "unknown"
        try:
            year, quarter = _infer_year_quarter(candidate.title, candidate.published_date)
            quarter_label = _quarter_label(year, quarter)

            html = _request_html(candidate.url, settings.request_timeout_seconds)
            body, parse_warnings, confidence, participants = _extract_transcript_body(html)
            if not body.strip():
                outcomes.append(
                    TranscriptFetchOutcome(
                        quarter=quarter_label,
                        status="not_found",
                        detail="Transcript body was empty after parsing.",
                    )
                )
                continue

            transcripts.append(
                TranscriptRecord(
                    symbol=symbol,
                    year=year,
                    quarter=quarter,
                    date=candidate.published_date,
                    content=body,
                    source="motley_fool",
                    source_url=candidate.url,
                    title=candidate.title,
                    extraction_confidence=confidence,
                    parsing_warnings=parse_warnings,
                    participants=participants,
                )
            )
            outcomes.append(TranscriptFetchOutcome(quarter=quarter_label, status="found"))
            for warning in parse_warnings:
                warnings.append(f"{quarter_label}: {warning}")
        except Exception as exc:
            outcomes.append(
                TranscriptFetchOutcome(
                    quarter=quarter_label,
                    status="error",
                    detail=str(exc),
                )
            )
            warnings.append(f"Motley Fool transcript error for {quarter_label}: {exc}")

    found_quarters = [o.quarter for o in outcomes if o.status == "found"]
    missing_quarters = [o.quarter for o in outcomes if o.status == "not_found"]
    errors = [f"{o.quarter}: {o.detail}" for o in outcomes if o.status == "error" and o.detail]
    discovery_audit.selected_count = len(outcomes)

    if not transcripts:
        warnings.append("No Motley Fool transcripts were parsed for the selected ticker.")

    diagnostics = TranscriptFetchDiagnostics(
        requested_quarters=[o.quarter for o in outcomes],
        found_quarters=found_quarters,
        missing_quarters=missing_quarters,
        errors=errors,
        outcomes=outcomes,
    )

    return transcripts, warnings, diagnostics, discovery_audit


def fetch_last_4_transcripts(
    symbol: str,
    settings: Settings,
) -> Tuple[list[TranscriptRecord], list[str], TranscriptFetchDiagnostics]:
    transcripts, warnings, diagnostics, _ = fetch_transcripts_motley_fool(
        symbol=symbol,
        company_name=None,
        settings=settings,
        target_count=4,
    )
    return transcripts, warnings, diagnostics


def _parse_news_score(raw: Any) -> float:
    try:
        return float(raw)
    except Exception:
        return 0.0


def _dedupe_news(records: list[NewsRecord]) -> list[NewsRecord]:
    by_url: dict[str, NewsRecord] = {}
    by_title: dict[str, NewsRecord] = {}
    ordered: list[NewsRecord] = []

    for record in records:
        if record.url in by_url:
            continue
        title_key = _normalize_title_key(record.title)
        if title_key in by_title:
            continue

        by_url[record.url] = record
        by_title[title_key] = record
        ordered.append(record)

    return ordered


def _news_relevance(
    *,
    symbol: str,
    company_name: Optional[str],
    item: dict[str, Any],
    title: str,
    summary: str,
) -> float:
    text = f"{title} {summary}".lower()
    symbol_l = symbol.lower()
    score = 0.0

    ticker_sentiment = item.get("ticker_sentiment")
    if isinstance(ticker_sentiment, list):
        for row in ticker_sentiment:
            if not isinstance(row, dict):
                continue
            row_ticker = str(row.get("ticker") or "").upper()
            if row_ticker != symbol.upper():
                continue
            relevance_raw = row.get("relevance_score")
            try:
                relevance = float(relevance_raw)
            except Exception:
                relevance = 0.0
            score += 3.0 + (relevance * 4.0)
            break

    if _contains_symbol(text, symbol):
        score += 2.5

    if company_name:
        company_l = company_name.lower().strip()
        if company_l and company_l in text:
            score += 2.0
        token_hits = sum(1 for tok in _company_tokens(company_name) if tok in text)
        score += min(token_hits, 4) * 0.45

    finance_hits = sum(1 for term in _FINANCE_TERMS if term in text)
    if finance_hits:
        score += min(finance_hits, 5) * 0.18

    if score < 0.9:
        return 0.0
    return round(score, 4)


def fetch_news_alpha_vantage(
    symbol: str,
    settings: Settings,
    limit: int = 12,
    pool_size: int = 50,
    company_name: Optional[str] = None,
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
) -> Tuple[list[NewsRecord], list[str], FeedFetchAudit]:
    warnings: list[str] = []

    if not settings.alpha_vantage_api_key:
        return [], ["ALPHAVANTAGE_API_KEY is missing in .env"], FeedFetchAudit(0, 0, 0)

    try:
        payload = _alpha_get(
            {
                "function": "NEWS_SENTIMENT",
                "tickers": symbol,
                "sort": "LATEST",
                "limit": str(max(pool_size, limit)),
                "apikey": settings.alpha_vantage_api_key,
            },
            settings.request_timeout_seconds,
        )
    except Exception as exc:
        return [], [f"Alpha Vantage news error for {symbol}: {exc}"], FeedFetchAudit(0, 0, 0)

    feed = payload.get("feed")
    if not isinstance(feed, list):
        return [], [f"No Alpha Vantage news feed available for {symbol}"], FeedFetchAudit(0, 0, 0)

    now_utc = datetime.now(timezone.utc)
    lookback_floor = now_utc - timedelta(days=max(lookback_days, 1))

    scored_records: list[tuple[float, NewsRecord]] = []
    for item in feed[: max(pool_size, limit)]:
        if not isinstance(item, dict):
            continue

        title = str(item.get("title") or "Untitled").strip()
        summary = str(item.get("summary") or "").strip()
        url = str(item.get("url") or "").strip()
        if not url or not title:
            continue

        published_dt = _safe_parse_date(item.get("time_published"))
        if published_dt and published_dt.tzinfo is None:
            published_dt = published_dt.replace(tzinfo=timezone.utc)
        if published_dt and published_dt < lookback_floor:
            continue

        relevance = _news_relevance(
            symbol=symbol,
            company_name=company_name,
            item=item,
            title=title,
            summary=summary,
        )
        if relevance <= 0:
            continue

        recency = _recency_weight(published_dt, lookback_days)
        rank_score = round(relevance * 0.72 + recency * 1.28, 4)

        score = _parse_news_score(item.get("overall_sentiment_score"))
        label = str(item.get("overall_sentiment_label") or "neutral")

        scored_records.append(
            (
                rank_score,
                NewsRecord(
                    title=title,
                    summary=summary,
                    url=url,
                    source=item.get("source"),
                    time_published=item.get("time_published"),
                    sentiment_score=score,
                    sentiment_label=label,
                ),
            )
        )

    scored_records.sort(key=lambda row: row[0], reverse=True)
    strict = [record for score, record in scored_records if score >= _MIN_NEWS_RELEVANCE]
    if len(strict) < max(4, limit // 2):
        strict = [record for score, record in scored_records if score >= 0.75]
    if len(strict) < max(3, limit // 3):
        strict = [record for _, record in scored_records]

    records = strict
    deduped = _dedupe_news(records)
    shown = deduped[:limit]

    if not shown:
        warnings.append(f"No Alpha Vantage news items returned for {symbol}")

    return shown, warnings, FeedFetchAudit(fetched_pool=len(records), deduped_pool=len(deduped), displayed_count=len(shown))


def _finance_relevance_score(
    symbol: str,
    title: str,
    body: str,
    subreddit: Optional[str],
) -> float:
    text = f"{title} {body}".lower()
    symbol_l = symbol.lower()

    score = 0.0
    score += 3.0 * len(re.findall(rf"\b{re.escape(symbol_l)}\b", text))
    score += 2.0 * text.count(f"${symbol_l}")

    for term in _FINANCE_TERMS:
        if term in text:
            score += 0.4

    if subreddit:
        score += _FINANCE_SUBREDDIT_WEIGHTS.get(subreddit.lower(), 0.0)

    return score


def _is_social_related(
    *,
    symbol: str,
    company_name: Optional[str],
    title: str,
    body: str,
) -> bool:
    text = f"{title} {body}".lower()
    symbol_hit = _contains_symbol(text, symbol)

    company_hit = False
    token_hits = 0
    if company_name:
        company_l = company_name.lower().strip()
        company_hit = bool(company_l and company_l in text)
        token_hits = sum(1 for tok in _company_tokens(company_name) if tok in text)

    if symbol_hit or company_hit:
        return True

    finance_hits = sum(1 for term in _FINANCE_TERMS if term in text)
    return token_hits >= 2 and finance_hits >= 1


def _excerpt(text: str, max_chars: int = 160) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""

    first_sentence = re.split(r"(?<=[.!?])\s+", text)[0].strip()
    if first_sentence and len(first_sentence) <= max_chars:
        return first_sentence

    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _social_similar(a: SocialRecord, b: SocialRecord) -> bool:
    if a.url == b.url:
        return True
    if _normalize_title_key(a.title) == _normalize_title_key(b.title):
        return True
    ratio = SequenceMatcher(a=_normalize_title_key(a.title), b=_normalize_title_key(b.title)).ratio()
    return ratio >= 0.93


def _dedupe_social(records: list[SocialRecord]) -> list[SocialRecord]:
    kept: list[SocialRecord] = []
    for record in records:
        if any(_social_similar(record, existing) for existing in kept):
            continue
        kept.append(record)
    return kept


def fetch_social_reddit(
    symbol: str,
    settings: Settings,
    limit: int = 12,
    pool_size: int = 80,
    company_name: Optional[str] = None,
    lookback_days: int = _DEFAULT_LOOKBACK_DAYS,
) -> Tuple[list[SocialRecord], list[str], FeedFetchAudit]:
    warnings: list[str] = []
    query = f"\"{symbol}\" OR \"${symbol}\" OR \"{symbol} stock\" OR \"{symbol} earnings\""
    endpoint = "https://www.reddit.com/search.json"

    try:
        response = requests.get(
            endpoint,
            params={
                "q": query,
                "sort": "new",
                "limit": str(max(pool_size, limit * 2)),
                "type": "link",
                "t": "month",
            },
            headers={"User-Agent": "finbert-earnings-signals/1.0"},
            timeout=settings.request_timeout_seconds,
        )
        if response.status_code != 200:
            return [], [f"Reddit social feed error for {symbol}: HTTP {response.status_code}"], FeedFetchAudit(0, 0, 0)

        payload = response.json()
        data = payload.get("data", {})
        children = data.get("children", [])
        if not isinstance(children, list):
            return [], [f"No Reddit social posts available for {symbol}"], FeedFetchAudit(0, 0, 0)

        records: list[SocialRecord] = []
        now = datetime.now(timezone.utc)
        lookback_floor = now - timedelta(days=max(lookback_days, 1))
        for child in children:
            post = child.get("data", {}) if isinstance(child, dict) else {}
            title = str(post.get("title") or "").strip()
            body = str(post.get("selftext") or "").strip()
            permalink = str(post.get("permalink") or "").strip()
            subreddit = str(post.get("subreddit") or "").strip() or None
            created_utc = int(post.get("created_utc")) if post.get("created_utc") else None

            if not title:
                continue

            if created_utc:
                created_dt = datetime.fromtimestamp(created_utc, tz=timezone.utc)
                if created_dt < lookback_floor:
                    continue
            else:
                created_dt = None

            if not _is_social_related(
                symbol=symbol,
                company_name=company_name,
                title=title,
                body=body,
            ):
                continue

            url = f"https://www.reddit.com{permalink}" if permalink else "https://www.reddit.com"
            relevance = _finance_relevance_score(symbol, title, body, subreddit)
            recency = _recency_weight(created_dt, lookback_days)
            relevance = round(relevance + (recency * 2.0), 3)

            body_for_excerpt = body if body else title

            records.append(
                SocialRecord(
                    source="reddit",
                    title=title,
                    body=body,
                    excerpt=_excerpt(body_for_excerpt),
                    url=url,
                    subreddit=subreddit,
                    created_utc=created_utc,
                    relevance_score=relevance,
                )
            )

        records.sort(key=lambda r: (r.relevance_score, r.created_utc or 0), reverse=True)
        deduped = _dedupe_social(records)
        ranked = [record for record in deduped if record.relevance_score >= max(_MIN_SOCIAL_RELEVANCE, 2.2)]
        if len(ranked) < max(3, min(limit, 5)):
            ranked = [record for record in deduped if record.relevance_score >= _MIN_SOCIAL_RELEVANCE]
        if len(ranked) < max(2, limit // 3):
            ranked = deduped

        shown = ranked[:limit]

        if not shown:
            warnings.append(f"No Reddit posts found for {symbol} in the recent window.")

        return shown, warnings, FeedFetchAudit(fetched_pool=len(records), deduped_pool=len(deduped), displayed_count=len(shown))
    except Exception as exc:
        return [], [f"Reddit social feed error for {symbol}: {exc}"], FeedFetchAudit(0, 0, 0)


def fetch_price_volume_history(symbol: str, period: str = "3mo") -> list[PriceVolumeRecord]:
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period=period)
        if not isinstance(history, pd.DataFrame) or history.empty:
            return []

        out: list[PriceVolumeRecord] = []
        for idx, row in history.iterrows():
            try:
                ts = pd.Timestamp(idx)
                out.append(
                    PriceVolumeRecord(
                        date=ts.strftime("%Y-%m-%d"),
                        close=float(row.get("Close") or 0.0),
                        volume=float(row.get("Volume") or 0.0),
                    )
                )
            except Exception:
                continue
        return out
    except Exception:
        return []


def _find_series_row(
    frame: Optional[pd.DataFrame],
    candidate_names: list[str],
    max_cols: int = 4,
) -> Dict[str, Optional[float]]:
    if frame is None or frame.empty:
        return {}

    for name in candidate_names:
        if name in frame.index:
            row = frame.loc[name]
            if hasattr(row, "iloc"):
                values = row.iloc[:max_cols]
                out: Dict[str, Optional[float]] = {}
                for idx, value in values.items():
                    ts = pd.Timestamp(idx)
                    q = _quarter_from_month(int(ts.month))
                    key = _quarter_label(int(ts.year), q)
                    out[key] = float(value) if pd.notna(value) else None
                return out
    return {}


def _safe_growth(newer: Optional[float], older: Optional[float]) -> Optional[float]:
    if newer is None or older in (None, 0):
        return None
    return ((newer - older) / abs(older)) * 100.0


def fetch_fundamentals(symbol: str) -> dict[str, Any]:
    ticker = yf.Ticker(symbol)

    info: dict[str, Any] = {}
    try:
        info = ticker.info or {}
    except Exception:
        info = {}

    try:
        income_stmt = ticker.quarterly_income_stmt
    except Exception:
        income_stmt = None

    revenue_map = _find_series_row(income_stmt, ["Total Revenue", "Revenue"])
    net_income_map = _find_series_row(income_stmt, ["Net Income", "NetIncome"])

    eps_map: Dict[str, Dict[str, Optional[float]]] = {}
    try:
        earnings = ticker.get_earnings_dates(limit=16)
        if isinstance(earnings, pd.DataFrame) and not earnings.empty:
            window = earnings.sort_index(ascending=False).head(12)
            for idx, row in window.iterrows():
                ts = pd.Timestamp(idx)
                label = _quarter_label(int(ts.year), _quarter_from_month(int(ts.month)))
                reported = float(row["Reported EPS"]) if pd.notna(row.get("Reported EPS")) else None
                estimate = float(row["EPS Estimate"]) if pd.notna(row.get("EPS Estimate")) else None

                if label not in eps_map:
                    eps_map[label] = {"reported": reported, "estimate": estimate}
                    continue

                if eps_map[label].get("reported") is None and reported is not None:
                    eps_map[label]["reported"] = reported
                if eps_map[label].get("estimate") is None and estimate is not None:
                    eps_map[label]["estimate"] = estimate
    except Exception:
        eps_map = {}

    quarters = sorted(
        set(revenue_map.keys()) | set(net_income_map.keys()) | set(eps_map.keys()),
        reverse=True,
    )[:4]

    snapshots: list[dict[str, Any]] = []
    for q in quarters:
        eps_entry = eps_map.get(q, {})
        snapshots.append(
            {
                "quarter": q,
                "revenue": revenue_map.get(q),
                "net_income": net_income_map.get(q),
                "reported_eps": eps_entry.get("reported"),
                "eps_estimate": eps_entry.get("estimate"),
            }
        )

    revenue_qoq = None
    eps_qoq = None
    if len(snapshots) >= 2:
        revenue_qoq = _safe_growth(snapshots[0].get("revenue"), snapshots[1].get("revenue"))
        eps_qoq = _safe_growth(snapshots[0].get("reported_eps"), snapshots[1].get("reported_eps"))

    company_name = (
        info.get("longName")
        or info.get("shortName")
        or info.get("displayName")
        or symbol
    )

    return {
        "company_name": company_name,
        "currency": info.get("currency"),
        "market_cap": info.get("marketCap"),
        "trailing_pe": info.get("trailingPE"),
        "forward_pe": info.get("forwardPE"),
        "debt_to_equity": info.get("debtToEquity"),
        "quarterly": snapshots,
        "revenue_qoq_growth_pct": revenue_qoq,
        "eps_qoq_growth_pct": eps_qoq,
    }
