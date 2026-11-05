import numpy as np
from sklearn.metrics import adjusted_rand_score

from ntl.assign import (
    _cap_clusters,
    assign_within_clusters,
    cluster_passages,
    stress_curve,
    tune_threshold,
)


def test_assignment_never_repeats_a_class_in_a_cluster():
    rng = np.random.default_rng(0)
    p = rng.dirichlet(np.ones(6), size=6)
    pred = assign_within_clusters(p, np.zeros(6, dtype=int))
    assert sorted(pred) == list(range(6))


def test_assignment_resolves_a_conflict_by_total_probability():
    p = np.array([[0.9, 0.1], [0.6, 0.4]])
    assert assign_within_clusters(p, np.array([0, 0])).tolist() == [0, 1]


def test_assignment_leaves_singletons_and_oversize_alone():
    p = np.array([[0.1, 0.9], [0.2, 0.8], [0.3, 0.7]])
    assert assign_within_clusters(p, np.array([0, 1, 2])).tolist() == [1, 1, 1]
    assert assign_within_clusters(p, np.zeros(3, dtype=int)).tolist() == [1, 1, 1]


def test_clusters_recover_prompts_on_fake_data(small):
    _, test, truth = small
    clusters = cluster_passages(test["text"].tolist(), max_size=18)
    assert adjusted_rand_score(truth["prompt_id"], clusters) > 0.9
    assert np.bincount(clusters).max() <= 18


def test_cap_splits_large_clusters_without_losing_rows():
    x = np.random.default_rng(0).random((50, 50))
    out = _cap_clusters(np.zeros(50, dtype=int), (x + x.T) / 2, 18)
    assert np.bincount(out).max() <= 18 and np.bincount(out).sum() == 50


def test_single_passage_does_not_crash():
    assert cluster_passages(["only one"]).tolist() == [0]


def test_threshold_tuning_reports_each_value(small):
    _, test, truth = small
    curve = tune_threshold(test["text"].tolist(), truth["prompt_id"].to_numpy(), grid=(0.5, 0.9))
    assert set(curve) == {0.5, 0.9} and all(-1 <= v <= 1 for v in curve.values())


def _grid_proba(n_prompts=60, k=8, seed=0):
    rng = np.random.default_rng(seed)
    y = np.tile(np.arange(k), n_prompts)
    prompts = np.repeat(np.arange(n_prompts), k)
    logits = rng.normal(0, 1, (len(y), k))
    logits[np.arange(len(y)), y] += 1.2
    p = np.exp(logits)
    return p / p.sum(1, keepdims=True), y, prompts


def test_stress_curve_gain_shrinks_with_noise():
    rows = stress_curve(*_grid_proba(), noise=(0.0, 0.5), keep=(1.0,))
    clean, noisy = rows
    assert clean["assigned"] > clean["argmax"] + 0.05
    assert noisy["assigned"] - noisy["argmax"] < clean["assigned"] - clean["argmax"]
