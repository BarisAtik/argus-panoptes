import numpy as np
import pandas as pd
import pytest

from combinelink import synth
from combinelink.run import analyse
from combinelink.schema import check
from combinelink.stats import (
    benjamini_hochberg,
    correlation_ceiling,
    empirical_bayes,
    grouped_skill,
    icc1,
    selection_report,
)


def _repeated(between, within, players=400, k=4, seed=0):
    rng = np.random.default_rng(seed)
    t = rng.normal(0, between, players)
    return pd.DataFrame({"p": np.repeat(np.arange(players), k),
                         "v": np.repeat(t, k) + rng.normal(0, within, players * k)})


def test_icc_matches_known_variance_ratio():
    assert icc1(_repeated(1, 1), "p", "v")["icc"] == pytest.approx(0.5, abs=0.05)
    assert icc1(_repeated(0, 1), "p", "v")["icc"] < 0.05


def test_mean_of_attempts_is_more_reliable_than_one():
    out = icc1(_repeated(1, 1), "p", "v")
    assert out["reliability_of_mean"] > out["icc"]


def test_correlation_ceiling():
    assert correlation_ceiling(0.64, 1.0) == pytest.approx(0.8)
    assert correlation_ceiling(-1, 1) == 0


def test_empirical_bayes_shrinks_small_samples_harder():
    rng = np.random.default_rng(0)
    rows = [("big", v) for v in rng.normal(3, 1, 200)] + [("small", v) for v in [9.0, 9.0]]
    rows += [(f"p{i}", v) for i in range(40) for v in rng.normal(rng.normal(0, .5), 1, 30)]
    eb = empirical_bayes(pd.DataFrame(rows, columns=["p", "v"]), "p", "v")
    assert eb.loc["small", "weight"] < eb.loc["big", "weight"]
    assert eb.loc["small", "shrunk"] < eb.loc["small", "raw"]


def test_bh_matches_hand_computation():
    assert benjamini_hochberg([0.01, 0.04, 0.03, 0.5]).tolist() == pytest.approx(
        [0.04, 0.0533333, 0.0533333, 0.5], abs=1e-4)


def test_skill_is_zero_ish_without_signal():
    rng = np.random.default_rng(0)
    groups = np.repeat(np.arange(100), 20)
    x = np.repeat(rng.normal(size=(100, 1)), 20, axis=0)
    y = rng.normal(size=2000)
    assert abs(grouped_skill(x, y, np.full(2000, "WR"), groups)) < 0.02


def test_selection_report_shows_censoring():
    x = np.arange(100.0)
    df = pd.DataFrame({"m": x, "played": x > 50})
    r = selection_report(df, "m", "played")
    assert r.iloc[0] == 0 and r.iloc[-1] == 1


def test_recovers_planted_effect_and_stays_quiet_on_null():
    tracks, plays = synth.make(n_players=60, seed=1)
    result, _ = analyse(tracks, plays, n_perm=30)
    assert result["reliability"]["peak_speed"]["icc"] > 0.5
    assert result["linkage"]["peak_speed"]["p_value"] < 0.1
    assert result["linkage"]["peak_speed"]["observed_r2"] > 0

    tracks, plays = synth.make(n_players=60, effect=0.0, seed=2)
    result, _ = analyse(tracks, plays, n_perm=30)
    assert result["linkage"]["peak_speed"]["observed_r2"] < 0.02


def test_schema_check_names_the_problem(tmp_path):
    (tmp_path / "player_play.csv").write_text("nfl_id,other\n1,2\n")
    problems = check(tmp_path)
    assert any("combine_tracking.csv: not found" in p for p in problems)
    assert any("lined_up_position" in p for p in problems)
