#!/usr/bin/env python3
"""Label block-level rows using LM Studio's OpenAI-compatible API."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
import time
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rocky.common import append_jsonl, ensure_dir, iso_now_utc, iter_jsonl, load_existing_sample_ids, read_json, write_json
from rocky.label_schema import TEACHER_LABEL_JSON_SCHEMA, validate_teacher_label


DEFAULT_BASE_URL = "http://127.0.0.1:1234/v1"
DEFAULT_API_KEY = "lm-studio"
DEFAULT_OUTPUT_DIR = "output/teacher_dataset"
DEFAULT_INPUT_JSONL = "output/teacher_dataset/blocks_labelable.jsonl"

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", flags=re.IGNORECASE)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Label block-level rows via LM Studio.")
    parser.add_argument("--input-jsonl", default=DEFAULT_INPUT_JSONL, help=f"Input block rows (default: {DEFAULT_INPUT_JSONL}).")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).")
    parser.add_argument("--model", required=True, help="LM Studio model identifier.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help=f"OpenAI-compatible base URL (default: {DEFAULT_BASE_URL}).")
    parser.add_argument("--api-key", default=DEFAULT_API_KEY, help=f"API key placeholder (default: {DEFAULT_API_KEY}).")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature (default: 0).")
    parser.add_argument("--timeout-seconds", type=float, default=45.0, help="Request timeout seconds.")
    parser.add_argument("--retries", type=int, default=3, help="Retries for malformed/unparseable output.")
    parser.add_argument("--max-rows", type=int, default=0, help="Limit rows per run (0 means all available).")
    parser.add_argument("--resume", action="store_true", help="Resume from existing labeled output.")
    parser.add_argument("--skip-labeled", action="store_true", help="Skip rows already present in labeled output.")
    parser.add_argument("--system-prompt-file", help="Optional system prompt file; omit to rely on LM Studio configured prompt.")
    return parser.parse_args(argv)


def _extract_json_payload(content: Any) -> dict[str, Any]:
    if isinstance(content, dict):
        return content
    if isinstance(content, list):
        joined: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    joined.append(str(item.get("text") or ""))
                elif "text" in item:
                    joined.append(str(item.get("text") or ""))
            else:
                joined.append(str(item))
        content = "\n".join(joined)
    if not isinstance(content, str):
        raise ValueError("Model response content is not text.")
    cleaned = _JSON_FENCE_RE.sub("", content.strip()).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("Model response JSON must be an object.")
    return parsed


def _build_messages(*, row: dict[str, Any], system_prompt: str | None) -> list[dict[str, str]]:
    block_payload = {
        "sample_id": row.get("sample_id"),
        "ticker": row.get("ticker"),
        "company_name": row.get("company_name"),
        "quarter": row.get("quarter"),
        "published_date": row.get("published_date"),
        "transcript_source_url": row.get("transcript_source_url"),
        "transcript_id": row.get("transcript_id"),
        "speaker": row.get("speaker"),
        "speaker_role": row.get("speaker_role"),
        "section_type": row.get("section_type"),
        "order_index": row.get("order_index"),
        "text": row.get("text"),
        "char_count": row.get("char_count"),
        "word_count": row.get("word_count"),
        "previous_speaker": row.get("previous_speaker"),
        "next_speaker": row.get("next_speaker"),
        "previous_role": row.get("previous_role"),
        "next_role": row.get("next_role"),
        "previous_section_type": row.get("previous_section_type"),
        "next_section_type": row.get("next_section_type"),
        "transcript_has_qa": row.get("transcript_has_qa"),
        "metadata": row.get("metadata"),
    }
    user_message = (
        "Label this single earnings-call speaker block for communication and dataset quality.\n"
        "Return only JSON matching the provided schema.\n"
        "Use evidence snippets from this block text.\n\n"
        f"{json.dumps(block_payload, ensure_ascii=False)}"
    )

    messages: list[dict[str, str]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_message})
    return messages


def _request_label(
    *,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float,
    timeout_seconds: float,
    retries: int,
    messages: list[dict[str, str]],
) -> tuple[dict[str, Any] | None, str | None]:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    attempt_messages = list(messages)
    json_schema_enabled = True
    last_error = ""
    last_raw_text = ""

    for attempt in range(max(0, retries) + 1):
        payload = {
            "model": model,
            "temperature": float(temperature),
            "messages": attempt_messages,
        }
        if json_schema_enabled:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "teacher_label_v1",
                    "strict": True,
                    "schema": TEACHER_LABEL_JSON_SCHEMA,
                },
            }
        else:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=max(5.0, float(timeout_seconds)))
            if response.status_code >= 400:
                lowered = response.text.lower()
                if json_schema_enabled and "response_format" in lowered:
                    json_schema_enabled = False
                    last_error = f"LM Studio did not accept json_schema response_format: {response.text[:500]}"
                    time.sleep(0.25)
                    continue
                response.raise_for_status()

            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                raise ValueError("Model response had no choices.")
            content = choices[0].get("message", {}).get("content")
            last_raw_text = json.dumps(content, ensure_ascii=False) if isinstance(content, (dict, list)) else str(content or "")
            parsed = _extract_json_payload(content)
            validated = validate_teacher_label(parsed)
            return validated, None
        except Exception as exc:
            last_error = str(exc)
            if attempt >= retries:
                break
            # Retry malformed JSON by asking for strict JSON only.
            correction_note = (
                "Your previous response was invalid for the schema. "
                "Return only a single valid JSON object matching the required fields."
            )
            attempt_messages = list(messages) + [{"role": "user", "content": correction_note}]
            time.sleep(0.5 * (2 ** attempt))

    error_text = last_error or "Unknown LM Studio labeling error."
    if last_raw_text:
        error_text = f"{error_text} | last_raw={last_raw_text[:500]}"
    return None, error_text


def _load_rows(path: Path) -> list[dict[str, Any]]:
    return list(iter_jsonl(path))


def _load_system_prompt(path: str | None) -> str | None:
    if not path:
        return None
    prompt_path = Path(path)
    return prompt_path.read_text(encoding="utf-8").strip()


def _load_or_init_manifest(path: Path) -> dict[str, Any]:
    manifest = read_json(path)
    if manifest is None:
        return {
            "pipeline": "rocky_teacher_dataset_v1",
            "status": "running",
            "started_at": iso_now_utc(),
            "updated_at": iso_now_utc(),
            "counts": {},
            "ticker_results": {},
            "errors": [],
            "labeling": {},
        }
    manifest["status"] = "running"
    manifest["updated_at"] = iso_now_utc()
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_path = Path(args.input_jsonl)
    if not input_path.exists():
        raise RuntimeError(f"Input rows not found: {input_path}")

    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)
    labeled_path = output_dir / "labeled_blocks.jsonl"
    failures_path = output_dir / "failures.jsonl"
    manifest_path = output_dir / "run_manifest.json"

    system_prompt = _load_system_prompt(args.system_prompt_file)
    rows = _load_rows(input_path)
    if not rows:
        print(f"[rocky] No rows found in {input_path}")
        return 0

    skip_existing = bool(args.resume or args.skip_labeled)
    already_labeled: set[str] = set()
    if skip_existing:
        already_labeled = load_existing_sample_ids(labeled_path)

    manifest = _load_or_init_manifest(manifest_path)
    labeling_state = manifest.setdefault("labeling", {})
    run_state = {
        "started_at": iso_now_utc(),
        "updated_at": iso_now_utc(),
        "input_jsonl": str(input_path),
        "model": args.model,
        "base_url": args.base_url,
        "skip_existing": skip_existing,
        "max_rows": int(args.max_rows),
        "attempted": 0,
        "succeeded": 0,
        "failed": 0,
    }

    candidates: list[dict[str, Any]] = []
    for row in rows:
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id:
            continue
        if skip_existing and sample_id in already_labeled:
            continue
        candidates.append(row)

    if args.max_rows and args.max_rows > 0:
        candidates = candidates[: args.max_rows]

    print(
        "[rocky] Labeling rows via LM Studio"
        f" model={args.model} candidates={len(candidates)} skip_existing={skip_existing}"
    )

    for row in candidates:
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id:
            continue

        messages = _build_messages(row=row, system_prompt=system_prompt)
        label_payload, error = _request_label(
            base_url=args.base_url,
            api_key=args.api_key,
            model=args.model,
            temperature=args.temperature,
            timeout_seconds=args.timeout_seconds,
            retries=max(0, int(args.retries)),
            messages=messages,
        )

        run_state["attempted"] = int(run_state["attempted"]) + 1
        run_state["updated_at"] = iso_now_utc()

        if label_payload is None:
            run_state["failed"] = int(run_state["failed"]) + 1
            failure_row = {
                "failed_at": iso_now_utc(),
                "sample_id": sample_id,
                "transcript_id": row.get("transcript_id"),
                "ticker": row.get("ticker"),
                "model": args.model,
                "error": error,
            }
            append_jsonl(failures_path, failure_row)
            manifest.setdefault("errors", []).append(
                {
                    "stage": "labeling",
                    "sample_id": sample_id,
                    "error": error,
                    "timestamp": iso_now_utc(),
                }
            )
            print(f"[rocky] label failed sample={sample_id}: {error}")
        else:
            run_state["succeeded"] = int(run_state["succeeded"]) + 1
            output_row = {
                **row,
                "teacher_label": label_payload,
                "label_model": args.model,
                "label_base_url": args.base_url,
                "labeled_at": iso_now_utc(),
            }
            append_jsonl(labeled_path, output_row)
            already_labeled.add(sample_id)
            print(f"[rocky] labeled sample={sample_id}")

        labeling_state["last_run"] = dict(run_state)
        labeling_state["last_run"]["completed_at"] = iso_now_utc()
        manifest["updated_at"] = iso_now_utc()
        write_json(manifest_path, manifest)

    manifest["status"] = "completed"
    manifest["updated_at"] = iso_now_utc()
    labeling_state["last_run"] = dict(run_state)
    labeling_state["last_run"]["completed_at"] = iso_now_utc()
    write_json(manifest_path, manifest)

    print(
        "[rocky] Labeling done."
        f" attempted={run_state['attempted']}"
        f" succeeded={run_state['succeeded']}"
        f" failed={run_state['failed']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

