"""
SO4 — Dual-Model Anomaly Detection Microservice
=================================================
Flask service combining Isolation Forest (IF) + Matrix Profile (MP).

  IF  → point anomaly  : single reading scored against learned distribution
  MP  → pattern anomaly: unusual subsequence in recent fuel time series

The Node.js backend calls POST /detect on every sensor ingestion,
sending both a single-point feature vector AND a rolling fuel_series.

Run AFTER train_model.py:
    python anomaly_service.py
"""

import os
import pickle
import numpy as np
from flask import Flask, request, jsonify
from matrix_profile import detect_mp

app       = Flask(__name__)
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model.pkl')
model_data = None


# ── Load model ─────────────────────────────────────────────────────────────────
def load_model():
    global model_data
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(
            f"model.pkl not found. Run: python train_model.py"
        )
    with open(MODEL_PATH, 'rb') as f:
        model_data = pickle.load(f)
    print(f"[anomaly_service] IF model loaded. Features: {model_data['features']}")


# ── Health ─────────────────────────────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status':       'ok',
        'if_loaded':    model_data is not None,
        'mp_available': True,
        'models':       ['IsolationForest', 'MatrixProfile'],
    })


# ── Main detection endpoint ────────────────────────────────────────────────────
@app.route('/detect', methods=['POST'])
def detect():
    """
    Request body (from Node.js server.js):
    {
      "fuel_level"  : float,      current fuel %
      "speed_kmph"  : float,      current speed
      "fuel_delta"  : float,      change since previous reading
      "odometer_delta": float,    km since previous reading
      "fuel_per_km" : float,      consumption rate (positive = consumed)
      "fuel_series" : [float, …]  rolling window of recent fuel_level values
                                  (optional — enables Matrix Profile)
    }

    Response:
    {
      "is_anomaly"   : bool,      true if IF OR MP flags it
      "if_result"    : {...},     Isolation Forest result
      "mp_result"    : {...},     Matrix Profile result (or null)
      "model_source" : str,       "IF" | "MP" | "IF+MP" | "none"
      "combined_score": float,    max(IF_score, MP_score)
      "details"      : str        human-readable summary
    }
    """
    if model_data is None:
        return jsonify({'error': 'Model not loaded'}), 500

    body     = request.get_json(force=True) or {}
    pipeline = model_data['pipeline']

    # ── Isolation Forest ───────────────────────────────────────────────────────
    X = np.array([[
        float(body.get('fuel_level',  0) or 0),
        float(body.get('speed_kmph',  0) or 0),
        float(body.get('fuel_per_km', 0) or 0),
    ]])

    if_pred  = pipeline.predict(X)[0]          # 1=normal, -1=anomaly
    if_score = pipeline.decision_function(X)[0] # lower = more anomalous
    # Normalize IF score: invert and scale so higher = more anomalous
    if_z     = -float(if_score)

    if_result = {
        'is_anomaly': bool(if_pred == -1),
        'score':      round(if_z, 4),
        'model':      'IF',
        'raw_score':  round(float(if_score), 4),
    }

    # ── Matrix Profile ─────────────────────────────────────────────────────────
    fuel_series = body.get('fuel_series')
    if fuel_series and isinstance(fuel_series, list) and len(fuel_series) >= 10:
        mp_result = detect_mp(fuel_series)
    else:
        mp_result = None

    # ── Combine ────────────────────────────────────────────────────────────────
    if_flag = if_result['is_anomaly']
    mp_flag = mp_result['is_anomaly'] if mp_result else False

    is_anomaly = if_flag or mp_flag

    if if_flag and mp_flag:
        model_source = 'IF+MP'
    elif if_flag:
        model_source = 'IF'
    elif mp_flag:
        model_source = 'MP'
    else:
        model_source = 'none'

    # Combined score: max of both normalised scores
    mp_z           = mp_result['score'] if mp_result else 0.0
    combined_score = round(max(if_z, mp_z), 4)

    # Human-readable detail for the alert record
    details_parts = []
    if if_flag:
        details_parts.append(
            f"IF: fuel={body.get('fuel_level')}% "
            f"speed={body.get('speed_kmph')}km/h "
            f"rate={body.get('fuel_per_km'):.3f}%/km "
            f"(score={if_z:.3f})"
        )
    if mp_flag and mp_result:
        details_parts.append(f"MP: {mp_result.get('reason', '')}")

    details = ' | '.join(details_parts) if details_parts else 'No anomaly'

    if is_anomaly:
        print(f"[anomaly_service] ANOMALY [{model_source}] — {details}")

    return jsonify({
        'is_anomaly':    is_anomaly,
        'if_result':     if_result,
        'mp_result':     mp_result,
        'model_source':  model_source,
        'combined_score': combined_score,
        'details':       details,
    })


# ── Batch endpoint for evaluate.py ────────────────────────────────────────────
@app.route('/detect/batch', methods=['POST'])
def detect_batch():
    """
    Accepts a list of feature rows and returns predictions for all.
    Used by evaluate.py for bulk evaluation.

    Body: { "rows": [{"fuel_level":…, "speed_kmph":…, "fuel_per_km":…}, …] }
    """
    if model_data is None:
        return jsonify({'error': 'Model not loaded'}), 500

    body = request.get_json(force=True) or {}
    rows = body.get('rows', [])
    if not rows:
        return jsonify({'error': 'No rows provided'}), 400

    pipeline = model_data['pipeline']
    X = np.array([
        [float(r.get('fuel_level', 0) or 0),
         float(r.get('speed_kmph', 0) or 0),
         float(r.get('fuel_per_km', 0) or 0)]
        for r in rows
    ])

    preds  = pipeline.predict(X)
    scores = pipeline.decision_function(X)

    return jsonify({
        'results': [
            {
                'is_anomaly': bool(preds[i] == -1),
                'score':      round(-float(scores[i]), 4),
                'model':      'IF',
            }
            for i in range(len(rows))
        ]
    })


# ── Start ──────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    load_model()
    print("[anomaly_service] Listening on http://localhost:5001")
    print("[anomaly_service] Models: Isolation Forest + Matrix Profile")
    app.run(host='0.0.0.0', port=5001, debug=False)
