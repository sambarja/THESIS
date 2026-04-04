"""Preprocessing utilities for the canonical thesis telemetry datasets.

The thesis methodology assumes that the edge layer has already timestamped and
roughly synchronized ECU fuel, GPS, and trip-session records before cloud-side
anomaly detection. This module keeps that assumption explicit by:

- supporting no-op sensor calibration parameters for already calibrated signals
- applying median and moving-average filtering to noisy telemetry channels
- merging trip-session timing so fuel/GPS/operating-hour records stay aligned
- deriving thesis-facing features for fuel efficiency, route segments, and
  driver-behavior context without inventing unavailable signals
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
PROCESSED_DIR = OUTPUT_DIR / "processed"
PREDICTION_DIR = OUTPUT_DIR / "predictions"
MODEL_DIR = BASE_DIR / "models"
DATASET_DIR = OUTPUT_DIR / "datasets"

CLEANED_TELEMETRY_PATH = DATASET_DIR / "cleaned_telemetry.csv"
EVALUATION_DATASET_PATH = DATASET_DIR / "evaluation_dataset.csv"
TRIP_SESSIONS_PATH = DATASET_DIR / "trip_sessions.csv"

FEATURE_COLUMNS = [
    "fuel_level_filtered",
    "speed_filtered",
    "fuel_delta",
    "odometer_delta",
    "fuel_per_km",
    "fuel_rate_per_hour",
    "distance_per_fuel",
    "route_segment_performance",
    "driver_behavior_score",
]

FILTER_WINDOW = 3
MEDIAN_WINDOW = 3
TIME_BUCKET_ORDER = ["night", "morning", "afternoon", "evening"]
TRIP_DURATION_BINS = [-0.01, 12.0, 30.0, np.inf]
TRIP_DURATION_LABELS = ["short", "medium", "long"]


def ensure_directories() -> None:
    for path in [OUTPUT_DIR, PROCESSED_DIR, PREDICTION_DIR, MODEL_DIR, DATASET_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def load_dataset_csv(path: str | Path) -> pd.DataFrame:
    csv_path = Path(path)
    if not csv_path.exists():
        raise FileNotFoundError(f"Dataset file not found: {csv_path}")
    return pd.read_csv(csv_path)


def load_cleaned_telemetry(path: str | Path = CLEANED_TELEMETRY_PATH) -> pd.DataFrame:
    return load_dataset_csv(path)


def load_evaluation_dataset(path: str | Path = EVALUATION_DATASET_PATH) -> pd.DataFrame:
    return load_dataset_csv(path)


def load_trip_sessions(path: str | Path = TRIP_SESSIONS_PATH) -> pd.DataFrame:
    frame = load_dataset_csv(path)
    if "start_time" in frame.columns:
        frame["start_time"] = pd.to_datetime(frame["start_time"], utc=True, errors="coerce")
    if "end_time" in frame.columns:
        frame["end_time"] = pd.to_datetime(frame["end_time"], utc=True, errors="coerce")
    return frame


def standardize_telemetry_schema(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    rename_map: dict[str, str] = {}
    if "speed" in df.columns and "speed_kmph" not in df.columns:
        rename_map["speed"] = "speed_kmph"
    if "is_anomaly" in df.columns and "anomaly_label" not in df.columns:
        rename_map["is_anomaly"] = "anomaly_label"
    if "anomaly_flag" in df.columns and "anomaly_label" not in df.columns:
        rename_map["anomaly_flag"] = "anomaly_label"
    if rename_map:
        df = df.rename(columns=rename_map)

    required = {"timestamp", "truck_id", "trip_id", "fuel_level"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Telemetry data missing required columns: {sorted(missing)}")

    if "driver_id" not in df.columns:
        df["driver_id"] = pd.NA
    if "speed_kmph" not in df.columns:
        df["speed_kmph"] = 0.0
    if "lat" not in df.columns:
        df["lat"] = np.nan
    if "lon" not in df.columns:
        df["lon"] = np.nan
    if "odometer_km" not in df.columns:
        df["odometer_km"] = 0.0
    if "engine_status" not in df.columns:
        df["engine_status"] = "on"
    if "anomaly_label" not in df.columns:
        df["anomaly_label"] = False
    if "anomaly_type" not in df.columns:
        df["anomaly_type"] = "normal"
    if "source_file" not in df.columns:
        df["source_file"] = "canonical_dataset"
    if "source_dataset" not in df.columns:
        df["source_dataset"] = "canonical_dataset"
    if "record_origin" not in df.columns:
        df["record_origin"] = "canonical_dataset"
    if "label_source" not in df.columns:
        df["label_source"] = "clean"
    if "is_injected" not in df.columns:
        df["is_injected"] = False

    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()

    numeric_cols = [
        "fuel_level",
        "speed_kmph",
        "odometer_km",
        "lat",
        "lon",
        "latency_ms",
        "fuel_delta",
        "odometer_delta",
        "delta_time_sec",
        "fuel_per_km",
        "fuel_rate_per_hour",
        "anomaly_score",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    text_cols = [
        "truck_id",
        "trip_id",
        "driver_id",
        "engine_status",
        "anomaly_type",
        "source_file",
        "source_dataset",
        "record_origin",
        "label_source",
    ]
    for col in text_cols:
        if col in df.columns:
            df[col] = df[col].astype(str)

    df["fuel_level"] = df["fuel_level"].clip(lower=0.0, upper=100.0)
    df["speed_kmph"] = df["speed_kmph"].fillna(0.0).clip(lower=0.0)
    df["odometer_km"] = df["odometer_km"].ffill().fillna(0.0)
    df["anomaly_label"] = df["anomaly_label"].fillna(False).astype(bool)
    df["is_injected"] = df["is_injected"].fillna(False).astype(bool)
    return df.sort_values(["truck_id", "trip_id", "timestamp"]).reset_index(drop=True)


def apply_sensor_calibration(series: pd.Series, gain: float = 1.0, offset: float = 0.0) -> pd.Series:
    """Support thesis-documented calibration parameters.

    The ECU feed is treated as pre-calibrated by default, so the default gain
    and offset leave the signal unchanged while keeping calibration support
    explicit in the pipeline.
    """

    return (series.astype(float) * gain) + offset


def _rolling_median(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).median()


def _moving_average(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).mean()


def _time_bucket(hour: int) -> str:
    if 0 <= hour < 6:
        return "night"
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 18:
        return "afternoon"
    return "evening"


def _behavior_context(score: float) -> str:
    if score >= 2.0:
        return "aggressive"
    if score >= 1.0:
        return "active"
    return "steady"


def normalize_trip_source_category(source_dataset: str | None, record_origin: str | None) -> str:
    source_dataset = "" if source_dataset is None else str(source_dataset)
    record_origin = "" if record_origin is None else str(record_origin)
    if "geolife" in source_dataset or "public_geolife" in record_origin:
        return "public_route"
    return "project_native"


def build_threshold_context_key(
    source_category: str | None,
    trip_length_band: str | None,
    context_key: str | None,
) -> str:
    source_label = "unknown_source" if source_category is None or pd.isna(source_category) else str(source_category)
    length_label = "unknown_length" if trip_length_band is None or pd.isna(trip_length_band) else str(trip_length_band)
    base_context = "global" if context_key is None or pd.isna(context_key) or str(context_key).strip() == "" else str(context_key)
    return f"{source_label}|{length_label}|{base_context}"


def build_context_key(
    hour_of_day: int | float | None,
    route_segment_index: int | float | None,
    driver_behavior_score: float | None,
) -> str:
    if hour_of_day is None or pd.isna(hour_of_day):
        time_bucket = "unknown"
    else:
        time_bucket = _time_bucket(int(hour_of_day))

    if route_segment_index is None or pd.isna(route_segment_index):
        segment_label = "segment_unknown"
    else:
        segment_label = f"segment_{int(route_segment_index)}"

    behavior = _behavior_context(float(driver_behavior_score or 0.0))
    return f"{time_bucket}|{segment_label}|{behavior}"


def _merge_trip_sessions(frame: pd.DataFrame, trip_sessions: pd.DataFrame | None) -> pd.DataFrame:
    if trip_sessions is None or trip_sessions.empty:
        return frame

    session_cols = [
        "id",
        "start_time",
        "end_time",
        "distance_km",
        "operating_hours",
        "trip_status",
    ]
    available_cols = [col for col in session_cols if col in trip_sessions.columns]
    if "id" not in available_cols:
        return frame

    session_frame = trip_sessions[available_cols].copy().rename(columns={"id": "trip_id"})
    if "start_time" in session_frame.columns:
        session_frame["start_time"] = pd.to_datetime(session_frame["start_time"], utc=True, errors="coerce")
    if "end_time" in session_frame.columns:
        session_frame["end_time"] = pd.to_datetime(session_frame["end_time"], utc=True, errors="coerce")
    return frame.merge(session_frame, on="trip_id", how="left")


def engineer_features(
    frame: pd.DataFrame,
    trip_sessions: pd.DataFrame | None = None,
    calibration_gain: float = 1.0,
    calibration_offset: float = 0.0,
    moving_window: int = FILTER_WINDOW,
    median_window: int = MEDIAN_WINDOW,
) -> pd.DataFrame:
    df = standardize_telemetry_schema(frame)
    df = _merge_trip_sessions(df, trip_sessions)
    group_cols = ["truck_id", "trip_id"]
    grouped = df.groupby(group_cols, dropna=False)

    source_fuel_delta = pd.to_numeric(df["fuel_delta"], errors="coerce") if "fuel_delta" in df.columns else pd.Series(np.nan, index=df.index)
    source_odometer_delta = (
        pd.to_numeric(df["odometer_delta"], errors="coerce") if "odometer_delta" in df.columns else pd.Series(np.nan, index=df.index)
    )
    source_delta_time = (
        pd.to_numeric(df["delta_time_sec"], errors="coerce") if "delta_time_sec" in df.columns else pd.Series(np.nan, index=df.index)
    )
    source_fuel_per_km = (
        pd.to_numeric(df["fuel_per_km"], errors="coerce") if "fuel_per_km" in df.columns else pd.Series(np.nan, index=df.index)
    )
    source_fuel_rate_per_hour = (
        pd.to_numeric(df["fuel_rate_per_hour"], errors="coerce") if "fuel_rate_per_hour" in df.columns else pd.Series(np.nan, index=df.index)
    )

    df["fuel_level_calibrated"] = apply_sensor_calibration(df["fuel_level"].fillna(0.0), calibration_gain, calibration_offset)
    df["speed_calibrated"] = apply_sensor_calibration(df["speed_kmph"].fillna(0.0), 1.0, 0.0)
    df["fuel_level_median"] = grouped["fuel_level_calibrated"].transform(lambda s: _rolling_median(s, median_window))
    df["fuel_level_filtered"] = grouped["fuel_level_median"].transform(lambda s: _moving_average(s, moving_window))
    df["speed_median"] = grouped["speed_calibrated"].transform(lambda s: _rolling_median(s, median_window))
    df["speed_filtered"] = grouped["speed_median"].transform(lambda s: _moving_average(s, moving_window))

    prev_fuel = grouped["fuel_level_filtered"].shift(1)
    prev_odo = grouped["odometer_km"].shift(1)
    prev_speed = grouped["speed_filtered"].shift(1)
    prev_ts = grouped["timestamp"].shift(1)

    df["fuel_delta_filtered"] = (df["fuel_level_filtered"] - prev_fuel).fillna(0.0)
    df["odometer_delta_filtered"] = (df["odometer_km"] - prev_odo).fillna(0.0).clip(lower=0.0)
    df["delta_time_sec_synced"] = (df["timestamp"] - prev_ts).dt.total_seconds().fillna(0.0).clip(lower=0.0)

    filtered_fuel_used = (-df["fuel_delta_filtered"]).clip(lower=0.0)
    df["fuel_per_km_filtered"] = np.where(
        df["odometer_delta_filtered"] > 0,
        filtered_fuel_used / df["odometer_delta_filtered"],
        0.0,
    )
    df["fuel_rate_per_hour_filtered"] = np.where(
        df["delta_time_sec_synced"] > 0,
        filtered_fuel_used / (df["delta_time_sec_synced"] / 3600.0),
        0.0,
    )

    df["fuel_delta"] = source_fuel_delta.fillna(df["fuel_delta_filtered"]).fillna(0.0)
    df["odometer_delta"] = source_odometer_delta.fillna(df["odometer_delta_filtered"]).fillna(0.0).clip(lower=0.0)
    df["delta_time_sec"] = source_delta_time.fillna(df["delta_time_sec_synced"]).fillna(0.0).clip(lower=0.0)
    fuel_used = (-df["fuel_delta"]).clip(lower=0.0)
    fallback_fuel_per_km = pd.Series(
        np.where(df["odometer_delta"] > 0, fuel_used / df["odometer_delta"], 0.0),
        index=df.index,
        dtype=float,
    )
    fallback_fuel_rate_per_hour = pd.Series(
        np.where(df["delta_time_sec"] > 0, fuel_used / (df["delta_time_sec"] / 3600.0), 0.0),
        index=df.index,
        dtype=float,
    )
    df["fuel_per_km"] = source_fuel_per_km.fillna(fallback_fuel_per_km)
    df["fuel_rate_per_hour"] = source_fuel_rate_per_hour.fillna(fallback_fuel_rate_per_hour)
    df["distance_per_fuel"] = np.where(fuel_used > 0, df["odometer_delta"] / fuel_used, 0.0)

    df["speed_delta"] = (df["speed_filtered"] - prev_speed).fillna(0.0)
    df["acceleration_kmph_per_sec"] = np.where(df["delta_time_sec"] > 0, df["speed_delta"] / df["delta_time_sec"], 0.0)
    df["speed_variability"] = grouped["speed_filtered"].transform(lambda s: s.rolling(window=moving_window, min_periods=1).std()).fillna(0.0)
    df["idle_flag"] = ((df["speed_filtered"] <= 3.0) & df["engine_status"].isin(["on", "idle"])).astype(int)
    df["harsh_accel_flag"] = (df["acceleration_kmph_per_sec"] >= 2.5).astype(int)
    df["harsh_brake_flag"] = (df["acceleration_kmph_per_sec"] <= -3.0).astype(int)
    df["driver_behavior_score"] = (
        df["harsh_accel_flag"] + df["harsh_brake_flag"] + (df["speed_variability"] >= 12.0).astype(int)
    ).astype(float)

    if "start_time" in df.columns:
        df["trip_elapsed_sec"] = (df["timestamp"] - df["start_time"]).dt.total_seconds().fillna(0.0).clip(lower=0.0)
    else:
        df["trip_elapsed_sec"] = grouped["delta_time_sec"].cumsum()
    df["trip_elapsed_hours"] = df["trip_elapsed_sec"] / 3600.0

    if "operating_hours" in df.columns:
        df["operating_hours"] = pd.to_numeric(df["operating_hours"], errors="coerce")
    else:
        df["operating_hours"] = np.nan

    session_duration_sec = np.where(
        df["operating_hours"].notna(),
        df["operating_hours"].clip(lower=0.0) * 3600.0,
        grouped["trip_elapsed_sec"].transform("max"),
    )
    df["route_progress"] = np.where(session_duration_sec > 0, df["trip_elapsed_sec"] / session_duration_sec, 0.0)
    df["route_progress"] = np.clip(df["route_progress"], 0.0, 1.0)
    df["route_segment_index"] = pd.cut(
        df["route_progress"],
        bins=[-0.01, 0.33, 0.66, 1.01],
        labels=[0, 1, 2],
        include_lowest=True,
    ).astype(int)
    df["route_segment_label"] = df["route_segment_index"].map({0: "start", 1: "mid", 2: "end"}).astype(str)
    df["route_segment_performance"] = (
        df.groupby(group_cols + ["route_segment_index"], dropna=False)["fuel_per_km"]
        .transform("mean")
        .fillna(0.0)
    )

    df["hour_of_day"] = df["timestamp"].dt.hour
    df["time_of_day_bucket"] = df["hour_of_day"].map(_time_bucket)
    df["driver_behavior_context"] = df["driver_behavior_score"].map(_behavior_context)
    df["trip_duration_min"] = grouped["trip_elapsed_sec"].transform("max") / 60.0
    df["trip_length_band"] = pd.cut(
        df["trip_duration_min"],
        bins=TRIP_DURATION_BINS,
        labels=TRIP_DURATION_LABELS,
        include_lowest=True,
    ).astype(str)
    df["trip_source_category"] = df.apply(
        lambda row: normalize_trip_source_category(row.get("source_dataset"), row.get("record_origin")),
        axis=1,
    )
    df["evaluation_subset"] = np.select(
        [
            df["trip_source_category"].eq("public_route"),
            df["is_injected"].astype(bool),
        ],
        [
            "public_clean",
            "project_native_injected",
        ],
        default="project_native_clean",
    )
    df["source_threshold_key"] = df["trip_source_category"].astype(str) + "|" + df["trip_length_band"].astype(str)
    df["context_key"] = df.apply(
        lambda row: build_context_key(row["hour_of_day"], row["route_segment_index"], row["driver_behavior_score"]),
        axis=1,
    )
    df["threshold_context_key"] = df.apply(
        lambda row: build_threshold_context_key(row["trip_source_category"], row["trip_length_band"], row["context_key"]),
        axis=1,
    )
    df["telemetry_sync_ok"] = (
        df[["timestamp", "fuel_level_filtered", "lat", "lon"]].notna().all(axis=1)
    ).astype(bool)
    df["sequence_id"] = df["truck_id"] + "::" + df["trip_id"]
    df["fuel_level"] = df["fuel_level"].fillna(0.0)
    df["fuel_rate_per_hour"] = df["fuel_rate_per_hour"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df["distance_per_fuel"] = df["distance_per_fuel"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df["route_segment_performance"] = df["route_segment_performance"].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df[FEATURE_COLUMNS] = df[FEATURE_COLUMNS].replace([np.inf, -np.inf], np.nan).fillna(0.0)
    return df.reset_index(drop=True)


def split_by_trip(
    frame: pd.DataFrame,
    train_ratio: float = 0.6,
    val_ratio: float = 0.2,
    trip_sessions: pd.DataFrame | None = None,
) -> dict[str, pd.DataFrame]:
    if frame.empty:
        raise ValueError("No trip data available for splitting.")

    frame_trips = frame[["truck_id", "trip_id", "timestamp", "trip_source_category"]].copy()
    trip_meta = frame_trips[["truck_id", "trip_id", "trip_source_category"]].drop_duplicates()
    fallback = frame.groupby(["truck_id", "trip_id"], dropna=False)["timestamp"].min().reset_index(name="frame_start_time")
    trip_meta = trip_meta.merge(fallback, on=["truck_id", "trip_id"], how="left")
    if trip_sessions is not None and not trip_sessions.empty and {"id", "start_time"}.issubset(trip_sessions.columns):
        ordering = trip_meta.merge(trip_sessions[["id", "start_time"]], left_on="trip_id", right_on="id", how="left").drop(columns=["id"])
        ordering["sort_time"] = ordering["start_time"].fillna(ordering["frame_start_time"])
    else:
        ordering = trip_meta.copy()
        ordering["sort_time"] = ordering["frame_start_time"]

    def _allocate(keys: list[tuple[str, str]]) -> tuple[set[tuple[str, str]], set[tuple[str, str]], set[tuple[str, str]]]:
        total = len(keys)
        if total == 0:
            return set(), set(), set()
        if total == 1:
            return {keys[0]}, set(), set()
        if total == 2:
            return {keys[0]}, set(), {keys[1]}

        train_cut = max(1, int(round(total * train_ratio)))
        val_cut = int(round(total * val_ratio))
        test_cut = total - train_cut - val_cut

        if test_cut <= 0:
            test_cut = 1
            train_cut = max(1, train_cut - 1)
        if val_cut <= 0 and total >= 3:
            val_cut = 1
            if train_cut > test_cut:
                train_cut = max(1, train_cut - 1)
            else:
                test_cut = max(1, test_cut - 1)

        while train_cut + val_cut + test_cut > total:
            if train_cut >= max(val_cut, test_cut) and train_cut > 1:
                train_cut -= 1
            elif val_cut > 0:
                val_cut -= 1
            else:
                test_cut -= 1
        while train_cut + val_cut + test_cut < total:
            train_cut += 1

        train = set(keys[:train_cut])
        val = set(keys[train_cut : train_cut + val_cut])
        test = set(keys[train_cut + val_cut :])
        if not test:
            moved = sorted(train or val)[-1]
            if moved in train:
                train.remove(moved)
            elif moved in val:
                val.remove(moved)
            test.add(moved)
        return train, val, test

    train_keys: set[tuple[str, str]] = set()
    val_keys: set[tuple[str, str]] = set()
    test_keys: set[tuple[str, str]] = set()
    for _, group in ordering.groupby("trip_source_category", dropna=False):
        trip_order = list(group.sort_values(["sort_time", "truck_id", "trip_id"])[["truck_id", "trip_id"]].itertuples(index=False, name=None))
        train_part, val_part, test_part = _allocate(trip_order)
        train_keys |= train_part
        val_keys |= val_part
        test_keys |= test_part

    def _pick(keys: set[tuple[str, str]]) -> pd.DataFrame:
        if not keys:
            return frame.iloc[0:0].copy()
        mask = frame.apply(lambda row: (row["truck_id"], row["trip_id"]) in keys, axis=1)
        return frame.loc[mask].copy().reset_index(drop=True)

    return {
        "train": _pick(train_keys),
        "validation": _pick(val_keys),
        "test": _pick(test_keys),
    }


def save_split_outputs(splits: dict[str, pd.DataFrame], stem: str = "telemetry") -> dict[str, Path]:
    ensure_directories()
    saved: dict[str, Path] = {}
    for split_name, split_frame in splits.items():
        path = PROCESSED_DIR / f"{stem}_{split_name}.csv"
        split_frame.to_csv(path, index=False)
        saved[split_name] = path
    return saved


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Preprocess the canonical thesis telemetry datasets")
    parser.add_argument(
        "--dataset",
        choices=["cleaned", "evaluation"],
        default="cleaned",
        help="Which canonical dataset to preprocess",
    )
    parser.add_argument("--stem", default=None)
    args = parser.parse_args()

    trip_sessions = load_trip_sessions()
    raw = load_cleaned_telemetry() if args.dataset == "cleaned" else load_evaluation_dataset()
    processed = engineer_features(raw, trip_sessions=trip_sessions)
    stem = args.stem or ("cleaned_telemetry" if args.dataset == "cleaned" else "evaluation_dataset")
    saved = save_split_outputs(split_by_trip(processed, trip_sessions=trip_sessions), stem=stem)
    for name, path in saved.items():
        print(f"{name}: {path}")


if __name__ == "__main__":
    _cli()
