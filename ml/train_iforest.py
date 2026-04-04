"""Train the thesis Isolation Forest model from canonical telemetry datasets."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from matrix_profile import calibrate_matrix_profile
from preprocess import (
    CLEANED_TELEMETRY_PATH,
    FEATURE_COLUMNS,
    MODEL_DIR,
    PREDICTION_DIR,
    engineer_features,
    ensure_directories,
    load_cleaned_telemetry,
    load_trip_sessions,
    save_split_outputs,
    split_by_trip,
)


IFOREST_PATH = MODEL_DIR / "iforest.pkl"


def fit_iforest(train_frame: pd.DataFrame, contamination: float = 0.03) -> dict:
    pipeline = Pipeline(
        [
            ("scaler", StandardScaler()),
            (
                "model",
                IsolationForest(
                    n_estimators=300,
                    contamination=contamination,
                    random_state=42,
                    n_jobs=-1,
                ),
            ),
        ]
    )
    X_train = train_frame[FEATURE_COLUMNS].to_numpy(dtype=float)
    pipeline.fit(X_train)
    train_scores = -pipeline.decision_function(X_train)
    threshold = float(np.quantile(train_scores, 0.995))
    return {
        "pipeline": pipeline,
        "features": list(FEATURE_COLUMNS),
        "score_threshold": threshold,
        "base_score_threshold": threshold,
        "training_score_threshold": threshold,
        "training_threshold_quantile": 0.995,
        "contamination": contamination,
    }


def _build_context_thresholds(
    scores: pd.Series,
    contexts: pd.Series,
    base_threshold: float,
    quantile: float,
    min_scale: float = 0.70,
    max_scale: float = 1.50,
) -> dict[str, float]:
    thresholds: dict[str, float] = {}
    if scores.empty or contexts.empty:
        return thresholds

    min_threshold = base_threshold * min_scale
    max_threshold = base_threshold * max_scale
    scored = pd.DataFrame({"score": scores.astype(float), "context_key": contexts.astype(str)})
    for context_key, group in scored.groupby("context_key", dropna=False):
        if len(group) < 10:
            continue
        raw_threshold = float(np.quantile(group["score"], quantile))
        thresholds[str(context_key)] = float(np.clip(raw_threshold, min_threshold, max_threshold))
    return thresholds


def calibrate_iforest_threshold(
    bundle: dict,
    primary_calibration_frame: pd.DataFrame,
    secondary_calibration_frame: pd.DataFrame | None = None,
    quantile: float = 0.99,
    secondary_quantile: float = 0.999,
) -> dict:
    if primary_calibration_frame.empty and (secondary_calibration_frame is None or secondary_calibration_frame.empty):
        bundle["threshold_quantile"] = None
        bundle["threshold_source"] = "training"
        bundle["context_thresholds"] = {}
        return bundle

    if primary_calibration_frame.empty:
        primary_calibration_frame = secondary_calibration_frame.copy()
        secondary_calibration_frame = None

    primary_scores = -bundle["pipeline"].decision_function(primary_calibration_frame[FEATURE_COLUMNS].to_numpy(dtype=float))
    primary_threshold = float(np.quantile(primary_scores, quantile))
    base_threshold = float(max(bundle.get("training_score_threshold", primary_threshold), primary_threshold))
    bundle["score_threshold"] = base_threshold
    bundle["base_score_threshold"] = base_threshold
    bundle["threshold_quantile"] = quantile
    bundle["threshold_source"] = "project_native_anchor_plus_secondary_clean_validation"
    bundle["context_thresholds"] = {}
    if secondary_calibration_frame is not None and not secondary_calibration_frame.empty:
        secondary_scores = -bundle["pipeline"].decision_function(secondary_calibration_frame[FEATURE_COLUMNS].to_numpy(dtype=float))
        secondary_base_threshold = float(np.quantile(secondary_scores, secondary_quantile))
        raw_context_thresholds = _build_context_thresholds(
            pd.Series(secondary_scores),
            secondary_calibration_frame.get(
                "source_threshold_key",
                secondary_calibration_frame.get("threshold_context_key", secondary_calibration_frame.get("context_key", pd.Series(["global"] * len(secondary_calibration_frame)))),
            ),
            secondary_base_threshold,
            secondary_quantile,
            min_scale=1.0,
            max_scale=1.5,
        )
        public_keys = (
            secondary_calibration_frame.get("source_threshold_key", pd.Series(dtype=str))
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )
        bundle["context_thresholds"] = {
            key: float(max(secondary_base_threshold, raw_context_thresholds.get(key, secondary_base_threshold)))
            for key in public_keys
        }
        bundle["secondary_score_threshold"] = secondary_base_threshold
    return bundle


def resolve_iforest_thresholds(bundle: dict, frame: pd.DataFrame) -> np.ndarray:
    base_threshold = float(bundle.get("score_threshold", bundle.get("base_score_threshold", 0.0)))
    context_thresholds = bundle.get("context_thresholds") or {}
    if ("context_key" not in frame.columns and "threshold_context_key" not in frame.columns) or not context_thresholds:
        return np.full(len(frame), base_threshold, dtype=float)

    threshold_key = frame.get(
        "source_threshold_key",
        frame.get("threshold_context_key", frame.get("context_key", pd.Series(["global"] * len(frame), index=frame.index))),
    ).astype(str)
    thresholds = threshold_key.map(context_thresholds)
    return thresholds.fillna(base_threshold).to_numpy(dtype=float)


def score_iforest(bundle: dict, frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    X = result[FEATURE_COLUMNS].to_numpy(dtype=float)
    scores = -bundle["pipeline"].decision_function(X)
    thresholds = resolve_iforest_thresholds(bundle, result)
    result["iforest_score"] = scores
    result["iforest_threshold"] = thresholds
    result["iforest_flag"] = result["iforest_score"] >= result["iforest_threshold"]
    result["model_source_if"] = "isolation_forest"
    result["anomaly_score"] = result["iforest_score"]
    result["anomaly_flag"] = result["iforest_flag"]
    result["model_source"] = "isolation_forest"
    return result


def save_iforest_bundle(bundle: dict, path: Path = IFOREST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(bundle, handle)


def train_pipeline(dataset_path: str | Path = CLEANED_TELEMETRY_PATH) -> dict:
    ensure_directories()
    raw = load_cleaned_telemetry(dataset_path)
    trip_sessions = load_trip_sessions()
    processed = engineer_features(raw, trip_sessions=trip_sessions)
    splits = split_by_trip(processed, trip_sessions=trip_sessions)
    save_split_outputs(splits, stem="cleaned_telemetry")

    clean_train_frame = splits["train"][~splits["train"]["anomaly_label"]].copy()
    clean_validation_frame = splits["validation"][~splits["validation"]["anomaly_label"]].copy()
    anchor_train_frame = clean_train_frame[clean_train_frame["trip_source_category"] == "project_native"].copy()
    anchor_validation_frame = clean_validation_frame[clean_validation_frame["trip_source_category"] == "project_native"].copy()
    robustness_calibration_frame = pd.concat(
        [
            clean_train_frame[clean_train_frame["trip_source_category"] == "public_route"].copy(),
            clean_validation_frame[clean_validation_frame["trip_source_category"] == "public_route"].copy(),
        ],
        ignore_index=True,
    )

    train_frame = anchor_train_frame if not anchor_train_frame.empty else clean_train_frame
    validation_frame = anchor_validation_frame if not anchor_validation_frame.empty else clean_validation_frame
    if train_frame.empty:
        raise ValueError("Training split has no normal rows to train on.")

    iforest_bundle = fit_iforest(train_frame)
    iforest_bundle = calibrate_iforest_threshold(
        iforest_bundle,
        validation_frame,
        secondary_calibration_frame=robustness_calibration_frame,
    )
    save_iforest_bundle(iforest_bundle)

    mp_detector = calibrate_matrix_profile(train_frame)
    mp_path = mp_detector.save()

    training_predictions = score_iforest(iforest_bundle, train_frame)
    training_predictions.to_csv(PREDICTION_DIR / "training_predictions_iforest.csv", index=False)

    summary = {
        "training_rows": int(len(train_frame)),
        "validation_rows": int(len(validation_frame)),
        "training_trip_count": int(train_frame["trip_id"].nunique()),
        "training_trip_source_counts": train_frame[["trip_id", "trip_source_category"]].drop_duplicates()["trip_source_category"].value_counts(dropna=False).to_dict()
        if "trip_source_category" in train_frame.columns
        else {},
        "validation_trip_source_counts": validation_frame[["trip_id", "trip_source_category"]].drop_duplicates()["trip_source_category"].value_counts(dropna=False).to_dict()
        if "trip_source_category" in validation_frame.columns
        else {},
        "iforest_training_policy": "project_native_clean_anchor_only",
        "iforest_secondary_calibration_trip_source_counts": robustness_calibration_frame[["trip_id", "trip_source_category"]].drop_duplicates()["trip_source_category"].value_counts(dropna=False).to_dict()
        if not robustness_calibration_frame.empty and "trip_source_category" in robustness_calibration_frame.columns
        else {},
        "matrix_profile_training_policy": "project_native_clean_anchor_only",
        "feature_columns": FEATURE_COLUMNS,
        "data_source": str(Path(dataset_path)),
        "iforest_model": str(IFOREST_PATH),
        "matrix_profile_model": str(mp_path),
        "iforest_threshold": float(iforest_bundle["score_threshold"]),
        "iforest_threshold_source": iforest_bundle.get("threshold_source"),
        "iforest_threshold_quantile": iforest_bundle.get("threshold_quantile"),
        "iforest_context_threshold_count": int(len(iforest_bundle.get("context_thresholds", {}))),
        "iforest_threshold_context_column": "source_threshold_key",
        "matrix_profile_signal_column": mp_detector.signal_column,
        "matrix_profile_window_size": int(mp_detector.window_size),
        "matrix_profile_localization_window_size": int(mp_detector.localization_window_size),
        "matrix_profile_threshold_z": float(mp_detector.threshold_z),
        "matrix_profile_localization_threshold_z": float(mp_detector.localization_threshold_z),
        "matrix_profile_context_threshold_count": int(len(mp_detector.context_thresholds or {})),
        "matrix_profile_localization_context_threshold_count": int(len(mp_detector.localization_context_thresholds or {})),
    }
    (MODEL_DIR / "training_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Train the thesis Isolation Forest model")
    parser.add_argument(
        "--dataset",
        default=str(CLEANED_TELEMETRY_PATH),
        help="Canonical cleaned telemetry dataset path",
    )
    args = parser.parse_args()
    print(json.dumps(train_pipeline(args.dataset), indent=2))


if __name__ == "__main__":
    _cli()
