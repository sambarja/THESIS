"""Matrix Profile utilities for thesis-ready fuel anomaly detection.

Matrix Profile stays unsupervised in this project. It is calibrated only on
normal/reference trip sequences and is used as a discord detector over ordered
fuel telemetry. The implementation intentionally separates:

- trip-level discord scoring with a slightly longer subsequence window
- row-level localization with a slightly shorter subsequence window

This keeps trip decisions more stable on the current simulated dataset while
preserving earlier detection overlays and backend responsiveness.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

try:
    import stumpy
except ImportError as exc:  # pragma: no cover
    raise ImportError(
        "stumpy is required for Matrix Profile support. Install ml/requirements.txt."
    ) from exc


BASE_DIR = Path(__file__).resolve().parent
MODEL_DIR = BASE_DIR / "models"

DEFAULT_WINDOW_SIZE = 5
DEFAULT_LOCALIZATION_WINDOW_SIZE = 4
DEFAULT_MIN_SERIES_LENGTH = DEFAULT_WINDOW_SIZE * 2
DEFAULT_LOCALIZATION_MIN_SERIES_LENGTH = DEFAULT_LOCALIZATION_WINDOW_SIZE * 2
DEFAULT_THRESHOLD_Z = 2.5
DEFAULT_SIGNAL_COLUMN = "fuel_level_filtered"


@dataclass
class MatrixProfileDetector:
    window_size: int = DEFAULT_WINDOW_SIZE
    localization_window_size: int = DEFAULT_LOCALIZATION_WINDOW_SIZE
    threshold_z: float = DEFAULT_THRESHOLD_Z
    localization_threshold_z: float = DEFAULT_THRESHOLD_Z
    calibration_quantile: float = 0.99
    min_series_length: int = DEFAULT_MIN_SERIES_LENGTH
    localization_min_series_length: int = DEFAULT_LOCALIZATION_MIN_SERIES_LENGTH
    series_transform: str = "raw"
    signal_column: str = DEFAULT_SIGNAL_COLUMN
    context_thresholds: dict[str, float] | None = None
    localization_context_thresholds: dict[str, float] | None = None

    def fit(self, sequences: list[Iterable[float]]) -> "MatrixProfileDetector":
        self.threshold_z = self._calibrate_threshold(sequences, self.window_size)
        self.localization_threshold_z = self._calibrate_threshold(sequences, self.localization_window_size)
        return self

    def _calibrate_threshold(self, sequences: list[Iterable[float]], window_size: int) -> float:
        z_values: list[np.ndarray] = []
        for sequence in sequences:
            _, profile = compute_matrix_profile(sequence, window_size, transform=self.series_transform)
            z_scores = profile_to_zscores(profile)
            if z_scores.size:
                z_values.append(z_scores)
        if not z_values:
            return float(DEFAULT_THRESHOLD_Z)
        merged = np.concatenate(z_values)
        return float(np.quantile(merged, self.calibration_quantile))

    def resolve_threshold(self, context_key: str | None = None, mode: str = "primary") -> float:
        if mode == "localization":
            base_threshold = float(self.localization_threshold_z)
            context_thresholds = self.localization_context_thresholds or {}
        else:
            base_threshold = float(self.threshold_z)
            context_thresholds = self.context_thresholds or {}

        if context_key and context_key in context_thresholds:
            return float(context_thresholds[context_key])
        return base_threshold

    def _analysis_parameters(self, mode: str) -> tuple[int, float, int]:
        if mode == "localization":
            return (
                int(self.localization_window_size),
                float(self.localization_threshold_z),
                int(self.localization_min_series_length),
            )
        return int(self.window_size), float(self.threshold_z), int(self.min_series_length)

    def analyze_series(
        self,
        series: Iterable[float],
        context_key: str | None = None,
        mode: str = "primary",
    ) -> dict:
        window_size, _, min_series_length = self._analysis_parameters(mode)
        values, profile = compute_matrix_profile(series, window_size, transform=self.series_transform)
        z_scores = profile_to_zscores(profile)
        effective_threshold = self.resolve_threshold(context_key=context_key, mode=mode)
        return {
            "analysis_mode": mode,
            "series_length": int(values.size),
            "window_size": int(window_size),
            "min_series_length": int(min_series_length),
            "threshold_z": float(self.localization_threshold_z if mode == "localization" else self.threshold_z),
            "effective_threshold_z": float(effective_threshold),
            "context_key": context_key,
            "profile": profile,
            "z_scores": z_scores,
            "flags": z_scores >= effective_threshold,
        }

    def localize_series(self, series: Iterable[float], context_key: str | None = None) -> dict:
        return self.analyze_series(series, context_key=context_key, mode="localization")

    def detect_latest(self, series: Iterable[float], context_key: str | None = None) -> dict:
        analysis = self.localize_series(series, context_key=context_key)
        z_scores = analysis["z_scores"]
        effective_threshold = float(analysis["effective_threshold_z"])
        window_size = int(analysis["window_size"])
        min_series_length = int(analysis["min_series_length"])
        if z_scores.size == 0:
            return {
                "is_anomaly": False,
                "score": 0.0,
                "model_source": "matrix_profile",
                "window_size": window_size,
                "threshold_z": round(effective_threshold, 6),
                "signal_column": self.signal_column,
                "reason": f"need at least {min_series_length} ordered readings",
            }

        latest_start = int(z_scores.size - 1)
        latest_score = float(z_scores[latest_start])
        is_anomaly = bool(latest_score >= effective_threshold)
        return {
            "is_anomaly": is_anomaly,
            "score": round(latest_score, 6),
            "model_source": "matrix_profile",
            "window_size": window_size,
            "threshold_z": round(effective_threshold, 6),
            "context_key": context_key,
            "signal_column": self.signal_column,
            "latest_window_start": latest_start,
            "latest_window_end": latest_start + window_size - 1,
            "reason": (
                f"latest fuel-pattern discord score {latest_score:.3f} "
                f"{'>=' if is_anomaly else '<'} threshold {effective_threshold:.3f}"
            ),
        }

    def score_dataframe(
        self,
        frame: pd.DataFrame,
        group_cols: list[str] | None = None,
        value_col: str | None = None,
        sort_col: str = "timestamp",
    ) -> pd.DataFrame:
        if group_cols is None:
            group_cols = ["truck_id", "trip_id"]
        if value_col is None:
            value_col = self.signal_column

        scored_groups: list[pd.DataFrame] = []
        for _, group in frame.sort_values(group_cols + [sort_col]).groupby(group_cols, dropna=False):
            scored_groups.append(self._score_group(group.copy(), value_col=value_col))
        return pd.concat(scored_groups, ignore_index=True) if scored_groups else frame.copy()

    def _score_group(self, group: pd.DataFrame, value_col: str) -> pd.DataFrame:
        context_key = None
        if "source_threshold_key" in group.columns and not group["source_threshold_key"].dropna().empty:
            context_key = str(group["source_threshold_key"].mode(dropna=True).iloc[0])
        elif "threshold_context_key" in group.columns and not group["threshold_context_key"].dropna().empty:
            context_key = str(group["threshold_context_key"].mode(dropna=True).iloc[0])
        elif "context_key" in group.columns and not group["context_key"].dropna().empty:
            context_key = str(group["context_key"].mode(dropna=True).iloc[0])
        analysis = self.localize_series(group[value_col].tolist(), context_key=context_key)
        effective_threshold = float(analysis["effective_threshold_z"])
        window_size = int(analysis["window_size"])
        group["mp_score"] = 0.0
        group["mp_anomaly_flag"] = False
        group["mp_window_start"] = pd.Series([pd.NA] * len(group), dtype="Int64")
        group["mp_threshold"] = effective_threshold
        group["mp_window_size"] = window_size
        group["model_source_mp"] = "matrix_profile"
        group["anomaly_score"] = 0.0
        group["anomaly_flag"] = False
        group["model_source"] = "matrix_profile"

        z_scores: np.ndarray = analysis["z_scores"]
        if z_scores.size == 0:
            return group

        score_idx = group.columns.get_loc("mp_score")
        flag_idx = group.columns.get_loc("mp_anomaly_flag")
        start_idx = group.columns.get_loc("mp_window_start")

        for window_start, z_score in enumerate(z_scores):
            window_end = min(window_start + window_size, len(group))
            current = group.iloc[window_start:window_end]["mp_score"].to_numpy(dtype=float)
            group.iloc[window_start:window_end, score_idx] = np.maximum(current, z_score)
            if z_score >= effective_threshold:
                group.iloc[window_start:window_end, flag_idx] = True
                group.iloc[window_start:window_end, start_idx] = window_start

        group["anomaly_score"] = group["mp_score"]
        group["anomaly_flag"] = group["mp_anomaly_flag"]
        return group

    def save(self, path: Path | None = None) -> Path:
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        target = path or (MODEL_DIR / "matrix_profile.json")
        target.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: Path | None = None) -> "MatrixProfileDetector":
        source = path or (MODEL_DIR / "matrix_profile.json")
        return cls(**json.loads(source.read_text(encoding="utf-8")))


def _clean_series(series: Iterable[float]) -> np.ndarray:
    arr = np.asarray(list(series), dtype=float)
    if arr.size == 0:
        return arr
    if np.isnan(arr).all():
        return np.zeros_like(arr, dtype=float)
    fill_value = float(np.nanmedian(arr))
    return np.nan_to_num(arr, nan=fill_value, posinf=fill_value, neginf=fill_value)


def _transform_series(arr: np.ndarray, transform: str) -> np.ndarray:
    if transform == "diff":
        if arr.size < 2:
            return np.array([], dtype=float)
        return np.diff(arr)
    return arr


def compute_matrix_profile(series: Iterable[float], window_size: int, transform: str = "raw") -> tuple[np.ndarray, np.ndarray]:
    arr = _clean_series(series)
    arr = _transform_series(arr, transform)
    if arr.size < max(window_size * 2, 3):
        return arr, np.array([], dtype=float)
    profile = stumpy.stump(arr, m=window_size)[:, 0].astype(float)
    return arr, profile


def profile_to_zscores(profile: np.ndarray) -> np.ndarray:
    if profile.size == 0:
        return np.array([], dtype=float)
    mean_value = float(np.mean(profile))
    std_value = float(np.std(profile))
    if std_value <= 1e-9:
        return np.zeros_like(profile, dtype=float)
    return (profile - mean_value) / std_value


def _build_context_thresholds(
    detector: MatrixProfileDetector,
    context_sequences: list[tuple[str, list[float]]],
    window_size: int,
    base_threshold: float,
    min_scale: float = 0.70,
    max_scale: float = 1.50,
) -> dict[str, float]:
    context_z_values: dict[str, list[np.ndarray]] = {}
    min_threshold = base_threshold * min_scale
    max_threshold = base_threshold * max_scale

    for context_key, sequence in context_sequences:
        _, profile = compute_matrix_profile(sequence, window_size, transform=detector.series_transform)
        z_scores = profile_to_zscores(profile)
        if context_key and z_scores.size:
            context_z_values.setdefault(context_key, []).append(z_scores)

    thresholds: dict[str, float] = {}
    for context_key, values in context_z_values.items():
        merged = np.concatenate(values) if values else np.array([], dtype=float)
        if merged.size < 10:
            continue
        raw_threshold = float(np.quantile(merged, detector.calibration_quantile))
        thresholds[context_key] = float(np.clip(raw_threshold, min_threshold, max_threshold))
    return thresholds


def calibrate_matrix_profile(
    normal_frame: pd.DataFrame,
    group_cols: list[str] | None = None,
    value_col: str = DEFAULT_SIGNAL_COLUMN,
    window_size: int = DEFAULT_WINDOW_SIZE,
    localization_window_size: int = DEFAULT_LOCALIZATION_WINDOW_SIZE,
) -> MatrixProfileDetector:
    if group_cols is None:
        group_cols = ["truck_id", "trip_id"]
    detector = MatrixProfileDetector(
        window_size=window_size,
        localization_window_size=localization_window_size,
        signal_column=value_col,
    )

    sequences: list[list[float]] = []
    context_sequences: list[tuple[str, list[float]]] = []
    for _, group in normal_frame.groupby(group_cols, dropna=False):
        ordered = group.sort_values("timestamp")
        sequence = ordered[value_col].tolist()
        sequences.append(sequence)
        context_key = None
        if "source_threshold_key" in ordered.columns and not ordered["source_threshold_key"].dropna().empty:
            context_key = str(ordered["source_threshold_key"].mode(dropna=True).iloc[0])
        elif "threshold_context_key" in ordered.columns and not ordered["threshold_context_key"].dropna().empty:
            context_key = str(ordered["threshold_context_key"].mode(dropna=True).iloc[0])
        elif "context_key" in ordered.columns and not ordered["context_key"].dropna().empty:
            context_key = str(ordered["context_key"].mode(dropna=True).iloc[0])
        if context_key:
            context_sequences.append((context_key, sequence))

    detector.fit(sequences)
    detector.context_thresholds = _build_context_thresholds(
        detector,
        context_sequences,
        detector.window_size,
        detector.threshold_z,
    )
    detector.localization_context_thresholds = _build_context_thresholds(
        detector,
        context_sequences,
        detector.localization_window_size,
        detector.localization_threshold_z,
    )
    return detector


def _cli() -> None:
    parser = argparse.ArgumentParser(description="Matrix Profile latest-window scorer")
    parser.add_argument("--series", type=str, required=True, help="JSON array of fuel levels")
    parser.add_argument("--window-size", type=int, default=DEFAULT_WINDOW_SIZE)
    parser.add_argument("--localization-window-size", type=int, default=DEFAULT_LOCALIZATION_WINDOW_SIZE)
    args = parser.parse_args()

    detector = MatrixProfileDetector(
        window_size=args.window_size,
        localization_window_size=args.localization_window_size,
    )
    print(json.dumps(detector.detect_latest(json.loads(args.series)), indent=2))


if __name__ == "__main__":
    _cli()
