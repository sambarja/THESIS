"""
SO4 — Anomaly Detection Training Script
=========================================
Trains an Isolation Forest on a multi-source dataset:

  Source A  bus_fuel_sensors.csv   — 79 000 real bus readings (fuel_per_km, VehicleID)
  Source B  vehicle_telematics.csv — 88 real vehicle readings (speed, kpl)
  Source C  obd2_kit/*.csv         — 2.7 M real OBD-II readings (speed, throttle)
  Source D  Fleet Simulator        — 10 trucks × 30 days (synthetic fallback)
  Source E  User CSV               — any CSV dropped in ml/data/ or --csv flag

Usage:
    python train_model.py
    python train_model.py --csv data/my_fleet.csv
"""

import os
import glob
import pickle
import argparse
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))
SUPABASE_URL = os.environ.get('SUPABASE_URL')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')

# 3 time-resolution-independent features used for training.
# fuel_delta and odometer_delta vary with reporting interval (1s vs 5min)
# and break cross-dataset consistency, so they are excluded from training.
FEATURES   = ['fuel_level', 'speed_kmph', 'fuel_per_km']
DATA_DIR   = os.path.join(os.path.dirname(__file__), 'data')

# ── Helpers ────────────────────────────────────────────────────────────────────
def _row(fuel_level=50.0, speed_kmph=0.0, fuel_delta=0.0,
         odometer_delta=0.0, fuel_per_km=0.0, anomaly=False):
    return {
        'fuel_level':     float(fuel_level),
        'speed_kmph':     float(speed_kmph),
        'fuel_delta':     float(fuel_delta),
        'odometer_delta': float(odometer_delta),
        'fuel_per_km':    float(fuel_per_km),
        '_anomaly':       bool(anomaly),
    }


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE A  — Bus Fuel Sensor Dataset (79 k rows)
#  Columns: Date-time ; VehicleID ; avg_slope ; mass ; stop_ptime ;
#            brake_usage ; accel ; fuel_per_km
#  Key feature: fuel_per_km  (litres consumed per km)
#  Anomaly signal: abnormally HIGH fuel_per_km while bus is stopped
# ══════════════════════════════════════════════════════════════════════════════
def load_bus_dataset(path):
    print(f"      Loading bus sensor dataset ({path})…")
    df = pd.read_csv(path, sep=';', low_memory=False)

    # Estimate speed: stopped fraction correlates inversely with speed
    # avg bus interval ~6 min → odometer_delta ≈ (1-stop_ptime) × avg_speed × 6 min
    avg_speed_est   = 35.0   # km/h typical urban bus
    interval_h      = 6 / 60
    stop_ptime      = pd.to_numeric(df.get('stop_ptime', 0), errors='coerce').fillna(0)
    speed_est       = (1 - stop_ptime.clip(0, 1)) * avg_speed_est
    odo_delta_est   = speed_est * interval_h

    fuel_per_km     = pd.to_numeric(df['fuel_per_km'], errors='coerce').fillna(0)

    # fuel_delta ≈ fuel_per_km × odometer_delta  (all in %-tank units via scale)
    # Bus tank ~150 L → 1 L = 0.67 %
    LITRES_TO_PCT   = 100 / 150
    fuel_delta_est  = -fuel_per_km * odo_delta_est * LITRES_TO_PCT  # negative = consumed

    rng = np.random.default_rng(0)
    records = []
    for i in range(len(df)):
        fpk = float(fuel_per_km.iloc[i])
        spd = float(speed_est.iloc[i])
        od  = float(odo_delta_est.iloc[i])
        fd  = float(fuel_delta_est.iloc[i])
        records.append(_row(
            fuel_level     = float(rng.uniform(20, 100)),  # realistic range
            speed_kmph     = spd,
            fuel_delta     = fd,
            odometer_delta = od,
            fuel_per_km    = fpk,
        ))

    result = pd.DataFrame(records)
    print(f"      → {len(result)} rows from bus dataset.")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE B  — Vehicle Telematics Dataset (88 rows)
#  Columns: deviceID, timeStamp, gps_speed, speed, kpl, rpm …
#  Key features: speed, kpl (km per litre → invert for fuel per km)
# ══════════════════════════════════════════════════════════════════════════════
def load_telematics_dataset(path):
    print(f"      Loading vehicle telematics dataset ({path})…")
    df = pd.read_csv(path, low_memory=False)

    speed    = pd.to_numeric(df.get('speed', df.get('gps_speed', 0)), errors='coerce').fillna(0)
    kpl      = pd.to_numeric(df.get('kpl', 0), errors='coerce').replace(0, np.nan)
    # kpl = km/litre → fuel per km (L/km) → convert to % per km (assume 50L tank)
    fuel_per_km = (1 / kpl).fillna(0) * (100 / 50)

    rng = np.random.default_rng(1)
    records = [
        _row(fuel_level=float(rng.uniform(20, 100)),
             speed_kmph=float(speed.iloc[i]),
             fuel_per_km=float(fuel_per_km.iloc[i]))
        for i in range(len(df))
    ]
    result = pd.DataFrame(records)
    print(f"      → {len(result)} rows from telematics dataset.")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE C  — OBD-II KIT Dataset (81 files, 2.7M rows total)
#  Columns: Time, Vehicle Speed Sensor [km/h], Absolute Throttle Position [%],
#            Engine RPM [RPM], Air Flow Rate from Mass Flow Sensor [g/s] …
#
#  Fuel estimation:
#    MAF (g/s) → fuel flow (g/s) ÷ AFR (14.7 petrol) → litres/s → % per km
#    If MAF unavailable: estimate from throttle × RPM proxy
# ══════════════════════════════════════════════════════════════════════════════
def load_obd2_dataset(folder, sample_per_file=300):
    files = sorted(glob.glob(os.path.join(folder, '*.csv')))
    if not files:
        return pd.DataFrame()

    print(f"      Loading {len(files)} OBD-II files (sample {sample_per_file} rows each)…")
    all_records = []

    for fpath in files:
        try:
            df = pd.read_csv(fpath, low_memory=False)
            df = df.dropna(subset=['Vehicle Speed Sensor [km/h]'])
            if len(df) == 0:
                continue
            # Sample evenly to avoid over-weighting long files
            df = df.sample(min(sample_per_file, len(df)), random_state=42)

            speed   = pd.to_numeric(df['Vehicle Speed Sensor [km/h]'],      errors='coerce').fillna(0)
            rpm     = pd.to_numeric(df.get('Engine RPM [RPM]', 0),           errors='coerce').fillna(800)
            throttle= pd.to_numeric(df.get('Absolute Throttle Position [%]', 0), errors='coerce').fillna(0)
            maf_col = 'Air Flow Rate from Mass Flow Sensor [g/s]'

            if maf_col in df.columns:
                maf         = pd.to_numeric(df[maf_col], errors='coerce').fillna(0)
                # Petrol: stoichiometric AFR 14.7; density ~0.74 kg/L
                fuel_gs     = maf / 14.7            # g/s fuel
                fuel_ls     = fuel_gs / 740         # L/s
                # At 1-second intervals, per km = fuel_L / (speed_km_per_s)
                speed_mps   = (speed / 3.6).replace(0, np.nan)
                fuel_per_m  = fuel_ls / speed_mps   # L/m
                fuel_per_km = (fuel_per_m * 1000).fillna(0)   # L/km
                fuel_per_km_pct = fuel_per_km * (100 / 50)    # % per km (50L tank)
            else:
                # Simplified proxy: throttle + RPM → consumption estimate
                fuel_per_km_pct = (throttle * 0.002 + rpm * 0.00002).clip(0, 5)

            for i in range(len(df)):
                spd = float(speed.iloc[i])
                fpk = float(fuel_per_km_pct.iloc[i])
                all_records.append(_row(
                    fuel_level     = float(np.random.uniform(20, 100)),
                    speed_kmph     = spd,
                    fuel_delta     = -fpk * (spd / 3600),
                    odometer_delta = spd / 3600,
                    fuel_per_km    = fpk,
                ))
        except Exception:
            continue

    result = pd.DataFrame(all_records) if all_records else pd.DataFrame()
    print(f"      → {len(result)} rows from OBD-II dataset.")
    return result


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE D  — Fleet Simulator  (realistic fallback, always included)
# ══════════════════════════════════════════════════════════════════════════════
def simulate_fleet(n_trucks=10, n_days=30, seed=42):
    rng    = np.random.default_rng(seed)
    records = []

    for truck_id in range(n_trucks):
        fuel     = float(rng.uniform(70, 100))
        odometer = float(rng.integers(5000, 80000))
        base_con = rng.uniform(0.15, 0.25)  # % per km

        for day in range(n_days):
            n_trips = rng.integers(1, 4)
            for trip in range(n_trips):
                trip_km    = rng.uniform(30, 150)
                avg_speed  = rng.uniform(40, 95)
                n_readings = max(2, int(trip_km / (avg_speed * 5 / 60)))

                anomaly_type = None
                anomaly_at   = -1
                if rng.random() < 0.05:
                    anomaly_type = rng.choice(['theft', 'leak', 'sensor'])
                    anomaly_at   = rng.integers(1, max(2, n_readings - 1))

                leak_active = False
                for r in range(n_readings):
                    speed   = float(rng.uniform(avg_speed * 0.7, avg_speed * 1.3))
                    km_this = speed * 5 / 60
                    con     = base_con
                    is_anom = False

                    if anomaly_type == 'theft' and r == anomaly_at:
                        fuel   -= float(rng.uniform(20, 45))
                        speed   = 0.0
                        km_this = 0.0
                        is_anom = True
                    elif anomaly_type == 'leak':
                        if r == anomaly_at:
                            leak_active = True
                        if leak_active:
                            con     = float(rng.uniform(0.8, 1.5))
                            is_anom = True
                    elif anomaly_type == 'sensor' and r == anomaly_at:
                        fuel   += float(rng.uniform(15, 40))
                        fuel    = min(fuel, 100.0)
                        is_anom = True

                    prev_fuel = fuel
                    fuel     -= con * km_this + float(rng.normal(0, 0.05))
                    fuel      = max(0.5, min(fuel, 100.0))
                    odometer += km_this
                    fd        = fuel - prev_fuel
                    fpk       = (-fd / km_this) if km_this > 0 else 0  # positive = consumed

                    records.append(_row(
                        fuel_level     = round(fuel, 2),
                        speed_kmph     = round(speed, 1),
                        fuel_delta     = round(fd, 3),
                        odometer_delta = round(km_this, 2),
                        fuel_per_km    = round(fpk, 4),
                        anomaly        = is_anom,
                    ))

            if fuel < 20.0:
                fuel = float(rng.uniform(85, 100))

    df = pd.DataFrame(records)
    print(f"      → {len(df)} rows from fleet simulator "
          f"({df['_anomaly'].sum()} injected anomalies).")
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE E  — Generic CSV  (column-name auto-detection)
# ══════════════════════════════════════════════════════════════════════════════
_COL_MAP = {
    'vehicle_id':  ['vehicle_id','vehicle','truck_id','unit','deviceID','car_id','VehicleID'],
    'fuel_level':  ['fuel_level','fuel_pct','fuel_%','fuel_percent','fuel_quantity',
                    'fuel_gallons','fuel_liters','FUEL_LEVEL'],
    'speed_kmph':  ['speed_kmph','speed_kph','speed','speed_mph','SPEED','gps_speed',
                    'Vehicle Speed Sensor [km/h]'],
    'odometer_km': ['odometer_km','odometer','mileage','distance_km','distance','DISTANCE'],
    'timestamp':   ['created_at','timestamp','local_time','Date','datetime','time','Date-time'],
}

def _find_col(df, key):
    for c in _COL_MAP.get(key, []):
        if c in df.columns: return c
        for col in df.columns:
            if col.lower() == c.lower(): return col
    return None

def load_csv(path):
    df = pd.read_csv(path, sep=None, engine='python', low_memory=False)
    fuel_col  = _find_col(df, 'fuel_level')
    speed_col = _find_col(df, 'speed_kmph')
    odo_col   = _find_col(df, 'odometer_km')
    vid_col   = _find_col(df, 'vehicle_id')
    ts_col    = _find_col(df, 'timestamp')

    if fuel_col is None and speed_col is None:
        raise ValueError("CSV needs at least a fuel or speed column.")

    fuel   = pd.to_numeric(df[fuel_col], errors='coerce').fillna(50) if fuel_col else pd.Series([50]*len(df))
    speed  = pd.to_numeric(df[speed_col], errors='coerce').fillna(0) if speed_col else pd.Series([0]*len(df))
    odo    = pd.to_numeric(df[odo_col], errors='coerce').fillna(0) if odo_col else pd.Series([0]*len(df))

    # mph → km/h
    if speed_col and 'mph' in speed_col.lower(): speed = speed * 1.60934
    if odo_col   and 'mile' in odo_col.lower():  odo   = odo   * 1.60934

    vid    = df[vid_col].astype(str) if vid_col else pd.Series(['csv']*len(df))
    ts     = df[ts_col].astype(str)  if ts_col  else pd.RangeIndex(len(df)).astype(str)

    raw = pd.DataFrame({'vehicle_id': vid, 'fuel_level': fuel,
                        'speed_kmph': speed, 'odometer_km': odo, 'created_at': ts})
    raw = raw.dropna(subset=['fuel_level'])

    records = []
    for v_id, grp in raw.groupby('vehicle_id'):
        grp = grp.reset_index(drop=True)
        for i in range(1, len(grp)):
            fd  = float(grp.fuel_level.iloc[i]) - float(grp.fuel_level.iloc[i-1])
            od  = float(grp.odometer_km.iloc[i]) - float(grp.odometer_km.iloc[i-1])
            fpk = (-fd / od) if od > 0 else 0.0   # positive = consumed
            records.append(_row(
                fuel_level=float(grp.fuel_level.iloc[i]),
                speed_kmph=float(grp.speed_kmph.iloc[i]),
                fuel_delta=fd, odometer_delta=od, fuel_per_km=fpk,
            ))
    return pd.DataFrame(records) if records else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  SOURCE F  — Supabase
# ══════════════════════════════════════════════════════════════════════════════
def load_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return pd.DataFrame()
    try:
        from supabase import create_client
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        resp = (client.table('sensor_data')
                .select('vehicle_id, fuel_level, speed_kmph, odometer_km, created_at')
                .order('vehicle_id').order('created_at').execute())
        raw = pd.DataFrame(resp.data)
        if len(raw) < 4:
            print(f"      Supabase: only {len(raw)} rows, skipping.")
            return pd.DataFrame()
        return load_csv.__wrapped__(raw) if hasattr(load_csv, '__wrapped__') else _compute_deltas(raw)
    except Exception as e:
        print(f"      Supabase skipped: {e}")
        return pd.DataFrame()

def _compute_deltas(raw):
    records = []
    for v_id, grp in raw.groupby('vehicle_id'):
        grp = grp.sort_values('created_at').reset_index(drop=True)
        for i in range(1, len(grp)):
            fd  = float(grp.fuel_level.iloc[i] or 0) - float(grp.fuel_level.iloc[i-1] or 0)
            od  = float(grp.odometer_km.iloc[i] or 0) - float(grp.odometer_km.iloc[i-1] or 0)
            fpk = (-fd / od) if od > 0 else 0.0  # positive = consumed
            records.append(_row(
                fuel_level=float(grp.fuel_level.iloc[i] or 0),
                speed_kmph=float(grp.speed_kmph.iloc[i] or 0),
                fuel_delta=fd, odometer_delta=od, fuel_per_km=fpk,
            ))
    return pd.DataFrame(records) if records else pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--csv', type=str, default=None)
    args = parser.parse_args()

    print("=" * 60)
    print("  SO4 — Isolation Forest Training")
    print("=" * 60)

    frames = []

    # ── A: Bus sensor dataset ─────────────────────────────────────────────────
    print("\n[A] Bus Fuel Sensor Dataset")
    bus_path = os.path.join(DATA_DIR, 'bus_fuel_sensors.csv')
    if os.path.exists(bus_path):
        frames.append(load_bus_dataset(bus_path))
    else:
        print("      Not found — skipping.")

    # ── B: Vehicle telematics ─────────────────────────────────────────────────
    print("\n[B] Vehicle Telematics Dataset")
    tel_path = os.path.join(DATA_DIR, 'vehicle_telematics.csv')
    if os.path.exists(tel_path):
        frames.append(load_telematics_dataset(tel_path))
    else:
        print("      Not found — skipping.")

    # ── C: OBD-II KIT ─────────────────────────────────────────────────────────
    print("\n[C] OBD-II KIT Dataset (81 files)")
    obd2_dir = os.path.join(DATA_DIR, 'obd2_kit')
    if os.path.isdir(obd2_dir):
        frames.append(load_obd2_dataset(obd2_dir, sample_per_file=300))
    else:
        print("      Not found — skipping.")

    # ── D: User CSV ───────────────────────────────────────────────────────────
    csv_path = args.csv
    if csv_path is None:
        csvs = [f for f in os.listdir(DATA_DIR)
                if f.endswith('.csv') and f not in
                   ('bus_fuel_sensors.csv', 'vehicle_telematics.csv', 'fuel_consumption_canada.csv')]
        if csvs:
            csv_path = os.path.join(DATA_DIR, csvs[0])

    if csv_path and os.path.exists(csv_path):
        print(f"\n[D] User CSV: {os.path.basename(csv_path)}")
        try:
            frames.append(load_csv(csv_path))
        except Exception as e:
            print(f"      Failed: {e}")

    # ── E: Supabase ───────────────────────────────────────────────────────────
    print("\n[E] Supabase")
    sb = load_supabase()
    if len(sb):
        frames.append(sb)
    else:
        print("      No data yet.")

    # ── F: Fleet simulator (always added for anomaly ground-truth labels) ─────
    print("\n[F] Fleet Simulator")
    sim = simulate_fleet(n_trucks=10, n_days=30)
    frames.append(sim)

    # ── Combine ───────────────────────────────────────────────────────────────
    combined = pd.concat([f for f in frames if len(f) > 0], ignore_index=True)
    combined = combined.fillna(0)
    X        = combined[FEATURES].values
    y_true   = combined['_anomaly'].values

    print(f"\n[Training] Total rows: {len(X):,}  "
          f"| Real-world rows: {len(X) - len(sim):,}  "
          f"| Labelled anomalies: {int(y_true.sum())}")

    # ── Train ─────────────────────────────────────────────────────────────────
    pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('model',  IsolationForest(
            n_estimators=300,
            contamination=0.05,
            random_state=42,
            n_jobs=-1,
        ))
    ])
    pipeline.fit(X)
    print("      Isolation Forest trained.")

    # ── Evaluate against simulator ground-truth ───────────────────────────────
    sim_idx  = combined.index[-len(sim):]
    X_sim    = combined.loc[sim_idx, FEATURES].values
    y_sim    = combined.loc[sim_idx, '_anomaly'].values
    preds    = pipeline.predict(X_sim)
    flagged  = (preds == -1)

    if y_sim.sum() > 0:
        from sklearn.metrics import precision_score, recall_score, f1_score
        prec = precision_score(y_sim, flagged, zero_division=0)
        rec  = recall_score(y_sim, flagged, zero_division=0)
        f1   = f1_score(y_sim, flagged, zero_division=0)
        fpr  = (flagged & ~y_sim).sum() / max((~y_sim).sum(), 1)
        print(f"\n      Evaluation (simulator ground-truth):")
        print(f"        Precision  : {prec:.2%}  (target ≥ 90%)")
        print(f"        Recall     : {rec:.2%}")
        print(f"        F1         : {f1:.2%}")
        print(f"        False +ve  : {fpr:.2%}  (target ≤ 10%)")

    # ── Sanity checks ──────────────────────────────────────────────────────────
    # [fuel_level, speed_kmph, fuel_per_km]  (fuel_per_km positive = consumed %/km)
    checks = [
        ([5.0,   0.0,  110.0], "ANOMALY", "massive fuel drop while parked (theft)"),
        ([3.0,   0.0,  350.0], "ANOMALY", "near-empty + huge consumption rate"),
        ([15.0, 60.0,    2.5], "ANOMALY", "leak — 10x normal consumption at speed"),
        ([80.0, 80.0,    0.2], "normal",  "highway driving"),
        ([50.0, 40.0,    0.2], "normal",  "city driving"),
        ([50.0,  0.0,    0.0], "normal",  "parked, no change"),
    ]
    print("\n      Sanity checks:")
    for feat_vals, expected, desc in checks:
        p     = pipeline.predict([feat_vals])[0]
        label = "ANOMALY" if p == -1 else "normal "
        ok    = "✓" if (label.strip() == expected) else "✗"
        print(f"        {ok} [{label}]  {desc}")

    # ── Save ───────────────────────────────────────────────────────────────────
    out = os.path.join(os.path.dirname(__file__), 'model.pkl')
    with open(out, 'wb') as f:
        pickle.dump({'pipeline': pipeline, 'features': FEATURES}, f)
    print(f"\n      Saved → {out}")
    print("  Next: python anomaly_service.py\n")


if __name__ == '__main__':
    main()
