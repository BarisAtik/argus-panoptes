"""Run a matrix like `gauntlet run`, and also keep each trial's final answer and a timestamp.

`Trial` does not store final answers: they reach the oracle and are then dropped. This wrapper
catches them at that call, so nothing in `src/` changes. The other fields are the same as those
of `gauntlet run`, which `tests/test_elastic.py` checks. A cleaner fix is a `final` field on `Trial`.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import asdict
from pathlib import Path

import gauntlet.runner as runner
from gauntlet.defenses import ablations
from gauntlet.scenario import load_scenarios

DEFENSES = "none,injection_filter,allowlist,egress,dlp,trifecta,provenance,layered,strict"


def run(agent: str, defenses: list[str], seeds: int, scenarios: str | None = None, only: str | None = None) -> list[dict]:
    chosen = load_scenarios(scenarios)
    if only:
        chosen = [s for s in chosen if any(k in s.id for k in only.split(","))]
    finals: list[str] = []
    real_evaluate = runner.evaluate

    def catching(sc, world, answers, canary):
        finals.append("\n".join(answers))
        return real_evaluate(sc, world, answers, canary)

    runner.evaluate = catching
    try:
        trials = runner.run_matrix(chosen, agent, defenses, seeds)
    finally:
        runner.evaluate = real_evaluate
    if len(finals) != len(trials):
        raise RuntimeError(f"{len(finals)} final answers for {len(trials)} trials")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    return [{**asdict(t), "final_answer": f, "run_at": now} for t, f in zip(trials, finals)]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agent", default="compromised")
    p.add_argument("--defenses", default=DEFENSES)
    p.add_argument("--ablate", default="layered")
    p.add_argument("--seeds", type=int, default=3)
    p.add_argument("--scenarios")
    p.add_argument("--out", default="runs/trace-analytics.jsonl")
    a = p.parse_args()
    defenses = a.defenses.split(",")
    if a.ablate:
        defenses += [v for v in ablations(a.ablate).values() if v not in defenses]
    rows = run(a.agent, defenses, a.seeds, a.scenarios)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    print(f"{len(rows)} trials written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
