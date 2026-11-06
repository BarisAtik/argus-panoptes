"""Score the blind holdout: fixed stacks, one pass, Wilson intervals, per-scenario failures kept."""

from __future__ import annotations

import json
import math
from pathlib import Path

from .runner import matrix
from .scenario import load

STACKS = ["none", "perimeter", "identity", "caps", "taint_hwm", "lineage_typed", "hwm_typed", "full", "full_lineage"]


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if not n:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def score(path: Path, out: Path) -> dict:
    scenarios = load(path)
    atk = [s for s in scenarios if not s.control]
    ctl = [s for s in scenarios if s.control]
    rows = matrix(scenarios, STACKS)
    res: dict = {"attacks": len(atk), "controls": len(ctl), "stacks": {}, "crashes": [r.scenario for r in rows if r.crashed],
                 "baseline_inert": sorted({r.scenario for r in rows if r.stack == "none" and not r.control and not r.attack}),
                 "baseline_unsolved": sorted({r.scenario for r in rows if r.stack == "none" and r.control and not r.util})}
    for st in STACKS:
        a = [r for r in rows if r.stack == st and not r.control]
        c = [r for r in rows if r.stack == st and r.control]
        k, u = sum(r.attack for r in a), sum(r.util for r in c)
        res["stacks"][st] = {"asr": [k, len(a)], "asr_ci": wilson(k, len(a)), "utility": [u, len(c)],
                             "utility_ci": wilson(u, len(c)),
                             "succeeded": [r.scenario for r in a if r.attack], "broke": [r.scenario for r in c if not r.util]}
    (out / "holdout.json").write_text(json.dumps(res, indent=1))
    L = ["# Blind holdout", "", f"{len(atk)} attacks and {len(ctl)} controls, written without sight of the controls, "
         "scored once. No language model. Intervals are Wilson over scenarios.", "",
         "| Stack | ASR | 95% CI | Utility | 95% CI |", "| --- | ---: | ---: | ---: | ---: |"]
    for st, v in res["stacks"].items():
        a, c = v["asr"], v["utility"]
        L.append(f"| `{st}` | {a[0]}/{a[1]} | {v['asr_ci'][0]:.0%}–{v['asr_ci'][1]:.0%} | {c[0]}/{c[1]} | "
                 f"{v['utility_ci'][0]:.0%}–{v['utility_ci'][1]:.0%} |")
    L += ["", "## What got through `full`", ""] + [f"- `{s}`" for s in res["stacks"]["full"]["succeeded"]]
    L += ["", "## Benign tasks `full` broke", ""] + [f"- `{s}`" for s in res["stacks"]["full"]["broke"]]
    (out / "holdout.md").write_text("\n".join(L) + "\n")
    return {k: v for k, v in res.items() if k != "stacks"}
