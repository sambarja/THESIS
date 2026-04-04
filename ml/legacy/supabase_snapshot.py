"""Export the live Supabase dataset and derive ML-ready telemetry snapshots."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import dotenv_values
from supabase import create_client


BASE_DIR = Path(__file__).resolve().parent
BACKEND_ENV = BASE_DIR.parent / "backend" / ".env"
OUT_DIR = BASE_DIR / "outputs" / "datasets" / "live_supabase"
TABLES = ["trucks", "users", "trip_sessions", "telemetry_logs", "alerts"]


def load_client():
    env = dotenv_values(BACKEND_ENV)
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_KEY") or env.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("Supabase credentials were not found in backend/.env")
    return create_client(url, key)


def fetch_all(client, table: str, page_size: int = 1000) -> pd.DataFrame:
    rows = []
    start = 0
    while True:
        resp = client.table(table).select("*").range(start, start + page_size - 1).execute()
        batch = resp.data or []
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return pd.DataFrame(rows)


def derive_live_ml_telemetry(telem: pd.DataFrame) -> pd.DataFrame:
    df = telem.copy()
    if df.empty:
        return df

    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    for col in ["fuel_level", "lat", "lon", "speed", "odometer_km", "anomaly_score"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.sort_values(["truck_id", "trip_id", "timestamp"]).reset_index(drop=True)
    prev_fuel = df.groupby(["truck_id", "trip_id"], dropna=False)["fuel_level"].shift(1)
    prev_odo = df.groupby(["truck_id", "trip_id"], dropna=False)["odometer_km"].shift(1)
    prev_ts = df.groupby(["truck_id", "trip_id"], dropna=False)["timestamp"].shift(1)

    df["delta_time_sec"] = (df["timestamp"] - prev_ts).dt.total_seconds()
    df["fuel_delta"] = df["fuel_level"] - prev_fuel
    df["odometer_delta"] = df["odometer_km"] - prev_odo
    df["fuel_used_pct"] = (-df["fuel_delta"]).clip(lower=0.0)
    df["fuel_per_km"] = np.where(df["odometer_delta"] > 0, df["fuel_used_pct"] / df["odometer_delta"], 0.0)
    df["fuel_rate_per_hour"] = np.where(
        df["delta_time_sec"] > 0,
        df["fuel_used_pct"] / (df["delta_time_sec"] / 3600.0),
        0.0,
    )
    df["speed_kmph"] = df["speed"]
    df["record_origin"] = "live_supabase"
    return df[
        [
            "id",
            "timestamp",
            "truck_id",
            "driver_id",
            "trip_id",
            "fuel_level",
            "lat",
            "lon",
            "speed",
            "speed_kmph",
            "odometer_km",
            "engine_status",
            "anomaly_flag",
            "anomaly_score",
            "model_source",
            "fuel_delta",
            "odometer_delta",
            "delta_time_sec",
            "fuel_per_km",
            "fuel_rate_per_hour",
            "record_origin",
        ]
    ]


def build_quality_report(frames: dict[str, pd.DataFrame]) -> dict:
    telem = frames["telemetry_logs"]
    trips = frames["trip_sessions"]
    trucks = frames["trucks"]
    alerts = frames["alerts"]
    users = frames["users"]

    report = {
        "row_counts": {name: int(len(df)) for name, df in frames.items()},
        "truck_codes": trucks[["id", "truck_code", "status"]].to_dict(orient="records") if not trucks.empty else [],
        "user_roles": users["role"].value_counts(dropna=False).to_dict() if not users.empty else {},
        "alert_types": alerts["alert_type"].value_counts(dropna=False).to_dict() if not alerts.empty else {},
    }

    if not telem.empty:
        report["telemetry_by_truck"] = telem["truck_id"].value_counts(dropna=False).to_dict()
        report["telemetry_null_counts"] = {k: int(v) for k, v in telem.isna().sum().to_dict().items()}
        report["telemetry_trip_ids_missing_in_trip_sessions"] = sorted(
            set(telem["trip_id"].dropna().astype(str)) - set(trips["id"].dropna().astype(str))
        )
        report["trip_sessions_without_telemetry"] = sorted(
            set(trips["id"].dropna().astype(str)) - set(telem["trip_id"].dropna().astype(str))
        )
    return report


def run() -> dict[str, str]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    client = load_client()
    frames = {table: fetch_all(client, table) for table in TABLES}

    outputs = {}
    for table, frame in frames.items():
        path = OUT_DIR / f"{table}.csv"
        frame.to_csv(path, index=False)
        outputs[f"{table}_csv"] = str(path)

    ml_path = OUT_DIR / "live_telemetry_ml.csv"
    derive_live_ml_telemetry(frames["telemetry_logs"]).to_csv(ml_path, index=False)
    outputs["live_telemetry_ml_csv"] = str(ml_path)

    report = build_quality_report(frames)
    report_path = OUT_DIR / "live_quality_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    outputs["live_quality_report_json"] = str(report_path)
    return outputs


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
