import numpy as np
import pytest

from ntl.metrics import (
    balanced_accuracy,
    lab_accuracy,
    leaderboard_noise,
    paired_prompt_bootstrap,
    per_model_recall,
    prompt_bootstrap_ci,
)


def test_balanced_accuracy_weights_models_equally():
    y = ["a"] * 9 + ["b"]
    assert balanced_accuracy(y, ["a"] * 10) == pytest.approx(0.5)


def test_per_model_recall_sorted_worst_first():
    r = per_model_recall(["a", "a", "b"], ["a", "b", "b"])
    assert r.index[0] == "a" and r["a"] == 0.5 and r["b"] == 1.0


def test_lab_accuracy_forgives_sibling_errors():
    labs = {"x1": "x", "x2": "x", "y1": "y"}
    assert lab_accuracy(["x1", "y1"], ["x2", "y1"], labs) == 1.0
    with pytest.raises(ValueError):
        lab_accuracy(["x1"], ["zz"], labs)


def _noisy(n_prompts=40, per=6, seed=0):
    rng = np.random.default_rng(seed)
    groups = np.repeat(np.arange(n_prompts), per)
    y = np.tile(np.arange(per), n_prompts)
    # Prompt-level difficulty makes rows inside a prompt correlated.
    p = rng.uniform(0.1, 0.9, n_prompts)[groups]
    pred = np.where(rng.random(len(y)) < p, y, (y + 1) % per)
    return y, pred, groups


def test_prompt_bootstrap_contains_point_and_is_wider_than_row_bootstrap():
    y, pred, groups = _noisy()
    grouped = prompt_bootstrap_ci(y, pred, groups, n_boot=400)
    by_row = prompt_bootstrap_ci(y, pred, np.arange(len(y)), n_boot=400)
    assert grouped["lo"] < grouped["point"] < grouped["hi"]
    assert grouped["se"] > by_row["se"]


def test_paired_bootstrap_detects_a_clear_winner():
    y, pred, groups = _noisy()
    out = paired_prompt_bootstrap(y, y, pred, groups, n_boot=200)
    assert out["p_a_better"] == 1.0 and out["lo"] > 0


def test_leaderboard_noise_is_zero_for_perfect_predictions():
    y, _, groups = _noisy()
    assert leaderboard_noise(y, y, groups, n_sim=20)["gap_sd"] == 0
