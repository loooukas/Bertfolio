"""Transcript pipeline adapter for analysis.

Bridges deterministic Motley discovery/scrape output into provider-compatible
records expected by the core analysis flow.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable, Optional

from .openai_motley_search import discover_last_quarter_links, scrape_recent_transcripts_for_report
from .providers import (
    TranscriptDiscoveryAudit,
    TranscriptFetchDiagnostics,
    TranscriptFetchOutcome,
    TranscriptRecord,
    fetch_transcripts_motley_fool,
)
from .settings import Settings


def _parse_quarter_label(label: str) -> tuple[Optional[int], Optional[int]]:
    try:
        year_part, quarter_part = label.split("-Q", 1)
        year = int(year_part)
        quarter = int(quarter_part)
        if quarter not in (1, 2, 3, 4):
            return None, None
        return year, quarter
    except Exception:
        return None, None


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _speaker_sections_to_text(scraped: dict[str, Any]) -> str:
    sections = scraped.get("speaker_sections")
    lines: list[str] = []
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            speaker = str(section.get("speaker") or "Unknown").strip() or "Unknown"
            text = str(section.get("text") or "").strip()
            if not text:
                continue
            lines.append(f"{speaker}: {text}")
    if lines:
        return "\n".join(lines)
    raw_text = str(scraped.get("raw_text") or "").strip()
    return raw_text


def _section_quality_warnings(scraped: dict[str, Any]) -> list[str]:
    out: list[str] = []
    quality_flags = scraped.get("quality_flags")
    if isinstance(quality_flags, dict):
        low_conf = bool(quality_flags.get("parser_low_confidence"))
        low_reason = str(quality_flags.get("parser_low_confidence_reason") or "").strip()
        if low_conf:
            out.append(
                "Low-confidence section parse"
                + (f" ({low_reason})" if low_reason else "")
                + "."
            )
        openai_error = str(quality_flags.get("openai_error") or "").strip()
        if openai_error:
            out.append(f"OpenAI structuring fallback error: {openai_error}")
        browser_error = str(quality_flags.get("browser_error") or "").strip()
        if browser_error:
            out.append(f"Browser fallback note: {browser_error}")
    parse_method = str(scraped.get("section_parse_method") or "").strip()
    parse_reason = str(scraped.get("section_parse_reason") or "").strip()
    if parse_method:
        out.append(f"Section parse method: {parse_method}")
    if parse_reason:
        out.append(f"Section parse reason: {parse_reason}")
    return out


def _extraction_confidence(scraped: dict[str, Any]) -> float:
    parse_method = str(scraped.get("section_parse_method") or "").strip()
    quality_flags = scraped.get("quality_flags") if isinstance(scraped.get("quality_flags"), dict) else {}
    low_conf = bool(quality_flags.get("parser_low_confidence"))
    if parse_method in {"openai", "openai_page_text"}:
        return 0.92
    if low_conf:
        return 0.52
    if parse_method.startswith("regex"):
        return 0.78
    return 0.70


def _discovery_pages_scanned(report: dict[str, Any]) -> int:
    pages = 0
    trace = report.get("discovery_trace")
    phases = trace.get("phases") if isinstance(trace, dict) else None
    if isinstance(phases, list):
        for phase in phases:
            if not isinstance(phase, dict):
                continue
            phase_name = str(phase.get("phase") or "")
            if phase_name == "sitemap":
                pages += _safe_int(phase.get("months_scanned"), 0)
            else:
                pages += _safe_int(phase.get("pages_scanned"), 0)
    return pages


def _discovery_failures(report: dict[str, Any], scrape_payload: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    trace = report.get("discovery_trace")
    phases = trace.get("phases") if isinstance(trace, dict) else None
    if isinstance(phases, list):
        for phase in phases:
            if not isinstance(phase, dict):
                continue
            phase_name = str(phase.get("phase") or "unknown")
            phase_failures = phase.get("failures")
            if not isinstance(phase_failures, list):
                continue
            for item in phase_failures:
                if not isinstance(item, dict):
                    continue
                category = str(item.get("category") or "unknown_error")
                error = str(item.get("error") or "").strip()
                if error:
                    failures.append(f"{phase_name}:{category}: {error}")

    scrape_errors = scrape_payload.get("scrape_errors")
    if isinstance(scrape_errors, list):
        for item in scrape_errors:
            if not isinstance(item, dict):
                continue
            quarter = str(item.get("quarter") or "unknown")
            category = str(item.get("error_category") or "unknown_error")
            error = str(item.get("error") or "").strip()
            if error:
                failures.append(f"scrape:{quarter}:{category}: {error}")

    return failures[:50]


def _build_provider_payload_from_motley_pipeline(
    *,
    symbol: str,
    report: dict[str, Any],
    scrape_payload: dict[str, Any],
    target_count: int,
) -> tuple[list[TranscriptRecord], list[str], TranscriptFetchDiagnostics, TranscriptDiscoveryAudit]:
    warnings: list[str] = []

    report_warnings = report.get("warnings")
    if isinstance(report_warnings, list):
        warnings.extend(str(item) for item in report_warnings if str(item).strip())

    requested_quarters = [
        str(item).strip()
        for item in (report.get("requested_quarters") or [])
        if str(item).strip()
    ]
    quarter_rows = report.get("quarters") if isinstance(report.get("quarters"), list) else []

    scraped_list = scrape_payload.get("scraped_transcripts")
    scraped_items = scraped_list if isinstance(scraped_list, list) else []

    transcripts_by_quarter: dict[str, TranscriptRecord] = {}
    for item in scraped_items:
        if not isinstance(item, dict):
            continue
        quarter_label = str(item.get("quarter") or "").strip()
        if not quarter_label:
            continue
        year, quarter = _parse_quarter_label(quarter_label)
        if year is None or quarter is None:
            continue

        text = _speaker_sections_to_text(item)
        if not text.strip():
            warnings.append(f"{quarter_label}: scraped transcript had empty speaker text.")
            continue

        participants = item.get("participants")
        participant_rows: list[dict[str, str]] = []
        if isinstance(participants, list):
            for participant in participants[:30]:
                if not isinstance(participant, dict):
                    continue
                name = str(participant.get("name") or "").strip()
                if not name:
                    continue
                participant_rows.append(
                    {
                        "name": name,
                        "role": str(participant.get("role") or "").strip(),
                    }
                )

        parsing_warnings = _section_quality_warnings(item)
        for note in parsing_warnings:
            warnings.append(f"{quarter_label}: {note}")

        transcripts_by_quarter[quarter_label] = TranscriptRecord(
            symbol=symbol,
            year=year,
            quarter=quarter,
            date=str(item.get("published_date") or "").strip() or None,
            content=text,
            source="motley_cli_pipeline",
            source_url=str(item.get("url") or "").strip() or None,
            title=str(item.get("title") or "").strip() or None,
            extraction_confidence=_extraction_confidence(item),
            parsing_warnings=parsing_warnings,
            participants=participant_rows,
        )

    ordered_transcripts: list[TranscriptRecord] = []
    for quarter_label in requested_quarters:
        record = transcripts_by_quarter.get(quarter_label)
        if record:
            ordered_transcripts.append(record)
    if len(ordered_transcripts) < target_count:
        for quarter_label, record in transcripts_by_quarter.items():
            if quarter_label in requested_quarters:
                continue
            ordered_transcripts.append(record)
    transcripts = ordered_transcripts[:target_count]

    scrape_errors = scrape_payload.get("scrape_errors")
    scrape_error_map: dict[str, dict[str, Any]] = {}
    if isinstance(scrape_errors, list):
        for item in scrape_errors:
            if not isinstance(item, dict):
                continue
            quarter_label = str(item.get("quarter") or "").strip()
            if not quarter_label:
                continue
            scrape_error_map[quarter_label] = item
            err = str(item.get("error") or "").strip()
            if err:
                warnings.append(f"{quarter_label}: scrape error: {err}")

    outcomes: list[TranscriptFetchOutcome] = []
    transcript_quarters = {f"{record.year}-Q{record.quarter}" for record in transcripts}

    quarter_row_map: dict[str, dict[str, Any]] = {}
    for row in quarter_rows:
        if not isinstance(row, dict):
            continue
        label = str(row.get("quarter") or "").strip()
        if label:
            quarter_row_map[label] = row

    for quarter_label in requested_quarters:
        if quarter_label in transcript_quarters:
            outcomes.append(TranscriptFetchOutcome(quarter=quarter_label, status="found"))
            continue
        scrape_error = scrape_error_map.get(quarter_label)
        if scrape_error:
            outcomes.append(
                TranscriptFetchOutcome(
                    quarter=quarter_label,
                    status="error",
                    detail=str(scrape_error.get("error") or "").strip() or "Scrape error.",
                )
            )
            continue
        row = quarter_row_map.get(quarter_label)
        if row and str(row.get("status") or "").strip() == "not_found":
            outcomes.append(
                TranscriptFetchOutcome(
                    quarter=quarter_label,
                    status="not_found",
                    detail="No transcript URL resolved during discovery.",
                )
            )
            continue
        outcomes.append(
            TranscriptFetchOutcome(
                quarter=quarter_label,
                status="not_found",
                detail="Transcript was not available after discovery and scrape.",
            )
        )

    requested_set = set(requested_quarters)
    for quarter_label, scrape_error in scrape_error_map.items():
        if quarter_label in requested_set:
            continue
        outcomes.append(
            TranscriptFetchOutcome(
                quarter=quarter_label,
                status="error",
                detail=str(scrape_error.get("error") or "").strip() or "Scrape error.",
            )
        )

    found_quarters = [outcome.quarter for outcome in outcomes if outcome.status == "found"]
    missing_quarters = [outcome.quarter for outcome in outcomes if outcome.status == "not_found"]
    errors = [
        f"{outcome.quarter}: {outcome.detail}"
        for outcome in outcomes
        if outcome.status == "error" and outcome.detail
    ]

    diagnostics = TranscriptFetchDiagnostics(
        requested_quarters=requested_quarters or [outcome.quarter for outcome in outcomes],
        found_quarters=found_quarters,
        missing_quarters=missing_quarters,
        errors=errors,
        outcomes=outcomes,
    )

    fetch_failures = _discovery_failures(report, scrape_payload)
    playwright_used = any(
        isinstance(item, dict) and str(item.get("scrape_method") or "") == "browser"
        for item in scraped_items
    )
    discovery = TranscriptDiscoveryAudit(
        pages_scanned=_discovery_pages_scanned(report),
        candidates_total=_safe_int(report.get("raw_candidate_count"), 0),
        transcript_like_count=_safe_int(report.get("accepted_candidate_count"), 0),
        match_filtered_count=_safe_int(report.get("accepted_candidate_count"), 0),
        selected_count=len(outcomes),
        discarded_near_matches=[
            str(item)
            for item in warnings
            if "off-ticker" in str(item).lower() or "dropped" in str(item).lower()
        ][:25],
        fetch_failures=fetch_failures,
        playwright_fallback_used=playwright_used,
    )

    if not transcripts:
        warnings.append("No Motley transcripts were parsed for the selected ticker.")

    return transcripts, warnings, diagnostics, discovery


def _fetch_transcripts_motley_cli(
    *,
    symbol: str,
    settings: Settings,
    target_count: int,
    log_fn: Optional[Callable[[str], None]] = None,
) -> tuple[list[TranscriptRecord], list[str], TranscriptFetchDiagnostics, TranscriptDiscoveryAudit]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for transcript pipeline mode 'motley_cli'.")

    def _cache_mode_for_run(configured_mode: str) -> str:
        if not getattr(settings, "use_cache", True):
            return "off"
        normalized = str(configured_mode or "use").strip().lower()
        if normalized not in {"refresh", "use", "off"}:
            return "use"
        return "use" if normalized == "off" else normalized

    discovery_report = discover_last_quarter_links(
        ticker=symbol,
        api_key=settings.openai_api_key,
        model=settings.openai_search_model,
        timeout_seconds=settings.motley_timeout_seconds,
        target_quarters=max(1, target_count),
        retry_attempts=settings.motley_openai_retries,
        discovery_mode=settings.motley_discovery_mode,
        sitemap_lookback_months=settings.motley_sitemap_lookback_months,
        author_max_pages=settings.motley_author_max_pages,
        discovery_cache_mode=_cache_mode_for_run(settings.motley_discovery_cache_mode),
        discovery_cache_dir=settings.motley_discovery_cache_dir,
        log_fn=log_fn,
    )

    scrape_payload = scrape_recent_transcripts_for_report(
        report=discovery_report,
        scrape_count=max(target_count, settings.motley_scrape_count),
        timeout_seconds=settings.motley_timeout_seconds,
        api_key=settings.openai_api_key,
        model=settings.openai_search_model,
        retry_attempts=settings.motley_openai_retries,
        cache_mode=_cache_mode_for_run(settings.motley_scrape_cache_mode),
        cache_dir=settings.motley_scrape_cache_dir,
        log_fn=log_fn,
    )

    return _build_provider_payload_from_motley_pipeline(
        symbol=symbol,
        report=discovery_report,
        scrape_payload=scrape_payload,
        target_count=target_count,
    )


def _append_fallback_context(
    *,
    reason: str,
    legacy_payload: tuple[list[TranscriptRecord], list[str], TranscriptFetchDiagnostics, TranscriptDiscoveryAudit],
) -> tuple[list[TranscriptRecord], list[str], TranscriptFetchDiagnostics, TranscriptDiscoveryAudit]:
    transcripts, warnings, diagnostics, discovery = legacy_payload
    fallback_note = f"Deterministic Motley pipeline fallback to legacy provider: {reason}"
    warnings = [fallback_note] + list(warnings)

    diagnostics_dict = asdict(diagnostics)
    diagnostics_dict["errors"] = [fallback_note] + list(diagnostics_dict.get("errors") or [])
    diagnostics_dict["outcomes"] = [
        *diagnostics_dict.get("outcomes", []),
        {"quarter": "pipeline", "status": "error", "detail": fallback_note},
    ]
    diagnostics = TranscriptFetchDiagnostics(
        requested_quarters=list(diagnostics_dict.get("requested_quarters") or []),
        found_quarters=list(diagnostics_dict.get("found_quarters") or []),
        missing_quarters=list(diagnostics_dict.get("missing_quarters") or []),
        errors=list(diagnostics_dict.get("errors") or []),
        outcomes=[
            TranscriptFetchOutcome(
                quarter=str(item.get("quarter") or ""),
                status=str(item.get("status") or "error"),
                detail=str(item.get("detail") or "") or None,
            )
            for item in diagnostics_dict.get("outcomes", [])
            if isinstance(item, dict)
        ],
    )

    discovery_dict = asdict(discovery)
    discovery_dict["fetch_failures"] = [fallback_note] + list(discovery_dict.get("fetch_failures") or [])
    discovery = TranscriptDiscoveryAudit(
        pages_scanned=_safe_int(discovery_dict.get("pages_scanned"), 0),
        candidates_total=_safe_int(discovery_dict.get("candidates_total"), 0),
        transcript_like_count=_safe_int(discovery_dict.get("transcript_like_count"), 0),
        match_filtered_count=_safe_int(discovery_dict.get("match_filtered_count"), 0),
        selected_count=_safe_int(discovery_dict.get("selected_count"), 0),
        discarded_near_matches=list(discovery_dict.get("discarded_near_matches") or []),
        fetch_failures=list(discovery_dict.get("fetch_failures") or []),
        playwright_fallback_used=bool(discovery_dict.get("playwright_fallback_used")),
    )
    return transcripts, warnings, diagnostics, discovery


def fetch_transcripts_for_analysis(
    *,
    symbol: str,
    company_name: Optional[str],
    settings: Settings,
    target_count: int,
    log_fn: Optional[Callable[[str], None]] = None,
) -> tuple[list[TranscriptRecord], list[str], TranscriptFetchDiagnostics, TranscriptDiscoveryAudit]:
    mode = str(settings.transcript_pipeline_mode or "motley_cli").strip().lower()
    if mode not in {"motley_cli", "legacy"}:
        mode = "motley_cli"

    if mode == "legacy":
        return fetch_transcripts_motley_fool(
            symbol=symbol,
            company_name=company_name,
            settings=settings,
            target_count=target_count,
        )

    try:
        return _fetch_transcripts_motley_cli(
            symbol=symbol,
            settings=settings,
            target_count=target_count,
            log_fn=log_fn,
        )
    except Exception as exc:
        if not settings.transcript_pipeline_fallback_to_legacy:
            raise
        return _append_fallback_context(
            reason=str(exc),
            legacy_payload=fetch_transcripts_motley_fool(
                symbol=symbol,
                company_name=company_name,
                settings=settings,
                target_count=target_count,
            ),
        )
