"""Column names in one place.

Only some names below were confirmed from public descriptions of the data (nfl_id, x/y-style
tracking, lined_up_position, separation_at_pass_forward). The rest are guesses. After downloading,
run `python -m combinelink.schema data/raw`, fix this file once, and everything else follows.
"""
from __future__ import annotations

import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Columns:
    player: str = "nfl_id"
    attempt: str = "drill_attempt_id"  # UNVERIFIED
    drill: str = "drill_name"  # UNVERIFIED
    frame: str = "frame_id"  # UNVERIFIED
    x: str = "x"  # UNVERIFIED
    y: str = "y"  # UNVERIFIED
    position: str = "lined_up_position"
    separation: str = "separation_at_pass_forward"
    game: str = "game_id"  # UNVERIFIED


COLUMNS = Columns()
EXPECTED = {
    "combine_tracking.csv": ("player", "attempt", "drill", "frame", "x", "y"),
    "player_play.csv": ("player", "position", "separation", "game"),
}


def check(data_dir: str | Path) -> list[str]:
    """Return problems found; an empty list means this file matches the download."""
    import pandas as pd

    problems = []
    names = asdict(COLUMNS)
    for file, fields in EXPECTED.items():
        path = Path(data_dir) / file
        if not path.exists():
            problems.append(f"{file}: not found")
            continue
        have = set(pd.read_csv(path, nrows=5).columns)
        problems += [f"{file}: no column {names[f]!r} (field {f}); has {sorted(have)}"
                     for f in fields if names[f] not in have]
    return problems


if __name__ == "__main__":
    found = check(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
    print("\n".join(found) or "schema OK")
    raise SystemExit(1 if found else 0)
