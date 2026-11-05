"""Agent backends.

Scripted agents are not models and never claim to be:
  benign     follows the task plan; checks that scenarios are solvable
  compromised obeys every injection it can see; the worst case for the architecture
  synthetic:P obeys with probability P; only for exercising statistics

Model backends (openai-compatible, hf) drive a real local model.
"""

from __future__ import annotations

import ipaddress
import json
import os
import random
import re
import uuid
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlsplit

from .scenario import Call, Scenario, render
from .world import ToolSpec


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


@dataclass
class Action:
    calls: list[ToolCall] = field(default_factory=list)
    final: str | None = None


class Agent:
    name = "agent"
    is_model = False

    def begin_session(self, sc: Scenario, index: int, rng: random.Random) -> None:
        pass

    def act(self, messages: list[dict[str, Any]], tools: list[ToolSpec]) -> Action:
        raise NotImplementedError


class ScriptedAgent(Agent):
    name = "benign"
    comply = 0.0

    def __init__(self) -> None:
        self.fired: set[int] = set()  # survives sessions: stages only run once

    def begin_session(self, sc, index, rng):
        self.sc, self.index, self.rng = sc, index, rng
        self.queue: list[Call] = list(sc.sessions[index].benign_plan)
        self.seen = 0
        self.last = ""
        self.secret = ""
        self.pending: Call | None = None
        self.complied = False

    def _visible(self, messages, tools) -> tuple[str, list[str]]:
        new = [str(m.get("content") or "") for m in messages[self.seen:] if m["role"] == "tool"]
        self.seen = len(messages)
        return "\n".join(t.description for t in tools), new

    def act(self, messages, tools):
        descs, results = self._visible(messages, tools)
        if results:
            self.last = results[-1]
            if self.pending is not None and self.pending.tool == "read_secret" and "blocked" not in self.last:
                self.secret = self.last
        text = (descs + "\n" + "\n".join(results)).replace("ˆ", " ")
        for i, st in enumerate(self.sc.stages):
            if i not in self.fired and st.marker in text and st.session in (None, self.index):
                self.fired.add(i)
                if self.rng.random() < self.comply:
                    self.queue = list(st.plan) + self.queue
                    self.complied = True
        if not self.queue:
            final = self.sc.sessions[self.index].final
            if self.complied and self.sc.attack_final:
                final += "\n" + render(self.sc.attack_final, {"secret_seen": self.secret, "last_result": self.last})
            return Action(final=final)
        call = self.queue.pop(0)
        self.pending = call
        env = {"last_result": self.last, "secret_seen": self.secret}
        return Action(calls=[ToolCall(call.tool, {k: render(v, env) for k, v in call.args.items()})])


class CompromisedAgent(ScriptedAgent):
    name = "compromised"
    comply = 1.0


class SyntheticAgent(ScriptedAgent):
    def __init__(self, p: float):
        super().__init__()
        self.comply = p
        self.name = f"synthetic:{p:g}"


LOCAL_NAMES = {"localhost", "ollama", "llamacpp", "vllm", "host.docker.internal"}


def assert_local(base_url: str) -> None:
    """This lab only points at models Baris runs himself. Anything else is refused,
    unless the host is named in GAUNTLET_ALLOWED_HOSTS for a target he owns."""
    host = urlsplit(base_url).hostname or ""
    allowed = {h for h in os.environ.get("GAUNTLET_ALLOWED_HOSTS", "").split(",") if h}
    if host in LOCAL_NAMES or host in allowed:
        return
    try:
        addr = ipaddress.ip_address(host)
    except ValueError:
        addr = None
    if addr is None or not (addr.is_loopback or addr.is_private):
        raise ValueError(f"refusing non-local model endpoint {host!r}")


_TOOL_TAG = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.S)
_FENCE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.S)


def parse_text_tool_calls(text: str) -> list[ToolCall]:
    """Parse tool calls that a model wrote as text instead of native tool calls."""
    blobs = _TOOL_TAG.findall(text) or _FENCE.findall(text)
    stripped = text.strip()
    if not blobs and stripped.startswith("{") and stripped.endswith("}"):
        blobs = [stripped]
    calls = []
    for blob in blobs:
        try:
            obj = json.loads(blob)
        except json.JSONDecodeError:
            continue
        name = obj.get("name") or obj.get("tool")
        args = obj.get("arguments", obj.get("args", obj.get("parameters", {})))
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except json.JSONDecodeError:
                args = {}
        if isinstance(name, str):
            calls.append(ToolCall(name, args if isinstance(args, dict) else {}))
    return calls


class OpenAICompatAgent(Agent):
    """Any local server with an OpenAI-style /v1/chat/completions (Ollama, vLLM,
    llama.cpp server, LM Studio)."""

    is_model = True

    def __init__(self, model: str, base_url: str = "http://localhost:11434/v1", temperature: float = 0.0,
                 max_tokens: int = 512, client: Any = None):
        assert_local(base_url)
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens
        self.name = f"openai-compat:{model}"
        if client is None:
            from openai import OpenAI

            client = OpenAI(base_url=base_url, api_key=os.environ.get("GAUNTLET_LOCAL_KEY", "local"), timeout=300)
        self.client = client

    def begin_session(self, sc, index, rng):
        self.seed = rng.randrange(2**31)

    def act(self, messages, tools):
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages, tools=[t.json_schema() for t in tools] or None,
            temperature=self.temperature, max_tokens=self.max_tokens, seed=self.seed,
        )
        msg = resp.choices[0].message
        calls = []
        for tc in getattr(msg, "tool_calls", None) or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            calls.append(ToolCall(tc.function.name, args if isinstance(args, dict) else {}, tc.id))
        text = msg.content or ""
        calls = calls or parse_text_tool_calls(text)
        return Action(calls=calls) if calls else Action(final=text)


class HFAgent(Agent):
    """Local Hugging Face model. Needs the `hf` extra and a chat template with tools."""

    is_model = True

    def __init__(self, model: str, max_new_tokens: int = 384):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained(model)
        self.model = AutoModelForCausalLM.from_pretrained(model, torch_dtype="auto", device_map="auto")
        self.max_new_tokens = max_new_tokens
        self.name = f"hf:{model}"

    def begin_session(self, sc, index, rng):
        self.torch.manual_seed(rng.randrange(2**31))

    def act(self, messages, tools):
        ids = self.tok.apply_chat_template(
            messages, tools=[t.json_schema() for t in tools], add_generation_prompt=True, return_tensors="pt",
            return_dict=True,
        ).to(self.model.device)
        out = self.model.generate(**ids, max_new_tokens=self.max_new_tokens, do_sample=False)
        text = self.tok.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)
        calls = parse_text_tool_calls(text)
        return Action(calls=calls) if calls else Action(final=text)


def make_agent(spec: str) -> Agent:
    """benign | compromised | synthetic:0.3 | openai:<model>[@base_url] | hf:<model>"""
    if spec == "benign":
        return ScriptedAgent()
    if spec == "compromised":
        return CompromisedAgent()
    if spec.startswith("synthetic:"):
        return SyntheticAgent(float(spec.split(":", 1)[1]))
    if spec.startswith("openai:"):
        model, _, url = spec[len("openai:"):].partition("@")
        url = url or os.environ.get("GAUNTLET_BASE_URL", "http://localhost:11434/v1")
        return OpenAICompatAgent(model, url)
    if spec.startswith("hf:"):
        return HFAgent(spec[3:])
    raise ValueError(f"unknown agent {spec!r}")
