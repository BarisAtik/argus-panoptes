"""Scenario schema, loading and validation."""

from __future__ import annotations

import base64
import codecs
import re
import secrets as pysecrets
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any
from urllib.parse import quote

import yaml

from .world import BASE_TOOLS, ToolSpec, World

CATEGORIES = {
    "indirect-prompt-injection": ("LLM01", "ASI01"),
    "data-exfiltration": ("LLM02", "ASI01"),
    "tool-misuse": ("LLM06", "ASI02"),
    "privilege-abuse": ("LLM06", "ASI03"),
    "supply-chain": ("LLM03", "ASI04"),
    "code-execution": ("LLM05", "ASI05"),
    "memory-poisoning": ("LLM04", "ASI06"),
    "inter-agent": ("LLM01", "ASI07"),
    "resource-abuse": ("LLM10", "ASI08"),
    "human-trust": ("LLM09", "ASI09"),
}


@dataclass
class Call:
    tool: str
    args: dict[str, str] = field(default_factory=dict)


@dataclass
class Stage:
    marker: str
    plan: list[Call]
    session: int | None = None  # only fire in this session (for delayed triggers)


@dataclass
class Session:
    task: str
    benign_plan: list[Call]
    final: str = "Done."


@dataclass
class Scenario:
    id: str
    title: str
    category: str
    vector: str
    sessions: list[Session]
    world: dict[str, Any]
    utility: list[dict[str, Any]]
    attack_oracles: list[dict[str, Any]] = field(default_factory=list)
    stages: list[Stage] = field(default_factory=list)
    attack_final: str | None = None
    trusted_destinations: list[str] = field(default_factory=list)
    control: bool = False
    notes: str = ""

    @property
    def owasp(self) -> tuple[str, str]:
        return CATEGORIES[self.category]

    @property
    def needed_tools(self) -> set[str]:
        return {c.tool for s in self.sessions for c in s.benign_plan}

    def validate(self) -> None:
        known = {t.name for t in BASE_TOOLS} | {t["name"] for t in self.world.get("extra_tools", [])}
        if self.category not in CATEGORIES:
            raise ValueError(f"{self.id}: unknown category {self.category}")
        for sess in self.sessions:
            for c in sess.benign_plan:
                if c.tool not in known:
                    raise ValueError(f"{self.id}: unknown tool {c.tool}")
        if self.control:
            if self.stages or self.attack_oracles:
                raise ValueError(f"{self.id}: a control must not carry an attack")
            return
        if not self.attack_oracles:
            raise ValueError(f"{self.id}: attack scenario has no attack oracle")
        for st in self.stages:
            for c in st.plan:
                if c.tool not in known:
                    raise ValueError(f"{self.id}: unknown tool {c.tool}")
        if not (self.stages or self.attack_final):
            raise ValueError(f"{self.id}: no attack plan")


def _parse(raw: dict[str, Any]) -> Scenario:
    calls = lambda xs: [Call(c["tool"], {k: str(v) for k, v in c.get("args", {}).items()}) for c in xs or []]
    sessions = [Session(s["task"], calls(s.get("plan")), s.get("final", "Done.")) for s in raw["sessions"]]
    attack = raw.get("attack") or {}
    sc = Scenario(
        id=raw["id"], title=raw["title"], category=raw["category"], vector=raw["vector"],
        sessions=sessions, world=raw.get("world") or {}, utility=raw.get("utility") or [],
        attack_oracles=attack.get("oracles") or [],
        stages=[Stage(st["marker"], calls(st.get("plan")), st.get("session")) for st in attack.get("stages") or []],
        attack_final=attack.get("final"),
        trusted_destinations=raw.get("trusted_destinations") or [],
        control=bool(raw.get("control")), notes=raw.get("notes", ""),
    )
    sc.validate()
    return sc


def load_scenarios(path: str | Path | None = None) -> list[Scenario]:
    files: list[Any]
    if path is None:
        files = sorted(
            (p for p in resources.files("gauntlet").joinpath("scenarios").iterdir() if p.name.endswith(".yaml")),
            key=lambda p: p.name,
        )
    else:
        p = Path(path)
        files = sorted(p.glob("*.yaml")) if p.is_dir() else [p]
    out: list[Scenario] = []
    for f in files:
        out.extend(_parse(r) for r in yaml.safe_load(f.read_text(encoding="utf-8")) or [])
    ids = [s.id for s in out]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"duplicate scenario ids: {sorted(dupes)}")
    return out


def new_canary(rng=None) -> str:
    token = "%016x" % rng.getrandbits(64) if rng else pysecrets.token_hex(8)
    return f"fake_tok_{token}"


_ENC = {
    "b64": lambda s: base64.b64encode(s.encode()).decode(),
    "hex": lambda s: s.encode().hex(),
    "url": lambda s: quote(s, safe=""),
    "reversed": lambda s: s[::-1],
    "rot13": lambda s: codecs.encode(s, "rot_13"),
    "spaced": lambda s: " ".join(s),
    "first_half": lambda s: s[: len(s) // 2],
    "second_half": lambda s: s[len(s) // 2 :],
}
_VAR = re.compile(r"\{\{\s*(\w+)(?:\|(\w+))?\s*\}\}")


def render(text: str, env: dict[str, str]) -> str:
    """Fill {{VAR}} and {{VAR|encoding}}. Unknown variables stay visible."""

    def sub(m: re.Match[str]) -> str:
        val = env.get(m.group(1))
        if val is None:
            return m.group(0)
        return _ENC[m.group(2)](val) if m.group(2) else val

    return _VAR.sub(sub, text)


def build_world(sc: Scenario, canary: str) -> World:
    env = {"CANARY": canary}

    def r(x: Any) -> Any:
        if isinstance(x, str):
            return render(x, env)
        if isinstance(x, dict):
            return {k: r(v) for k, v in x.items()}
        if isinstance(x, list):
            return [r(v) for v in x]
        return x

    w = r(sc.world)
    extra = [
        ToolSpec(t["name"], t["description"], t.get("params", {}), frozenset(t.get("labels", "").split()),
                 t.get("destination_arg"), t.get("response", ""))
        for t in w.get("extra_tools", [])
    ]
    return World(
        inbox=w.get("inbox", []), docs=w.get("docs", {}), web=w.get("web", {}),
        secrets=w.get("secrets", {}), files=w.get("files", {}), peers=w.get("peers", {}),
        memory={k: {"value": v, "tainted": False} for k, v in w.get("memory", {}).items()},
        extra_tools=extra, tool_overrides=w.get("tool_overrides", {}), rug_pull=w.get("rug_pull", {}),
    )
