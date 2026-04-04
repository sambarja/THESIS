"""Reusable inference helpers for backend and offline evaluation."""

from __future__ import annotations

import argparse
import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from matrix_profile import MatrixProfileDetector
from preprocess import (
    FEATURE_COLUMNS,
    MODEL_DIR,
    build_context_key,
    build_threshold_context_key,
    normalize_trip_source_category,
)


IFOREST_PATH = MODEL_DIR / "iforest.pkl"
MP_PATH = MODEL_DIR / "matrix_profile.json"


def load_iforest_bundle(path: Path = IFOREST_PATH) -> dict:
    with path.open("rb") as handle:
        return pickle.load(handle)


def load_mp_detector(path: Path = MP_PATH) -> MatrixProfileDetector:
    return MatrixProfileDetector.load(path)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        return default if value is None else float(value)
    except (TypeError, ValueError):
        return default


def normalize_feature_payload(payload: dict) -> dict[str, float]:
    fuel_level = _to_float(payload.get("fuel_level"))
    speed_kmph = _to_float(payload.get("speed_kmph", payload.get("speed")))
    fuel_delta = _to_float(payload.get("fuel_delta"))
    odometer_delta = max(_to_float(payload.get("odometer_delta")), 0.0)

    if "fuel_per_km" in payload:
        fuel_per_km = max(_to_float(payload.get("fuel_per_km")), 0.0)
    else:
        fuel_used = max(-fuel_delta, 0.0)
        fuel_per_km = fuel_used / odometer_delta if odometer_delta > 0 else 0.0

    if "fuel_rate_per_hour" in payload:
        fuel_rate_per_hour = max(_to_float(payload.get("fuel_rate_per_hour")), 0.0)
    else:
        delta_time_sec = max(_to_float(payload.get("delta_time_sec")), 0.0)
        fuel_used = max(-fuel_delta, 0.0)
        fuel_rate_per_hour = fuel_used / (delta_time_sec / 3600.0) if delta_time_sec > 0 else 0.0

    if "distance_per_fuel" in payload:
        distance_per_fuel = max(_to_float(payload.get("distance_per_fuel")), 0.0)
    else:
        fuel_used = max(-fuel_delta, 0.0)
        distance_per_fuel = odometer_delta / fuel_used if fuel_used > 0 else 0.0

    route_segment_performance = max(
        _to_float(payload.get("route_segment_performance", payload.get("fuel_per_km", fuel_per_km))),
        0.0,
    )
    driver_behavior_score = max(_to_float(payload.get("driver_behavior_score")), 0.0)
    fuel_level_filtered = _to_float(payload.get("fuel_level_filtered", fuel_level))
    speed_filtered = _to_float(payload.get("speed_filtered", speed_kmph))

    route_segment_index = payload.get("route_segment_index")
    if route_segment_index is None and "route_progress" in payload:
        route_progress = _to_float(payload.get("route_progress"), default=0.5)
        route_segment_index = 0 if route_progress < 0.33 else 1 if route_progress < 0.66 else 2

    timestamp = payload.get("timestamp")
    if "context_key" in payload and payload.get("context_key"):
        context_key = str(payload["context_key"])
    else:
        hour_of_day = None
        if isinstance(timestamp, str) and timestamp:
            try:
                hour_of_day = int(pd.to_datetime(timestamp, utc=True, errors="coerce").hour)
            except Exception:
                hour_of_day = None
        context_key = build_context_key(hour_of_day, route_segment_index, driver_behavior_score)

    trip_source_category = payload.get("trip_source_category")
    if not trip_source_category:
        trip_source_category = normalize_trip_source_category(payload.get("source_dataset"), payload.get("record_origin"))
    trip_length_band = payload.get("trip_length_band", "unknown_length")
    source_threshold_key = f"{trip_source_category}|{trip_length_band}"
    threshold_context_key = build_threshold_context_key(trip_source_category, trip_length_band, context_key)

    return {
        "fuel_level_filtered": fuel_level_filtered,
        "speed_filtered": speed_filtered,
        "fuel_delta": fuel_delta,
        "odometer_delta": odometer_delta,
        "fuel_per_km": fuel_per_km,
        "fuel_rate_per_hour": fuel_rate_per_hour,
        "distance_per_fuel": distance_per_fuel,
        "route_segment_performance": route_segment_performance,
        "driver_behavior_score": driver_behavior_score,
        "context_key": context_key,
        "trip_source_category": trip_source_category,
        "trip_length_band": trip_length_band,
        "source_threshold_key": source_threshold_key,
        "threshold_context_key": threshold_context_key,
    }


def run_iforest_inference(payload: dict, bundle: dict | None = None) -> dict:
    bundle = bundle or load_iforest_bundle()
    normalized = normalize_feature_payload(payload)
    vector = np.array([[normalized[feature] for feature in FEATURE_COLUMNS]], dtype=float)
    score = float(-bundle["pipeline"].decision_function(vector)[0])
    threshold = float(
        bundle.get("context_thresholds", {}).get(
            normalized["source_threshold_key"],
            bundle.get("context_thresholds", {}).get(
                normalized["threshold_context_key"],
                bundle.get("context_thresholds", {}).get(normalized["context_key"], bundle["score_threshold"]),
            ),
        )
    )
    is_anomaly = bool(score >= threshold)
    return {
        "anomaly_score": round(score, 6),
        "anomaly_flag": is_anomaly,
        "model_source": "isolation_forest",
        "threshold": round(threshold, 6),
        "context_key": normalized["context_key"],
        "threshold_context_key": normalized["threshold_context_key"],
        "features": normalized,
    }


def run_mp_inference(
    fuel_series: list[float] | None,
    detector: MatrixProfileDetector | None = None,
    context_key: str | None = None,
) -> dict | None:
    if not fuel_series:
        return None
    detector = detector or load_mp_detector()
    result = detector.detect_latest(fuel_series, context_key=context_key)
    return {
        "anomaly_score": result["score"],
        "anomaly_flag": result["is_anomaly"],
        "model_source": "matrix_profile",
        "threshold": result.get("threshold_z"),
        "window_size": result.get("window_size"),
        "signal_column": result.get("signal_column"),
        "context_key": result.get("context_key"),
        "reason": result.get("reason"),
    }


def run_combined_inference(
    payload: dict,
    fuel_series: list[float] | None = None,
    iforest_bundle: dict | None = None,
    mp_detector: MatrixProfileDetector | None = None,
) -> dict:
    if_result = run_iforest_inference(payload, bundle=iforest_bundle)
    mp_result = run_mp_inference(
        fuel_series,
        detector=mp_detector,
        context_key=if_result.get("source_threshold_key", if_result.get("threshold_context_key", if_result["context_key"])),
    )

    if_flag = if_result["anomaly_flag"]
    mp_flag = mp_result["anomaly_flag"] if mp_result else False

    if if_flag and mp_flag:
        source = "combined"
    elif if_flag:
        source = "isolation_forest"
    elif mp_flag:
        source = "matrix_profile"
    else:
        source = "none"

    return {
        "anomaly_score": round(
            max(if_result["anomaly_score"], mp_result["anomaly_score"] if mp_result else 0.0),
            6,
        ),
        "anomaly_flag": bool(if_flag or mp_flag),
        "model_source": source,
        "if_result": if_result,
        "mp_result": mp_result,
    }


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Run a single offline ML inference")
    parser.add_argument("--payload", required=True, help="JSON object containing telemetry fields")
    parser.add_argument("--fuel-series", default=None, help="Optional JSON list of fuel levels")
    args = parser.parse_args()

    payload = json.loads(args.payload)
    series = json.loads(args.fuel_series) if args.fuel_series else None
    print(json.dumps(run_combined_inference(payload, series), indent=2))


if __name__ == "__main__":
    _cli()
