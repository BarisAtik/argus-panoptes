"""Fake tables only. The real tables haven't been analysed: see reports/public_proxy_plan.md."""
import numpy as np
import pandas as pd

from combinelink.public_proxy import (
    adjust_for_role,
    analyse,
    build_tables,
    fake_tables,
    signed_within_position,
)


def run(effect, seed=0):
    return analyse(*build_tables(*fake_tables(effect=effect, seed=seed)), n_perm=30, power=False)[0]


def test_finds_a_planted_speed_link_and_not_agility():
    result = run(0.2)
    assert result["primary"]["speed_power"]["observed_r2"] > 0.05
    assert result["primary"]["speed_power"]["q_value"] < 0.1
    assert result["primary"]["speed_power"]["yards_per_sd"] > 0.1
    assert result["primary"]["agility"]["observed_r2"] < 0.02


def test_no_effect_gives_no_skill():
    result = run(0.0)
    assert result["primary"]["speed_power"]["observed_r2"] < 0.02


def test_signs_mean_higher_is_better_and_positions_are_centred():
    frame = pd.DataFrame({"position": ["WR", "WR", "TE", "TE"], "forty": [4.3, 4.5, 4.6, 4.8],
                          "vertical": [40., 30, 35, 25], "broad_jump": [130., 120, 120, 110],
                          "cone": [6.8, 7.0, 7.1, 7.3], "shuttle": [4.1, 4.3, 4.3, 4.5]})
    out = signed_within_position(frame)
    assert out.loc[0, "forty"] > out.loc[1, "forty"]
    assert out.loc[0, "vertical"] > out.loc[1, "vertical"]
    assert abs(out.groupby("position")["forty"].mean()).max() < 1e-9


def test_unfinished_season_and_playoffs_stay_out():
    combine, ngs, ids = fake_tables(n=50)
    extra = ngs.head(5).assign(season=2026)
    post = ngs.head(5).assign(season_type="POST")
    weekly = ngs.head(5).assign(week=3)
    _, seasons = build_tables(combine, pd.concat([ngs, extra, post, weekly]), ids)
    _, clean = build_tables(combine, ngs, ids)
    assert len(seasons) == len(clean)
    assert seasons["season"].max() <= 2025


def test_role_adjustment_removes_depth_and_cushion():
    rng = np.random.default_rng(0)
    frame = pd.DataFrame({"avg_intended_air_yards": rng.normal(9, 2, 300),
                          "avg_cushion": rng.normal(6, 1, 300)})
    frame["avg_separation"] = 3 - 0.1 * frame["avg_intended_air_yards"] + 0.2 * frame["avg_cushion"]
    assert adjust_for_role(frame).abs().max() < 1e-9
