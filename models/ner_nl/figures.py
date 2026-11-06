"""Draw the two README figures from a report. `python -m ner_nl.figures results/ner_nl`"""

from __future__ import annotations

import json
import sys
from pathlib import Path

INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"
BLUE, ORANGE = "#2a78d6", "#eb6834"


def _style(fig, ax) -> None:
    fig.patch.set_facecolor(SURFACE)
    ax.set_facecolor(SURFACE)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(length=0, colors=MUTED)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def transcript_figure(report: dict, path: Path) -> None:
    import matplotlib.pyplot as plt

    best, aug = report["meta"]["best_seed"], report["meta"]["best_seed_aug"]
    f1 = {(r["model"], r["condition"]): r["f1"] for r in report["evaluate_rows"]}
    names = [
        ("deduce", "DEDUCE (rules)"),
        ("gazetteer", "Lookup baseline"),
        ("nl_core_news_lg", "spaCy lg"),
        (best, "Own BiLSTM-CRF"),
        (aug, "Own, augmented"),
    ]
    fig, ax = plt.subplots(figsize=(7.2, 3.6), dpi=200)
    height = 0.34
    series = (("clean", "Clean text", BLUE), ("transcript", "Transcript style", ORANGE))
    for i, (key, _) in enumerate(names[::-1]):
        for j, (condition, label, color) in enumerate(series):
            y = i + (height / 2 + 0.02) * (1 if j == 0 else -1)
            value = f1[(key, condition)]
            ax.barh(y, value, height, color=color, label=label if i == 0 else None)
            ax.text(value + 0.012, y, f"{value:.2f}", va="center", fontsize=8, color=INK)
    ax.set_yticks(range(len(names)), [label for _, label in names[::-1]], color=INK)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Entity F1 on PER, LOC, ORG (test split)", color=MUTED, fontsize=9)
    ax.set_title(
        "Lowercase, unpunctuated text breaks every tagger not trained on it",
        loc="left", fontsize=10.5, color=INK,
    )
    ax.legend(frameon=False, loc="upper right", fontsize=8.5)
    _style(fig, ax)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)


def masking_figure(report: dict, path: Path) -> None:
    import matplotlib.pyplot as plt

    labels = {
        "dutch": "Dutch",
        "polish": "Polish",
        "moroccan": "Moroccan",
        "turkish": "Turkish",
        "hindustani": "Surinamese-Hindustani",
    }
    rows = {
        r["group"]: r["fully_masked"]
        for r in report["names_why"]
        if r["model"] == "nl_core_news_lg"
    }
    order = sorted(labels, key=lambda g: rows[g])
    fig, ax = plt.subplots(figsize=(7.2, 2.5), dpi=200)
    ax.barh(range(len(order)), [rows[g] for g in order], 0.56, color=BLUE)
    for i, group in enumerate(order):
        ax.text(rows[group] + 0.012, i, f"{rows[group]:.0%}", va="center", fontsize=8.5, color=INK)
    ax.set_yticks(range(len(order)), [labels[g] for g in order], color=INK)
    ax.set_xlim(0, 1)
    ax.set_xlabel("Swapped-in person names fully masked by spaCy lg", color=MUTED, fontsize=9)
    ax.set_title(
        "A redactor built on spaCy lg hides some names less often than others",
        loc="left", fontsize=10.5, color=INK,
    )
    _style(fig, ax)
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)


def main() -> None:
    folder = Path(sys.argv[1])
    report = json.loads((folder / "report.json").read_text())
    transcript_figure(report, folder / "transcript_f1.png")
    masking_figure(report, folder / "name_masking.png")


if __name__ == "__main__":
    main()
