"""
SO1-b — Fuel Sensor Calibration & Accuracy Validation Script
=============================================================
Compares sensor-reported fuel levels against manual dipstick readings
to compute:
  - Mean Absolute Percentage Error (MAPE)
  - Root Mean Squared Error (RMSE)
  - Max absolute error
  - Accuracy at ±5% tolerance (SO1 requirement: ≥ 95% within ±5%)

Usage — interactive (attach ESP32 to laptop, open serial or log):
    python calibrate.py                      # uses bundled demo data
    python calibrate.py --csv readings.csv   # your own CSV

CSV format (two columns, no header required, or with header):
    sensor_pct,manual_pct
    85.2,84.0
    60.1,61.5
    ...

Outputs:
    calibration_report.txt     — human-readable accuracy report
    calibration_results.csv    — per-reading error table
    calibration_plot.png       — scatter + error plot (requires matplotlib)

SO1-b requirement: MAPE ≤ 5%, at least 95% of readings within ±5% error.
"""

import os
import csv
import math
import argparse
from datetime import datetime

REPORT_DIR = os.path.join(os.path.dirname(__file__), 'calibration_reports')
os.makedirs(REPORT_DIR, exist_ok=True)

TOLERANCE_PCT = 5.0   # SO1 accuracy requirement: ±5%


# ──────────────────────────────────────────────────────────────────────────────
#  Demo dataset (used when no CSV is provided)
#  Simulates 30 calibration readings at different fill levels.
#  Replace with real sensor vs dipstick readings.
# ──────────────────────────────────────────────────────────────────────────────
DEMO_READINGS = [
    # (sensor_pct, manual_dipstick_pct)
    # Near full
    (97.2, 98.0), (95.8, 97.0), (92.1, 93.5), (90.4, 90.0),
    # Three-quarter
    (75.3, 76.0), (73.1, 74.5), (70.8, 71.0), (68.2, 68.0),
    # Mid-tank
    (55.6, 56.5), (53.2, 54.0), (50.1, 51.0), (48.8, 48.0),
    (45.2, 46.0), (42.7, 43.0), (40.3, 40.0),
    # Quarter-tank
    (30.5, 31.0), (28.2, 28.5), (25.9, 26.0), (23.4, 24.0),
    (21.1, 21.5),
    # Low fuel
    (15.8, 16.0), (13.2, 13.5), (10.4, 11.0), (8.1, 8.5),
    (6.9, 7.0),
    # Near empty
    (4.2, 4.5), (3.1, 3.0), (2.8, 3.0), (1.9, 2.0), (0.8, 1.0),
]


# ──────────────────────────────────────────────────────────────────────────────
#  Metrics
# ──────────────────────────────────────────────────────────────────────────────
def compute_metrics(readings):
    """
    Args:
        readings: list of (sensor_pct, manual_pct) tuples

    Returns dict of metrics.
    """
    errors     = []
    abs_errors = []
    pct_errors = []  # MAPE terms

    for sensor, manual in readings:
        err     = sensor - manual
        abs_err = abs(err)
        errors.append(err)
        abs_errors.append(abs_err)
        if manual > 0:
            pct_errors.append(abs_err / manual * 100.0)
        else:
            pct_errors.append(0.0)   # avoid div/0 at empty

    n = len(readings)
    mae  = sum(abs_errors) / n
    mape = sum(pct_errors) / n
    rmse = math.sqrt(sum(e**2 for e in errors) / n)
    max_err = max(abs_errors)
    bias    = sum(errors) / n   # systematic offset

    within_tol = sum(1 for e in abs_errors if e <= TOLERANCE_PCT)
    within_pct = within_tol / n * 100.0

    return {
        'n':            n,
        'mae':          round(mae,  3),
        'mape':         round(mape, 3),
        'rmse':         round(rmse, 3),
        'max_error':    round(max_err, 3),
        'bias':         round(bias, 3),
        'within_tol_n': within_tol,
        'within_tol_pct': round(within_pct, 2),
        'meets_so1':    mape <= TOLERANCE_PCT and within_pct >= 95.0,
    }


def per_reading_rows(readings):
    rows = []
    for i, (sensor, manual) in enumerate(readings, 1):
        err     = sensor - manual
        abs_err = abs(err)
        pct_err = abs_err / manual * 100.0 if manual > 0 else 0.0
        within  = abs_err <= TOLERANCE_PCT
        rows.append({
            'reading_no':  i,
            'sensor_pct':  round(sensor, 2),
            'manual_pct':  round(manual, 2),
            'error':       round(err,     2),
            'abs_error':   round(abs_err, 2),
            'pct_error':   round(pct_err, 2),
            'within_5pct': 'YES' if within else 'NO',
        })
    return rows


# ──────────────────────────────────────────────────────────────────────────────
#  Report writer
# ──────────────────────────────────────────────────────────────────────────────
def write_report(metrics, rows):
    ts  = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    sep = '=' * 60
    PASS = 'PASS' if metrics['meets_so1'] else 'FAIL'

    lines = [
        sep,
        '  SO1-b — Fuel Sensor Calibration Report',
        f'  Generated  : {ts}',
        f'  Readings   : {metrics["n"]}',
        f'  Tolerance  : ±{TOLERANCE_PCT}%',
        sep,
        '',
        '  ACCURACY METRICS',
        '  ────────────────────────────────────────',
        f'  MAE              : {metrics["mae"]:.3f}%',
        f'  MAPE             : {metrics["mape"]:.3f}%  (target ≤ 5%)',
        f'  RMSE             : {metrics["rmse"]:.3f}%',
        f'  Max abs error    : {metrics["max_error"]:.3f}%',
        f'  Systematic bias  : {metrics["bias"]:+.3f}%  '
        f'({"over-reads" if metrics["bias"] > 0 else "under-reads"})',
        '',
        f'  Within ±5% tol   : {metrics["within_tol_n"]}/{metrics["n"]} '
        f'({metrics["within_tol_pct"]:.1f}%)  (target ≥ 95%)',
        '',
        f'  SO1-b RESULT     : [{PASS}]',
        '',
        sep,
        '  PER-READING DETAIL (sensor vs dipstick)',
        sep,
        f'  {"#":>3}  {"Sensor":>7}  {"Manual":>7}  {"Error":>7}  {"Abs Err":>8}  {"% Err":>7}  {"OK?":>5}',
        '  ' + '-' * 52,
    ]

    for r in rows:
        flag = '' if r['within_5pct'] == 'YES' else ' <--'
        lines.append(
            f'  {r["reading_no"]:>3}  '
            f'{r["sensor_pct"]:>7.2f}  '
            f'{r["manual_pct"]:>7.2f}  '
            f'{r["error"]:>+7.2f}  '
            f'{r["abs_error"]:>8.2f}  '
            f'{r["pct_error"]:>7.2f}  '
            f'{"YES":>5}{flag}'
        )

    lines += ['', sep, '  END OF REPORT', sep]

    report_text = '\n'.join(lines)
    report_path = os.path.join(REPORT_DIR, 'calibration_report.txt')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report_text)

    print(report_text)
    print(f'\n  Saved: {report_path}')

    # CSV export
    csv_path = os.path.join(REPORT_DIR, 'calibration_results.csv')
    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f'  Saved: {csv_path}')

    return report_path


# ──────────────────────────────────────────────────────────────────────────────
#  Optional: matplotlib plot
# ──────────────────────────────────────────────────────────────────────────────
def plot_calibration(rows):
    try:
        import matplotlib.pyplot as plt
        import matplotlib.patches as mpatches
    except ImportError:
        print('  (matplotlib not installed — skipping plot)')
        return

    sensor = [r['sensor_pct'] for r in rows]
    manual = [r['manual_pct'] for r in rows]
    errors = [r['error']      for r in rows]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    fig.patch.set_facecolor('#1e1e1e')

    for ax in (ax1, ax2):
        ax.set_facecolor('#2a2d34')
        ax.tick_params(colors='#e0e0e0')
        for spine in ax.spines.values():
            spine.set_edgecolor('#555')

    # Scatter: sensor vs manual
    colors = ['#22c55e' if abs(e) <= TOLERANCE_PCT else '#ef4444' for e in errors]
    ax1.scatter(manual, sensor, c=colors, s=40, alpha=0.85, zorder=3)
    lo = min(min(manual), min(sensor)) - 2
    hi = max(max(manual), max(sensor)) + 2
    ax1.plot([lo, hi], [lo, hi],      'w--', lw=1, alpha=0.5, label='Perfect')
    ax1.plot([lo, hi], [lo + TOLERANCE_PCT, hi + TOLERANCE_PCT], 'y-', lw=0.8, alpha=0.4)
    ax1.plot([lo, hi], [lo - TOLERANCE_PCT, hi - TOLERANCE_PCT], 'y-', lw=0.8, alpha=0.4,
             label=f'±{TOLERANCE_PCT}% band')
    ax1.set_xlabel('Manual Dipstick (%)', color='#e0e0e0')
    ax1.set_ylabel('Sensor Reading (%)', color='#e0e0e0')
    ax1.set_title('Sensor vs Manual Reading', color='#e0e0e0')
    green_patch = mpatches.Patch(color='#22c55e', label=f'Within ±{TOLERANCE_PCT}%')
    red_patch   = mpatches.Patch(color='#ef4444', label='Outside tolerance')
    ax1.legend(handles=[green_patch, red_patch], facecolor='#1e1e1e', labelcolor='white', fontsize=8)
    ax1.grid(True, color='#444', alpha=0.4)

    # Error bar chart
    bar_colors = ['#22c55e' if abs(e) <= TOLERANCE_PCT else '#ef4444' for e in errors]
    ax2.bar(range(1, len(errors) + 1), errors, color=bar_colors, alpha=0.8)
    ax2.axhline(0,              color='white',  lw=0.8, alpha=0.5)
    ax2.axhline( TOLERANCE_PCT, color='yellow', lw=0.8, linestyle='--', alpha=0.5)
    ax2.axhline(-TOLERANCE_PCT, color='yellow', lw=0.8, linestyle='--', alpha=0.5,
                label=f'±{TOLERANCE_PCT}% tolerance')
    ax2.set_xlabel('Reading #', color='#e0e0e0')
    ax2.set_ylabel('Error (sensor − manual) %', color='#e0e0e0')
    ax2.set_title('Per-Reading Error', color='#e0e0e0')
    ax2.legend(facecolor='#1e1e1e', labelcolor='white', fontsize=8)
    ax2.grid(True, color='#444', alpha=0.4, axis='y')

    plt.tight_layout()
    plot_path = os.path.join(REPORT_DIR, 'calibration_plot.png')
    plt.savefig(plot_path, dpi=150, facecolor='#1e1e1e')
    plt.close()
    print(f'  Saved: {plot_path}')


# ──────────────────────────────────────────────────────────────────────────────
#  CSV loader
# ──────────────────────────────────────────────────────────────────────────────
def load_csv(path):
    readings = []
    with open(path, newline='', encoding='utf-8') as f:
        sample = f.read(512)
        f.seek(0)
        has_header = not sample.strip()[0].isdigit()
        reader = csv.reader(f)
        if has_header:
            next(reader, None)   # skip header row
        for row in reader:
            if len(row) >= 2:
                try:
                    readings.append((float(row[0]), float(row[1])))
                except ValueError:
                    continue   # skip malformed rows
    return readings


# ──────────────────────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description='SO1-b Fuel Sensor Calibration Validator')
    parser.add_argument('--csv', metavar='FILE',
                        help='CSV file with sensor_pct,manual_pct columns')
    parser.add_argument('--plot', action='store_true', default=True,
                        help='Generate calibration plot (requires matplotlib)')
    args = parser.parse_args()

    print('=' * 60)
    print('  SO1-b — Fuel Sensor Calibration Validator')
    print('=' * 60)

    if args.csv:
        print(f'\n  Loading readings from: {args.csv}')
        readings = load_csv(args.csv)
        print(f'  Loaded {len(readings)} readings.')
    else:
        print('\n  Using built-in demo dataset (30 simulated readings).')
        print('  To use real data: python calibrate.py --csv your_readings.csv')
        readings = DEMO_READINGS

    if len(readings) < 5:
        print('  ERROR: need at least 5 readings for meaningful statistics.')
        return

    metrics = compute_metrics(readings)
    rows    = per_reading_rows(readings)

    write_report(metrics, rows)

    if args.plot:
        plot_calibration(rows)


if __name__ == '__main__':
    main()
