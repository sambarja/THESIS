"""
SO4 — Matrix Profile Anomaly Detection Module
===============================================
Detects anomalous PATTERNS in fuel level time series using Matrix Profile.

Unlike Isolation Forest (point anomaly), Matrix Profile finds unusual
subsequences — e.g., an abnormal rate of decline over 10 consecutive readings
that no other window in the series resembles. This is called a "discord."

Used alongside Isolation Forest for dual-model anomaly detection.

Standalone usage:
    from matrix_profile import detect_mp, get_top_discords
    result = detect_mp(fuel_series=[85.2, 84.8, 84.1, ..., 62.0])

Called by anomaly_service.py on every sensor ingestion (when fuel_series
is provided by the Node.js backend).
"""

import numpy as np

try:
    import stumpy
    STUMPY_AVAILABLE = True
except ImportError:
    STUMPY_AVAILABLE = False
    print("[matrix_profile] WARNING: stumpy not installed. "
          "Run: pip install stumpy")

# ── Configuration ──────────────────────────────────────────────────────────────
MP_WINDOW        = 12    # subsequence length (12 readings × 5s = 60s window)
DISCORD_Z_THRESH = 2.0   # z-score above mean → flag as anomaly


# ── Core: detect anomaly in latest window ──────────────────────────────────────
def detect_mp(fuel_series: list, window: int = MP_WINDOW) -> dict:
    """
    Run Matrix Profile on a fuel level time series and check whether the
    most recent subsequence is a discord (anomaly).

    Args:
        fuel_series : chronological list of fuel_level readings (latest LAST)
        window      : subsequence length for matrix profile

    Returns dict:
        is_anomaly  : bool
        score       : z-score (higher = more anomalous)
        model       : 'MP'
        reason      : human-readable explanation
        raw_mp_value: raw matrix profile distance at latest index
    """
    if not STUMPY_AVAILABLE:
        return _unavailable('stumpy not installed')

    arr = np.array(fuel_series, dtype=float)
    n   = len(arr)

    if n < window * 2:
        return _unavailable(f'need ≥{window * 2} readings, got {n}')

    # Remove NaN / Inf
    arr = np.nan_to_num(arr, nan=np.nanmean(arr))

    # Compute self-join matrix profile
    mp_result     = stumpy.stump(arr, m=window)
    profile_vals  = mp_result[:, 0].astype(float)   # MP distances

    mean_p = float(np.mean(profile_vals))
    std_p  = float(np.std(profile_vals)) + 1e-9

    # Check the last LOOK_BACK windows (covers the most recent readings)
    LOOK_BACK  = min(window, len(profile_vals))
    recent_vals = profile_vals[-LOOK_BACK:]
    max_recent  = float(np.max(recent_vals))
    max_idx     = int(np.argmax(recent_vals)) + (len(profile_vals) - LOOK_BACK)

    raw_score   = max_recent
    z_score     = (raw_score - mean_p) / std_p

    is_anomaly  = z_score > DISCORD_Z_THRESH

    # Build human-readable reason
    if is_anomaly:
        fuel_start = float(arr[max_idx])
        fuel_end   = float(arr[max_idx + window - 1]) if max_idx + window - 1 < n else float(arr[-1])
        delta      = round(fuel_end - fuel_start, 2)
        reason     = (f"Discord at window {max_idx}: fuel changed {delta:+.2f}% "
                      f"over {window} readings (z={z_score:.2f})")
    else:
        reason = f"Latest pattern normal (z={z_score:.2f} < {DISCORD_Z_THRESH})"

    return {
        'is_anomaly':   bool(is_anomaly),
        'score':        round(z_score, 4),
        'model':        'MP',
        'raw_mp_value': round(raw_score, 4),
        'window_used':  window,
        'series_length': n,
        'reason':       reason,
    }


# ── Batch: top-k discords for analysis / evaluation ───────────────────────────
def get_top_discords(fuel_series: list, window: int = MP_WINDOW,
                     top_k: int = 5) -> list:
    """
    Return the top-k most anomalous subsequence positions in the series.
    Used by evaluate.py for batch analysis and thesis validation reports.

    Returns list of dicts:
        index       : position in the series
        z_score     : anomaly score
        fuel_at_idx : fuel level at that index
        is_anomaly  : bool (z > threshold)
    """
    if not STUMPY_AVAILABLE:
        return []

    arr = np.array(fuel_series, dtype=float)
    if len(arr) < window * 2:
        return []

    arr          = np.nan_to_num(arr, nan=np.nanmean(arr))
    mp_result    = stumpy.stump(arr, m=window)
    profile_vals = mp_result[:, 0].astype(float)

    mean_p  = float(np.mean(profile_vals))
    std_p   = float(np.std(profile_vals)) + 1e-9
    z_scores = (profile_vals - mean_p) / std_p

    top_idx = np.argsort(z_scores)[-top_k:][::-1]

    return [
        {
            'index':       int(i),
            'z_score':     round(float(z_scores[i]), 4),
            'fuel_at_idx': round(float(arr[i]), 2),
            'is_anomaly':  bool(z_scores[i] > DISCORD_Z_THRESH),
        }
        for i in top_idx
    ]


# ── Motif finder (normal patterns, for reference) ─────────────────────────────
def get_top_motifs(fuel_series: list, window: int = MP_WINDOW,
                   top_k: int = 3) -> list:
    """
    Return the top-k most recurring (most normal) subsequences.
    The inverse of discords — used in evaluation reports.
    """
    if not STUMPY_AVAILABLE:
        return []

    arr = np.array(fuel_series, dtype=float)
    if len(arr) < window * 2:
        return []

    arr          = np.nan_to_num(arr, nan=np.nanmean(arr))
    mp_result    = stumpy.stump(arr, m=window)
    profile_vals = mp_result[:, 0].astype(float)

    # Motifs = lowest MP values (most similar to some other window)
    top_idx = np.argsort(profile_vals)[:top_k]

    return [
        {
            'index':        int(i),
            'mp_distance':  round(float(profile_vals[i]), 4),
            'fuel_at_idx':  round(float(arr[i]), 2),
        }
        for i in top_idx
    ]


# ── Internal helpers ──────────────────────────────────────────────────────────
def _unavailable(reason: str) -> dict:
    return {
        'is_anomaly':    False,
        'score':         0.0,
        'model':         'MP',
        'raw_mp_value':  0.0,
        'window_used':   MP_WINDOW,
        'series_length': 0,
        'reason':        reason,
    }


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == '__main__':
    import random
    random.seed(42)

    # Build normal series: gradual consumption ~0.2%/reading
    normal = [100.0 - i * 0.2 + random.gauss(0, 0.05) for i in range(60)]

    # Inject theft at reading 40: sudden -25%
    series = normal.copy()
    series[40] -= 25.0
    series[41] -= 24.5
    series[42] -= 24.0

    print("Matrix Profile self-test")
    print("=" * 40)

    # Normal window: series before injection (readings 0-34)
    result_normal = detect_mp(series[:35])
    print(f"Normal window : is_anomaly={result_normal['is_anomaly']}  "
          f"score={result_normal['score']:.4f}")

    # Real-time detection: rolling buffer ending just after theft (readings 15-54)
    # In production, detect_mp is called with the last 40 readings from the DB
    realtime_buf = series[15:55]   # 40 readings, theft at index 25 within this buffer
    result_rt = detect_mp(realtime_buf)
    print(f"Real-time buf : is_anomaly={result_rt['is_anomaly']}  "
          f"score={result_rt['score']:.4f}")
    print(f"Reason: {result_rt['reason']}")

    # Top discords
    discords = get_top_discords(series, top_k=3)
    print(f"\nTop discords: {discords}")
