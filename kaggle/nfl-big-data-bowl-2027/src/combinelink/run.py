"""Combine tracking -> attempt features -> reliability -> does it transfer to game separation?

    python -m combinelink.run --data data/synth --out artifacts/synth
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .schema import COLUMNS as C
from .stats import (
    benjamini_hochberg,
    composite,
    grouped_skill,
    icc1,
    minimum_detectable_effect,
    permutation_test,
)
from .tracking import features_from_tracking

METRICS = ("peak_speed", "time_to_90pct_peak", "peak_accel", "peak_decel", "peak_lateral",
           "speed_kept_after_peak")


def analyse(tracks: pd.DataFrame, plays: pd.DataFrame, n_perm: int = 100) -> tuple[dict, pd.DataFrame]:
    attempts = features_from_tracking(tracks)
    reliability = {m: icc1(attempts, C.player, m) for m in METRICS}
    players = attempts.groupby(C.player)[list(METRICS)].mean().reset_index()
    observed = plays.dropna(subset=[C.separation]).merge(players, on=C.player)
    y = observed[C.separation].to_numpy()
    pos = observed[C.position].to_numpy()
    groups = observed[C.player].to_numpy()
    links = {}
    for m in METRICS:
        x = observed[[m]].to_numpy()
        links[m] = permutation_test(x, y, pos, groups, n_perm=n_perm)
    adjusted = benjamini_hochberg([links[m]["p_value"] for m in METRICS])
    for m, q in zip(METRICS, adjusted):
        links[m]["q_value"] = float(q)
    joint = grouped_skill(observed[list(METRICS)].to_numpy(), y, pos, groups)
    players_with_outcome = plays.groupby(C.player)[C.separation].count()
    players = players.assign(n_plays=players[C.player].map(players_with_outcome).fillna(0).astype(int))
    return {"reliability": reliability, "linkage": links, "joint_oof_r2": joint}, players


def analyse_by_drill(tracks: pd.DataFrame, plays: pd.DataFrame, n_perm: int = 100,
                     min_reliability: float = 0.7, power: bool = True) -> dict:
    """The planned analysis: each drill alone, in the order reliability, transfer, correction.

    Drills measure different things, so pooling them makes a drill difference look like a player
    difference. Metrics below `min_reliability` are dropped before any outcome is touched, which
    also keeps them out of the multiple-testing count. Each drill's surviving metrics are combined
    into one composite. Composites are the primary tests; single metrics are follow-ups.
    """
    observed = plays.dropna(subset=[C.separation])
    primary, drills = [], {}
    for drill, part in tracks.groupby(C.drill):
        attempts = features_from_tracking(part)
        reliability = {m: icc1(attempts, C.player, m) for m in METRICS}
        kept = [m for m in METRICS if reliability[m]["reliability_of_mean"] >= min_reliability]
        entry = {"reliability": reliability, "kept": kept}
        drills[drill] = entry
        if not kept:
            continue
        players = attempts.groupby(C.player)[list(METRICS)].mean().reset_index()
        players["composite"] = composite(players, kept)
        merged = observed.merge(players, on=C.player)
        y, pos, groups = (merged[c].to_numpy() for c in (C.separation, C.position, C.player))
        test = permutation_test(merged[["composite"]].to_numpy(), y, pos, groups, n_perm=n_perm)
        entry["composite"] = test
        primary.append(drill)
        if power:
            entry["power"] = minimum_detectable_effect(merged["composite"].to_numpy(), y, pos,
                                                       groups)
    adjusted = benjamini_hochberg([drills[d]["composite"]["p_value"] for d in primary])
    for drill, q in zip(primary, adjusted):
        drills[drill]["composite"]["q_value"] = float(q)
    return {"min_reliability": min_reliability, "primary_tests": primary, "drills": drills}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data/raw")
    ap.add_argument("--out", default="artifacts/real")
    ap.add_argument("--perm", type=int, default=100)
    ap.add_argument("--by-drill", action="store_true", help="the planned per-drill analysis")
    args = ap.parse_args()
    d = Path(args.data)
    tracks = pd.read_csv(d / "combine_tracking.csv")
    plays = pd.read_csv(d / "player_play.csv")
    result, players = analyse(tracks, plays, args.perm)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=2))
    if args.by_drill:
        by_drill = analyse_by_drill(tracks, plays, args.perm)
        (out / "by_drill.json").write_text(json.dumps(by_drill, indent=2))
        print(json.dumps(by_drill, indent=2))
    players.to_csv(out / "player_features.csv", index=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
