#!/usr/bin/env python3
"""Calibrate transcript-internal and full-score weights with chronological OOS evaluation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Any, Optional

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.score_calibration_utils import (
    bucket_analysis,
    chronological_split_indices,
    classification_metrics,
    ensure_dir,
    parse_date,
    regression_metrics,
    safe_float,
    write_json,
)

DEFAULT_TRANSCRIPT_FEATURES = [
    "management_confidence",
    "management_directness",
    "management_outlook_strength",
    "management_specificity",
    "management_risk_intensity",
    "transcript_sentiment_directional_score",
]
DEFAULT_COMPONENT_FEATURES = ["fundamentals_signal", "news_signal", "social_signal"]
DEFAULT_META_COLUMNS = [
    "ticker",
    "company_name",
    "event_date",
    "quarter_label",
    "transcript_id",
    "transcript_source_url",
    "component_source",
]
TARGET_HORIZON_CHOICES = [1, 3, 5, 21, 63, 126]


@dataclass
class FeatureTransform:
    feature_columns: list[str]
    means: dict[str, float]
    stds: dict[str, float]
    standardize: bool

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        cols: list[np.ndarray] = []
        for col in self.feature_columns:
            series = pd.to_numeric(frame[col], errors="coerce") if col in frame.columns else pd.Series([np.nan] * len(frame))
            filled = series.fillna(self.means[col]).astype(float)
            arr = filled.to_numpy(dtype=float)
            if self.standardize:
                arr = (arr - self.means[col]) / self.stds[col]
            cols.append(arr)
        if not cols:
            return np.empty((len(frame), 0), dtype=float)
        return np.column_stack(cols)


@dataclass
class LinearModel:
    intercept: float
    coefficients: np.ndarray

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (X @ self.coefficients) + self.intercept


@dataclass
class LogisticModel:
    intercept: float
    coefficients: np.ndarray

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        logits = (X @ self.coefficients) + self.intercept
        logits = np.clip(logits, -35.0, 35.0)
        return 1.0 / (1.0 + np.exp(-logits))



def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Calibrate score weights with chronological out-of-sample validation.")
    parser.add_argument("--input", required=True, help="Prepared dataset CSV/JSON/JSONL.")
    parser.add_argument("--output-dir", default="output/score_calibration/calibration_run")
    parser.add_argument("--target-mode", choices=["continuous", "binary"], default="continuous")
    parser.add_argument("--target-horizon", type=int, choices=TARGET_HORIZON_CHOICES, default=3)
    parser.add_argument("--target-column", default="target")
    parser.add_argument("--split-column", default="split")
    parser.add_argument("--event-date-column", default="event_date")
    parser.add_argument("--train-fraction", type=float, default=0.60)
    parser.add_argument("--val-fraction", type=float, default=0.20)
    parser.add_argument("--min-per-split", type=int, default=10)
    parser.add_argument("--ridge-alpha", type=float, default=1.0)
    parser.add_argument("--logistic-alpha", type=float, default=1.0)
    parser.add_argument("--logistic-learning-rate", type=float, default=0.05)
    parser.add_argument("--logistic-max-iter", type=int, default=5000)
    parser.add_argument("--logistic-tol", type=float, default=1e-6)
    parser.add_argument("--binary-class-weight", choices=["none", "balanced"], default="balanced")
    parser.add_argument("--binary-threshold-metric", choices=["macro_f1", "accuracy", "precision", "recall"], default="macro_f1")
    parser.add_argument("--binary-threshold-grid-size", type=int, default=201)
    parser.add_argument(
        "--tune-binary-threshold",
        dest="tune_binary_threshold",
        action="store_true",
        default=True,
        help="Tune binary classification threshold on validation data.",
    )
    parser.add_argument(
        "--no-tune-binary-threshold",
        dest="tune_binary_threshold",
        action="store_false",
        help="Disable validation threshold tuning and use 0.5 for all binary model predictions.",
    )
    parser.add_argument("--transcript-feature-columns", help="Comma-separated transcript-internal feature list.")
    parser.add_argument("--component-feature-columns", help="Comma-separated full-score component feature list.")
    parser.add_argument("--meta-columns", help="Comma-separated metadata columns for test predictions export.")
    parser.add_argument("--handset-overall-column", default="current_handset_overall_score")
    parser.add_argument("--handset-transcript-column", default="current_handset_transcript_score")
    parser.add_argument("--enable-local-search", action="store_true", default=False)
    parser.add_argument("--local-search-samples", type=int, default=400)
    parser.add_argument("--local-search-radius", type=float, default=0.10)
    parser.add_argument("--no-progress", action="store_true", default=False, help="Disable terminal progress messages.")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def _load_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".json":
        return pd.read_json(path)
    if suffix == ".jsonl":
        return pd.read_json(path, orient="records", lines=True)
    raise RuntimeError(f"Unsupported input format: {path}")


def _target_column_from_horizon(horizon: int, mode: str) -> str:
    return f"binary_abnormal_up_{horizon}d" if mode == "binary" else f"abnormal_return_{horizon}d"


def _parse_list(raw: Optional[str], default_list: list[str]) -> list[str]:
    if not raw:
        return list(default_list)
    return [item.strip() for item in raw.split(",") if item.strip()]


def _fit_feature_transform(
    frame: pd.DataFrame,
    feature_columns: list[str],
    train_idx: np.ndarray,
    *,
    standardize: bool,
) -> FeatureTransform:
    means: dict[str, float] = {}
    stds: dict[str, float] = {}
    train_frame = frame.iloc[train_idx]
    for col in feature_columns:
        if col not in frame.columns:
            frame[col] = np.nan
        train_series = pd.to_numeric(train_frame[col], errors="coerce")
        mean_value = float(train_series.mean()) if train_series.notna().any() else 0.0
        std_value = float(train_series.std(ddof=0)) if train_series.notna().any() else 0.0
        if std_value == 0:
            std_value = 1.0
        means[col] = mean_value
        stds[col] = std_value
    return FeatureTransform(feature_columns=feature_columns, means=means, stds=stds, standardize=standardize)


def _fit_ridge(X: np.ndarray, y: np.ndarray, alpha: float) -> LinearModel:
    if X.ndim != 2:
        raise RuntimeError("Ridge expects a 2D feature matrix.")
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    n_rows = X.shape[0]
    if n_rows == 0:
        raise RuntimeError("Cannot fit ridge model on empty dataset.")

    X_aug = np.column_stack([np.ones(n_rows, dtype=float), X])
    reg = np.eye(X_aug.shape[1], dtype=float)
    reg[0, 0] = 0.0
    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        gram = X_aug.T @ X_aug
    gram = np.nan_to_num(gram, nan=0.0, posinf=1e12, neginf=-1e12)
    lhs = gram + (alpha * reg)
    rhs = X_aug.T @ y
    beta = np.linalg.pinv(lhs) @ rhs
    return LinearModel(intercept=float(beta[0]), coefficients=beta[1:])


def _fit_logistic_l2(
    X: np.ndarray,
    y: np.ndarray,
    *,
    alpha: float,
    learning_rate: float,
    max_iter: int,
    tol: float,
    sample_weight: np.ndarray | None = None,
) -> LogisticModel:
    if X.ndim != 2:
        raise RuntimeError("Logistic regression expects 2D feature matrix.")
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)
    n_rows = X.shape[0]
    if n_rows == 0:
        raise RuntimeError("Cannot fit logistic regression on empty dataset.")

    X_aug = np.column_stack([np.ones(n_rows, dtype=float), X])
    weights = np.zeros(X_aug.shape[1], dtype=float)
    if sample_weight is None:
        sample_weight = np.ones(n_rows, dtype=float)
    sample_weight = np.asarray(sample_weight, dtype=float)
    if sample_weight.shape[0] != n_rows:
        raise RuntimeError("sample_weight length must match number of rows.")
    denom = float(np.sum(sample_weight))
    if denom <= 0.0:
        raise RuntimeError("sample_weight must have positive sum.")

    for _ in range(max_iter):
        logits = np.clip(X_aug @ weights, -35.0, 35.0)
        probs = 1.0 / (1.0 + np.exp(-logits))
        residual = (probs - y) * sample_weight
        gradient = (X_aug.T @ residual) / denom
        gradient[1:] += alpha * weights[1:]
        weights -= learning_rate * gradient
        grad_norm = float(np.linalg.norm(gradient))
        if grad_norm <= tol:
            break

    return LogisticModel(intercept=float(weights[0]), coefficients=weights[1:])


def _fit_affine_baseline(raw_signal: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    mask = np.isfinite(raw_signal) & np.isfinite(y)
    if int(np.sum(mask)) < 3:
        return 0.0, 0.0
    x = raw_signal[mask]
    t = y[mask]
    X = np.column_stack([np.ones(len(x), dtype=float), x])
    beta = np.linalg.pinv(X.T @ X) @ (X.T @ t)
    return float(beta[0]), float(beta[1])


def _evaluate_predictions(
    *,
    target_mode: str,
    y_true: np.ndarray,
    y_score: np.ndarray,
    threshold: float = 0.5,
) -> dict[str, Optional[float]]:
    if target_mode == "binary":
        y_label = (y_score >= float(threshold)).astype(int)
        return classification_metrics(y_true=y_true.astype(int), y_pred_label=y_label, y_pred_score=y_score)
    return regression_metrics(y_true=y_true, y_pred=y_score)


def _binary_sample_weight(y: np.ndarray, mode: str) -> np.ndarray:
    y_arr = np.asarray(y, dtype=float)
    weights = np.ones(len(y_arr), dtype=float)
    if mode != "balanced" or len(y_arr) == 0:
        return weights
    n_pos = int(np.sum(y_arr == 1.0))
    n_neg = int(np.sum(y_arr == 0.0))
    if n_pos == 0 or n_neg == 0:
        return weights
    total = float(len(y_arr))
    pos_weight = total / (2.0 * float(n_pos))
    neg_weight = total / (2.0 * float(n_neg))
    weights[y_arr == 1.0] = pos_weight
    weights[y_arr == 0.0] = neg_weight
    return weights


def _tune_binary_threshold(
    *,
    y_true: np.ndarray,
    y_score: np.ndarray,
    metric_name: str,
    grid_size: int,
    enabled: bool,
) -> float:
    if not enabled:
        return 0.5
    steps = max(3, int(grid_size))
    thresholds = np.linspace(0.05, 0.95, num=steps, dtype=float)
    best_threshold = 0.5
    best_metric = -1.0
    best_accuracy = -1.0
    for threshold in thresholds:
        metrics = _evaluate_predictions(
            target_mode="binary",
            y_true=y_true,
            y_score=y_score,
            threshold=float(threshold),
        )
        metric_value = safe_float(metrics.get(metric_name))
        accuracy_value = safe_float(metrics.get("accuracy"))
        if metric_value is None:
            continue
        if accuracy_value is None:
            accuracy_value = -1.0
        if (
            metric_value > best_metric
            or (metric_value == best_metric and accuracy_value > best_accuracy)
            or (
                metric_value == best_metric
                and accuracy_value == best_accuracy
                and abs(float(threshold) - 0.5) < abs(best_threshold - 0.5)
            )
        ):
            best_metric = float(metric_value)
            best_accuracy = float(accuracy_value)
            best_threshold = float(threshold)
    return float(best_threshold)


def _ensure_split(frame: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    split_col = str(args.split_column)
    if split_col in frame.columns:
        normalized = frame[split_col].astype(str).str.strip().str.lower()
        mapping = {"train": "train", "validation": "validation", "val": "validation", "test": "test"}
        converted = normalized.map(mapping)
        if converted.notna().all():
            frame = frame.copy()
            frame[split_col] = converted
            return frame

    date_col = str(args.event_date_column)
    if date_col not in frame.columns:
        raise RuntimeError(f"Missing event date column for split: {date_col}")

    parsed_dates = frame[date_col].apply(parse_date)
    mask = parsed_dates.notna()
    frame = frame.loc[mask].copy()
    frame[date_col] = parsed_dates[mask].apply(lambda d: d.strftime("%Y-%m-%d"))
    frame = frame.sort_values([date_col, "ticker", "transcript_id"], ascending=[True, True, True]).reset_index(drop=True)

    train_idx, val_idx, test_idx = chronological_split_indices(
        n_rows=len(frame),
        train_fraction=float(args.train_fraction),
        val_fraction=float(args.val_fraction),
        min_per_split=int(args.min_per_split),
    )
    frame[split_col] = "train"
    frame.loc[val_idx, split_col] = "validation"
    frame.loc[test_idx, split_col] = "test"
    return frame


def _series_to_numpy(frame: pd.DataFrame, column: str) -> np.ndarray:
    series = pd.to_numeric(frame[column], errors="coerce")
    return series.to_numpy(dtype=float)


def _baseline_signal(
    frame: pd.DataFrame,
    *,
    name: str,
    transcript_signal_col: str,
    component_cols: list[str],
    handset_overall_col: str,
) -> np.ndarray:
    if name == "handset_overall":
        if handset_overall_col in frame.columns:
            arr = _series_to_numpy(frame, handset_overall_col)
            if np.isfinite(arr).any():
                return arr
        transcript = _series_to_numpy(frame, transcript_signal_col)
        fundamentals = _series_to_numpy(frame, component_cols[0]) if len(component_cols) > 0 else np.zeros(len(frame))
        news = _series_to_numpy(frame, component_cols[1]) if len(component_cols) > 1 else np.zeros(len(frame))
        social = _series_to_numpy(frame, component_cols[2]) if len(component_cols) > 2 else np.zeros(len(frame))
        return (0.40 * np.nan_to_num(transcript)) + (0.35 * np.nan_to_num(fundamentals)) + (0.15 * np.nan_to_num(news)) + (
            0.10 * np.nan_to_num(social)
        )

    if name == "equal_weight_blend":
        stack = []
        stack.append(_series_to_numpy(frame, transcript_signal_col))
        for col in component_cols:
            stack.append(_series_to_numpy(frame, col))
        raw = np.vstack(stack)
        counts = np.sum(np.isfinite(raw), axis=0)
        sums = np.nansum(raw, axis=0)
        out = np.zeros(raw.shape[1], dtype=float)
        valid = counts > 0
        out[valid] = sums[valid] / counts[valid]
        return out

    if name == "transcript_only":
        return _series_to_numpy(frame, transcript_signal_col)
    if name == "fundamentals_only":
        return _series_to_numpy(frame, component_cols[0]) if len(component_cols) > 0 else np.zeros(len(frame))
    if name == "news_only":
        return _series_to_numpy(frame, component_cols[1]) if len(component_cols) > 1 else np.zeros(len(frame))
    if name == "social_only":
        return _series_to_numpy(frame, component_cols[2]) if len(component_cols) > 2 else np.zeros(len(frame))

    raise RuntimeError(f"Unsupported baseline signal name: {name}")


def _local_search(
    *,
    seed: int,
    X_val: np.ndarray,
    y_val: np.ndarray,
    X_test: np.ndarray,
    y_test: np.ndarray,
    base_model: LinearModel,
    samples: int,
    radius: float,
) -> dict[str, Any]:
    base_val_pred = base_model.predict(X_val)
    base_metrics = regression_metrics(y_true=y_val, y_pred=base_val_pred)
    base_score = safe_float(base_metrics.get("spearman"))
    if base_score is None:
        base_score = -999.0

    best_model = base_model
    best_score = base_score
    best_metrics_val = base_metrics

    rng = np.random.default_rng(seed)
    for _ in range(samples):
        candidate_weights = base_model.coefficients + rng.normal(0.0, radius, size=base_model.coefficients.shape)
        candidate = LinearModel(intercept=base_model.intercept, coefficients=candidate_weights)
        pred_val = candidate.predict(X_val)
        metrics_val = regression_metrics(y_true=y_val, y_pred=pred_val)
        candidate_score = safe_float(metrics_val.get("spearman"))
        if candidate_score is None:
            continue
        if candidate_score > best_score:
            best_model = candidate
            best_score = candidate_score
            best_metrics_val = metrics_val

    best_test_pred = best_model.predict(X_test)
    best_metrics_test = regression_metrics(y_true=y_test, y_pred=best_test_pred)
    abs_weights = np.abs(best_model.coefficients)
    denom = float(np.sum(abs_weights))
    normalized_weights = (
        (abs_weights / denom).tolist()
        if denom > 0
        else np.zeros_like(abs_weights, dtype=float).tolist()
    )

    return {
        "samples": int(samples),
        "radius": float(radius),
        "base_validation_metrics": base_metrics,
        "best_validation_metrics": best_metrics_val,
        "best_test_metrics": best_metrics_test,
        "best_coefficients": best_model.coefficients.tolist(),
        "best_intercept": float(best_model.intercept),
        "normalized_abs_weights": normalized_weights,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rng_seed = int(args.seed)

    input_path = Path(args.input)
    if not input_path.exists():
        raise RuntimeError(f"Input dataset not found: {input_path}")

    if not args.no_progress:
        print("[calibrate] Step 1/8: loading prepared dataset...")
    frame = _load_table(input_path)
    if frame.empty:
        raise RuntimeError("Input dataset is empty.")

    frame = _ensure_split(frame, args)
    split_col = str(args.split_column)
    if not args.no_progress:
        print("[calibrate] Step 2/8: resolving split + target...")

    requested_target = str(args.target_column)
    fallback_target = _target_column_from_horizon(args.target_horizon, args.target_mode)
    if requested_target in frame.columns:
        target_col = requested_target
    elif fallback_target in frame.columns:
        target_col = fallback_target
    else:
        raise RuntimeError(
            f"Target column not found. Tried {requested_target} and fallback {fallback_target}."
        )

    if args.target_mode == "binary":
        frame[target_col] = frame[target_col].apply(lambda v: int(float(v)) if pd.notna(v) else np.nan)
    else:
        frame[target_col] = pd.to_numeric(frame[target_col], errors="coerce")

    frame = frame.loc[frame[target_col].notna()].copy()
    if len(frame) < int(args.min_per_split * 3):
        raise RuntimeError(f"Not enough rows after target filtering: {len(frame)}")

    transcript_features = _parse_list(args.transcript_feature_columns, DEFAULT_TRANSCRIPT_FEATURES)
    component_features = _parse_list(args.component_feature_columns, DEFAULT_COMPONENT_FEATURES)
    meta_columns = _parse_list(args.meta_columns, DEFAULT_META_COLUMNS)

    transcript_signal_col = args.handset_transcript_column
    if transcript_signal_col not in frame.columns:
        transcript_signal_col = "transcript_sentiment_directional_score"
    if transcript_signal_col not in frame.columns:
        frame[transcript_signal_col] = np.nan

    for col in transcript_features + component_features + [args.handset_overall_column, transcript_signal_col]:
        if col not in frame.columns:
            frame[col] = np.nan

    train_idx = np.where(frame[split_col].astype(str) == "train")[0]
    val_idx = np.where(frame[split_col].astype(str) == "validation")[0]
    test_idx = np.where(frame[split_col].astype(str) == "test")[0]
    if len(train_idx) == 0 or len(val_idx) == 0 or len(test_idx) == 0:
        raise RuntimeError("Split must contain non-empty train/validation/test rows.")

    y_all = pd.to_numeric(frame[target_col], errors="coerce").to_numpy(dtype=float)
    y_train = y_all[train_idx]
    y_val = y_all[val_idx]
    y_test = y_all[test_idx]

    if not args.no_progress:
        print("[calibrate] Step 3/8: fitting stage-1 transcript model...")

    stage1_transform = _fit_feature_transform(frame, transcript_features, train_idx, standardize=True)
    X_stage1_all = stage1_transform.transform(frame)
    X_stage1_train = X_stage1_all[train_idx]
    X_stage1_val = X_stage1_all[val_idx]
    X_stage1_test = X_stage1_all[test_idx]

    if args.target_mode == "binary":
        logistic_sample_weight = _binary_sample_weight(y_train, mode=str(args.binary_class_weight))
        stage1_model = _fit_logistic_l2(
            X_stage1_train,
            y_train,
            alpha=float(args.logistic_alpha),
            learning_rate=float(args.logistic_learning_rate),
            max_iter=int(args.logistic_max_iter),
            tol=float(args.logistic_tol),
            sample_weight=logistic_sample_weight,
        )
        stage1_score_all = stage1_model.predict_proba(X_stage1_all)
    else:
        stage1_model = _fit_ridge(X_stage1_train, y_train, alpha=float(args.ridge_alpha))
        stage1_score_all = stage1_model.predict(X_stage1_all)

    frame = frame.copy()
    frame["transcript_stage_score"] = stage1_score_all

    stage2_features = ["transcript_stage_score", *component_features]
    for col in stage2_features:
        if col not in frame.columns:
            frame[col] = np.nan

    stage2_transform = _fit_feature_transform(frame, stage2_features, train_idx, standardize=False)
    X_stage2_all = stage2_transform.transform(frame)
    X_stage2_train = X_stage2_all[train_idx]
    X_stage2_val = X_stage2_all[val_idx]
    X_stage2_test = X_stage2_all[test_idx]

    if not args.no_progress:
        print("[calibrate] Step 4/8: fitting stage-2 full-score model...")

    if args.target_mode == "binary":
        stage2_model = _fit_logistic_l2(
            X_stage2_train,
            y_train,
            alpha=float(args.logistic_alpha),
            learning_rate=float(args.logistic_learning_rate),
            max_iter=int(args.logistic_max_iter),
            tol=float(args.logistic_tol),
            sample_weight=logistic_sample_weight,
        )
        stage2_score_all = stage2_model.predict_proba(X_stage2_all)
    else:
        stage2_model = _fit_ridge(X_stage2_train, y_train, alpha=float(args.ridge_alpha))
        stage2_score_all = stage2_model.predict(X_stage2_all)

    direct_features = [*transcript_features, *component_features]
    direct_transform = _fit_feature_transform(frame, direct_features, train_idx, standardize=True)
    X_direct_all = direct_transform.transform(frame)
    X_direct_train = X_direct_all[train_idx]
    X_direct_val = X_direct_all[val_idx]
    X_direct_test = X_direct_all[test_idx]

    if not args.no_progress:
        print("[calibrate] Step 5/8: fitting direct single-stage model...")

    if args.target_mode == "binary":
        direct_model = _fit_logistic_l2(
            X_direct_train,
            y_train,
            alpha=float(args.logistic_alpha),
            learning_rate=float(args.logistic_learning_rate),
            max_iter=int(args.logistic_max_iter),
            tol=float(args.logistic_tol),
            sample_weight=logistic_sample_weight,
        )
        direct_score_all = direct_model.predict_proba(X_direct_all)
    else:
        direct_model = _fit_ridge(X_direct_train, y_train, alpha=float(args.ridge_alpha))
        direct_score_all = direct_model.predict(X_direct_all)

    frame["prediction_stage1"] = stage1_score_all
    frame["prediction_stage2"] = stage2_score_all
    frame["prediction_direct"] = direct_score_all

    metrics: dict[str, Any] = {
        "target_mode": args.target_mode,
        "target_column": target_col,
        "split_counts": frame[split_col].value_counts().to_dict(),
        "binary_settings": {
            "class_weight": str(args.binary_class_weight),
            "threshold_metric": str(args.binary_threshold_metric),
            "threshold_grid_size": int(args.binary_threshold_grid_size),
            "threshold_tuned": bool(args.tune_binary_threshold),
        }
        if args.target_mode == "binary"
        else None,
        "models": {},
        "baselines": {},
    }

    if not args.no_progress:
        print("[calibrate] Step 6/8: evaluating models and baselines...")

    model_predictions = {
        "stage1": frame["prediction_stage1"].to_numpy(dtype=float),
        "stage2": frame["prediction_stage2"].to_numpy(dtype=float),
        "direct": frame["prediction_direct"].to_numpy(dtype=float),
    }

    model_thresholds: dict[str, float] = {}
    for model_name, pred_all in model_predictions.items():
        threshold = 0.5
        if args.target_mode == "binary":
            threshold = _tune_binary_threshold(
                y_true=y_val,
                y_score=pred_all[val_idx],
                metric_name=str(args.binary_threshold_metric),
                grid_size=int(args.binary_threshold_grid_size),
                enabled=bool(args.tune_binary_threshold),
            )
        model_thresholds[model_name] = float(threshold)
        metrics["models"][model_name] = {
            "threshold": float(threshold),
            "validation": _evaluate_predictions(
                target_mode=args.target_mode,
                y_true=y_val,
                y_score=pred_all[val_idx],
                threshold=float(threshold),
            ),
            "test": _evaluate_predictions(
                target_mode=args.target_mode,
                y_true=y_test,
                y_score=pred_all[test_idx],
                threshold=float(threshold),
            ),
        }

    baseline_names = [
        "handset_overall",
        "equal_weight_blend",
        "transcript_only",
        "fundamentals_only",
        "news_only",
        "social_only",
    ]

    for baseline_name in baseline_names:
        raw_signal = _baseline_signal(
            frame,
            name=baseline_name,
            transcript_signal_col=transcript_signal_col,
            component_cols=component_features,
            handset_overall_col=args.handset_overall_column,
        )

        if args.target_mode == "continuous":
            offset, slope = _fit_affine_baseline(raw_signal[train_idx], y_train)
            pred_all = offset + (slope * np.nan_to_num(raw_signal, nan=0.0))
            metrics["baselines"][baseline_name] = {
                "calibration": {"intercept": offset, "slope": slope},
                "validation": _evaluate_predictions(
                    target_mode="continuous",
                    y_true=y_val,
                    y_score=pred_all[val_idx],
                ),
                "test": _evaluate_predictions(
                    target_mode="continuous",
                    y_true=y_test,
                    y_score=pred_all[test_idx],
                ),
            }
        else:
            score_all = np.nan_to_num(raw_signal, nan=0.0)
            metrics["baselines"][baseline_name] = {
                "validation": _evaluate_predictions(
                    target_mode="binary",
                    y_true=y_val,
                    y_score=score_all[val_idx],
                ),
                "test": _evaluate_predictions(
                    target_mode="binary",
                    y_true=y_test,
                    y_score=score_all[test_idx],
                ),
            }

    if args.target_mode == "continuous":
        zero_pred_val = np.zeros_like(y_val)
        zero_pred_test = np.zeros_like(y_test)
        metrics["baselines"]["zero_return"] = {
            "validation": _evaluate_predictions(target_mode="continuous", y_true=y_val, y_score=zero_pred_val),
            "test": _evaluate_predictions(target_mode="continuous", y_true=y_test, y_score=zero_pred_test),
        }
    else:
        majority_class = int(np.mean(y_train) >= 0.5)
        majority_val = np.full_like(y_val, fill_value=float(majority_class), dtype=float)
        majority_test = np.full_like(y_test, fill_value=float(majority_class), dtype=float)
        metrics["baselines"]["majority_direction"] = {
            "majority_class": majority_class,
            "validation": _evaluate_predictions(target_mode="binary", y_true=y_val, y_score=majority_val),
            "test": _evaluate_predictions(target_mode="binary", y_true=y_test, y_score=majority_test),
        }

    if args.target_mode == "binary":
        selection_metric = str(args.binary_threshold_metric)
    else:
        selection_metric = "spearman"

    def _selection_score(payload: dict[str, Any]) -> float:
        metric_value = safe_float((payload.get("validation") or {}).get(selection_metric))
        if metric_value is None:
            return -999.0
        return float(metric_value)

    selected_model_name = max(metrics["models"].keys(), key=lambda name: _selection_score(metrics["models"][name]))
    selected_model_threshold = float(model_thresholds.get(selected_model_name, 0.5))
    metrics["model_selection"] = {
        "selected_model": selected_model_name,
        "selection_metric": selection_metric,
        "validation_score": _selection_score(metrics["models"][selected_model_name]),
        "threshold": selected_model_threshold,
        "validation_metrics": metrics["models"][selected_model_name]["validation"],
        "test_metrics": metrics["models"][selected_model_name]["test"],
    }

    if not args.no_progress:
        print("[calibrate] Step 7/8: optional local search + ranking analysis...")

    local_search_result = None
    if args.enable_local_search and args.target_mode == "continuous":
        local_search_result = _local_search(
            seed=rng_seed,
            X_val=X_stage2_val,
            y_val=y_val,
            X_test=X_stage2_test,
            y_test=y_test,
            base_model=stage2_model,
            samples=int(args.local_search_samples),
            radius=float(args.local_search_radius),
        )

    horizon_return_col = f"abnormal_return_{int(args.target_horizon)}d"
    if horizon_return_col in frame.columns:
        abnormal_series = pd.to_numeric(frame[horizon_return_col], errors="coerce").to_numpy(dtype=float)
    elif args.target_mode == "continuous":
        abnormal_series = y_all.copy()
    else:
        abnormal_series = np.full_like(y_all, np.nan)

    ranking = {}
    test_abnormal = abnormal_series[test_idx]
    valid_test_abnormal_mask = np.isfinite(test_abnormal)

    def _bucket_payload(name: str, score_values: np.ndarray) -> dict[str, Any]:
        if not np.isfinite(score_values).any() or not np.isfinite(test_abnormal).any():
            return {"quintiles": [], "deciles": []}
        keep = valid_test_abnormal_mask & np.isfinite(score_values)
        if int(np.sum(keep)) < 10:
            return {"quintiles": [], "deciles": []}
        return {
            "quintiles": bucket_analysis(
                scores=score_values[keep],
                abnormal_returns=test_abnormal[keep],
                n_buckets=5,
            ),
            "deciles": bucket_analysis(
                scores=score_values[keep],
                abnormal_returns=test_abnormal[keep],
                n_buckets=10,
            ),
        }

    ranking["stage2"] = _bucket_payload("stage2", model_predictions["stage2"][test_idx])
    ranking["handset_overall"] = _bucket_payload(
        "handset_overall",
        _baseline_signal(
            frame.iloc[test_idx],
            name="handset_overall",
            transcript_signal_col=transcript_signal_col,
            component_cols=component_features,
            handset_overall_col=args.handset_overall_column,
        ),
    )

    metrics["ranking"] = ranking
    if local_search_result is not None:
        metrics["local_search"] = local_search_result

    coefficients = {
        "stage1": {
            "features": stage1_transform.feature_columns,
            "standardize": stage1_transform.standardize,
            "means": stage1_transform.means,
            "stds": stage1_transform.stds,
            "intercept": float(stage1_model.intercept),
            "coefficients": {feature: float(value) for feature, value in zip(stage1_transform.feature_columns, stage1_model.coefficients)},
        },
        "stage2": {
            "features": stage2_transform.feature_columns,
            "standardize": stage2_transform.standardize,
            "means": stage2_transform.means,
            "stds": stage2_transform.stds,
            "intercept": float(stage2_model.intercept),
            "coefficients": {feature: float(value) for feature, value in zip(stage2_transform.feature_columns, stage2_model.coefficients)},
        },
        "direct": {
            "features": direct_transform.feature_columns,
            "standardize": direct_transform.standardize,
            "means": direct_transform.means,
            "stds": direct_transform.stds,
            "intercept": float(direct_model.intercept),
            "coefficients": {feature: float(value) for feature, value in zip(direct_transform.feature_columns, direct_model.coefficients)},
        },
    }

    comparison_rows: list[dict[str, Any]] = []
    for name, payload in metrics["models"].items():
        row = {"name": f"model:{name}", **(payload.get("test") or {})}
        if args.target_mode == "binary":
            row["threshold"] = float(payload.get("threshold", 0.5))
        comparison_rows.append(row)
    selected_payload = metrics.get("model_selection") or {}
    if selected_payload:
        selected_test = selected_payload.get("test_metrics") or {}
        selected_row = {
            "name": "model:selected_by_validation",
            "selected_model": selected_payload.get("selected_model"),
            **selected_test,
        }
        if args.target_mode == "binary":
            selected_row["threshold"] = float(selected_payload.get("threshold", 0.5))
        comparison_rows.append(selected_row)
    for name, payload in metrics["baselines"].items():
        row = {"name": f"baseline:{name}", **(payload.get("test") or {})}
        comparison_rows.append(row)

    if args.target_mode == "continuous":
        comparison_rows.sort(
            key=lambda row: (
                -(safe_float(row.get("spearman")) if safe_float(row.get("spearman")) is not None else -999.0),
                safe_float(row.get("rmse")) if safe_float(row.get("rmse")) is not None else 1e12,
            )
        )
    else:
        comparison_rows.sort(
            key=lambda row: (
                -(safe_float(row.get("macro_f1")) if safe_float(row.get("macro_f1")) is not None else -999.0),
                -(safe_float(row.get("accuracy")) if safe_float(row.get("accuracy")) is not None else -999.0),
            )
        )

    test_frame = frame.iloc[test_idx].copy()
    test_frame["prediction_stage1"] = model_predictions["stage1"][test_idx]
    test_frame["prediction_stage2"] = model_predictions["stage2"][test_idx]
    test_frame["prediction_direct"] = model_predictions["direct"][test_idx]
    selected_pred = model_predictions[str(selected_model_name)][test_idx]
    test_frame["prediction_selected_by_validation"] = selected_pred
    if args.target_mode == "binary":
        for model_name in ("stage1", "stage2", "direct"):
            model_threshold = float(model_thresholds.get(model_name, 0.5))
            test_frame[f"prediction_{model_name}_label"] = (
                test_frame[f"prediction_{model_name}"].to_numpy(dtype=float) >= model_threshold
            ).astype(int)
        test_frame["prediction_selected_by_validation_label"] = (
            selected_pred >= float(selected_model_threshold)
        ).astype(int)
    for baseline_name in baseline_names:
        if baseline_name == "handset_overall":
            signal = _baseline_signal(
                test_frame,
                name="handset_overall",
                transcript_signal_col=transcript_signal_col,
                component_cols=component_features,
                handset_overall_col=args.handset_overall_column,
            )
            if args.target_mode == "continuous":
                calib = metrics["baselines"][baseline_name].get("calibration", {})
                offset = float(calib.get("intercept", 0.0))
                slope = float(calib.get("slope", 0.0))
                test_frame[f"prediction_baseline_{baseline_name}"] = offset + slope * np.nan_to_num(signal, nan=0.0)
            else:
                test_frame[f"prediction_baseline_{baseline_name}"] = np.nan_to_num(signal, nan=0.0)
        else:
            signal = _baseline_signal(
                test_frame,
                name=baseline_name,
                transcript_signal_col=transcript_signal_col,
                component_cols=component_features,
                handset_overall_col=args.handset_overall_column,
            )
            if args.target_mode == "continuous":
                calib = metrics["baselines"][baseline_name].get("calibration", {})
                offset = float(calib.get("intercept", 0.0))
                slope = float(calib.get("slope", 0.0))
                test_frame[f"prediction_baseline_{baseline_name}"] = offset + slope * np.nan_to_num(signal, nan=0.0)
            else:
                test_frame[f"prediction_baseline_{baseline_name}"] = np.nan_to_num(signal, nan=0.0)

    keep_meta = [col for col in meta_columns if col in test_frame.columns]
    prediction_cols = [col for col in test_frame.columns if col.startswith("prediction_")]
    keep_cols = keep_meta + [target_col] + prediction_cols
    predictions_test = test_frame[keep_cols].copy()

    if not args.no_progress:
        print("[calibrate] Step 8/8: writing report artifacts...")

    out_dir = Path(args.output_dir)
    ensure_dir(out_dir)
    metrics_path = out_dir / "metrics.json"
    coefs_path = out_dir / "coefficients.json"
    predictions_path = out_dir / "predictions_test.csv"
    comparison_path = out_dir / "comparison_table.json"
    summary_md_path = out_dir / "calibration_summary.md"

    write_json(metrics_path, metrics)
    write_json(coefs_path, coefficients)
    predictions_test.to_csv(predictions_path, index=False)
    write_json(comparison_path, comparison_rows)

    lines = []
    lines.append("# Score Calibration Summary")
    lines.append("")
    lines.append(f"- Target mode: `{args.target_mode}`")
    lines.append(f"- Target column: `{target_col}`")
    lines.append(f"- Events: `{len(frame)}` (train={len(train_idx)}, val={len(val_idx)}, test={len(test_idx)})")
    lines.append(f"- Selected model (validation `{selection_metric}`): `{selected_model_name}`")
    if args.target_mode == "binary":
        lines.append(f"- Selected threshold: `{selected_model_threshold:.3f}`")
    lines.append("")
    lines.append("## Test Comparison")
    lines.append("")
    for row in comparison_rows[:12]:
        metrics_preview = ", ".join([f"{k}={v:.4f}" for k, v in row.items() if k != "name" and isinstance(v, float)])
        lines.append(f"- `{row['name']}`: {metrics_preview}")
    lines.append("")
    lines.append("## Stage 2 Coefficients")
    lines.append("")
    for feature, value in coefficients["stage2"]["coefficients"].items():
        lines.append(f"- `{feature}`: {value:.6f}")
    if local_search_result is not None:
        lines.append("")
        lines.append("## Local Search")
        lines.append("")
        lines.append(
            f"- samples={local_search_result['samples']} radius={local_search_result['radius']} "
            f"best_validation_spearman={safe_float(local_search_result['best_validation_metrics'].get('spearman'))}"
        )

    summary_md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"[calibrate] Wrote metrics: {metrics_path}")
    print(f"[calibrate] Wrote coefficients: {coefs_path}")
    print(f"[calibrate] Wrote test predictions: {predictions_path}")
    print(f"[calibrate] Wrote comparison table: {comparison_path}")
    print(f"[calibrate] Wrote markdown summary: {summary_md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
