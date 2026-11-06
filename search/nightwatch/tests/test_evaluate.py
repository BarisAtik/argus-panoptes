import pytest

from nightwatch.evaluate import (
    clustered_permutation,
    holm,
    mcnemar_one_sided,
    on_target,
    parent,
    wilson,
)


def test_parent_and_target():
    assert parent("T1059.001") == "T1059"
    assert on_target(["T1059.001"], ["T1059.003"])
    assert not on_target(["T1003"], ["T1059"])
    assert not on_target([], ["T1059"])


def test_wilson_known_value():
    low, high = wilson(5, 10)
    assert low == pytest.approx(0.2366, abs=1e-3) and high == pytest.approx(0.7634, abs=1e-3)
    assert wilson(0, 0) == (0.0, 0.0)


def test_mcnemar():
    assert mcnemar_one_sided(5, 0) == pytest.approx(1 / 32)
    assert mcnemar_one_sided(0, 0) == 1.0
    assert mcnemar_one_sided(0, 3) == 1.0


def test_holm():
    assert holm({"a": 0.01, "b": 0.04, "c": 0.03}) == pytest.approx(
        {"a": 0.03, "c": 0.06, "b": 0.06}
    )


def test_permutation_counts_clusters_not_rows():
    outcome = [1] * 100 + [0] * 3 + [0, 0, 0]
    group = [1] * 103 + [0] * 3
    cluster = ["big"] * 100 + ["x", "y", "z"] + ["p", "q", "r"]
    difference, p = clustered_permutation(outcome, group, cluster, rounds=2000)
    assert difference > 0.9
    assert p > 0.05  # one noisy rule is one piece of evidence


def test_permutation_rejects_mixed_cluster():
    with pytest.raises(ValueError):
        clustered_permutation([1, 0], [1, 0], ["a", "a"], rounds=10)
