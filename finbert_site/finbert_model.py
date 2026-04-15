"""Local FinBERT model wrapper."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer


class FinBertEngine:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_name)

        if torch.backends.mps.is_available():
            self.device = torch.device("mps")
        else:
            self.device = torch.device("cpu")

        self.model.to(self.device)
        self.model.eval()

        # Normalize labels from model config to lower-case keys.
        self.index_to_label = {
            int(k): str(v).lower()
            for k, v in getattr(self.model.config, "id2label", {0: "positive", 1: "negative", 2: "neutral"}).items()
        }

    def score_text(self, text: str, chunk_size: int = 510) -> dict[str, float]:
        tokens = self.tokenizer.encode(text, add_special_tokens=False)
        if not tokens:
            return {
                "positive": 0.0,
                "negative": 0.0,
                "neutral": 1.0,
                "directional_score": 0.0,
                "label": "mixed",
            }

        all_scores: list[np.ndarray] = []

        for i in range(0, len(tokens), chunk_size):
            chunk = tokens[i : i + chunk_size]
            chunk = [self.tokenizer.cls_token_id] + chunk + [self.tokenizer.sep_token_id]

            input_ids = torch.tensor([chunk], device=self.device)
            attention_mask = torch.ones_like(input_ids, device=self.device)

            with torch.no_grad():
                outputs = self.model(input_ids=input_ids, attention_mask=attention_mask)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1)
                all_scores.append(probs.squeeze().detach().cpu().numpy())

        avg_scores = np.mean(np.array(all_scores), axis=0)

        label_scores = {"positive": 0.0, "negative": 0.0, "neutral": 0.0}
        for idx, value in enumerate(avg_scores.tolist()):
            label = self.index_to_label.get(idx, "neutral")
            if label in label_scores:
                label_scores[label] = float(value)

        directional_score = label_scores["positive"] - label_scores["negative"]
        if directional_score > 0.25:
            label = "cautiously_positive"
        elif directional_score < -0.25:
            label = "weakly_negative"
        else:
            label = "mixed"

        return {
            **label_scores,
            "directional_score": float(directional_score),
            "label": label,
        }

    def classify_sentences(self, sentences: List[str], batch_size: int = 16) -> List[Dict[str, Any]]:
        if not sentences:
            return []

        results: List[Dict[str, Any]] = []

        for i in range(0, len(sentences), batch_size):
            batch = sentences[i : i + batch_size]
            encoded = self.tokenizer(
                batch,
                truncation=True,
                max_length=512,
                padding=True,
                return_tensors="pt",
            )
            encoded = {key: value.to(self.device) for key, value in encoded.items()}

            with torch.no_grad():
                outputs = self.model(**encoded)
                probs = torch.nn.functional.softmax(outputs.logits, dim=-1).detach().cpu().numpy()

            for sentence, row in zip(batch, probs):
                scored_labels = []
                for idx, score in enumerate(row.tolist()):
                    label = self.index_to_label.get(idx, "neutral")
                    scored_labels.append((label, float(score)))
                best_label, best_score = max(scored_labels, key=lambda x: x[1])
                results.append(
                    {
                        "sentence": sentence,
                        "label": best_label,
                        "score": best_score,
                        "positive": dict(scored_labels).get("positive", 0.0),
                        "negative": dict(scored_labels).get("negative", 0.0),
                        "neutral": dict(scored_labels).get("neutral", 0.0),
                    }
                )

        return results


@lru_cache(maxsize=1)
def get_engine(model_name: str) -> FinBertEngine:
    return FinBertEngine(model_name=model_name)
