"""One chart for the README: pixel leak by damage, against what a text audit would report."""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from pii_nl.evaluate import rate  # noqa: E402

from .degrade import CONDITIONS  # noqa: E402
from .run import load  # noqa: E402

SURFACE, INK, MUTED = "#fcfcfb", "#0b0b0b", "#52514e"
GRID = "#e4e3df"
SERIES = (
    ("tesseract_nld", "none", "pixel", "#2a78d6", "o", "Tesseract, pixels"),
    ("tesseract_nld", "none", "text", "#2a78d6", "D", "Tesseract, text audit"),
    ("tesseract_enh", "none", "pixel", "#eb6834", "o", "Enhanced + Tesseract, pixels"),
    ("tesseract_nld", "unread", "pixel", "#1baf7a", "s", "Tesseract, fail closed, pixels"),
)


def main(split: str, out: str) -> None:
    pixel, text = load(split), load(split, "text")
    conditions = list(CONDITIONS)[::-1]
    fig, ax = plt.subplots(figsize=(8.2, 5.2), dpi=160, facecolor=SURFACE)
    ax.set_facecolor(SURFACE)
    for engine, defence, metric, colour, marker, label in SERIES:
        rows = pixel if metric == "pixel" else text
        values = [
            rate(
                [r for r in rows if r["engine"] == engine and r["defence"] == defence
                 and r["condition"] == c],
                kind=None,
            )["rate"]
            for c in conditions
        ]
        solid = metric == "pixel"
        ax.scatter(
            [v * 100 for v in values], range(len(conditions)), s=46, marker=marker, zorder=3,
            label=label, linewidth=1.5, edgecolor=SURFACE if solid else colour,
            facecolor=colour if solid else SURFACE,
        )
    ax.set_yticks(range(len(conditions)), [c.replace("_", " ") for c in conditions])
    ax.set_xlim(-2, 72)
    ax.set_xlabel("Personal values with a word left visible (%)", color=MUTED)
    ax.grid(axis="x", color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED, length=0)
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(False)
    ax.set_title(
        "What the page shows, and what a text check would report", loc="left", color=INK,
        fontsize=12,
    )
    ax.legend(frameon=False, loc="upper center", bbox_to_anchor=(0.5, -0.12), ncol=2,
              labelcolor=MUTED, fontsize=9)
    fig.tight_layout()
    fig.savefig(Path(out), facecolor=SURFACE)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
