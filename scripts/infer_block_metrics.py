#!/usr/bin/env python3
"""Run a trained block metric classifier on block rows for local inference."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Iterable

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rocky.training_utils import BAND_LABELS, BAND_TO_SCORE_DEFAULT, build_input_text, iter_jsonl, write_jsonl


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infer one metric over block rows with a trained student model.")
    parser.add_argument("--model-dir", required=True, help="Directory containing trained model/tokenizer.")
    parser.add_argument("--input", required=True, help="Input JSONL block rows or normalized transcript JSON.")
    parser.add_argument("--output", required=True, help="Output predictions JSONL.")
    parser.add_argument("--metric", required=True, help="Metric this model predicts.")
    parser.add_argument("--max-length", type=int, default=384, help="Tokenizer max length.")
    parser.add_argument("--batch-size", type=int, default=8, help="Inference batch size.")
    parser.add_argument("--max-rows", type=int, default=0, help="Optional cap on input rows.")
    return parser.parse_args(argv)


def _resolve_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _flatten_normalized_document(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if "document" in payload and isinstance(payload["document"], dict):
        document = payload["document"]
        transcript_id = str(payload.get("transcript_id") or "")
    else:
        document = payload
        transcript_id = str(payload.get("transcript_id") or "")

    sections = document.get("sections") if isinstance(document, dict) else None
    if not isinstance(sections, list):
        return []

    out: list[dict[str, Any]] = []
    for idx, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        order_index = int(section.get("order_index", idx))
        sample_id = f"{transcript_id}::b{order_index:04d}" if transcript_id else f"sample::{order_index:04d}"
        out.append(
            {
                "sample_id": sample_id,
                "ticker": payload.get("ticker") or document.get("ticker"),
                "transcript_id": transcript_id,
                "speaker": section.get("speaker"),
                "speaker_role": section.get("speaker_role"),
                "section_type": section.get("section_type"),
                "text": section.get("text"),
                "metadata": {
                    "order_index": order_index,
                    "source": payload.get("source") or document.get("source"),
                    "source_url": payload.get("source_url") or document.get("source_url"),
                    "published_date": payload.get("published_date") or document.get("published_date"),
                },
            }
        )
    return out


def _load_input_rows(path: Path, max_rows: int) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        out: list[dict[str, Any]] = []
        for idx, row in enumerate(iter_jsonl(path), start=1):
            out.append(row)
            if max_rows > 0 and idx >= max_rows:
                break
        return out

    raw = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    if isinstance(raw, dict):
        rows = _flatten_normalized_document(raw)
    elif isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            if "text" in item:
                rows.append(item)
            else:
                rows.extend(_flatten_normalized_document(item))
    else:
        rows = []

    if max_rows > 0:
        rows = rows[:max_rows]
    return rows


class InferenceDataset(Dataset):
    def __init__(self, rows: list[dict[str, Any]], tokenizer: Any, max_length: int):
        self.rows = rows
        self.inputs = [
            str(row.get("input_text") or "")
            or build_input_text(
                speaker_role=str(row.get("speaker_role") or ""),
                section_type=str(row.get("section_type") or ""),
                text=str(row.get("text") or ""),
            )
            for row in rows
        ]
        self.encodings = tokenizer(
            self.inputs,
            truncation=True,
            max_length=max_length,
            padding=False,
        )

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        payload = {key: self.encodings[key][idx] for key in self.encodings}
        payload["row_idx"] = idx
        return payload


def _iter_predictions(
    *,
    rows: list[dict[str, Any]],
    model: Any,
    dataloader: DataLoader,
    device: torch.device,
    metric: str,
) -> Iterable[dict[str, Any]]:
    model.eval()
    with torch.no_grad():
        for batch in dataloader:
            row_idxs = batch.pop("row_idx").tolist()
            model_inputs = {key: value.to(device) for key, value in batch.items()}
            outputs = model(**model_inputs)
            probs = torch.softmax(outputs.logits.detach().cpu(), dim=1)
            preds = torch.argmax(probs, dim=1)
            for local_idx, row_idx in enumerate(row_idxs):
                row = rows[row_idx]
                pred_id = int(preds[local_idx].item())
                pred_band = BAND_LABELS[pred_id]
                prob_values = probs[local_idx].tolist()
                yield {
                    "sample_id": row.get("sample_id"),
                    "metric": metric,
                    "predicted_band": pred_band,
                    "predicted_score": BAND_TO_SCORE_DEFAULT.get(pred_band),
                    "predicted_probabilities": {
                        label: float(prob_values[idx]) for idx, label in enumerate(BAND_LABELS)
                    },
                    "predicted_confidence": float(max(prob_values)),
                    "ticker": row.get("ticker"),
                    "transcript_id": row.get("transcript_id"),
                    "speaker": row.get("speaker"),
                    "speaker_role": row.get("speaker_role"),
                    "section_type": row.get("section_type"),
                    "text": row.get("text"),
                    "metadata": row.get("metadata"),
                }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    input_path = Path(args.input)
    if not input_path.exists():
        raise RuntimeError(f"Input file not found: {input_path}")

    rows = _load_input_rows(input_path, max_rows=max(0, int(args.max_rows)))
    rows = [row for row in rows if str(row.get("text") or "").strip() or str(row.get("input_text") or "").strip()]
    if not rows:
        raise RuntimeError("No valid rows found for inference.")

    device = _resolve_device()
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, use_fast=True)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_dir).to(device)

    dataset = InferenceDataset(rows, tokenizer, max_length=int(args.max_length))
    collator = DataCollatorWithPadding(tokenizer=tokenizer, padding=True, return_tensors="pt")
    dataloader = DataLoader(dataset, batch_size=int(args.batch_size), shuffle=False, collate_fn=collator)

    predictions = list(
        _iter_predictions(
            rows=rows,
            model=model,
            dataloader=dataloader,
            device=device,
            metric=args.metric,
        )
    )
    write_jsonl(Path(args.output), predictions)
    print(f"[infer] Done metric={args.metric} rows={len(predictions)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
