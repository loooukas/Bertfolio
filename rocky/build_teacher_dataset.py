#!/usr/bin/env python3
"""Build a block-level teacher-label dataset from existing transcript pipeline logic."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import re
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rocky.common import (
    append_jsonl,
    build_sample_id,
    build_transcript_id,
    clean_text,
    count_words,
    ensure_dir,
    iso_now_utc,
    parse_ticker_inputs,
    quarter_label,
    read_json,
    write_json,
)


DEFAULT_OUTPUT_DIR = "output/teacher_dataset"
DEFAULT_MAX_TRANSCRIPTS = 100
DEFAULT_TRANSCRIPTS_PER_TICKER = 4
DEFAULT_MIN_USEFUL_CHARS = 90
DEFAULT_MIN_USEFUL_WORDS = 14

_SUBSTANTIVE_KEYWORDS = {
    "guidance",
    "outlook",
    "expect",
    "forecast",
    "margin",
    "margins",
    "revenue",
    "eps",
    "demand",
    "bookings",
    "backlog",
    "pipeline",
    "headwind",
    "risk",
    "pricing",
    "cash flow",
    "free cash flow",
    "capex",
    "opex",
    "year over year",
    "quarter over quarter",
}
_SUBSTANTIVE_RE = re.compile(
    r"\b(?:guidance|outlook|expect|forecast|margin|revenue|eps|demand|bookings|backlog|pipeline|risk|headwind|cash flow|capex|opex)\b",
    flags=re.IGNORECASE,
)
_LEGAL_RE = re.compile(
    r"(?:forward-looking statements?|safe harbor|sec|form\s+10-[kq]|risk factors?|non-gaap|reconciliation)",
    flags=re.IGNORECASE,
)
_ADMIN_RE = re.compile(
    r"(?:next question|please go ahead|line is open|conference call|operator instructions|joining us today|turn the call over|opening remarks|closing remarks)",
    flags=re.IGNORECASE,
)
_ACK_RE = re.compile(r"^(?:thanks?|thank you|okay|great|good morning|good afternoon)[.! ]*$", flags=re.IGNORECASE)
_OPERATOR_HINT_RE = re.compile(r"\b(operator|moderator|host)\b", flags=re.IGNORECASE)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build block-level teacher-label dataset from transcript pipeline.")
    parser.add_argument("--tickers", nargs="*", help="Tickers, either space-separated or comma-separated.")
    parser.add_argument("--tickers-file", help="File containing one ticker per line (or comma-separated rows).")
    parser.add_argument(
        "--max-transcripts",
        type=int,
        default=DEFAULT_MAX_TRANSCRIPTS,
        help=f"Cap total processed transcripts (default: {DEFAULT_MAX_TRANSCRIPTS}).",
    )
    parser.add_argument(
        "--transcripts-per-ticker",
        type=int,
        default=DEFAULT_TRANSCRIPTS_PER_TICKER,
        help=f"Target transcripts fetched per ticker call (default: {DEFAULT_TRANSCRIPTS_PER_TICKER}).",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument("--resume", action="store_true", help="Resume from existing run_manifest.json.")
    return parser.parse_args(argv)


def _new_manifest(args: argparse.Namespace, tickers: list[str]) -> dict[str, Any]:
    return {
        "pipeline": "rocky_teacher_dataset_v1",
        "status": "running",
        "started_at": iso_now_utc(),
        "updated_at": iso_now_utc(),
        "arguments": {
            "tickers": tickers,
            "max_transcripts": int(args.max_transcripts),
            "transcripts_per_ticker": int(args.transcripts_per_ticker),
            "output_dir": str(args.output_dir),
            "resume": bool(args.resume),
        },
        "processed_transcript_ids": [],
        "counts": {
            "transcripts_processed": 0,
            "blocks_full": 0,
            "blocks_labelable": 0,
            "blocks_skipped_default": 0,
            "ticker_errors": 0,
        },
        "ticker_results": {},
        "errors": [],
        "labeling": {},
    }


def _validate_fresh_run(output_dir: Path) -> None:
    collision_paths = [
        output_dir / "blocks_full.jsonl",
        output_dir / "blocks_labelable.jsonl",
        output_dir / "run_manifest.json",
    ]
    existing = [path for path in collision_paths if path.exists()]
    if existing:
        joined = ", ".join(str(path) for path in existing)
        raise RuntimeError(
            f"Output files already exist ({joined}). Re-run with --resume or choose a different --output-dir."
        )


def _load_manifest(args: argparse.Namespace, output_dir: Path, tickers: list[str]) -> dict[str, Any]:
    manifest_path = output_dir / "run_manifest.json"
    if args.resume:
        existing = read_json(manifest_path)
        if existing is None:
            raise RuntimeError(f"--resume was set but manifest does not exist: {manifest_path}")
        existing["status"] = "running"
        existing["updated_at"] = iso_now_utc()
        return existing

    _validate_fresh_run(output_dir)
    return _new_manifest(args, tickers)


def _is_operator_or_host_like(*, speaker: str, speaker_role: str | None, text: str) -> bool:
    speaker_text = str(speaker or "")
    role_text = str(speaker_role or "").strip().lower()
    if role_text in {"operator", "host_ir"}:
        return True
    if _OPERATOR_HINT_RE.search(speaker_text):
        return True
    lowered = text.lower()
    return "next question" in lowered or "line is open" in lowered


def _looks_substantive(text: str) -> bool:
    lowered = text.lower()
    if re.search(r"\d", lowered):
        return True
    if _SUBSTANTIVE_RE.search(lowered):
        return True
    return any(keyword in lowered for keyword in _SUBSTANTIVE_KEYWORDS)


def _skip_flags(
    *,
    speaker: str,
    speaker_role: str | None,
    section_type: str,
    text: str,
    char_count: int,
    word_count: int,
) -> tuple[bool, bool, bool, list[str]]:
    reasons: list[str] = []
    compact = clean_text(text)
    is_short_block = char_count < DEFAULT_MIN_USEFUL_CHARS or word_count < DEFAULT_MIN_USEFUL_WORDS
    is_operator_or_host_like = _is_operator_or_host_like(
        speaker=speaker,
        speaker_role=speaker_role,
        text=compact,
    )
    substantive = _looks_substantive(compact)

    if not compact or char_count < 12:
        reasons.append("malformed_or_empty")
    if _ACK_RE.match(compact):
        reasons.append("tiny_acknowledgment")
    if _LEGAL_RE.search(compact):
        reasons.append("legal_disclaimer_fragment")
    if _ADMIN_RE.search(compact):
        reasons.append("procedural_or_admin")
    if is_operator_or_host_like and not substantive:
        reasons.append("operator_or_host_fluff")
    if is_short_block and not substantive:
        reasons.append("too_short")
    if section_type == "other" and not substantive:
        reasons.append("low_value_other_section")

    deduped_reasons = list(dict.fromkeys(reasons))
    return bool(deduped_reasons), is_short_block, is_operator_or_host_like, deduped_reasons


def _flatten_document(
    *,
    transcript_id: str,
    transcript_quarter: str | None,
    document_dict: dict[str, Any],
) -> list[dict[str, Any]]:
    sections = list(document_dict.get("sections") or [])
    sections = sorted(sections, key=lambda row: int(row.get("order_index", 0)))
    participants = list(document_dict.get("participants") or [])
    participant_names = [str(p.get("name") or "").strip() for p in participants if str(p.get("name") or "").strip()]
    participant_roles = {
        str(p.get("name") or "").strip(): str(p.get("role") or "").strip()
        for p in participants
        if str(p.get("name") or "").strip() and str(p.get("role") or "").strip()
    }
    transcript_has_qa = any(str(section.get("section_type") or "") == "qa" for section in sections)
    qa_order_indices = [int(section.get("order_index", 0)) for section in sections if section.get("section_type") == "qa"]
    total_blocks = len(sections)

    rows: list[dict[str, Any]] = []
    for idx, section in enumerate(sections):
        speaker = str(section.get("speaker") or "").strip() or "Unknown"
        speaker_role = str(section.get("speaker_role") or "").strip() or None
        section_type = str(section.get("section_type") or "other")
        order_index = int(section.get("order_index", idx))
        text = clean_text(str(section.get("text") or ""))
        char_count = len(text)
        word_count = count_words(text)

        previous_section = sections[idx - 1] if idx > 0 else None
        next_section = sections[idx + 1] if idx + 1 < total_blocks else None
        previous_order_index = int(previous_section.get("order_index", idx - 1)) if previous_section else None
        next_order_index = int(next_section.get("order_index", idx + 1)) if next_section else None

        previous_sample_id = (
            build_sample_id(transcript_id=transcript_id, order_index=previous_order_index)
            if previous_order_index is not None
            else None
        )
        next_sample_id = (
            build_sample_id(transcript_id=transcript_id, order_index=next_order_index)
            if next_order_index is not None
            else None
        )

        should_skip, is_short_block, is_operator_or_host_like, skip_reasons = _skip_flags(
            speaker=speaker,
            speaker_role=speaker_role,
            section_type=section_type,
            text=text,
            char_count=char_count,
            word_count=word_count,
        )

        sample_id = build_sample_id(transcript_id=transcript_id, order_index=order_index)
        previous_speaker = str(previous_section.get("speaker") or "").strip() if previous_section else None
        next_speaker = str(next_section.get("speaker") or "").strip() if next_section else None
        previous_role = str(previous_section.get("speaker_role") or "").strip() if previous_section else None
        next_role = str(next_section.get("speaker_role") or "").strip() if next_section else None
        previous_section_type = str(previous_section.get("section_type") or "").strip() if previous_section else None
        next_section_type = str(next_section.get("section_type") or "").strip() if next_section else None

        row = {
            "sample_id": sample_id,
            "ticker": document_dict.get("ticker"),
            "company_name": document_dict.get("company_name"),
            "quarter": transcript_quarter,
            "published_date": document_dict.get("published_date"),
            "transcript_source_url": document_dict.get("source_url"),
            "transcript_id": transcript_id,
            "speaker": speaker,
            "canonical_speaker": speaker,
            "speaker_role": speaker_role,
            "section_type": section_type,
            "order_index": order_index,
            "text": text,
            "char_count": char_count,
            "word_count": word_count,
            "previous_speaker": previous_speaker,
            "next_speaker": next_speaker,
            "previous_role": previous_role or None,
            "next_role": next_role or None,
            "previous_section_type": previous_section_type or None,
            "next_section_type": next_section_type or None,
            "transcript_has_qa": transcript_has_qa,
            "is_short_block": is_short_block,
            "is_operator_or_host_like": is_operator_or_host_like,
            "should_skip_labeling": should_skip,
            "skip_reasons": skip_reasons,
            "metadata": {
                "transcript_position_index": idx,
                "transcript_total_blocks": total_blocks,
                "adjacent_sample_ids": {
                    "previous_sample_id": previous_sample_id,
                    "next_sample_id": next_sample_id,
                },
                "qa_pairing_hints": {
                    "is_qa_block": section_type == "qa",
                    "qa_order_indices": qa_order_indices,
                    "has_question_mark": "?" in text,
                    "prev_role": previous_role or None,
                    "next_role": next_role or None,
                    "prev_section_type": previous_section_type or None,
                    "next_section_type": next_section_type or None,
                },
                "participant_names": participant_names,
                "participant_roles": participant_roles,
                "evidence_snippets": list(section.get("evidence_snippets") or []),
                "normalization_mode": document_dict.get("normalization_mode"),
            },
        }
        rows.append(row)
    return rows


def _raw_envelope_payload(
    *,
    ticker: str,
    transcript_id: str,
    transcript_quarter: str | None,
    record: Any,
    fetch_context_file: str,
    normalization_warnings: list[str],
) -> dict[str, Any]:
    return {
        "transcript_id": transcript_id,
        "ticker": ticker,
        "quarter": transcript_quarter,
        "year": record.year,
        "quarter_num": record.quarter,
        "company_name": None,
        "source": record.source,
        "source_url": record.source_url,
        "title": record.title,
        "published_date": record.date,
        "extraction_confidence": record.extraction_confidence,
        "parsing_warnings": list(record.parsing_warnings or []),
        "participants": list(record.participants or []),
        "content": record.content,
        "normalization_warnings": normalization_warnings,
        "fetch_context_file": fetch_context_file,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    from finbert_site.normalizer import normalize_transcript_document
    from finbert_site.settings import Settings
    from finbert_site.transcript_pipeline import fetch_transcripts_for_analysis

    tickers = parse_ticker_inputs(inline_tickers=args.tickers, tickers_file=args.tickers_file)
    if not tickers:
        raise RuntimeError("No tickers available after parsing inputs.")

    output_dir = Path(args.output_dir)
    raw_root = output_dir / "raw_transcripts"
    normalized_root = output_dir / "normalized_transcripts"
    blocks_full_path = output_dir / "blocks_full.jsonl"
    blocks_labelable_path = output_dir / "blocks_labelable.jsonl"
    manifest_path = output_dir / "run_manifest.json"

    ensure_dir(output_dir)
    ensure_dir(raw_root)
    ensure_dir(normalized_root)

    manifest = _load_manifest(args, output_dir, tickers)
    processed_transcript_ids = set(manifest.get("processed_transcript_ids") or [])
    counts = manifest.setdefault("counts", {})
    counts.setdefault("transcripts_processed", len(processed_transcript_ids))
    counts.setdefault("blocks_full", 0)
    counts.setdefault("blocks_labelable", 0)
    counts.setdefault("blocks_skipped_default", 0)
    counts.setdefault("ticker_errors", 0)

    settings = Settings()
    max_transcripts = max(1, int(args.max_transcripts))
    per_ticker = max(1, int(args.transcripts_per_ticker))

    print(
        f"[rocky] Starting teacher dataset build | tickers={len(tickers)} max_transcripts={max_transcripts} resume={args.resume}"
    )

    for ticker in tickers:
        if len(processed_transcript_ids) >= max_transcripts:
            break

        remaining = max_transcripts - len(processed_transcript_ids)
        target_count = min(per_ticker, remaining)
        ticker_dir = raw_root / ticker
        ensure_dir(ticker_dir)
        ensure_dir(normalized_root / ticker)

        print(f"[rocky] Fetching transcripts for {ticker} (target={target_count}, remaining={remaining})")
        try:
            transcript_records, warnings, diagnostics, discovery = fetch_transcripts_for_analysis(
                symbol=ticker,
                company_name=None,
                settings=settings,
                target_count=target_count,
            )
        except Exception as exc:
            counts["ticker_errors"] = int(counts.get("ticker_errors", 0)) + 1
            error_payload = {
                "ticker": ticker,
                "stage": "fetch",
                "error": str(exc),
                "timestamp": iso_now_utc(),
            }
            manifest.setdefault("errors", []).append(error_payload)
            manifest["ticker_results"][ticker] = {
                "status": "error",
                "error": str(exc),
                "updated_at": iso_now_utc(),
            }
            manifest["updated_at"] = iso_now_utc()
            write_json(manifest_path, manifest)
            print(f"[rocky] Fetch failed for {ticker}: {exc}")
            continue

        fetch_stamp = re.sub(r"[^0-9T]", "", iso_now_utc().replace(":", "").replace("-", ""))
        fetch_file = ticker_dir / f"fetch_{fetch_stamp}.json"
        fetch_payload = {
            "ticker": ticker,
            "fetched_at": iso_now_utc(),
            "target_count": target_count,
            "transcripts_found": len(transcript_records),
            "warnings": list(warnings or []),
            "diagnostics": asdict(diagnostics),
            "discovery_audit": asdict(discovery),
        }
        write_json(fetch_file, fetch_payload)
        fetch_context_file = str(fetch_file.relative_to(output_dir))

        processed_for_ticker = 0
        for idx, record in enumerate(transcript_records):
            if len(processed_transcript_ids) >= max_transcripts:
                break
            transcript_quarter = quarter_label(record.year, record.quarter)
            transcript_id = build_transcript_id(
                ticker=ticker,
                year=record.year,
                quarter=record.quarter,
                published_date=record.date,
                source_url=record.source_url,
                title=record.title,
                ordinal_hint=idx,
            )
            if transcript_id in processed_transcript_ids:
                continue

            normalized_result = normalize_transcript_document(
                ticker=ticker,
                company_name=None,
                source=record.source,
                source_url=record.source_url,
                title=record.title,
                published_date=record.date,
                content=record.content,
                extraction_confidence=record.extraction_confidence,
                parsing_warnings=record.parsing_warnings,
                participants=record.participants,
                management_roster=[],
                settings=settings,
            )
            document = normalized_result.document
            document_dict = document.model_dump()

            raw_envelope = _raw_envelope_payload(
                ticker=ticker,
                transcript_id=transcript_id,
                transcript_quarter=transcript_quarter,
                record=record,
                fetch_context_file=fetch_context_file,
                normalization_warnings=list(normalized_result.warnings or []),
            )
            write_json(ticker_dir / f"{transcript_id}.json", raw_envelope)

            normalized_payload = {
                "transcript_id": transcript_id,
                "quarter": transcript_quarter,
                "normalization_warnings": list(normalized_result.warnings or []),
                "document": document_dict,
            }
            write_json(normalized_root / ticker / f"{transcript_id}.json", normalized_payload)

            block_rows = _flatten_document(
                transcript_id=transcript_id,
                transcript_quarter=transcript_quarter,
                document_dict=document_dict,
            )
            labelable_count = 0
            skipped_count = 0
            for row in block_rows:
                append_jsonl(blocks_full_path, row)
                if row.get("should_skip_labeling"):
                    skipped_count += 1
                else:
                    append_jsonl(blocks_labelable_path, row)
                    labelable_count += 1

            processed_transcript_ids.add(transcript_id)
            processed_for_ticker += 1
            counts["transcripts_processed"] = len(processed_transcript_ids)
            counts["blocks_full"] = int(counts.get("blocks_full", 0)) + len(block_rows)
            counts["blocks_labelable"] = int(counts.get("blocks_labelable", 0)) + labelable_count
            counts["blocks_skipped_default"] = int(counts.get("blocks_skipped_default", 0)) + skipped_count

            manifest["processed_transcript_ids"] = sorted(processed_transcript_ids)
            manifest["ticker_results"][ticker] = {
                "status": "ok",
                "updated_at": iso_now_utc(),
                "transcripts_returned": len(transcript_records),
                "transcripts_processed_this_run": processed_for_ticker,
                "warnings": list(warnings or []),
                "diagnostics_missing_quarters": list(getattr(diagnostics, "missing_quarters", []) or []),
                "discovery_failures": list(getattr(discovery, "fetch_failures", []) or []),
            }
            manifest["updated_at"] = iso_now_utc()
            write_json(manifest_path, manifest)

            print(
                "[rocky] transcript="
                f"{transcript_id} blocks={len(block_rows)} labelable={labelable_count} skipped={skipped_count}"
            )

    manifest["status"] = "completed"
    manifest["updated_at"] = iso_now_utc()
    write_json(manifest_path, manifest)
    print(
        "[rocky] Done."
        f" transcripts={counts.get('transcripts_processed', 0)}"
        f" blocks_full={counts.get('blocks_full', 0)}"
        f" blocks_labelable={counts.get('blocks_labelable', 0)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
