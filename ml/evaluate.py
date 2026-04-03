"""
SO4 / GO-e — Evaluation Report Script
=======================================
Generates thesis-ready precision/recall/FPR metrics for both
Isolation Forest and Matrix Profile on labeled test scenarios.

Outputs:
  ml/reports/evaluation_report.txt   — human-readable summary
  ml/reports/evaluation_results.csv  — per-row predictions (importable to Excel)
  ml/reports/confusion_matrix.txt    — confusion matrix

Usage:
    python evaluate.py
    python evaluate.py --service   # call anomaly_service.py REST API instead
"""

import os
import csv
import json
import pickle
import argparse
import numpy as np
import pandas as pd
from datetime import datetime

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

from matrix_profile import detect_mp, get_top_discords

REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model.pkl')
SERVICE_URL = 'http://localhost:5001'

os.makedirs(REPORT_DIR, exist_ok=True)


# ══════════════════════════════════════════════════════════════════════════════
#  Test scenario builder
# ══════════════════════════════════════════════════════════════════════════════
def build_test_scenarios():
    """
    Build labeled test cases for evaluation.
    Each row: (fuel_level, speed_kmph, fuel_per_km, label, scenario_name)
    label: 1 = anomaly, 0 = normal
    """
    rng = np.random.default_rng(99)
    rows = []

    # ── NORMAL scenarios (label=0) ────────────────────────────────────────────
    for _ in range(200):
        rows.append((
            float(rng.uniform(25, 100)),
            float(rng.uniform(0, 110)),
            float(rng.uniform(0.10, 0.30)),
            0, 'normal_driving'
        ))

    for _ in range(50):   # parked/idle
        rows.append((float(rng.uniform(20, 100)), 0.0, 0.0, 0, 'parked'))

    for _ in range(50):   # refuel event (fuel goes UP — not an anomaly we flag)
        rows.append((float(rng.uniform(60, 100)), 0.0, 0.0, 0, 'refuel'))

    # ── ANOMALY scenarios (label=1) ───────────────────────────────────────────
    # Fuel theft: massive drop while parked
    for _ in range(50):
        rows.append((
            float(rng.uniform(5, 30)),
            0.0,
            float(rng.uniform(50, 150)),
            1, 'fuel_theft'
        ))

    # Fuel leak: high consumption rate while driving
    for _ in range(50):
        rows.append((
            float(rng.uniform(10, 50)),
            float(rng.uniform(30, 90)),
            float(rng.uniform(2.0, 8.0)),
            1, 'fuel_leak'
        ))

    # Sensor error: near-empty + impossible rate
    for _ in range(30):
        rows.append((
            float(rng.uniform(1, 8)),
            float(rng.uniform(0, 20)),
            float(rng.uniform(80, 300)),
            1, 'sensor_error'
        ))

    return pd.DataFrame(rows, columns=[
        'fuel_level', 'speed_kmph', 'fuel_per_km', 'label', 'scenario'
    ])


# ══════════════════════════════════════════════════════════════════════════════
#  IF evaluation (direct model)
# ══════════════════════════════════════════════════════════════════════════════
def evaluate_if(df: pd.DataFrame):
    if not os.path.exists(MODEL_PATH):
        print("  model.pkl not found — run train_model.py first.")
        return None

    with open(MODEL_PATH, 'rb') as f:
        model_data = pickle.load(f)

    pipeline = model_data['pipeline']
    X        = df[['fuel_level', 'speed_kmph', 'fuel_per_km']].values
    preds    = pipeline.predict(X)         # 1=normal, -1=anomaly
    scores   = pipeline.decision_function(X)

    df = df.copy()
    df['if_pred']  = (preds == -1).astype(int)
    df['if_score'] = -scores   # invert: higher = more anomalous
    return df


# ══════════════════════════════════════════════════════════════════════════════
#  MP evaluation (on synthetic time-series per scenario type)
# ══════════════════════════════════════════════════════════════════════════════
def build_mp_test_series():
    """
    Build time-series scenarios for Matrix Profile evaluation.
    Each series has a known injection point.
    """
    rng = np.random.default_rng(42)
    scenarios = []

    def normal_series(n=80):
        base = 100.0
        s = []
        for _ in range(n):
            base -= rng.uniform(0.15, 0.25)
            base += rng.normal(0, 0.03)
            s.append(max(0, min(100, base)))
        return s

    # Normal only — no anomaly
    s = normal_series(80)
    scenarios.append({'series': s, 'label': 0, 'scenario': 'normal_series',
                      'inject_idx': None})

    # Theft: sudden -25% in LAST window (positions 65-69 of 80-point series)
    s = normal_series(80)
    for i in range(65, 70):
        s[i] = max(0, s[i] - 25)
    scenarios.append({'series': s, 'label': 1, 'scenario': 'theft_series',
                      'inject_idx': 65})

    # Leak: accelerated drain in last 20 readings
    s = normal_series(80)
    for i in range(60, 80):
        s[i] = max(0, s[i] - (i - 59) * 0.8)
    scenarios.append({'series': s, 'label': 1, 'scenario': 'leak_series',
                      'inject_idx': 60})

    # Sensor spike: impossible +30% near end
    s = normal_series(80)
    s[72] = min(100, s[72] + 35)
    s[73] = min(100, s[73] + 30)
    scenarios.append({'series': s, 'label': 1, 'scenario': 'sensor_spike',
                      'inject_idx': 72})

    return scenarios


def evaluate_mp():
    test_series = build_mp_test_series()
    results = []
    for tc in test_series:
        result = detect_mp(tc['series'])
        results.append({
            'scenario':   tc['scenario'],
            'label':      tc['label'],
            'mp_pred':    int(result['is_anomaly']),
            'mp_score':   result['score'],
            'inject_idx': tc['inject_idx'],
            'reason':     result.get('reason', ''),
        })
    return pd.DataFrame(results)


# ══════════════════════════════════════════════════════════════════════════════
#  Metrics
# ══════════════════════════════════════════════════════════════════════════════
def compute_metrics(y_true, y_pred, model_name='Model'):
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())

    precision  = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall     = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    fpr        = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    f1         = (2 * precision * recall / (precision + recall)
                  if (precision + recall) > 0 else 0.0)
    accuracy   = (tp + tn) / (tp + fp + fn + tn) if (tp + fp + fn + tn) > 0 else 0.0

    return {
        'model':     model_name,
        'TP': tp, 'FP': fp, 'FN': fn, 'TN': tn,
        'precision': precision,
        'recall':    recall,
        'fpr':       fpr,
        'f1':        f1,
        'accuracy':  accuracy,
    }


def confusion_matrix_str(m: dict) -> str:
    return (
        f"\n  Confusion Matrix ({m['model']}):\n"
        f"                Predicted +   Predicted -\n"
        f"  Actual    +      {m['TP']:5d}         {m['FN']:5d}\n"
        f"  Actual    -      {m['FP']:5d}         {m['TN']:5d}\n"
    )


# ══════════════════════════════════════════════════════════════════════════════
#  Report writer
# ══════════════════════════════════════════════════════════════════════════════
def write_report(if_metrics, mp_metrics, if_df, mp_df):
    ts  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sep = '=' * 60

    lines = [
        sep,
        '  SO4 — Anomaly Detection Evaluation Report',
        f'  Generated: {ts}',
        sep,
        '',
        '  Models evaluated:',
        '    1. Isolation Forest (IF)  — point anomaly detection',
        '    2. Matrix Profile   (MP)  — pattern/subsequence anomaly',
        '',
        sep,
        '  ISOLATION FOREST RESULTS',
        sep,
        f"  Test samples   : {if_metrics['TP']+if_metrics['FP']+if_metrics['FN']+if_metrics['TN']}",
        f"  Precision      : {if_metrics['precision']:.2%}  (thesis target ≥ 90%)",
        f"  Recall         : {if_metrics['recall']:.2%}",
        f"  False Pos Rate : {if_metrics['fpr']:.2%}  (thesis target ≤ 10%)",
        f"  F1 Score       : {if_metrics['f1']:.2%}",
        f"  Accuracy       : {if_metrics['accuracy']:.2%}",
        confusion_matrix_str(if_metrics),
        '',
        sep,
        '  MATRIX PROFILE RESULTS',
        sep,
        f"  Test series    : {len(mp_df)}",
        f"  Anomaly series : {mp_df['label'].sum()}",
        f"  Detected       : {mp_df['mp_pred'].sum()}",
        '',
    ]

    for _, row in mp_df.iterrows():
        status = 'CORRECT' if row['mp_pred'] == row['label'] else 'WRONG  '
        lines.append(
            f"  [{status}] {row['scenario']:20s}  "
            f"pred={'ANOMALY' if row['mp_pred'] else 'normal ':7s}  "
            f"score={row['mp_score']:.4f}"
        )

    if len(mp_df) > 0:
        mp_m = compute_metrics(mp_df['label'].values, mp_df['mp_pred'].values, 'MP')
        lines += [
            '',
            f"  Precision      : {mp_m['precision']:.2%}",
            f"  Recall         : {mp_m['recall']:.2%}",
            f"  False Pos Rate : {mp_m['fpr']:.2%}",
            f"  F1 Score       : {mp_m['f1']:.2%}",
            confusion_matrix_str(mp_m),
        ]

    lines += [
        '',
        sep,
        '  PER-SCENARIO BREAKDOWN (Isolation Forest)',
        sep,
    ]

    for scenario, grp in if_df.groupby('scenario'):
        n_anom  = (grp['label'] == 1).sum()
        n_total = len(grp)
        caught  = ((grp['if_pred'] == 1) & (grp['label'] == 1)).sum()
        fp_cnt  = ((grp['if_pred'] == 1) & (grp['label'] == 0)).sum()
        lines.append(
            f"  {scenario:20s}  n={n_total:3d}  "
            f"anomalies={n_anom}  caught={caught}  FP={fp_cnt}"
        )

    lines += ['', sep, '  END OF REPORT', sep]

    report_text = '\n'.join(lines)
    report_path = os.path.join(REPORT_DIR, 'evaluation_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    print(report_text)
    print(f"\n  Saved: {report_path}")

    # CSV export
    csv_path = os.path.join(REPORT_DIR, 'evaluation_results.csv')
    if_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")

    mp_path = os.path.join(REPORT_DIR, 'mp_evaluation_results.csv')
    mp_df.to_csv(mp_path, index=False)
    print(f"  Saved: {mp_path}")


# ══════════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--service', action='store_true',
                        help='Send test rows to anomaly_service.py via HTTP')
    args = parser.parse_args()

    print("=" * 60)
    print("  SO4 — Evaluation Report Generator")
    print("=" * 60)

    print("\n[1/3] Building test scenarios…")
    df = build_test_scenarios()
    print(f"      {len(df)} test rows  "
          f"({(df['label']==1).sum()} anomalies, "
          f"{(df['label']==0).sum()} normal)")

    print("\n[2/3] Evaluating Isolation Forest…")
    if_df = evaluate_if(df)
    if if_df is None:
        return
    if_metrics = compute_metrics(if_df['label'].values,
                                 if_df['if_pred'].values, 'IF')

    print("\n[3/3] Evaluating Matrix Profile (time-series scenarios)…")
    mp_df      = evaluate_mp()
    mp_metrics = compute_metrics(mp_df['label'].values,
                                 mp_df['mp_pred'].values, 'MP')

    print("\nWriting report…")
    write_report(if_metrics, mp_metrics, if_df, mp_df)


if __name__ == '__main__':
    main()
