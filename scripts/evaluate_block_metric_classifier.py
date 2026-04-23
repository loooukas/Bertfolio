#!/usr/bin/env python3
"""Evaluate a trained block-level metric classifier on held-out data."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Any

import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, DataCollatorWithPadding

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rocky.training_utils import (
    LABEL_MODES,
    BAND_TO_SCORE_DEFAULT,
    compute_classification_metrics,
    get_metric_band,
    labels_for_mode,
    normalize_label_mode,
    read_jsonl,
    write_json,
    write_jsonl,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate a trained block-level metric classifier.")
    parser.add_argument("--model-dir", required=True, help="Directory containing trained model/tokenizer.")
    parser.add_argument("--test-file", required=True, help="Prepared test.jsonl file.")
    parser.add_argument("--output-dir", required=True, help="Evaluation artifact output directory.")
    parser.add_argument("--metric", required=True, help="Metric this model predicts.")
    parser.add_argument(
        "--label-mode",
        choices=list(LABEL_MODES),
        default="five_band",
        help="Band target mode expected by model: five_band | three_band | binary (default: five_band).",
    )
    parser.add_argument("--max-length", type=int, default=384, help="Tokenizer max length.")
    parser.add_argument("--batch-size", type=int, default=8, help="Evaluation batch size.")
    parser.add_argument("--max-rows", type=int, default=0, help="Optional cap on test rows.")
    parser.add_argument(
        "--max-error-examples",
        type=int,
        default=100,
        help="Max mismatched examples to save in error_examples.jsonl.",
    )
    return parser.parse_args(argv)


def _resolve_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _load_tokenizer_with_fallback(model_dir: str) -> Any:
    try:
        return AutoTokenizer.from_pretrained(model_dir, use_fast=True)
    except Exception as exc:
        print(f"[eval] Fast tokenizer load failed for {model_dir}: {exc}")
        print("[eval] Falling back to slow tokenizer.")
        try:
            if "deberta-v3" in model_dir.lower() or "deberta-v2" in model_dir.lower():
                try:
                    import sentencepiece  # noqa: F401
                except Exception as sp_exc:
                    raise RuntimeError(
                        "DeBERTa slow tokenizer requires `sentencepiece`. "
                        "Install it with `.venv/bin/pip install sentencepiece`."
                    ) from sp_exc
                from transformers.models.deberta_v2.tokenization_deberta_v2 import DebertaV2Tokenizer

                return DebertaV2Tokenizer.from_pretrained(model_dir)
            return AutoTokenizer.from_pretrained(model_dir, use_fast=False)
        except Exception as slow_exc:
            raise RuntimeError(
                f"Tokenizer load failed for {model_dir}. fast_error={exc} slow_error={slow_exc}"
            ) from slow_exc


class EvalDataset(Dataset):
    def __init__(
        self,
        rows: list[dict[str, Any]],
        tokenizer: Any,
        max_length: int,
        metric: str,
        label_mode: str,
        label_to_id: dict[str, int],
    ):
        self.rows = rows
        self.metric = metric
        self.label_mode = label_mode
        self.label_to_id = label_to_id
        self.encodings = tokenizer(
            [str(row.get("input_text") or "") for row in rows],
            truncation=True,
            max_length=max_length,
            padding=False,
        )

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        payload = {key: self.encodings[key][idx] for key in self.encodings}
        band = get_metric_band(self.rows[idx], self.metric, label_mode=self.label_mode)
        payload["labels"] = self.label_to_id.get(band, -1)
        payload["row_idx"] = idx
        return payload


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    label_mode = normalize_label_mode(str(args.label_mode))
    label_names = labels_for_mode(label_mode)
    label_to_id = {label: idx for idx, label in enumerate(label_names)}
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = read_jsonl(Path(args.test_file), max_rows=max(0, int(args.max_rows)))
    rows = [
        row
        for row in rows
        if get_metric_band(row, args.metric, label_mode=label_mode) in label_to_id
        and str(row.get("input_text") or "").strip()
    ]
    if not rows:
        raise RuntimeError("No valid test rows found for evaluation.")

    device = _resolve_device()
    tokenizer = _load_tokenizer_with_fallback(args.model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(args.model_dir).to(device)
    if int(getattr(model.config, "num_labels", 0)) != len(label_names):
        raise RuntimeError(
            "Model label count does not match --label-mode. "
            f"model_num_labels={getattr(model.config, 'num_labels', None)} expected={len(label_names)}"
        )
    model.eval()

    dataset = EvalDataset(
        rows,
        tokenizer,
        max_length=int(args.max_length),
        metric=args.metric,
        label_mode=label_mode,
        label_to_id=label_to_id,
    )
    collator = DataCollatorWithPadding(tokenizer=tokenizer, padding=True, return_tensors="pt")
    dataloader = DataLoader(dataset, batch_size=int(args.batch_size), shuffle=False, collate_fn=collator)

    y_true: list[int] = []
    y_pred: list[int] = []
    prediction_rows: list[dict[str, Any]] = []

    with torch.no_grad():
        for batch in dataloader:
            row_idxs = batch.pop("row_idx").tolist()
            target_labels = batch["labels"].to(device)
            model_inputs = {key: value.to(device) for key, value in batch.items()}
            outputs = model(**model_inputs)
            probs = torch.softmax(outputs.logits.detach().cpu(), dim=1)
            preds = torch.argmax(probs, dim=1)

            y_true.extend(target_labels.detach().cpu().tolist())
            y_pred.extend(preds.tolist())

            for local_idx, row_idx in enumerate(row_idxs):
                row = rows[row_idx]
                pred_id = int(preds[local_idx].item())
                prob_values = probs[local_idx].tolist()
                prob_map = {label: float(prob_values[i]) for i, label in enumerate(label_names)}
                predicted_label = label_names[pred_id]
                teacher_label = get_metric_band(row, args.metric, label_mode=label_mode)
                prediction_rows.append(
                    {
                        "sample_id": row.get("sample_id"),
                        "metric": args.metric,
                        "predicted_band": predicted_label,
                        "predicted_score": BAND_TO_SCORE_DEFAULT.get(predicted_label),
                        "predicted_probabilities": prob_map,
                        "predicted_confidence": float(max(prob_values)),
                        "teacher_band": teacher_label,
                        "teacher_score": row.get(f"target_{args.metric}_score"),
                        "text": row.get("text"),
                        "input_text": row.get("input_text"),
                        "ticker": row.get("ticker"),
                        "transcript_id": row.get("transcript_id"),
                        "speaker": row.get("speaker"),
                        "speaker_role": row.get("speaker_role"),
                        "section_type": row.get("section_type"),
                        "metadata": row.get("metadata"),
                    }
                )

    metrics = compute_classification_metrics(y_true=y_true, y_pred=y_pred, labels=label_names)
    metrics["created_at"] = _utc_now_iso()
    metrics["metric"] = args.metric
    metrics["label_mode"] = label_mode
    metrics["labels"] = list(label_names)
    metrics["rows_evaluated"] = len(prediction_rows)
    write_json(output_dir / "metrics.json", metrics)
    write_json(output_dir / "confusion_matrix.json", metrics["confusion_matrix"])
    write_jsonl(output_dir / "predictions.jsonl", prediction_rows)

    mismatches = [row for row in prediction_rows if row["predicted_band"] != row["teacher_band"]]
    mismatches.sort(key=lambda row: row["predicted_confidence"], reverse=True)
    write_jsonl(output_dir / "error_examples.jsonl", mismatches[: max(0, int(args.max_error_examples))])

    print(
        f"[eval] Done metric={args.metric} rows={len(prediction_rows)} "
        f"accuracy={metrics['accuracy']:.4f} macro_f1={metrics['macro_f1']:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
