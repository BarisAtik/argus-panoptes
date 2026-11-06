"""Every combination of controls: which stacks are not dominated?

Ten independent controls, each on or off, and one choice of label scheme, so 4,096 stacks. The picking rule is fixed
here, before any frontier was computed:

  floor   the lowest ASR any stack reaches.
  pick    the highest-utility stack within 2 points of that floor, then the fewest controls.
  cheap   the highest-utility stack with ASR at or under 25%, then the fewest controls.

ASR is over all cells, factorial and surface together, so it is weighted by a designed space, not by real attacks.
"""

from __future__ import annotations

import json
from itertools import combinations
from multiprocessing import Pool
from pathlib import Path

from .factorial import attack_cells, control_cells
from .runner import matrix
from .scenario import Scenario, load

BINARY = ["agent_egress", "agent_dlp", "agent_trifecta", "peer_acl", "caps", "typed_declass", "card_sig", "card_pin",
          "human_gate", "push_guard"]
LABELS = [None, "taint_inband", "taint_lineage", "taint_hwm"]
_ATK: list[Scenario] = []
_CTL: list[Scenario] = []


def stacks() -> list[tuple[str, ...]]:
    out = []
    for n in range(len(BINARY) + 1):
        for combo in combinations(BINARY, n):
            for lab in LABELS:
                out.append((*combo, *([lab] if lab else [])))
    return out


def _load() -> None:
    global _ATK, _CTL
    surface = load()
    _ATK = attack_cells() + [s for s in surface if not s.control]
    _CTL = control_cells() + [s for s in surface if s.control]


def _score(stack: tuple[str, ...]) -> dict:
    name = "+".join(stack) or "none"
    a = matrix(_ATK, [name])
    c = matrix(_CTL, [name])
    return {"stack": list(stack), "asr": sum(r.attack for r in a) / len(a), "utility": sum(r.util for r in c) / len(c)}


def pareto(rows: list[dict]) -> list[dict]:
    """Best trade-offs; ties in both scores keep only the smallest stack."""
    best: dict[tuple, dict] = {}
    for r in rows:
        key = (round(r["asr"], 6), round(r["utility"], 6))
        if key not in best or len(r["stack"]) < len(best[key]["stack"]):
            best[key] = r
    unique = list(best.values())
    front = [r for r in unique
             if not any(o is not r and o["asr"] <= r["asr"] and o["utility"] >= r["utility"] for o in unique)]
    return sorted(front, key=lambda r: r["asr"])


def pick(rows: list[dict]) -> dict:
    floor = min(r["asr"] for r in rows)
    near = [r for r in rows if r["asr"] <= floor + 0.02]
    chosen = max(near, key=lambda r: (r["utility"], -len(r["stack"])))
    within = [r for r in rows if r["asr"] <= 0.25]
    cheap = max(within, key=lambda r: (r["utility"], -len(r["stack"]))) if within else None
    return {"floor": floor, "pick": chosen, "cheap": cheap}


def run(out_dir: Path, workers: int = 2) -> dict:
    _load()
    with Pool(workers, initializer=_load) as pool:
        rows = pool.map(_score, stacks(), chunksize=32)
    result = {"stacks": len(rows), "attack_cells": len(_ATK), "control_cells": len(_CTL),
              "pareto": pareto(rows), **pick(rows)}
    (out_dir / "frontier.json").write_text(json.dumps(result, indent=1))
    L = ["# Control frontier", "", f"All {len(rows)} stacks over {len(_ATK)} attack cells and {len(_CTL)} benign cells. "
         "No language model. ASR is weighted by a designed space, so compare stacks and do not quote it as a rate.", "",
         f"Floor: {result['floor']:.1%} ASR.", "", "| ASR | Utility | Stack |", "| ---: | ---: | --- |"]
    L += [f"| {r['asr']:.1%} | {r['utility']:.1%} | {' + '.join(r['stack']) or 'none'} |" for r in result["pareto"]]
    L += ["", f"**Pick** (best utility within 2 points of the floor): {' + '.join(result['pick']['stack'])}, "
          f"{result['pick']['asr']:.1%} ASR, {result['pick']['utility']:.1%} utility."]
    if result["cheap"]:
        L += [f"**Cheap** (best utility at or under 25% ASR): {' + '.join(result['cheap']['stack'])}, "
              f"{result['cheap']['asr']:.1%} ASR, {result['cheap']['utility']:.1%} utility."]
    (out_dir / "frontier.md").write_text("\n".join(L) + "\n")
    return result
