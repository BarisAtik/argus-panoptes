"""Turn an OOF file into a failure report: who is confused with whom, on which passages, and why.

    python -m ntl.failure --oof artifacts/synth/oof_blend.parquet --data data/synth \
        --out reports/generated/failure.md
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .data import ID, LABEL, PROMPT, TEXT, load
from .labs import LAB_OF
from .metrics import balanced_accuracy, lab_accuracy, per_model_recall

META = {ID, "fold", LABEL, PROMPT}


def predictions(oof: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    classes = np.array([c for c in oof.columns if c not in META])
    p = oof[classes].to_numpy()
    return classes, classes[p.argmax(axis=1)], p.max(axis=1)


def top_confusions(y, pred, k: int = 10) -> pd.DataFrame:
    frame = pd.DataFrame({"true": y, "pred": pred})
    wrong = frame[frame.true != frame.pred]
    pairs = wrong.value_counts().rename("n").reset_index()
    support = frame.true.value_counts()
    pairs["share_of_true"] = (pairs.n / pairs.true.map(support)).round(3)
    return pairs.head(k)


def by_length(y, pred, words, edges=(0, 80, 120, 160, 200, 1000)) -> pd.DataFrame:
    frame = pd.DataFrame({"hit": np.asarray(y) == np.asarray(pred),
                          "bin": pd.cut(words, edges, right=False)})
    return frame.groupby("bin", observed=True)["hit"].agg(["mean", "size"]).round(3)


def calibration(y, pred, conf, bins: int = 10) -> pd.DataFrame:
    frame = pd.DataFrame({"hit": np.asarray(y) == np.asarray(pred), "conf": conf})
    frame["bin"] = pd.cut(frame.conf, np.linspace(0, 1, bins + 1), include_lowest=True)
    table = frame.groupby("bin", observed=True).agg(conf=("conf", "mean"), acc=("hit", "mean"),
                                                    n=("hit", "size"))
    return table.round(3)


def hardest_prompts(y, pred, prompts, k: int = 10) -> pd.DataFrame:
    frame = pd.DataFrame({"prompt": prompts, "hit": np.asarray(y) == np.asarray(pred)})
    return frame.groupby("prompt")["hit"].mean().sort_values().head(k).round(3).reset_index()


def report(oof: pd.DataFrame, train: pd.DataFrame) -> str:
    train = train.set_index(ID).loc[oof[ID]].reset_index()
    y = oof[LABEL].to_numpy()
    _, pred, conf = predictions(oof)
    words = train[TEXT].str.split().str.len().to_numpy()
    lab_line = ""
    if set(y) <= set(LAB_OF) and set(pred) <= set(LAB_OF):
        lab_line = (f" Right lab: **{lab_accuracy(y, pred, LAB_OF):.4f}**. The gap between the two "
                    "is confusion among siblings.")
    parts = [
        f"# Failure analysis\n\nBalanced accuracy: **{balanced_accuracy(y, pred):.4f}** "
        f"on {len(y)} out-of-fold rows.{lab_line}",
        "## Per-model recall (worst first)\n\n" + per_model_recall(y, pred).round(3)
        .rename("recall").to_markdown(),
        "## Top confusions\n\n" + top_confusions(y, pred).to_markdown(index=False),
        "## Accuracy by passage length (words)\n\n" + by_length(y, pred, words).to_markdown(),
        "## Calibration of the top prediction\n\n" + calibration(y, pred, conf).to_markdown(),
        "## Hardest prompts\n\n" + hardest_prompts(y, pred, oof[PROMPT]).to_markdown(index=False),
    ]
    return "\n\n".join(parts) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--oof", required=True)
    ap.add_argument("--data", default=None)
    ap.add_argument("--out", default="reports/generated/failure.md")
    args = ap.parse_args()
    train, _ = load(args.data)
    text = report(pd.read_parquet(args.oof), train)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text)
    print(text)


if __name__ == "__main__":
    main()
