"""Train the final model on all third-party sources, and load it for use.

The Gauntlet scenarios and the mcp-lens corpora are never training data, so they
stay outside tests. Weights go under data/ and are not committed; `make final`
rebuilds them in about a minute. Text is canonicalised before scoring, the variant the
rewriting experiment favoured, and that choice was made on third-party data only.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
import torch

from . import metrics as M
from .dataset import MAX_CHARS, build, split_groups, split_list
from .evasion import canon
from .experiment import TARGET_FPR
from .model import ByteCNN, fit, fit_temperature, logits
from .sources import collect

DEFAULT = Path(__file__).resolve().parents[2] / "data" / "tripwire.pt"


class Detector:
    def __init__(self, model: ByteCNN, temperature: float, threshold: float):
        self.model, self.temperature, self.threshold = model, temperature, threshold

    @classmethod
    def load(cls, path: str | Path = DEFAULT) -> "Detector":
        blob = torch.load(path, weights_only=True)
        m = ByteCNN()
        m.load_state_dict(blob["state"])
        return cls(m.eval(), float(blob["temperature"]), float(blob["threshold"]))

    def score(self, texts: list[str]) -> np.ndarray:
        """Raw logit per text. Long text is scanned in overlapping windows and takes the worst one."""
        windows, owner = [], []
        for i, t in enumerate(texts):
            step = MAX_CHARS // 2
            t = canon(t)
            for s in range(0, max(1, len(t) - step), step):
                windows.append(t[s : s + MAX_CHARS])
                owner.append(i)
        z = logits(self.model, windows)
        out = np.full(len(texts), -np.inf)
        np.maximum.at(out, np.array(owner, dtype=int), z)
        return out

    def flags(self, texts: list[str]) -> list[bool]:
        return (self.score(texts) >= self.threshold).tolist()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wheels", default="data/wheels")
    ap.add_argument("--n", type=int, default=2500)
    a = ap.parse_args(argv)
    pos, neg = collect(Path(a.wheels))
    rng = random.Random(0)
    ptr, pva = split_groups(pos, 0.15, rng)
    ntr, nva = split_list(neg, 0.15, rng)
    train, val = build(ptr, ntr, a.n, rng), build(pva, nva, a.n // 4, rng)
    model = fit([canon(d.text) for d in train], [d.label for d in train], seed=0)
    z = logits(model, [canon(d.text) for d in val])
    y = np.array([d.label for d in val])
    blob = {"state": model.state_dict(), "temperature": fit_temperature(z, y),
            "threshold": M.threshold_at_fpr(z[y == 0], TARGET_FPR)}
    DEFAULT.parent.mkdir(exist_ok=True)
    torch.save(blob, DEFAULT)
    print(json.dumps({k: blob[k] for k in ("temperature", "threshold")}))
    print({"val_auroc": M.auroc(y, z), **M.rates(y, z, blob["threshold"])})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
