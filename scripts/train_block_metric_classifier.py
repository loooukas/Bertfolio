#!/usr/bin/env python3
"""Train a block-level student classifier for one communication metric."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import math
from pathlib import Path
import random
import sys
from typing import Any

import numpy as np
import torch
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset
from transformers import (
    AutoModelForSequenceClassification,
    AutoTokenizer,
    DataCollatorWithPadding,
    get_linear_schedule_with_warmup,
)

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rocky.training_utils import (
    LABEL_MODES,
    METRICS,
    compute_classification_metrics,
    get_metric_band,
    labels_for_mode,
    normalize_label_mode,
    read_jsonl,
    write_json,
)


MODEL_ALIASES = {
    "modernbert-base": "answerdotai/ModernBERT-base",
    "deberta-v3-base": "microsoft/deberta-v3-base",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train one block-level metric classifier.")
    parser.add_argument("--train-file", required=True, help="Prepared train.jsonl.")
    parser.add_argument("--validation-file", required=True, help="Prepared validation.jsonl.")
    parser.add_argument("--metric", required=True, choices=list(METRICS), help="Metric target to train.")
    parser.add_argument(
        "--label-mode",
        choices=list(LABEL_MODES),
        default="five_band",
        help="Band target mode: five_band | three_band | binary (default: five_band).",
    )
    parser.add_argument(
        "--model-name",
        default="deberta-v3-base",
        help="HF model name or alias: modernbert-base | deberta-v3-base.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory to save model and artifacts.")
    parser.add_argument("--epochs", type=int, default=3, help="Training epochs (default: 3).")
    parser.add_argument("--batch-size", type=int, default=8, help="Batch size (default: 8).")
    parser.add_argument(
        "--eval-batch-size",
        type=int,
        default=0,
        help="Validation batch size (default: use --batch-size).",
    )
    parser.add_argument(
        "--gradient-accumulation-steps",
        type=int,
        default=1,
        help="Gradient accumulation steps (default: 1).",
    )
    parser.add_argument("--learning-rate", type=float, default=2e-5, help="Learning rate (default: 2e-5).")
    parser.add_argument("--weight-decay", type=float, default=0.01, help="Weight decay (default: 0.01).")
    parser.add_argument("--warmup-ratio", type=float, default=0.1, help="Warmup ratio (default: 0.1).")
    parser.add_argument("--max-length", type=int, default=384, help="Tokenizer max length (default: 384).")
    parser.add_argument(
        "--device",
        choices=["auto", "mps", "cuda", "cpu"],
        default="auto",
        help="Device selection (default: auto).",
    )
    parser.add_argument(
        "--mps-memory-fraction",
        type=float,
        default=0.0,
        help="Optional per-process MPS memory fraction in (0,1], e.g. 0.75.",
    )
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument("--max-train-rows", type=int, default=0, help="Optional cap on train rows.")
    parser.add_argument("--max-validation-rows", type=int, default=0, help="Optional cap on validation rows.")
    return parser.parse_args(argv)


def _resolve_model_name(raw: str) -> str:
    key = raw.strip()
    return MODEL_ALIASES.get(key, key)


def _set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def _resolve_device(preference: str) -> torch.device:
    pref = preference.strip().lower()
    if pref == "auto":
        if torch.backends.mps.is_available():
            return torch.device("mps")
        if torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")
    if pref == "mps":
        if not torch.backends.mps.is_available():
            raise RuntimeError("Requested --device mps but MPS is not available.")
        return torch.device("mps")
    if pref == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError("Requested --device cuda but CUDA is not available.")
        return torch.device("cuda")
    if pref == "cpu":
        return torch.device("cpu")
    return torch.device("cpu")


def _configure_mps_memory(device: torch.device, fraction: float) -> None:
    if device.type != "mps":
        return
    if fraction <= 0:
        return
    if fraction > 1:
        raise RuntimeError("--mps-memory-fraction must be in (0, 1].")
    torch.mps.set_per_process_memory_fraction(float(fraction))
    print(f"[train] Set MPS per-process memory fraction={fraction:.3f}")


def _load_tokenizer_with_fallback(model_name: str) -> Any:
    try:
        return AutoTokenizer.from_pretrained(model_name, use_fast=True)
    except Exception as exc:
        print(f"[train] Fast tokenizer load failed for {model_name}: {exc}")
        print("[train] Falling back to slow tokenizer.")
        try:
            # Some DeBERTa tokenizer configs force the Fast class even with use_fast=False.
            if "deberta-v3" in model_name.lower() or "deberta-v2" in model_name.lower():
                try:
                    import sentencepiece  # noqa: F401
                except Exception as sp_exc:
                    raise RuntimeError(
                        "DeBERTa slow tokenizer requires `sentencepiece`. "
                        "Install it with `.venv/bin/pip install sentencepiece`."
                    ) from sp_exc
                from transformers.models.deberta_v2.tokenization_deberta_v2 import DebertaV2Tokenizer

                return DebertaV2Tokenizer.from_pretrained(model_name)
            return AutoTokenizer.from_pretrained(model_name, use_fast=False)
        except Exception as slow_exc:
            raise RuntimeError(
                f"Tokenizer load failed for {model_name}. fast_error={exc} slow_error={slow_exc}"
            ) from slow_exc


@dataclass
class Example:
    text: str
    label_id: int


def _build_label_maps(label_mode: str) -> tuple[tuple[str, ...], dict[str, int], dict[int, str]]:
    labels = labels_for_mode(label_mode)
    label_to_id = {label: idx for idx, label in enumerate(labels)}
    id_to_label = {idx: label for label, idx in label_to_id.items()}
    return labels, label_to_id, id_to_label


def _load_examples(
    path: Path,
    *,
    metric: str,
    label_mode: str,
    label_to_id: dict[str, int],
    max_rows: int = 0,
) -> list[Example]:
    rows = read_jsonl(path, max_rows=max_rows)
    examples: list[Example] = []
    missing = 0
    for row in rows:
        text = str(row.get("input_text") or "").strip()
        band = get_metric_band(row, metric, label_mode=label_mode)
        if not text or band not in label_to_id:
            missing += 1
            continue
        examples.append(Example(text=text, label_id=label_to_id[band]))
    if not examples:
        raise RuntimeError(f"No valid examples found in {path} for metric={metric}.")
    if missing:
        print(f"[train] Skipped malformed rows from {path.name}: {missing}")
    return examples


class TextDataset(Dataset):
    def __init__(self, examples: list[Example], tokenizer: Any, max_length: int):
        self.examples = examples
        self.encodings = tokenizer(
            [item.text for item in examples],
            truncation=True,
            max_length=max_length,
            padding=False,
        )

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict[str, Any]:
        payload = {key: self.encodings[key][idx] for key in self.encodings}
        payload["labels"] = self.examples[idx].label_id
        return payload


def _evaluate(
    *,
    model: Any,
    dataloader: DataLoader,
    device: torch.device,
    label_names: tuple[str, ...],
) -> dict[str, Any]:
    model.eval()
    y_true: list[int] = []
    y_pred: list[int] = []
    losses: list[float] = []
    with torch.no_grad():
        for batch in dataloader:
            target_labels = batch["labels"].to(device)
            model_inputs = {key: value.to(device) for key, value in batch.items() if key != "labels"}
            outputs = model(**model_inputs, labels=target_labels)
            losses.append(float(outputs.loss.detach().cpu().item()))
            logits = outputs.logits.detach().cpu()
            preds = torch.argmax(logits, dim=1)
            y_true.extend(target_labels.detach().cpu().tolist())
            y_pred.extend(preds.tolist())

    metrics = compute_classification_metrics(y_true=y_true, y_pred=y_pred, labels=label_names)
    metrics["loss"] = float(sum(losses) / len(losses)) if losses else math.nan
    return metrics


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    label_mode = normalize_label_mode(str(args.label_mode))
    labels, label_to_id, id_to_label = _build_label_maps(label_mode)
    _set_seed(int(args.seed))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    model_name = _resolve_model_name(args.model_name)
    device = _resolve_device(str(args.device))
    _configure_mps_memory(device, float(args.mps_memory_fraction))
    grad_accum_steps = max(1, int(args.gradient_accumulation_steps))
    eval_batch_size = int(args.eval_batch_size) if int(args.eval_batch_size) > 0 else int(args.batch_size)

    train_examples = _load_examples(
        Path(args.train_file),
        metric=args.metric,
        label_mode=label_mode,
        label_to_id=label_to_id,
        max_rows=max(0, int(args.max_train_rows)),
    )
    validation_examples = _load_examples(
        Path(args.validation_file),
        metric=args.metric,
        label_mode=label_mode,
        label_to_id=label_to_id,
        max_rows=max(0, int(args.max_validation_rows)),
    )
    print(
        f"[train] metric={args.metric} model={model_name} device={device} "
        f"train_rows={len(train_examples)} validation_rows={len(validation_examples)} "
        f"batch={int(args.batch_size)} eval_batch={eval_batch_size} grad_accum={grad_accum_steps} "
        f"label_mode={label_mode} labels={list(labels)}"
    )

    tokenizer = _load_tokenizer_with_fallback(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(labels),
        id2label=dict(id_to_label),
        label2id=dict(label_to_id),
        ignore_mismatched_sizes=True,
    ).to(device)

    train_dataset = TextDataset(train_examples, tokenizer, max_length=int(args.max_length))
    validation_dataset = TextDataset(validation_examples, tokenizer, max_length=int(args.max_length))
    collator = DataCollatorWithPadding(tokenizer=tokenizer, padding=True, return_tensors="pt")

    train_loader = DataLoader(
        train_dataset,
        batch_size=int(args.batch_size),
        shuffle=True,
        collate_fn=collator,
    )
    validation_loader = DataLoader(
        validation_dataset,
        batch_size=eval_batch_size,
        shuffle=False,
        collate_fn=collator,
    )

    optimizer = AdamW(
        model.parameters(),
        lr=float(args.learning_rate),
        weight_decay=float(args.weight_decay),
    )
    optimizer_steps_per_epoch = math.ceil(len(train_loader) / grad_accum_steps)
    total_steps = max(1, optimizer_steps_per_epoch * max(1, int(args.epochs)))
    warmup_steps = int(total_steps * max(0.0, float(args.warmup_ratio)))
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=warmup_steps,
        num_training_steps=total_steps,
    )

    history: list[dict[str, Any]] = []
    best_state_dict: dict[str, torch.Tensor] | None = None
    best_macro_f1 = -1.0
    best_epoch = 0

    for epoch in range(1, max(1, int(args.epochs)) + 1):
        model.train()
        train_losses: list[float] = []
        optimizer.zero_grad(set_to_none=True)
        try:
            for step_idx, batch in enumerate(train_loader, start=1):
                target_labels = batch["labels"].to(device)
                model_inputs = {key: value.to(device) for key, value in batch.items() if key != "labels"}
                outputs = model(**model_inputs, labels=target_labels)
                loss = outputs.loss
                (loss / grad_accum_steps).backward()
                should_step = (step_idx % grad_accum_steps == 0) or (step_idx == len(train_loader))
                if should_step:
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    scheduler.step()
                    optimizer.zero_grad(set_to_none=True)
                train_losses.append(float(loss.detach().cpu().item()))
        except RuntimeError as exc:
            if "MPS backend out of memory" in str(exc):
                raise RuntimeError(
                    "MPS out of memory during training. Try smaller --batch-size (e.g. 2-4), "
                    "smaller --max-length (e.g. 256-320), higher --gradient-accumulation-steps "
                    "(e.g. 2-4), and/or set --mps-memory-fraction (e.g. 0.65-0.80)."
                ) from exc
            raise

        train_loss = float(sum(train_losses) / len(train_losses)) if train_losses else math.nan
        validation_metrics = _evaluate(model=model, dataloader=validation_loader, device=device, label_names=labels)
        epoch_metrics = {
            "epoch": epoch,
            "train_loss": train_loss,
            "validation": validation_metrics,
        }
        history.append(epoch_metrics)
        print(
            f"[train] epoch={epoch} train_loss={train_loss:.4f} "
            f"val_loss={validation_metrics['loss']:.4f} "
            f"val_acc={validation_metrics['accuracy']:.4f} val_macro_f1={validation_metrics['macro_f1']:.4f}"
        )

        if float(validation_metrics["macro_f1"]) > best_macro_f1:
            best_macro_f1 = float(validation_metrics["macro_f1"])
            best_epoch = epoch
            best_state_dict = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}

    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)

    model_dir = output_dir / "model"
    model_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(model_dir)
    tokenizer.save_pretrained(model_dir)

    label_mapping = {
        "labels": list(labels),
        "label2id": {label: int(idx) for label, idx in label_to_id.items()},
        "id2label": {str(idx): label for idx, label in id_to_label.items()},
        "label_mode": label_mode,
        "metric": args.metric,
    }
    write_json(output_dir / "label_mapping.json", label_mapping)

    run_config = {
        "created_at": _utc_now_iso(),
        "metric": args.metric,
        "model_name": model_name,
        "device": str(device),
        "train_file": str(args.train_file),
        "validation_file": str(args.validation_file),
        "train_rows": len(train_examples),
        "validation_rows": len(validation_examples),
        "args": vars(args),
    }
    write_json(output_dir / "training_config.json", run_config)
    write_json(output_dir / "training_history.json", {"epochs": history})

    best_validation = next((row["validation"] for row in history if row["epoch"] == best_epoch), history[-1]["validation"])
    metrics_payload = {
        "metric": args.metric,
        "best_epoch": best_epoch,
        "best_validation": best_validation,
        "history": history,
    }
    write_json(output_dir / "metrics.json", metrics_payload)

    print(
        f"[train] Done. best_epoch={best_epoch} "
        f"best_val_macro_f1={best_validation['macro_f1']:.4f} model_dir={model_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
