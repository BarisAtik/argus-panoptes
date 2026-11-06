"""Scenario format. Hand-written YAML and the factorial generator both produce these."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

import yaml

from .core import TOOLS

STEP_KINDS = {"call", "ask", "reply", "discover", "prompt_user", "let", "defer", "parallel"}


def flat(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Steps, with those nested in `defer` and `parallel` spelled out."""
    out = []
    for st in steps:
        out.append(st)
        out += flat(st.get("defer") or st.get("parallel") or [])
    return out


@dataclass
class Task:
    text: str
    entry: str
    skill: str
    input: str = ""
    allow_private: list[str] = field(default_factory=list)


@dataclass
class AgentDef:
    name: str
    tools: list[str] = field(default_factory=list)
    skills: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    inputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    runtime: str = "honest"  # honest | rogue


@dataclass
class Scenario:
    id: str
    title: str
    weakness: str
    agents: dict[str, AgentDef]
    tasks: list[Task]
    world: dict[str, Any] = field(default_factory=dict)
    cards: list[dict[str, Any]] = field(default_factory=list)
    org_allow: list[str] = field(default_factory=list)
    contacts: dict[str, str] = field(default_factory=dict)
    utility: list[dict[str, Any]] = field(default_factory=list)
    attack: dict[str, Any] | None = None
    control: bool = False
    factors: dict[str, Any] = field(default_factory=dict)
    notes: str = ""

    @property
    def marker(self) -> str | None:
        return (self.attack or {}).get("marker")

    def declared_edges(self) -> set[tuple[str, str, str]]:
        """Edges in the benign workflow: this is the peer map a team would register."""
        edges = set()
        for a in self.agents.values():
            for steps in a.skills.values():
                for st in flat(steps):
                    if "ask" in st:
                        edges.add((a.name, st["ask"], st.get("skill", "work")))
                    if "discover" in st:  # a routed call is declared only towards registered agents
                        edges |= {(a.name, c["agent"], st.get("skill", "work")) for c in self.cards
                                  if c.get("capability") == st["discover"] and c.get("pinned")}
        return edges

    def validate(self) -> None:
        for a in self.agents.values():
            unknown = set(a.tools) - set(TOOLS)
            if unknown:
                raise ValueError(f"{self.id}: unknown tools {unknown}")
            plans = (self.attack or {}).get("plans", {})
            mine = [p for k, p in plans.items() if k.split("@")[0] == a.name]
            for steps in [*a.skills.values(), *mine]:
                for st in flat(steps):
                    if not STEP_KINDS & set(st):
                        raise ValueError(f"{self.id}: bad step {st}")
                    peer = st.get("ask")
                    if peer and peer not in self.agents:
                        raise ValueError(f"{self.id}: unknown peer {peer}")
        for t in self.tasks:
            if t.entry not in self.agents or t.skill not in self.agents[t.entry].skills:
                raise ValueError(f"{self.id}: bad entry {t.entry}.{t.skill}")
        if self.control and self.attack:
            raise ValueError(f"{self.id}: a control must not carry an attack")
        if not self.control and not (self.attack and self.attack.get("oracles")):
            raise ValueError(f"{self.id}: attack has no oracle")


def _agent(name: str, raw: dict[str, Any]) -> AgentDef:
    skills, outputs, inputs = {}, {}, {}
    for skill, body in (raw.get("skills") or {}).items():
        if isinstance(body, dict):
            skills[skill] = body.get("steps") or []
            if body.get("output"):
                outputs[skill] = body["output"]
            if body.get("input"):
                inputs[skill] = body["input"]
        else:
            skills[skill] = body or []
    return AgentDef(name, raw.get("tools") or [], skills, outputs, inputs, raw.get("runtime", "honest"))


def parse(raw: dict[str, Any]) -> Scenario:
    sc = Scenario(
        id=raw["id"], title=raw["title"], weakness=raw["weakness"],
        agents={n: _agent(n, a or {}) for n, a in raw["agents"].items()},
        tasks=[Task(t["text"], t["entry"], t.get("skill", "work"), t.get("input", ""), t.get("allow_private") or [])
               for t in raw["tasks"]],
        world=raw.get("world") or {}, cards=raw.get("cards") or [], org_allow=raw.get("org_allow") or [],
        contacts=raw.get("contacts") or {}, utility=raw.get("utility") or [], attack=raw.get("attack"),
        control=bool(raw.get("control")), factors=raw.get("factors") or {}, notes=raw.get("notes", ""),
    )
    _expand(sc)
    sc.validate()
    return sc


def _expand(sc: Scenario) -> None:
    """Attack shapes that would be tedious to spell out in YAML."""
    a = sc.attack or {}
    if a.get("loop"):
        a["plans"] = {"ping": [{"ask": "pong", "skill": "work", "text": a["marker"]}],
                      "pong": [{"ask": "ping", "skill": "work", "text": a["marker"]}]}
    if a.get("fan_out"):
        f = a["fan_out"]
        a["plans"] = {f["agent"]: [{"ask": f["peer"], "skill": f["skill"], "text": "go"}] * f["count"]}


def load(path: str | Path | None = None) -> list[Scenario]:
    if path is None:
        files = sorted((f for f in resources.files("hermes").joinpath("scenarios").iterdir()
                        if f.name.endswith(".yaml")), key=lambda f: f.name)
    else:
        p = Path(path)
        files = sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    out = [parse(r) for f in files for r in yaml.safe_load(f.read_text(encoding="utf-8")) or []]
    ids = [s.id for s in out]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scenario ids")
    return out
