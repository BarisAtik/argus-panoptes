import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from combinelink import synth
from combinelink.run import METRICS, analyse, analyse_by_drill
from combinelink.schema import check
from combinelink.stats import (
    benjamini_hochberg,
    composite,
    correlation_ceiling,
    empirical_bayes,
    grouped_skill,
    icc1,
    minimum_detectable_effect,
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


def test_composite_is_one_trait_with_a_stable_sign():
    rng = np.random.default_rng(0)
    t = rng.normal(size=300)
    df = pd.DataFrame({"a": t + rng.normal(0, .2, 300), "b": 2 * t + rng.normal(0, .4, 300),
                       "c": -t + rng.normal(0, .2, 300)})
    assert np.corrcoef(composite(df, ["a", "b", "c"]), t)[0, 1] > 0.95
    assert composite(df, ["a"]).corr(df["a"]) == pytest.approx(1)


def test_minimum_detectable_effect_finds_the_scale_of_noise():
    rng = np.random.default_rng(0)
    players = 200
    groups = np.repeat(np.arange(players), 20)
    pos = np.repeat(rng.choice(["WR", "TE"], players), 20)
    x = np.repeat(rng.normal(size=players), 20)
    y = rng.normal(0, 1.5, len(groups))
    out = minimum_detectable_effect(x, y, pos, groups, effects=(0.005, 1.0), n_sim=15, n_null=30)
    assert out["power_curve"][0.005] < 0.5
    assert out["power_curve"][1.0] == 1.0
    assert out["min_detectable_per_sd"] == 1.0


def _with_noise_drill():
    tracks, plays = synth.make(n_players=60, attempts=3, plays=30, effect=0.8)
    noise = tracks.copy()
    rng = np.random.default_rng(0)
    ids = noise["nfl_id"].unique()
    swap = dict(zip(ids, rng.permutation(ids)))
    keyed = noise["nfl_id"].astype(str) + "_" + noise["drill_attempt_id"].astype(str)
    shift = keyed.map({k: rng.normal(0, .9) for k in keyed.unique()})
    noise["x"] = noise["x"] * (1 + shift / 8.5)
    noise["y"] = noise["y"] * (1 + shift / 8.5)
    noise["nfl_id"] = noise["nfl_id"].map(swap)
    noise["drill_name"] = "pure_noise"
    return pd.concat([tracks, noise], ignore_index=True), plays


def test_by_drill_gates_on_reliability_before_touching_outcomes():
    tracks, plays = _with_noise_drill()
    out = analyse_by_drill(tracks, plays, n_perm=19, power=False)
    good, bad = out["drills"]["shuttle"], out["drills"]["pure_noise"]
    assert len(good["kept"]) > len(bad["kept"])
    assert "peak_speed" in good["kept"] and "peak_speed" not in bad["kept"]
    assert set(good["kept"]) <= set(METRICS)
    assert good["composite"]["p_value"] <= 0.1 and good["composite"]["observed_r2"] > 0
    assert "q_value" in good["composite"]


def test_by_drill_finds_no_link_when_none_exists():
    tracks, plays = synth.make(n_players=60, attempts=3, plays=30, effect=0.0)
    out = analyse_by_drill(tracks, plays, n_perm=19, power=False)
    assert out["drills"]["shuttle"]["composite"]["observed_r2"] < 0.02


def test_writeup_counter_skips_comments_code_and_tables():
    path = Path(__file__).parents[1] / "scripts" / "check_writeup.py"
    spec = importlib.util.spec_from_file_location("check_writeup", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    text = "one two\n<!-- hidden words -->\n```\ncode\n```\n| a |\n| --- |\n| b |\n![x](y.png)\nthree\n"
    assert module.measure(text) == (3, 2)
