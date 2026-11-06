"""The planned chain on public season tables: see reports/public_proxy_plan.md before running.

Not run in this lab yet. nflverse gives no licence for the data, which belongs to its owners, so
read their terms first. Nothing downloaded here belongs in git.

    ./scripts/download_public.sh                   # your own decision, see the plan
    python -m combinelink.public_proxy --data data/public --out artifacts/public

`--synth` runs on fake tables in the same format, for checking the code only.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .stats import (
    benjamini_hochberg,
    composite,
    correlation_ceiling,
    grouped_skill,
    icc1,
    minimum_detectable_effect,
    permutation_test,
    selection_report,
)

SPEED_POWER = {"forty": -1, "vertical": 1, "broad_jump": 1}
AGILITY = {"cone": -1, "shuttle": -1}
TESTS = {**SPEED_POWER, **AGILITY}
COMPOSITES = {"speed_power": list(SPEED_POWER), "agility": list(AGILITY)}
POSITIONS = ("WR", "TE")
LAST_SEASON = 2025  # 2026 was unfinished when this was written
EFFECTS = (0.02, 0.05, 0.1, 0.15, 0.2, 0.3)


def signed_within_position(players: pd.DataFrame) -> pd.DataFrame:
    """z-score each test inside its position, higher is better. Pooling positions would turn the
    gap between a tight end and a receiver into a fake trait."""
    out = players.copy()
    for test, sign in TESTS.items():
        by_pos = out.groupby("position")[test]
        out[test] = sign * (out[test] - by_pos.transform("mean")) / by_pos.transform("std")
    return out


def build_tables(combine: pd.DataFrame, ngs: pd.DataFrame,
                 ids: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Players with tests, and player-seasons with outcomes, keyed on gsis_id."""
    link = ids.dropna(subset=["gsis_id", "pfr_id"]).drop_duplicates("pfr_id")[["gsis_id", "pfr_id"]]
    players = combine[combine["pos"].isin(POSITIONS)].dropna(subset=["pfr_id"])
    players = players.drop_duplicates("pfr_id").merge(link, on="pfr_id").rename(
        columns={"pos": "position", "season": "combine_season"})
    players = signed_within_position(players)
    keep = ngs[(ngs["season_type"] == "REG") & (ngs["week"] == 0) & (ngs["season"] <= LAST_SEASON)]
    seasons = keep.rename(columns={"player_gsis_id": "gsis_id"})[
        ["gsis_id", "season", "avg_separation", "avg_cushion", "avg_intended_air_yards", "targets"]]
    return players, seasons.merge(players[["gsis_id", "position"]], on="gsis_id")


def adjust_for_role(seasons: pd.DataFrame) -> pd.Series:
    """Residual separation after depth and cushion. May remove part of the effect: see the plan."""
    x = seasons[["avg_intended_air_yards", "avg_cushion"]].to_numpy()
    x = np.column_stack([np.ones(len(x)), x])
    y = seasons["avg_separation"].to_numpy()
    return pd.Series(y - x @ np.linalg.lstsq(x, y, rcond=None)[0], index=seasons.index)


def slope_per_sd(x, y, groups, n_boot: int = 500, seed: int = 0) -> dict[str, float]:
    """Yards per SD, with whole players resampled, since seasons from one player aren't independent."""
    frame = pd.DataFrame({"x": np.ravel(x), "y": y, "g": groups})
    frame["x"] = (frame["x"] - frame["x"].mean()) / frame["x"].std(ddof=1)
    rows = [g.index.to_numpy() for _, g in frame.groupby("g")]
    rng = np.random.default_rng(seed)
    point = float(np.polyfit(frame["x"], frame["y"], 1)[0])
    boots = []
    for _ in range(n_boot):
        pick = np.concatenate([rows[i] for i in rng.integers(0, len(rows), len(rows))])
        boots.append(np.polyfit(frame["x"].to_numpy()[pick], frame["y"].to_numpy()[pick], 1)[0])
    return {"yards_per_sd": point, "lo": float(np.quantile(boots, .025)),
            "hi": float(np.quantile(boots, .975))}


def _test(merged: pd.DataFrame, column: str, outcome: str, n_perm: int) -> dict:
    data = merged.dropna(subset=[column, outcome]).reset_index(drop=True)
    x, y = data[[column]].to_numpy(), data[outcome].to_numpy()
    pos, groups = data["position"].to_numpy(), data["gsis_id"].to_numpy()
    return {**permutation_test(x, y, pos, groups, n_perm=n_perm),
            **slope_per_sd(x, y, groups), "rows": len(data), "players": data["gsis_id"].nunique()}


def time_split(merged: pd.DataFrame, column: str, cut: int = 2019) -> dict:
    """Fit on older combines, score on newer ones, skill above a position baseline."""
    data = merged.dropna(subset=[column])
    old, new = data[data["combine_season"] <= cut], data[data["combine_season"] > cut]
    if old.empty or new.empty:
        return {"r2": None, "old_rows": len(old), "new_rows": len(new)}
    base = old.groupby("position")["avg_separation"].mean()
    y_new = new["avg_separation"] - new["position"].map(base)
    y_old = old["avg_separation"] - old["position"].map(base)
    slope, icpt = np.polyfit(old[column], y_old, 1)
    resid = y_new - (slope * new[column] + icpt)
    return {"r2": float(1 - (resid ** 2).sum() / (y_new ** 2).sum()), "old_rows": len(old),
            "new_rows": len(new)}


def beyond_draft(merged: pd.DataFrame, column: str) -> dict:
    """Out-of-player R2 with draft slot alone, and with the composite added. Undrafted get 260."""
    data = merged.dropna(subset=[column]).reset_index(drop=True)
    slot = np.log(data["draft_ovr"].fillna(260).to_numpy(float))[:, None]
    both = np.column_stack([slot, data[column].to_numpy()])
    y, pos, groups = (data[c].to_numpy() for c in ("avg_separation", "position", "gsis_id"))
    return {"draft_only": grouped_skill(slot, y, pos, groups),
            "draft_plus_composite": grouped_skill(both, y, pos, groups)}


def analyse(players: pd.DataFrame, seasons: pd.DataFrame, n_perm: int = 1000,
            power: bool = True) -> tuple[dict, pd.DataFrame]:
    players = players.copy()
    for name, tests in COMPOSITES.items():
        complete = players.dropna(subset=tests)
        players[name] = composite(complete, tests).reindex(players.index)
    merged = seasons.merge(players.drop(columns="position"), on="gsis_id").reset_index(drop=True)
    merged["separation_adjusted"] = adjust_for_role(merged)

    primary = {c: _test(merged, c, "avg_separation", n_perm) for c in COMPOSITES}
    for c, q in zip(COMPOSITES, benjamini_hochberg([primary[c]["p_value"] for c in COMPOSITES])):
        primary[c]["q_value"] = float(q)
    single = {t: _test(merged, t, "avg_separation", min(n_perm, 500)) for t in TESTS}
    for t, q in zip(TESTS, benjamini_hochberg([single[t]["p_value"] for t in TESTS])):
        single[t]["q_value"] = float(q)

    repeat = icc1(merged, "gsis_id", "avg_separation")
    result = {
        "primary": primary, "single_tests_followup": single,
        "adjusted_outcome_followup": {c: _test(merged, c, "separation_adjusted", min(n_perm, 500))
                                      for c in COMPOSITES},
        "outcome_repeatability": repeat,
        "ceiling_if_tests_were_perfect": correlation_ceiling(1.0, repeat["reliability_of_mean"]),
        "time_split": {c: time_split(merged, c) for c in COMPOSITES},
        "beyond_draft": {c: beyond_draft(merged, c) for c in COMPOSITES},
        "missing_share": players[list(TESTS)].isna().mean().to_dict(),
    }
    if "draft_ovr" in players:
        missing = players[list(TESTS)].isna().any(axis=1)
        result["missing_by_draft"] = {"any_test_missing_mean_slot": float(
            players.loc[missing, "draft_ovr"].mean()), "all_tests_mean_slot": float(
            players.loc[~missing, "draft_ovr"].mean())}
    seen = players.assign(reached_table=players["gsis_id"].isin(seasons["gsis_id"]).astype(float))
    recent = seen[seen["combine_season"] >= 2016]
    result["selection"] = {c: selection_report(recent, c, "reached_table").to_dict() for c in COMPOSITES}
    if power:
        result["power"] = {}
        for c in COMPOSITES:
            data = merged.dropna(subset=[c]).reset_index(drop=True)
            result["power"][c] = minimum_detectable_effect(
                data[c].to_numpy(), data["avg_separation"].to_numpy(), data["position"].to_numpy(),
                data["gsis_id"].to_numpy(), effects=EFFECTS)
    return result, merged


def fake_tables(n: int = 400, effect: float = 0.15, seed: int = 0):
    """Tables shaped like the public ones, with `effect` yards per SD of a hidden speed trait."""
    rng = np.random.default_rng(seed)
    pos = rng.choice(POSITIONS, n, p=[0.7, 0.3])
    speed, agile = rng.normal(size=n), rng.normal(size=n)
    gap = (pos == "TE").astype(float)

    def noise(sd: float) -> np.ndarray:
        return rng.normal(0, sd, n)

    combine = pd.DataFrame({
        "season": rng.integers(2014, 2025, n), "draft_ovr": rng.integers(1, 260, n).astype(float),
        "pfr_id": [f"P{i}" for i in range(n)], "pos": pos,
        "forty": 4.5 + 0.2 * gap - 0.08 * speed + noise(0.03),
        "vertical": 36 - 3 * gap + 2 * speed + noise(1.5),
        "broad_jump": 122 - 5 * gap + 4 * speed + noise(3),
        "cone": 7.0 + 0.2 * gap - 0.15 * agile + noise(0.08),
        "shuttle": 4.3 + 0.1 * gap - 0.1 * agile + noise(0.06),
    })
    for test in ("cone", "shuttle"):
        combine.loc[rng.random(n) < 0.35, test] = np.nan
    ids = pd.DataFrame({"pfr_id": combine["pfr_id"], "gsis_id": [f"G{i}" for i in range(n)]})
    trait = rng.normal(0, 0.25, n) + effect * speed + 0.1 * gap
    rows = []
    for i in rng.choice(n, int(n * 0.8), replace=False):
        for season in rng.integers(2016, 2026, rng.integers(1, 6)):
            air, cushion = rng.normal(9, 2), rng.normal(6, 1)
            rows.append(("REG", 0, season, f"G{i}", 2.5 + trait[i] + 0.05 * (cushion - 6)
                         - 0.04 * (air - 9) + rng.normal(0, 0.2), cushion, air, rng.integers(23, 150)))
    ngs = pd.DataFrame(rows, columns=["season_type", "week", "season", "player_gsis_id",
                                      "avg_separation", "avg_cushion", "avg_intended_air_yards",
                                      "targets"]).drop_duplicates(["player_gsis_id", "season"])
    return combine, ngs, ids


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=Path("data/public"))
    ap.add_argument("--out", type=Path, default=Path("artifacts/public"))
    ap.add_argument("--perm", type=int, default=1000)
    ap.add_argument("--synth", action="store_true", help="fake tables, code check only")
    args = ap.parse_args()
    if args.synth:
        combine, ngs, ids = fake_tables()
    else:
        combine = pd.read_csv(args.data / "combine.csv")
        ngs = pd.read_csv(args.data / "ngs_receiving.csv.gz")
        ids = pd.read_csv(args.data / "players.csv", usecols=["gsis_id", "pfr_id"])
    players, seasons = build_tables(combine, ngs, ids)
    result, merged = analyse(players, seasons, args.perm)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "public_proxy.json").write_text(json.dumps(result, indent=2, default=float))
    merged.drop(columns=["player_name", "school"], errors="ignore").to_csv(
        args.out / "player_seasons.csv", index=False)
    print(json.dumps(result["primary"], indent=2, default=float))


if __name__ == "__main__":
    main()
