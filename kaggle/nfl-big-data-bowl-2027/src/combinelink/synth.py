"""Fake Combine and game data with a planted effect, so the statistics can be checked for recovery.

    python -m combinelink.synth --out data/synth            # planted effect
    python -m combinelink.synth --out data/synth0 --effect 0  # null
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .schema import COLUMNS as C


def drill_path(rng: np.random.Generator, top: float, frames: int = 50, noise: float = 0.02):
    """Sprint to `top`, then cut 90 degrees."""
    speed = np.minimum(top, np.arange(frames) * 0.1 * 6.0)
    heading = np.where(np.arange(frames) < 30, 0.0, np.pi / 2)
    x = np.cumsum(speed * np.cos(heading) * 0.1) + rng.normal(0, noise, frames)
    y = np.cumsum(speed * np.sin(heading) * 0.1) + rng.normal(0, noise, frames)
    return x, y


def make(n_players: int = 120, attempts: int = 3, plays: int = 40, effect: float = 0.5,
         trait_sd: float = 0.5, attempt_sd: float = 0.25, seed: int = 0):
    """Returns (tracks, plays). `effect` is yards of separation per trait SD."""
    rng = np.random.default_rng(seed)
    trait = rng.normal(0, 1, n_players)
    pos = rng.choice(["WR", "TE"], n_players, p=[0.75, 0.25])
    track_rows, play_rows = [], []
    for i in range(n_players):
        pid = 1000 + i
        for a in range(attempts):
            top = 8.5 + trait_sd * trait[i] + rng.normal(0, attempt_sd)
            x, y = drill_path(rng, top)
            track_rows.append(pd.DataFrame({C.player: pid, C.drill: "shuttle", C.attempt: a,
                                            C.frame: np.arange(len(x)), C.x: x, C.y: y}))
        n = rng.poisson(plays) + 1
        sep = (2.8 if pos[i] == "WR" else 2.2) + effect * trait[i] + rng.normal(0, 1.5, n)
        play_rows.append(pd.DataFrame({C.player: pid, C.position: pos[i], C.separation: sep,
                                       C.game: rng.integers(0, 60, n)}))
    return pd.concat(track_rows, ignore_index=True), pd.concat(play_rows, ignore_index=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="data/synth")
    ap.add_argument("--effect", type=float, default=0.5)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tracks, plays = make(effect=args.effect)
    tracks.to_csv(out / "combine_tracking.csv", index=False)
    plays.to_csv(out / "player_play.csv", index=False)
    print(f"wrote {len(tracks)} frames and {len(plays)} plays to {out}")


if __name__ == "__main__":
    main()
