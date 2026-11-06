"""Run one scenario against one stack, and matrices of them."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .controls import build
from .mesh import Mesh
from .oracle import attack_success, utility
from .scenario import Scenario


@dataclass
class Result:
    scenario: str
    stack: str
    seed: int
    control: bool
    attack: bool = False
    util: bool = False
    crashed: str = ""
    blocked_by: list[str] = field(default_factory=list)
    factors: dict = field(default_factory=dict)
    weakness: str = ""


async def run_async(sc: Scenario, stack: str, seed: int, transport=None) -> Result:
    mode = "benign" if sc.control else "compromised"
    r = Result(sc.id, stack, seed, sc.control, factors=sc.factors, weakness=sc.weakness)
    try:
        m = Mesh(sc, build(stack), mode, seed)
        if transport is not None:
            m.transport = transport(m)
        for i in range(len(sc.tasks)):
            await m.run_task(i)
        if sc.control:
            r.util = utility(m)
        else:
            r.attack = attack_success(m)
        r.blocked_by = sorted({e.blocked_by for e in m.events if e.blocked_by})
    except Exception as exc:  # a crash stays in the denominator as a failed trial
        r.crashed = f"{type(exc).__name__}: {exc}"
    return r


def run(sc: Scenario, stack: str, seed: int = 0) -> Result:
    return asyncio.run(run_async(sc, stack, seed))


async def _matrix(scenarios, stacks, seeds):
    return [await run_async(sc, st, s) for sc in scenarios for st in stacks for s in range(seeds)]


def matrix(scenarios: list[Scenario], stacks: list[str], seeds: int = 1) -> list[Result]:
    return asyncio.run(_matrix(scenarios, stacks, seeds))
