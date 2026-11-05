"""Movement features from 10 Hz (x, y) tracks. Pure functions, tested on paths with known answers."""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import savgol_filter

from .schema import COLUMNS as C

HZ = 10.0


def kinematics(x, y, hz: float = HZ, window: int = 7, poly: int = 2) -> pd.DataFrame:
    """Speed, tangential and lateral acceleration, from smoothed derivatives of position.

    Differencing raw 10 Hz positions turns centimetre noise into huge accelerations, so all
    derivatives come from a local polynomial fit (Savitzky-Golay).
    """
    x, y = np.asarray(x, float), np.asarray(y, float)
    if len(x) < window:
        raise ValueError(f"need at least {window} frames, got {len(x)}")
    dt = 1 / hz
    vx = savgol_filter(x, window, poly, deriv=1, delta=dt)
    vy = savgol_filter(y, window, poly, deriv=1, delta=dt)
    ax = savgol_filter(x, window, poly, deriv=2, delta=dt)
    ay = savgol_filter(y, window, poly, deriv=2, delta=dt)
    speed = np.hypot(vx, vy)
    safe = np.maximum(speed, 0.25)  # below walking pace, heading is mostly noise
    return pd.DataFrame({
        "speed": speed,
        "accel": (vx * ax + vy * ay) / safe,
        "lateral": np.abs(vx * ay - vy * ax) / safe,
    })


def attempt_features(x, y, hz: float = HZ) -> dict[str, float]:
    k = kinematics(x, y, hz)
    peak = int(k.speed.to_numpy().argmax())
    before = k.speed.iloc[: peak + 1]
    after = k.speed.iloc[peak:]
    return {
        "peak_speed": float(k.speed.max()),
        "time_to_90pct_peak": float((before >= 0.9 * k.speed.max()).to_numpy().argmax() / hz),
        "peak_accel": float(k.accel.max()),
        "peak_decel": float(-k.accel.min()),
        "peak_lateral": float(k.lateral.max()),
        "speed_kept_after_peak": float(after.min() / max(k.speed.max(), 1e-6)),
    }


def features_from_tracking(tracks: pd.DataFrame) -> pd.DataFrame:
    """One row per player x drill x attempt."""
    rows = []
    keys = [C.player, C.drill, C.attempt]
    for key, g in tracks.sort_values(C.frame).groupby(keys, sort=False):
        if len(g) < 7:
            continue
        rows.append(dict(zip(keys, key)) | attempt_features(g[C.x], g[C.y]))
    return pd.DataFrame(rows)
