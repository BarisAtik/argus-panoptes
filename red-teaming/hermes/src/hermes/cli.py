"""Command line. Everything is local: mock tools, fake canaries, loopback only."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .controls import STACKS
from .runner import matrix, run
from .scenario import load


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="hermes")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="list scenarios and stacks")
    r = sub.add_parser("run", help="run one scenario file or the built-in surface set")
    r.add_argument("--scenarios")
    r.add_argument("--stacks", default="none,identity,full")
    r.add_argument("--wire", action="store_true", help="run over the real A2A protocol, on loopback TCP")
    e = sub.add_parser("experiment", help="the pre-registered experiment")
    e.add_argument("--out", default="reports")
    f = sub.add_parser("frontier", help="every control combination, about 10 minutes on two cores")
    f.add_argument("--out", default="reports")
    f.add_argument("--workers", type=int, default=2)
    h = sub.add_parser("holdout", help="score the blind holdout. Once.")
    h.add_argument("--path", default="holdout/05_blind.yaml")
    h.add_argument("--out", default="reports")
    h2 = sub.add_parser("holdout2", help="score the second blind holdout. Once.")
    h2.add_argument("--path", default="holdout/06_blind_controls_2.yaml")
    h2.add_argument("--out", default="reports")
    inf = sub.add_parser("inference", help="gateway inference and typed forwards, H10 to H18")
    inf.add_argument("--out", default="reports")
    li = sub.add_parser("lint", help="check Agent Card JSON files")
    li.add_argument("files", nargs="+")
    li.add_argument("--sarif")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        for s in load():
            print(f"{'control' if s.control else 'attack ':8} {s.weakness:26} {s.id}")
        print("stacks:", ", ".join(STACKS))
    elif a.cmd == "run":
        scenarios = load(a.scenarios)
        stacks = a.stacks.split(",")
        if a.wire:
            from .wire import run_on_wire
            for sc in scenarios:
                for st in stacks:
                    _, ok, sends = asyncio.run(run_on_wire(sc, st, tcp=True))
                    print(f"{sc.id:34} {st:14} {'utility' if sc.control else 'attack'}={ok} a2a_sends={sends}")
            return 0
        for r_ in matrix(scenarios, stacks):
            out = r_.util if r_.control else r_.attack
            print(f"{r_.scenario:34} {r_.stack:14} {'utility' if r_.control else 'attack'}={out} {r_.crashed}")
    elif a.cmd == "experiment":
        from .experiment import run as go
        s = go(Path(a.out))
        print(json.dumps({k: v["verdict"] for k, v in s["hypotheses"].items()}, indent=1))
    elif a.cmd == "frontier":
        from .frontier import run as go
        r2 = go(Path(a.out), a.workers)
        print(r2["pick"], r2["cheap"])
    elif a.cmd == "holdout":
        from .holdout import score
        print(score(Path(a.path), Path(a.out)))
    elif a.cmd == "holdout2":
        from .holdout import score_second
        print(score_second(Path(a.path), Path(a.out)))
    elif a.cmd == "inference":
        from .inference import run as go
        s = go(Path(a.out))
        print(json.dumps({k: v["verdict"] for k, v in s["hypotheses"].items()}, indent=1))
    elif a.cmd == "lint":
        from .lint import lint_file, sarif
        code = 0
        for path in a.files:
            found = lint_file(path)
            for x in found:
                print(f"{path}: {x.severity}: {x.rule}: {x.message} {x.where}".rstrip())
                code = code or (1 if x.severity == "high" else 0)
            if a.sarif:
                Path(a.sarif).write_text(json.dumps(sarif(path, found), indent=1))
        return code
    return 0


if __name__ == "__main__":
    sys.exit(main())
