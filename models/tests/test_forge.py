import numpy as np
import pytest

from forge import calibration as cal
from forge import retrieval as ret
from forge.report import SMOKE_BANNER, markdown_table, run_metadata, write_report
from forge.simulate import simulate_speakers
from forge.stats import (
    holm,
    mcnemar_exact,
    mean_ci,
    paired_ratio_difference,
    ratio_ci,
    wilson_interval,
)


def test_ratio_ci_estimate_is_ratio_of_sums_not_mean_of_ratios():
    result = ratio_ci([1, 10], [10, 100], n_boot=200)
    assert result.estimate == pytest.approx(11 / 110)


def test_cluster_interval_is_wider_when_clusters_are_homogeneous():
    # Two kinds of speaker, many identical clips each: the effective n is the number of speakers.
    values = np.array([0.0] * 50 + [1.0] * 50)
    clusters = [0] * 50 + [1] * 50
    naive = mean_ci(values, seed=1)
    clustered = mean_ci(values, clusters, seed=1)
    assert clustered.high - clustered.low > 3 * (naive.high - naive.low)
    assert clustered.n_clusters == 2


def test_cluster_sums_matches_every_cluster_with_string_and_int_ids():
    assert ratio_ci([1, 2, 3], [1, 1, 1], ["a", "a", "b"], n_boot=50).n_clusters == 2
    assert ratio_ci([1, 2, 3], [1, 1, 1], [7, 7, 9], n_boot=50).n_clusters == 2


def test_cluster_bootstrap_covers_truth_where_clip_bootstrap_does_not():
    rng = np.random.default_rng(3)
    truth_runs = [simulate_speakers(30, 15, 0.15, 0.7, rng) for _ in range(120)]
    # The pooled estimate over many runs stands in for the true WER.
    truth = np.mean([e.sum() / d.sum() for _, e, _, d in truth_runs])
    clip_hits = speaker_hits = 0
    for i, (speakers, errors, _, words) in enumerate(truth_runs):
        naive = ratio_ci(errors, words, None, n_boot=300, seed=i)
        cluster = ratio_ci(errors, words, speakers, n_boot=300, seed=i)
        clip_hits += naive.low <= truth <= naive.high
        speaker_hits += cluster.low <= truth <= cluster.high
    assert clip_hits / 120 < 0.75
    assert speaker_hits / 120 > 0.82


def test_paired_difference_detects_a_real_gap_and_not_a_null_one():
    rng = np.random.default_rng(0)
    speakers = np.repeat(np.arange(60), 5)
    words = np.full(300, 10.0)
    base = rng.binomial(10, 0.2, 300).astype(float)
    worse = base + rng.binomial(1, 0.5, 300)
    gap = paired_ratio_difference(worse, base, words, speakers)
    assert gap.low > 0 and gap.p_value < 0.01
    jitter = rng.choice([-1.0, 0.0, 1.0], 300)
    null = paired_ratio_difference(base + jitter, base, words, speakers)
    assert null.low < 0 < null.high + 1e-3 or null.p_value > 0.01


def test_mcnemar_and_holm_and_wilson():
    assert mcnemar_exact([1, 1, 0], [1, 1, 0])["p_value"] == 1.0
    assert mcnemar_exact([1] * 20 + [0], [0] * 20 + [1])["p_value"] < 0.001
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    low, high = wilson_interval(0, 50)
    assert low == pytest.approx(0) and 0.05 < high < 0.1


def test_temperature_recovers_overconfidence():
    rng = np.random.default_rng(0)
    true_logits = rng.normal(0, 2, (20000, 3))
    labels = (true_logits + rng.gumbel(size=true_logits.shape)).argmax(axis=1)
    overconfident = true_logits * 3
    assert cal.fit_temperature(overconfident, labels) == pytest.approx(3.0, rel=0.05)
    before = cal.ece(cal.probabilities(overconfident), labels)
    after = cal.ece(cal.probabilities(overconfident, 3.0), labels)
    assert after < before / 3 and after < 0.02


def test_brier_and_reliability():
    probs = np.array([[1.0, 0.0], [0.0, 1.0]])
    assert cal.brier(probs, np.array([0, 1])) == 0
    table = cal.reliability_table(probs, np.array([0, 1]), n_bins=2, adaptive=False)
    assert sum(row["n"] for row in table) == 2


def test_risk_coverage_orders_oracle_below_random():
    loss = np.array([0, 0, 0, 1, 1.0])
    good = cal.risk_coverage(np.array([5, 4, 3, 2, 1.0]), loss)
    bad = cal.risk_coverage(np.array([1, 2, 3, 4, 5.0]), loss)
    assert good["aurc"] == pytest.approx(good["oracle_aurc"])
    assert good["aurc"] < good["random_aurc"] < bad["aurc"]
    assert cal.risk_at(good, (0.6,))["0.60"] == 0


def test_retrieval_metrics_by_hand():
    scores = np.array([[0.9, 0.8, 0.7, 0.1]])
    relevant = np.array([[True, False, True, False]])
    assert ret.average_precision(scores, relevant)[0] == pytest.approx((1 + 2 / 3) / 2)
    assert ret.precision_at_k(scores, relevant, 2)[0] == 0.5
    assert ret.recall_at_k(scores, relevant, 1)[0] == 0.5
    assert ret.reciprocal_rank(scores, ~relevant)[0] == 0.5
    assert ret.average_precision(scores, np.zeros_like(relevant))[0] == 0


def test_smoke_reports_are_stamped(tmp_path):
    meta = run_metadata("smoke")
    _, md = write_report(tmp_path, {"meta": meta}, "# hi\n")
    assert md.read_text().startswith(SMOKE_BANNER)
    with pytest.raises(ValueError):
        run_metadata("probably-fine")


def test_markdown_table_escapes_and_formats():
    table = markdown_table([{"a": 0.5, "b": "x|y", "c": None}])
    assert "0.5000" in table and "x\\|y" in table and "–" in table


def test_cluster_t_interval_is_wider_than_bootstrap_on_few_speakers():
    from forge.stats import ratio_ci, ratio_ci_t

    rng = np.random.default_rng(0)
    speakers, errors, _, words = simulate_speakers(6, 5, 0.15, 0.7, rng)
    t_interval = ratio_ci_t(errors, words, speakers)
    boot = ratio_ci(errors, words, speakers)
    assert t_interval.estimate == pytest.approx(boot.estimate)
    assert t_interval.high - t_interval.low > boot.high - boot.low


def test_cluster_t_needs_two_clusters():
    from forge.stats import ratio_ci_t

    with pytest.raises(ValueError):
        ratio_ci_t([1.0, 2.0], [5.0, 5.0], ["a", "a"])
