"""Evaluate Isolation Forest and Matrix Profile on the canonical datasets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import auc, confusion_matrix, precision_recall_curve, roc_curve

from infer import load_iforest_bundle
from matrix_profile import MatrixProfileDetector
from preprocess import (
    EVALUATION_DATASET_PATH,
    MODEL_DIR,
    PREDICTION_DIR,
    engineer_features,
    ensure_directories,
    load_evaluation_dataset,
    load_trip_sessions,
)
from train_iforest import score_iforest, train_pipeline


REPORT_DIR = Path(__file__).resolve().parent / "reports"
PLOT_DIR = REPORT_DIR / "plots"
CURVE_DIR = REPORT_DIR / "curve_data"
DATASET_SUMMARY_PATH = REPORT_DIR / "evaluation_dataset_summary.json"
BREAKDOWN_METRICS_PATH = REPORT_DIR / "metrics_breakdown.csv"
BREAKDOWN_JSON_PATH = REPORT_DIR / "metrics_breakdown.json"

PRECISION_TARGET = 0.90
FPR_TARGET = 0.10
LATENCY_TARGET_SEC = 10.0


def compute_metrics(
    frame: pd.DataFrame,
    pred_col: str,
    label_col: str = "anomaly_label",
    score_col: str | None = None,
) -> dict:
    y_true = frame[label_col].astype(bool)
    y_pred = frame[pred_col].astype(bool)
    positive_count = int(y_true.sum())
    negative_count = int((~y_true).sum())

    tp = int((y_true & y_pred).sum())
    fp = int((~y_true & y_pred).sum())
    fn = int((y_true & ~y_pred).sum())
    tn = int((~y_true & ~y_pred).sum())

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    false_positive_rate = fp / (fp + tn) if (fp + tn) else 0.0
    accuracy = (tp + tn) / max(tp + fp + fn + tn, 1)

    metrics = {
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "precision": precision,
        "recall": recall,
        "false_positive_rate": false_positive_rate,
        "accuracy": accuracy,
        "positive_label_count": positive_count,
        "negative_label_count": negative_count,
    }

    if score_col is not None and frame[label_col].nunique(dropna=False) > 1:
        scores = frame[score_col].astype(float).to_numpy()
        fpr_values, tpr_values, _ = roc_curve(y_true.astype(int), scores)
        precision_values, recall_values, _ = precision_recall_curve(y_true.astype(int), scores)
        metrics["roc_auc"] = float(auc(fpr_values, tpr_values))
        metrics["pr_auc"] = float(auc(recall_values, precision_values))
    else:
        metrics["roc_auc"] = np.nan
        metrics["pr_auc"] = np.nan
    return metrics


def compute_detection_latency(
    frame: pd.DataFrame,
    pred_col: str,
    label_col: str = "anomaly_label",
) -> tuple[pd.DataFrame, dict]:
    latency_rows: list[dict] = []

    ordered = frame.sort_values(["truck_id", "trip_id", "timestamp"])
    for (truck_id, trip_id), group in ordered.groupby(["truck_id", "trip_id"], dropna=False):
        anomalous = group[group[label_col].astype(bool)]
        if anomalous.empty:
            continue

        onset_ts = anomalous["timestamp"].min()
        detected = group[(group["timestamp"] >= onset_ts) & group[pred_col].astype(bool)]
        detected_ts = detected["timestamp"].min() if not detected.empty else pd.NaT
        latency_sec = (
            float((detected_ts - onset_ts).total_seconds())
            if pd.notna(detected_ts)
            else np.nan
        )
        latency_rows.append(
            {
                "truck_id": truck_id,
                "trip_id": trip_id,
                "anomaly_onset": onset_ts,
                "first_detection": detected_ts,
                "latency_sec": latency_sec,
                "detected": pd.notna(detected_ts),
                "anomaly_type": "|".join(sorted(set(anomalous["anomaly_type"].astype(str)))) or "unknown",
            }
        )

    latency_frame = pd.DataFrame(latency_rows)
    detected_latencies = latency_frame.loc[latency_frame["detected"], "latency_sec"] if not latency_frame.empty else pd.Series(dtype=float)
    summary = {
        "average_detection_latency_sec": float(detected_latencies.mean()) if not detected_latencies.empty else np.nan,
        "median_detection_latency_sec": float(detected_latencies.median()) if not detected_latencies.empty else np.nan,
        "detected_anomalous_trips": int(latency_frame["detected"].sum()) if not latency_frame.empty else 0,
        "missed_anomalous_trips": int((~latency_frame["detected"]).sum()) if not latency_frame.empty else 0,
        "latency_target_sec": LATENCY_TARGET_SEC,
        "latency_target_met": bool(
            not detected_latencies.empty and float(detected_latencies.mean()) < LATENCY_TARGET_SEC
        ),
    }
    return latency_frame, summary


def _subset_scope(frame: pd.DataFrame, label_col: str = "anomaly_label") -> tuple[str, str]:
    if frame.empty:
        return "empty_subset", "No rows available in this subset."
    positive_count = int(frame[label_col].astype(bool).sum())
    negative_count = int((~frame[label_col].astype(bool)).sum())
    if positive_count > 0 and negative_count > 0:
        return "mixed_controlled_benchmark", "Subset contains both normal and anomalous samples."
    if positive_count > 0:
        return "positive_only_sensitivity", "Subset contains only anomalous samples; use recall/latency more than false-positive rate."
    return "clean_false_alarm_characterization", "Subset contains only normal samples; use false-positive rate more than recall."


def _build_subset_rows(
    model_name: str,
    frame: pd.DataFrame,
    pred_col: str,
    score_col: str,
    subsets: list[tuple[str, str, pd.DataFrame]],
    latency_source: pd.DataFrame | None = None,
    granularity: str | None = None,
    data_source: str | None = None,
) -> list[dict]:
    rows: list[dict] = []
    for subset_name, subset_group, subset_frame in subsets:
        metrics = {
            "model": model_name,
            "granularity": granularity,
            "data_source": data_source,
            "subset_name": subset_name,
            "subset_group": subset_group,
            "subset_rows": int(len(subset_frame)),
            "subset_trip_count": int(subset_frame["trip_id"].nunique()) if "trip_id" in subset_frame.columns else np.nan,
        }
        scope, note = _subset_scope(subset_frame)
        metrics["subset_scope"] = scope
        metrics["subset_note"] = note
        metrics.update(compute_metrics(subset_frame, pred_col, score_col=score_col))
        latency_frame = subset_frame
        if latency_source is not None:
            if {"truck_id", "trip_id"}.issubset(subset_frame.columns) and {"truck_id", "trip_id"}.issubset(latency_source.columns):
                subset_keys = subset_frame[["truck_id", "trip_id"]].drop_duplicates()
                latency_frame = latency_source.merge(subset_keys, on=["truck_id", "trip_id"], how="inner")
            else:
                latency_frame = latency_source
        _, latency_summary = compute_detection_latency(latency_frame, pred_col)
        metrics.update(latency_summary)
        rows.append(metrics)
    return rows


def save_curve_artifacts(
    frame: pd.DataFrame,
    label_col: str,
    score_col: str,
    prefix: str,
    title: str,
) -> dict[str, str | None]:
    CURVE_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)

    if frame[label_col].nunique(dropna=False) < 2:
        return {"roc_csv": None, "pr_csv": None, "roc_plot": None, "pr_plot": None}

    y_true = frame[label_col].astype(int).to_numpy()
    scores = frame[score_col].astype(float).to_numpy()

    fpr_values, tpr_values, roc_thresholds = roc_curve(y_true, scores)
    precision_values, recall_values, pr_thresholds = precision_recall_curve(y_true, scores)
    roc_auc_value = float(auc(fpr_values, tpr_values))
    pr_auc_value = float(auc(recall_values, precision_values))

    roc_frame = pd.DataFrame(
        {
            "false_positive_rate": fpr_values,
            "true_positive_rate": tpr_values,
            "threshold": np.append(roc_thresholds[:-1], np.nan),
        }
    )
    pr_frame = pd.DataFrame(
        {
            "recall": recall_values,
            "precision": precision_values,
            "threshold": np.append(pr_thresholds, np.nan),
        }
    )

    roc_csv = CURVE_DIR / f"{prefix}_roc_curve.csv"
    pr_csv = CURVE_DIR / f"{prefix}_pr_curve.csv"
    roc_plot = PLOT_DIR / f"{prefix}_roc_curve.png"
    pr_plot = PLOT_DIR / f"{prefix}_pr_curve.png"

    roc_frame.to_csv(roc_csv, index=False)
    pr_frame.to_csv(pr_csv, index=False)

    plt.figure(figsize=(6, 4))
    plt.plot(fpr_values, tpr_values, label=f"AUC = {roc_auc_value:.3f}", color="#0f766e")
    plt.plot([0, 1], [0, 1], linestyle="--", color="#94a3b8")
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title(f"{title} ROC Curve")
    plt.legend(loc="lower right")
    plt.tight_layout()
    plt.savefig(roc_plot, dpi=160)
    plt.close()

    plt.figure(figsize=(6, 4))
    plt.plot(recall_values, precision_values, label=f"AUC = {pr_auc_value:.3f}", color="#b45309")
    plt.xlabel("Recall")
    plt.ylabel("Precision")
    plt.title(f"{title} PR Curve")
    plt.legend(loc="lower left")
    plt.tight_layout()
    plt.savefig(pr_plot, dpi=160)
    plt.close()

    return {
        "roc_csv": str(roc_csv),
        "pr_csv": str(pr_csv),
        "roc_plot": str(roc_plot),
        "pr_plot": str(pr_plot),
    }


def plot_confusion_artifact(metrics_row: dict, prefix: str, title: str) -> str:
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    matrix = np.array([[metrics_row["TN"], metrics_row["FP"]], [metrics_row["FN"], metrics_row["TP"]]], dtype=float)
    path = PLOT_DIR / f"{prefix}_confusion_matrix.png"

    plt.figure(figsize=(4.5, 4))
    plt.imshow(matrix, cmap="Blues")
    plt.title(title)
    plt.xticks([0, 1], ["Pred Normal", "Pred Anomaly"])
    plt.yticks([0, 1], ["True Normal", "True Anomaly"])
    for row_index in range(2):
        for col_index in range(2):
            plt.text(col_index, row_index, int(matrix[row_index, col_index]), ha="center", va="center", color="#0f172a")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    return str(path)


def _select_focus_trip(frame: pd.DataFrame) -> tuple[str, str] | None:
    anomalous = (
        frame.groupby(["truck_id", "trip_id"], dropna=False)
        .agg(
            anomaly_label=("anomaly_label", "any"),
            sequence_length=("timestamp", "size"),
        )
        .reset_index()
        .sort_values(["anomaly_label", "sequence_length", "trip_id"], ascending=[False, False, True])
    )
    if anomalous.empty:
        return None
    first = anomalous.iloc[0]
    return str(first["truck_id"]), str(first["trip_id"])


def plot_fuel_overlay(
    evaluation_frame: pd.DataFrame,
    if_predictions: pd.DataFrame,
    mp_row_predictions: pd.DataFrame,
    focus_trip: tuple[str, str] | None,
) -> str | None:
    if focus_trip is None:
        return None

    truck_id, trip_id = focus_trip
    base = evaluation_frame[(evaluation_frame["truck_id"] == truck_id) & (evaluation_frame["trip_id"] == trip_id)].copy()
    if base.empty:
        return None

    if_trip = if_predictions[(if_predictions["truck_id"] == truck_id) & (if_predictions["trip_id"] == trip_id)].copy()
    mp_trip = mp_row_predictions[(mp_row_predictions["truck_id"] == truck_id) & (mp_row_predictions["trip_id"] == trip_id)].copy()
    path = PLOT_DIR / "fuel_level_anomaly_overlay.png"

    plt.figure(figsize=(10, 4.5))
    plt.plot(base["timestamp"], base["fuel_level"], label="Raw fuel level", color="#1d4ed8", linewidth=1.5)
    plt.plot(base["timestamp"], base["fuel_level_filtered"], label="Filtered fuel level", color="#0f766e", linewidth=2.0)

    truth = base[base["anomaly_label"].astype(bool)]
    if not truth.empty:
        plt.scatter(truth["timestamp"], truth["fuel_level_filtered"], color="#dc2626", label="True anomaly window", zorder=5)

    if_flags = if_trip[if_trip["iforest_flag"].astype(bool)]
    if not if_flags.empty:
        plt.scatter(if_flags["timestamp"], if_flags["fuel_level_filtered"], color="#7c3aed", marker="x", label="IF detected", zorder=6)

    mp_flags = mp_trip[mp_trip["mp_anomaly_flag"].astype(bool)]
    if not mp_flags.empty:
        plt.scatter(mp_flags["timestamp"], mp_flags["fuel_level_filtered"], color="#f59e0b", marker="^", label="MP detected", zorder=6)

    plt.title(f"Fuel Level vs Time with Anomaly Overlays\nTrip {trip_id[:8]}")
    plt.xlabel("Timestamp")
    plt.ylabel("Fuel level")
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    return str(path)


def plot_gps_overlay(
    evaluation_frame: pd.DataFrame,
    if_predictions: pd.DataFrame,
    focus_trip: tuple[str, str] | None,
) -> str | None:
    if focus_trip is None:
        return None

    truck_id, trip_id = focus_trip
    base = evaluation_frame[(evaluation_frame["truck_id"] == truck_id) & (evaluation_frame["trip_id"] == trip_id)].copy()
    if base.empty or base["lat"].isna().all() or base["lon"].isna().all():
        return None

    if_trip = if_predictions[(if_predictions["truck_id"] == truck_id) & (if_predictions["trip_id"] == trip_id)].copy()
    path = PLOT_DIR / "gps_anomaly_overlay.png"

    plt.figure(figsize=(6, 6))
    plt.plot(base["lon"], base["lat"], color="#334155", linewidth=1.5, label="Route")
    plt.scatter(base["lon"], base["lat"], c=base["fuel_level_filtered"], cmap="viridis", s=26, label="Telemetry samples")

    truth = base[base["anomaly_label"].astype(bool)]
    if not truth.empty:
        plt.scatter(truth["lon"], truth["lat"], color="#dc2626", s=60, label="True anomaly", zorder=5)

    detected = if_trip[if_trip["iforest_flag"].astype(bool)]
    if not detected.empty:
        plt.scatter(detected["lon"], detected["lat"], color="#7c3aed", marker="x", s=70, label="IF detected", zorder=6)

    plt.title(f"GPS / Time-Synchronized Anomaly Overlay\nTrip {trip_id[:8]}")
    plt.xlabel("Longitude")
    plt.ylabel("Latitude")
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    return str(path)


def plot_matrix_profile_visual(
    evaluation_frame: pd.DataFrame,
    detector: MatrixProfileDetector,
    focus_trip: tuple[str, str] | None,
) -> str | None:
    if focus_trip is None:
        return None

    truck_id, trip_id = focus_trip
    base = evaluation_frame[(evaluation_frame["truck_id"] == truck_id) & (evaluation_frame["trip_id"] == trip_id)].copy()
    if base.empty:
        return None

    context_key = (
        str(base["source_threshold_key"].mode().iloc[0])
        if "source_threshold_key" in base.columns and not base["source_threshold_key"].dropna().empty
        else str(base["threshold_context_key"].mode().iloc[0])
        if "threshold_context_key" in base.columns and not base["threshold_context_key"].dropna().empty
        else str(base["context_key"].mode().iloc[0])
        if "context_key" in base.columns and not base["context_key"].dropna().empty
        else None
    )
    analysis = detector.analyze_series(base["fuel_level_filtered"].tolist(), context_key=context_key)
    z_scores = analysis["z_scores"]
    if z_scores.size == 0:
        return None

    path = PLOT_DIR / "matrix_profile_overlay.png"
    threshold = float(analysis["effective_threshold_z"])
    x_values = np.arange(len(z_scores))

    plt.figure(figsize=(10, 6))
    plt.subplot(2, 1, 1)
    plt.plot(base["timestamp"], base["fuel_level_filtered"], color="#0f766e", linewidth=2)
    plt.scatter(
        base.loc[base["anomaly_label"].astype(bool), "timestamp"],
        base.loc[base["anomaly_label"].astype(bool), "fuel_level_filtered"],
        color="#dc2626",
        label="True anomaly",
        zorder=5,
    )
    plt.title(f"Matrix Profile Validation View\nTrip {trip_id[:8]}")
    plt.ylabel("Filtered fuel level")
    plt.legend(loc="best")

    plt.subplot(2, 1, 2)
    plt.plot(x_values, z_scores, color="#b45309", linewidth=1.8, label="MP z-score")
    plt.axhline(threshold, color="#7c2d12", linestyle="--", label=f"Threshold {threshold:.2f}")
    plt.xlabel("Subsequence start index")
    plt.ylabel("Discord z-score")
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()
    return str(path)


def evaluate_pipeline(dataset_path: str | Path = EVALUATION_DATASET_PATH) -> dict:
    ensure_directories()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    PLOT_DIR.mkdir(parents=True, exist_ok=True)
    CURVE_DIR.mkdir(parents=True, exist_ok=True)

    if not (MODEL_DIR / "iforest.pkl").exists() or not (MODEL_DIR / "matrix_profile.json").exists():
        train_pipeline()

    trip_sessions = load_trip_sessions()
    evaluation_frame = engineer_features(load_evaluation_dataset(dataset_path), trip_sessions=trip_sessions)
    if evaluation_frame.empty:
        raise ValueError("Evaluation dataset produced no usable rows.")

    iforest_bundle = load_iforest_bundle()
    if_predictions = score_iforest(iforest_bundle, evaluation_frame)

    mp_detector = MatrixProfileDetector.load()
    mp_row_predictions = mp_detector.score_dataframe(evaluation_frame)
    mp_sequence_rows = []
    for (truck_id, trip_id), group in evaluation_frame.groupby(["truck_id", "trip_id"], dropna=False):
        group = group.sort_values("timestamp")
        context_key = (
            str(group["source_threshold_key"].mode().iloc[0])
            if "source_threshold_key" in group.columns and not group["source_threshold_key"].dropna().empty
            else str(group["threshold_context_key"].mode().iloc[0])
            if "threshold_context_key" in group.columns and not group["threshold_context_key"].dropna().empty
            else str(group["context_key"].mode().iloc[0])
            if "context_key" in group.columns and not group["context_key"].dropna().empty
            else None
        )
        analysis = mp_detector.analyze_series(group["fuel_level_filtered"].tolist(), context_key=context_key)
        z_scores = analysis["z_scores"]
        mp_score = float(z_scores.max()) if len(z_scores) else 0.0
        effective_threshold = float(analysis["effective_threshold_z"])
        trip_source_category = str(group["trip_source_category"].iloc[0]) if "trip_source_category" in group.columns else "unknown"
        sequence_is_injected = bool(group["is_injected"].any()) if "is_injected" in group.columns else bool(group["anomaly_label"].any())
        if trip_source_category == "public_route":
            sequence_subset = "public_clean"
        elif sequence_is_injected:
            sequence_subset = "project_native_injected"
        else:
            sequence_subset = "project_native_clean"
        mp_sequence_rows.append(
            {
                "truck_id": truck_id,
                "trip_id": trip_id,
                "context_key": context_key,
                "mp_score": mp_score,
                "mp_threshold": effective_threshold,
                "mp_signal_column": mp_detector.signal_column,
                "mp_window_size": int(analysis["window_size"]),
                "mp_localization_window_size": int(mp_detector.localization_window_size),
                "mp_anomaly_flag": bool(mp_score >= effective_threshold),
                "anomaly_score": mp_score,
                "anomaly_flag": bool(mp_score >= effective_threshold),
                "model_source": "matrix_profile",
                "anomaly_label": bool(group["anomaly_label"].any()),
                "anomaly_type": "|".join(sorted(set(group.loc[group["anomaly_label"], "anomaly_type"].astype(str)))) or "normal",
                "sequence_length": int(len(group)),
                "record_origin": str(group["record_origin"].iloc[0]) if "record_origin" in group.columns else "unknown",
                "source_dataset": str(group["source_dataset"].iloc[0]) if "source_dataset" in group.columns else "unknown",
                "trip_source_category": trip_source_category,
                "evaluation_subset": sequence_subset,
                "trip_length_band": str(group["trip_length_band"].iloc[0]) if "trip_length_band" in group.columns else "unknown",
                "label_source": str(group["label_source"].iloc[0]) if "label_source" in group.columns else "unknown",
                "is_injected": sequence_is_injected,
            }
        )
    mp_sequence_predictions = pd.DataFrame(mp_sequence_rows)

    if_metrics = {"model": "Isolation Forest", "granularity": "row", "data_source": str(Path(dataset_path))}
    if_metrics.update(compute_metrics(if_predictions, "iforest_flag", score_col="iforest_score"))
    if_latency_frame, if_latency_summary = compute_detection_latency(if_predictions, "iforest_flag")
    if_metrics.update(if_latency_summary)

    mp_metrics = {"model": "Matrix Profile", "granularity": "trip_subsequence", "data_source": str(Path(dataset_path))}
    mp_metrics.update(compute_metrics(mp_sequence_predictions, "mp_anomaly_flag", score_col="mp_score"))
    mp_latency_frame, mp_latency_summary = compute_detection_latency(mp_row_predictions, "mp_anomaly_flag")
    mp_metrics.update(mp_latency_summary)

    metrics_rows = [if_metrics, mp_metrics]
    if_subset_rows = _build_subset_rows(
        "Isolation Forest",
        if_predictions,
        "iforest_flag",
        "iforest_score",
        [
            ("overall", "all_rows", if_predictions),
            ("project_native", "source_subset", if_predictions[if_predictions["trip_source_category"] == "project_native"].copy()),
            ("public_source", "source_subset", if_predictions[if_predictions["trip_source_category"] == "public_route"].copy()),
            ("project_native_clean", "benchmark_partition", if_predictions[if_predictions["evaluation_subset"] == "project_native_clean"].copy()),
            ("project_native_injected", "benchmark_partition", if_predictions[if_predictions["evaluation_subset"] == "project_native_injected"].copy()),
            ("public_clean", "benchmark_partition", if_predictions[if_predictions["evaluation_subset"] == "public_clean"].copy()),
        ],
        granularity="row",
        data_source=str(Path(dataset_path)),
    )
    mp_subset_rows = _build_subset_rows(
        "Matrix Profile",
        mp_sequence_predictions,
        "mp_anomaly_flag",
        "mp_score",
        [
            ("overall", "all_trips", mp_sequence_predictions),
            ("project_native", "source_subset", mp_sequence_predictions[mp_sequence_predictions["trip_source_category"] == "project_native"].copy()),
            ("public_source", "source_subset", mp_sequence_predictions[mp_sequence_predictions["trip_source_category"] == "public_route"].copy()),
            ("project_native_clean", "benchmark_partition", mp_sequence_predictions[mp_sequence_predictions["evaluation_subset"] == "project_native_clean"].copy()),
            ("project_native_injected", "benchmark_partition", mp_sequence_predictions[mp_sequence_predictions["evaluation_subset"] == "project_native_injected"].copy()),
            ("public_clean", "benchmark_partition", mp_sequence_predictions[mp_sequence_predictions["evaluation_subset"] == "public_clean"].copy()),
        ],
        latency_source=mp_row_predictions,
        granularity="trip_subsequence",
        data_source=str(Path(dataset_path)),
    )
    breakdown_rows = if_subset_rows + mp_subset_rows
    dataset_summary = {
        "rows": int(len(evaluation_frame)),
        "trip_count": int(evaluation_frame["trip_id"].nunique()),
        "anomalous_trip_count": int(evaluation_frame.groupby("trip_id", dropna=False)["anomaly_label"].any().sum()),
        "record_origin_counts": evaluation_frame["record_origin"].fillna("unknown").value_counts(dropna=False).to_dict()
        if "record_origin" in evaluation_frame.columns
        else {},
        "augmentation_type_counts": evaluation_frame["augmentation_type"].fillna("none").value_counts(dropna=False).to_dict()
        if "augmentation_type" in evaluation_frame.columns
        else {},
        "label_source_counts": evaluation_frame["label_source"].fillna("unknown").value_counts(dropna=False).to_dict()
        if "label_source" in evaluation_frame.columns
        else {},
        "trip_source_category_counts": evaluation_frame["trip_source_category"].fillna("unknown").value_counts(dropna=False).to_dict()
        if "trip_source_category" in evaluation_frame.columns
        else {},
        "evaluation_subset_counts": evaluation_frame["evaluation_subset"].fillna("unknown").value_counts(dropna=False).to_dict()
        if "evaluation_subset" in evaluation_frame.columns
        else {},
        "trip_length_band_counts": evaluation_frame[["trip_id", "trip_length_band"]].drop_duplicates()["trip_length_band"].fillna("unknown").value_counts(dropna=False).to_dict()
        if "trip_length_band" in evaluation_frame.columns
        else {},
    }

    predictions_path = PREDICTION_DIR / "evaluation_predictions_iforest.csv"
    mp_predictions_path = PREDICTION_DIR / "evaluation_predictions_matrix_profile.csv"
    mp_row_predictions_path = PREDICTION_DIR / "evaluation_predictions_matrix_profile_rows.csv"
    if_latency_path = PREDICTION_DIR / "detection_latency_iforest.csv"
    mp_latency_path = PREDICTION_DIR / "detection_latency_matrix_profile.csv"
    metrics_path = REPORT_DIR / "metrics_summary.csv"
    confusion_path = REPORT_DIR / "confusion_matrices.json"
    report_path = REPORT_DIR / "evaluation_report.txt"

    if_predictions.to_csv(predictions_path, index=False)
    mp_sequence_predictions.to_csv(mp_predictions_path, index=False)
    mp_row_predictions.to_csv(mp_row_predictions_path, index=False)
    if_latency_frame.to_csv(if_latency_path, index=False)
    mp_latency_frame.to_csv(mp_latency_path, index=False)
    pd.DataFrame(metrics_rows).to_csv(metrics_path, index=False)
    pd.DataFrame(breakdown_rows).to_csv(BREAKDOWN_METRICS_PATH, index=False)
    DATASET_SUMMARY_PATH.write_text(json.dumps(dataset_summary, indent=2), encoding="utf-8")
    BREAKDOWN_JSON_PATH.write_text(json.dumps(breakdown_rows, indent=2), encoding="utf-8")

    if_curve_artifacts = save_curve_artifacts(if_predictions, "anomaly_label", "iforest_score", "iforest", "Isolation Forest")
    mp_curve_artifacts = save_curve_artifacts(mp_sequence_predictions, "anomaly_label", "mp_score", "matrix_profile", "Matrix Profile")
    if_confusion_plot = plot_confusion_artifact(if_metrics, "iforest", "Isolation Forest Confusion Matrix")
    mp_confusion_plot = plot_confusion_artifact(mp_metrics, "matrix_profile", "Matrix Profile Confusion Matrix")

    focus_trip = _select_focus_trip(evaluation_frame)
    fuel_plot = plot_fuel_overlay(evaluation_frame, if_predictions, mp_row_predictions, focus_trip)
    gps_plot = plot_gps_overlay(evaluation_frame, if_predictions, focus_trip)
    mp_visual = plot_matrix_profile_visual(evaluation_frame, mp_detector, focus_trip)

    breakdown_lookup = {
        (row["model"], row["subset_name"]): row for row in breakdown_rows
    }
    if_project_native = breakdown_lookup.get(("Isolation Forest", "project_native"), {})
    mp_project_native = breakdown_lookup.get(("Matrix Profile", "project_native"), {})
    if_public_clean = breakdown_lookup.get(("Isolation Forest", "public_clean"), {})
    mp_public_clean = breakdown_lookup.get(("Matrix Profile", "public_clean"), {})

    objective_summary = {
        "precision_target": PRECISION_TARGET,
        "false_positive_rate_target": FPR_TARGET,
        "latency_target_sec": LATENCY_TARGET_SEC,
        "isolation_forest_meets_precision_target": bool(if_metrics["precision"] >= PRECISION_TARGET),
        "isolation_forest_meets_fpr_target": bool(if_metrics["false_positive_rate"] <= FPR_TARGET),
        "isolation_forest_meets_latency_target": bool(if_metrics["latency_target_met"]),
        "matrix_profile_meets_precision_target": bool(mp_metrics["precision"] >= PRECISION_TARGET),
        "matrix_profile_meets_fpr_target": bool(mp_metrics["false_positive_rate"] <= FPR_TARGET),
        "matrix_profile_meets_latency_target": bool(mp_metrics["latency_target_met"]),
        "project_native_benchmark": {
            "isolation_forest_precision": if_project_native.get("precision"),
            "isolation_forest_fpr": if_project_native.get("false_positive_rate"),
            "isolation_forest_latency_sec": if_project_native.get("average_detection_latency_sec"),
            "matrix_profile_precision": mp_project_native.get("precision"),
            "matrix_profile_fpr": mp_project_native.get("false_positive_rate"),
            "matrix_profile_latency_sec": mp_project_native.get("average_detection_latency_sec"),
        },
        "public_clean_false_alarm_characterization": {
            "isolation_forest_fpr": if_public_clean.get("false_positive_rate"),
            "matrix_profile_fpr": mp_public_clean.get("false_positive_rate"),
        },
    }

    confusion_payload = {
        "Isolation Forest": {
            "confusion_matrix": {"TN": if_metrics["TN"], "FP": if_metrics["FP"], "FN": if_metrics["FN"], "TP": if_metrics["TP"]},
            "metrics": if_metrics,
            "curve_artifacts": if_curve_artifacts,
            "confusion_plot": if_confusion_plot,
        },
        "Matrix Profile": {
            "confusion_matrix": {"TN": mp_metrics["TN"], "FP": mp_metrics["FP"], "FN": mp_metrics["FN"], "TP": mp_metrics["TP"]},
            "metrics": mp_metrics,
            "curve_artifacts": mp_curve_artifacts,
            "confusion_plot": mp_confusion_plot,
        },
        "objective_summary": objective_summary,
    }
    confusion_path.write_text(json.dumps(confusion_payload, indent=2), encoding="utf-8")

    visual_artifacts = {
        "fuel_overlay_plot": fuel_plot,
        "gps_overlay_plot": gps_plot,
        "matrix_profile_plot": mp_visual,
        "focus_trip": {"truck_id": focus_trip[0], "trip_id": focus_trip[1]} if focus_trip else None,
    }

    report_lines = [
        "Fuel Anomaly Detection Evaluation",
        "================================",
        f"Evaluation dataset: {Path(dataset_path)}",
        f"IF rows evaluated: {len(if_predictions)}",
        f"MP trip sequences evaluated: {len(mp_sequence_predictions)}",
        f"MP signal column: {mp_detector.signal_column}",
        f"MP trip window size: {mp_detector.window_size}",
        f"MP localization window size: {mp_detector.localization_window_size}",
        "",
        "Evaluation dataset composition:",
        json.dumps(dataset_summary, indent=2),
        "",
        "Objective thresholds:",
        f"- Precision >= {PRECISION_TARGET:.0%}",
        f"- False positive rate <= {FPR_TARGET:.0%}",
        f"- Average detection latency < {LATENCY_TARGET_SEC:.0f} seconds",
        "",
        "Metrics summary:",
        json.dumps(metrics_rows, indent=2),
        "",
        "Objective checks:",
        json.dumps(objective_summary, indent=2),
        "",
        "Source-aware / partition breakdown:",
        json.dumps(breakdown_rows, indent=2),
        "",
        "Visual artifacts:",
        json.dumps(visual_artifacts, indent=2),
        "",
        f"IF predictions CSV: {predictions_path}",
        f"MP predictions CSV: {mp_predictions_path}",
        f"MP row predictions CSV: {mp_row_predictions_path}",
        f"IF latency CSV: {if_latency_path}",
        f"MP latency CSV: {mp_latency_path}",
        f"Metrics CSV: {metrics_path}",
        f"Breakdown metrics CSV: {BREAKDOWN_METRICS_PATH}",
        f"Confusion JSON: {confusion_path}",
        f"Dataset summary JSON: {DATASET_SUMMARY_PATH}",
    ]
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "iforest_predictions_csv": str(predictions_path),
        "matrix_profile_predictions_csv": str(mp_predictions_path),
        "matrix_profile_row_predictions_csv": str(mp_row_predictions_path),
        "iforest_latency_csv": str(if_latency_path),
        "matrix_profile_latency_csv": str(mp_latency_path),
        "metrics_csv": str(metrics_path),
        "metrics_breakdown_csv": str(BREAKDOWN_METRICS_PATH),
        "confusion_json": str(confusion_path),
        "report_txt": str(report_path),
        "dataset_summary_json": str(DATASET_SUMMARY_PATH),
        "visual_artifacts": visual_artifacts,
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the thesis ML pipeline")
    parser.add_argument(
        "--dataset",
        default=str(EVALUATION_DATASET_PATH),
        help="Canonical controlled evaluation dataset path",
    )
    args = parser.parse_args()
    print(json.dumps(evaluate_pipeline(args.dataset), indent=2))


if __name__ == "__main__":
    _cli()
