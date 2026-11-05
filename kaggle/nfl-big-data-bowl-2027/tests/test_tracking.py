import numpy as np
import pytest

from combinelink.tracking import attempt_features, kinematics


def test_constant_speed_line():
    t = np.arange(40) / 10
    k = kinematics(8 * t, 0 * t)
    assert k.speed.iloc[5:-5].to_numpy() == pytest.approx(8, abs=1e-6)
    assert abs(k.accel.iloc[5:-5]).max() < 1e-6


def test_constant_acceleration_recovered():
    t = np.arange(40) / 10
    k = kinematics(0.5 * 3 * t ** 2, 0 * t)
    assert k.accel.iloc[5:-5].to_numpy() == pytest.approx(3, abs=1e-6)


def test_circle_lateral_acceleration_is_v2_over_r():
    t, v, r = np.arange(120) / 10, 6.0, 12.0
    k = kinematics(r * np.cos(v * t / r), r * np.sin(v * t / r))
    assert k.lateral.iloc[10:-10].mean() == pytest.approx(v ** 2 / r, rel=0.02)


def test_smoothing_tames_noise():
    rng = np.random.default_rng(0)
    t = np.arange(60) / 10
    k = kinematics(7 * t + rng.normal(0, 0.02, 60), rng.normal(0, 0.02, 60))
    assert k.speed.max() < 8


def test_features_see_a_stop():
    t = np.arange(30) / 10
    x = np.concatenate([7 * t, np.full(20, 7 * t[-1])])
    out = attempt_features(x, np.zeros(50))
    assert out["peak_decel"] > 5
    assert out["speed_kept_after_peak"] < 0.1


def test_too_short_raises():
    with pytest.raises(ValueError):
        kinematics([0, 1], [0, 1])
