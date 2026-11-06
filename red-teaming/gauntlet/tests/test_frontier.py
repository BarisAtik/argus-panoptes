import numpy as np

from gauntlet.frontier import pareto, pick, shapley, spec, spearman


def test_spec_names():
    assert spec(0) == "none" and spec(1) == "allowlist" and spec(3) == "allowlist+egress"


def test_shapley_sums_to_grand_coalition_and_splits_redundancy():
    # Two defenses that fully overlap, one that does nothing: a leave-one-out view gives zeros.
    v = np.array([1.0, 0, 0, 0, 1, 0, 0, 0])
    phi = shapley(v, 3)
    assert abs(phi.sum() - (v[-1] - v[0])) < 1e-12
    assert np.allclose(phi, [-0.5, -0.5, 0])


def test_pareto_keeps_tradeoffs_and_the_smallest_stack():
    asr = np.array([1.0, 0.5, 0.5, 0.0, 0.5])
    util = np.array([1.0, 0.8, 0.9, 0.2, 0.9])
    assert pareto(asr, util) == [3, 2, 0]


def test_pick_respects_floor_then_size():
    asr = np.array([1.0, 0.2, 0.2, 0.0])
    util = np.array([1.0, 0.9, 0.95, 0.5])
    assert pick(asr, util, 0.9) == 1


def test_spearman_is_one_on_monotone():
    assert spearman(np.arange(5.0), np.arange(5.0) ** 2) > 0.99
