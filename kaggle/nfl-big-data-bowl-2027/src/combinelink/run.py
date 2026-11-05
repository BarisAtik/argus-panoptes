"""Combine tracking -> attempt features -> reliability -> does it transfer to game separation?

    python -m combinelink.run --data data/synth --out artifacts/synth
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .schema import COLUMNS as C
from .stats import benjamini_hochberg, grouped_skill, icc1, permutation_test
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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--data", default="data/raw")
    ap.add_argument("--out", default="artifacts/real")
    ap.add_argument("--perm", type=int, default=100)
    args = ap.parse_args()
    d = Path(args.data)
    result, players = analyse(pd.read_csv(d / "combine_tracking.csv"),
                              pd.read_csv(d / "player_play.csv"), args.perm)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=2))
    players.to_csv(out / "player_features.csv", index=False)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
