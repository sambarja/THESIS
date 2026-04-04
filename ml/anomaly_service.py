"""Flask microservice wrapper around the thesis ML inference helpers."""

from __future__ import annotations

from flask import Flask, jsonify, request

from infer import IFOREST_PATH, MP_PATH, load_iforest_bundle, load_mp_detector, run_combined_inference, run_iforest_inference


app = Flask(__name__)
iforest_bundle = None
mp_detector = None


def load_models() -> None:
    global iforest_bundle, mp_detector
    iforest_bundle = load_iforest_bundle()
    mp_detector = load_mp_detector()


@app.route("/health", methods=["GET"])
def health() -> tuple:
    return jsonify(
        {
            "status": "ok",
            "iforest_loaded": iforest_bundle is not None,
            "matrix_profile_loaded": mp_detector is not None,
            "models": ["IsolationForest", "MatrixProfile"],
            "artifacts": {"iforest": str(IFOREST_PATH), "matrix_profile": str(MP_PATH)},
        }
    )


@app.route("/detect", methods=["POST"])
def detect() -> tuple:
    body = request.get_json(force=True) or {}
    combined = run_combined_inference(
        body,
        fuel_series=body.get("fuel_series"),
        iforest_bundle=iforest_bundle,
        mp_detector=mp_detector,
    )

    details = []
    if combined["if_result"]["anomaly_flag"]:
        details.append(f"IF score={combined['if_result']['anomaly_score']:.3f}")
    if combined["mp_result"] and combined["mp_result"]["anomaly_flag"]:
        details.append(combined["mp_result"].get("reason", "MP discord detected"))

    return jsonify(
        {
            "is_anomaly": combined["anomaly_flag"],
            "model_source": combined["model_source"],
            "combined_score": combined["anomaly_score"],
            "details": " | ".join(details) if details else "No anomaly",
            "if_result": combined["if_result"],
            "mp_result": combined["mp_result"],
        }
    )


@app.route("/detect/batch", methods=["POST"])
def detect_batch() -> tuple:
    body = request.get_json(force=True) or {}
    rows = body.get("rows", [])
    if not rows:
        return jsonify({"error": "No rows provided"}), 400
    return jsonify({"results": [run_iforest_inference(row, bundle=iforest_bundle) for row in rows]})


if __name__ == "__main__":
    load_models()
    app.run(host="0.0.0.0", port=5001, debug=False)
