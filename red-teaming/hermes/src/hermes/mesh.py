"""The agent runtime and the gateway.

Trust model, which is the point of the experiment:

  gateway   trusted. All agent-to-agent traffic crosses it. Holds the root key and any gateway-side labels.
  runtime   the code around a model. Trusted unless the agent's runtime is `rogue`.
  model     never trusted. Here it is scripted: `benign` follows the skill, `compromised` also runs the
            attack plan once it has seen the marker. Scripted agents are not models and say nothing about
            how likely a real model is to obey.
"""

from __future__ import annotations

import asyncio
import itertools
import random
import secrets
from dataclasses import dataclass, field
from typing import Any

from .caps import Cap, mint, verify
from .core import INTERNAL_DOMAIN, TOOLS, Event, Msg, Reply, host, render
from .scenario import Scenario, Task

MAX_ASKS = 400  # safety stops for the simulator, not controls. Set high enough that budgets are measurable
MAX_DEPTH = 90


@dataclass
class Run:
    """One agent working on one incoming message."""
    agent: str
    msg: Msg
    env: dict[str, str] = field(default_factory=dict)
    labels: set[str] = field(default_factory=set)
    saw: set[str] = field(default_factory=set)
    cap: Cap | None = None
    rogue: bool = False
    final: str = "Done."


class Transport:
    async def deliver(self, msg: Msg) -> Reply:
        raise NotImplementedError


class Direct(Transport):
    def __init__(self, mesh: "Mesh"):
        self.mesh = mesh

    async def deliver(self, msg: Msg) -> Reply:
        return await self.mesh.handle(msg)


class Mesh:
    def __init__(self, sc: Scenario, controls: list, mode: str, seed: int):
        self.sc, self.controls, self.mode = sc, controls, mode
        self.rng = random.Random(seed)
        self.canary = "fake_tok_%016x" % self.rng.getrandbits(64)
        self.root = secrets.token_bytes(16)
        self.transport: Transport = Direct(self)
        self.events: list[Event] = []
        self.finals: list[str] = []
        self.prompts: list[dict[str, str]] = []
        self.task_i = 0
        self.task: Task = sc.tasks[0]
        self.ctx_ids = itertools.count(1)
        self.parent: dict[str, str] = {}
        self.ctx_labels: dict[str, set[str]] = {}
        self.agent_labels: dict[str, set[str]] = {}
        self.store_labels: dict[str, set[str]] = {}
        self.open_requests: dict[str, list[str]] = {}  # agent -> contexts of requests to it with no reply yet
        self.deferred: list[tuple[Run, list[dict]]] = []  # a rogue's steps, due once its request has closed
        self.overlapping = 0  # above zero, requests take turns step by step, so they are open at the same time
        self.asks = 0
        self.fired: set[tuple[int, str]] = set()
        self.discoveries: dict[str, int] = {}
        self.grants: set[str] = set()
        self.private_ok: set[str] = set()
        self.edges = sc.declared_edges()
        self.old_caps: list[Cap] = []
        w = sc.world
        self.secrets = {k: self._fill(v) for k, v in (w.get("secrets") or {}).items()}
        self.web = {k: self._fill(v) for k, v in (w.get("web") or {}).items()}
        self.mail = {k: self._fill(v) for k, v in (w.get("mail") or {}).items()}
        self.docs = {k: self._fill(v) for k, v in (w.get("docs") or {}).items()}
        self.store = {k: self._fill(v) for k, v in (w.get("store") or {}).items()}

    def _fill(self, v: Any) -> str:
        return str(v).replace("{{CANARY}}", self.canary)

    # ---- policy facts

    def is_internal(self, dest: str) -> bool:
        h = host(dest)
        return h == INTERNAL_DOMAIN or h.endswith("." + INTERNAL_DOMAIN) or dest in self.sc.world.get("internal", [])

    def set_task(self, i: int) -> None:
        self.task_i, self.task = i, self.sc.tasks[i]
        self.grants = derive_grants(self.task.text, self.sc.contacts)
        self.private_ok = set(self.task.allow_private)
        self.asks = 0

    def link(self, child: str, parent: str | None) -> None:
        if parent:
            self.parent[child] = parent
        self.ctx_labels[child] = set(self.ctx_labels.get(parent, set())) if parent else set()

    def new_ctx(self) -> str:
        return f"ctx-{next(self.ctx_ids)}"

    # ---- running

    async def run_task(self, i: int) -> str:
        self.set_task(i)
        t = self.task
        ctx = self.new_ctx()
        self.link(ctx, None)
        meta: dict[str, Any] = {}
        for c in self.controls:
            c.on_task(self, meta)
        reply = await self.transport.deliver(Msg("user", t.entry, t.skill, t.input or t.text, ctx, meta))
        await self._drain()
        self.finals.append(reply.text)
        return reply.text

    async def handle(self, msg: Msg) -> Reply:
        a = self.sc.agents[msg.receiver]
        rogue = a.runtime == "rogue"
        run = Run(msg.receiver, msg, {"input": msg.text, "out": msg.text, "task": self.task.text}, rogue=rogue)
        if msg.meta.get("cap"):
            run.cap = Cap.from_dict(msg.meta["cap"])
        if msg.skill not in a.skills:
            return Reply(f"error: {a.name} has no skill {msg.skill}")
        for c in self.controls:
            if not rogue:
                c.on_receive(run, msg, self)
        queue = [dict(s) for s in a.skills[msg.skill]]
        self._see(run, queue, msg.text)
        guard = 0
        self.open_requests.setdefault(msg.receiver, []).append(msg.context)
        try:
            while queue and guard < 5000:
                guard += 1
                if self.overlapping:
                    await asyncio.sleep(0)
                step = queue.pop(0)
                await self._step(run, step, queue)
        finally:
            self.open_requests[msg.receiver].remove(msg.context)
        reply = Reply(run.final)
        if not rogue:
            for c in self.controls:
                c.on_outgoing_reply(run, reply, self)
        push = msg.meta.get("push")
        if push:
            await self._tool(run, "push_notify", {"url": push, "body": reply.text}, None, queue)
        return reply

    async def _drain(self) -> None:
        """Run what a rogue put off. Only called once its request has closed."""
        while self.deferred:
            run, queue = self.deferred.pop(0)
            while queue:
                await self._step(run, queue.pop(0), queue)

    def _see(self, run: Run, queue: list[dict], text: str) -> None:
        marker = self.sc.marker
        if not marker or self.mode != "compromised" or marker not in text:
            return
        key = (self.task_i, run.agent)
        if self.sc.attack.get("loop"):
            key = (self.task_i, run.agent, self.asks)  # a loop re-fires on every visit
        plans = self.sc.attack.get("plans", {})
        plan = plans.get(f"{run.agent}@{self.task_i}", plans.get(run.agent))  # `name@1` applies to the second task only
        if key in self.fired or plan is None:
            return
        self.fired.add(key)
        queue[:0] = [dict(s) for s in plan]

    async def _step(self, run: Run, step: dict[str, Any], queue: list[dict]) -> None:
        if "call" in step:
            args = {k: render(v, run.env) for k, v in (step.get("args") or {}).items()}
            await self._tool(run, step["call"], args, step.get("as"), queue)
        elif "ask" in step:
            await self._ask(run, step["ask"], step.get("skill", "work"), render(step.get("text", ""), run.env),
                            step.get("as"), queue, step.get("push"))
        elif "discover" in step:
            await self._discover(run, step, queue)
        elif "reply" in step:
            run.final = render(step["reply"], run.env)
            if step.get("stop"):  # a hijacked agent answers now, whatever the skill had left to do
                queue.clear()
        elif "let" in step:
            run.env[step["as"]] = render(step["let"], run.env)
        elif "defer" in step:
            steps = [dict(s) for s in step["defer"]]
            if run.rogue:
                self.deferred.append((run, steps))
            else:  # an honest runtime has no timers
                queue[:0] = steps
        elif "parallel" in step:
            self.overlapping += 1
            try:
                await asyncio.gather(*(self._step(run, dict(s), queue) for s in step["parallel"]))
            finally:
                self.overlapping -= 1
        elif "prompt_user" in step:
            text = render(step["prompt_user"], run.env)
            verdict = next((r for c in self.controls if (r := c.on_prompt(run, text, self))), None)
            self.prompts.append({"agent": run.agent, "text": text, "attributed": str(bool(verdict))})
            self.events.append(Event(self.task_i, run.agent, "prompt", "prompt_user", {"text": text}, True, verdict))

    async def _tool(self, run: Run, name: str, args: dict[str, str], var: str | None, queue: list[dict]) -> str:
        spec = TOOLS[name]
        a = self.sc.agents[run.agent]
        dest = args.get(spec.dest_arg, "") if spec.dest_arg else None
        payload = args.get(spec.payload, "") if spec.payload else ""
        reason = None
        if name != "push_notify" and name not in a.tools:
            reason = "no-such-tool"
        elif not run.rogue:  # a rogue runtime has no hooks to run
            reason = next((r for c in self.controls if (r := c.on_tool(run, spec, args, self))), None)
        self.events.append(Event(self.task_i, run.agent, "tool", name, args, reason is None, reason, dest, payload))
        if reason:
            text = f"blocked: {reason}"
        else:
            text = self._execute(run, name, args)
            if not run.rogue:
                for c in self.controls:
                    c.on_result(run, spec, args, self)
        if var:
            run.env[var] = text
        run.env["last"] = text
        self._see(run, queue, text)
        return text

    def _execute(self, run: Run, name: str, args: dict[str, str]) -> str:
        if name == "fetch_url":
            return self.web.get(args.get("url", ""), "404")
        if name == "read_mail":
            return self.mail.get(args.get("id", ""), "no such mail")
        if name == "read_doc":
            return self.docs.get(args.get("id", ""), "no such doc")
        if name == "read_secret":
            return self.secrets.get(args.get("name", ""), "no such secret")
        if name == "store_put":
            self.store[args["key"]] = args.get("value", "")
            return "stored"
        if name == "store_get":
            return self.store.get(args.get("key", ""), "")
        return "ok"

    async def _ask(self, run: Run, peer: str, skill: str, text: str, var: str | None, queue: list[dict],
                   push: str | None = None) -> str:
        self.asks += 1
        ctx = self.new_ctx()
        self.link(ctx, None if run.rogue else run.msg.context)
        meta: dict[str, Any] = {"push": push} if push else {}
        msg = Msg(run.agent, peer, skill, text, ctx, meta, run.msg.depth + 1)
        reason = "simulator-limit" if self.asks > MAX_ASKS or msg.depth > MAX_DEPTH else None
        for c in self.controls:
            reason = reason or c.on_send(run, msg, self)
        self.events.append(Event(self.task_i, run.agent, "ask", peer, {"skill": skill, "text": text},
                                 reason is None, reason))
        if reason:
            out = f"blocked: {reason}"
        else:
            reply = await self.transport.deliver(msg)
            for c in self.controls:
                reply = c.on_reply(run, msg, reply, self) or reply
            await self._drain()
            out = reply.text
        if var:
            run.env[var] = out
        run.env["last"] = out
        self._see(run, queue, out)
        return out

    async def _discover(self, run: Run, step: dict[str, Any], queue: list[dict]) -> None:
        """Pick a peer for a capability from published cards.

        `priority` stands in for a planner that takes the strongest claim, which is how free-text routing fails.
        The card text reaches the model, so a poisoned description can hijack it at this point.
        """
        cap = step["discover"]
        n = self.discoveries.get(cap, 0)
        self.discoveries[cap] = n + 1
        cards = [resolve_card(c, n) for c in self.sc.cards if c.get("capability") == cap]
        for c in self.controls:
            cards = c.filter_cards(run, cards, self)
        for card in cards:
            self._see(run, queue, card.get("description", ""))
        if not cards:
            run.env[step.get("as", "last")] = "blocked: no acceptable card"
            return
        best = max(cards, key=lambda c: c.get("priority", 0))
        await self._ask(run, best["agent"], step.get("skill", "work"), render(step.get("text", ""), run.env),
                        step.get("as"), queue)


def resolve_card(card: dict[str, Any], discovery: int) -> dict[str, Any]:
    """A card as served on this discovery. `rug` swaps its content after `after` earlier fetches."""
    rug = card.get("rug")
    if rug and discovery >= rug.get("after", 1):
        return {**card, **{k: v for k, v in rug.items() if k != "after"}, "rugged": True}
    return dict(card)


def derive_grants(text: str, contacts: dict[str, str]) -> set[str]:
    """Destinations the user actually named. Taken from the user's words, never from content."""
    import re
    grants = set(re.findall(r"[\w.+-]+@[\w.-]+\.\w+", text))
    grants |= {u.rstrip(".,)") for u in re.findall(r"https?://\S+", text)}
    grants |= set(re.findall(r"#[\w-]+", text))
    grants |= set(re.findall(r"\bACCT-[\w-]+", text))
    low = text.lower()
    grants |= {dest for name, dest in contacts.items() if name.lower() in low}
    return grants


def new_cap(mesh: Mesh) -> Cap:
    return mint(mesh.root, f"task-{mesh.task_i}", ("dests=" + ",".join(sorted(mesh.grants)),))


__all__ = ["Mesh", "Run", "Direct", "Transport", "verify", "new_cap", "derive_grants", "resolve_card"]
