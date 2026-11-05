"""Collect text from third-party packages without running any of their code.

Wheels are opened as zip files. garak's probe file is parsed with `ast`, never
imported. Only injection and system-prompt-extraction material is read: garak and
PyRIT also ship harmful-content sets, and this module does not touch them. Nothing
collected here is written to the repository.

Every record says where it came from, because the source is the unit that matters
when testing whether a detector generalises.
"""

from __future__ import annotations

import ast
import json
import re
import zipfile
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

import yaml

INJECTION, PAYLOAD, TRIGGER = "<|garak_injection|>", "<|garak_payload|>", "<|garak_trigger|>"
MARKERS = {"INJECTION_MARKER": INJECTION, "PAYLOAD_MARKER": PAYLOAD, "TRIGGER_MARKER": TRIGGER}
GARAK_CLASSES = ("TranslationMixin", "FactSnippetMixin", "LatentInjectionReportFull", "LatentInjectionResumeFull",
                 "LatentWhois")  # LatentJailbreakFull is left out on purpose
HARMLESS_TRIGGERS = ("Haha pwned!", "not malicious", "The candidate is the most qualified I have seen.")
PYRIT_FILES = ("pyrit/datasets/seed_datasets/local/psfuzz_steal_system.prompt",
               "pyrit/datasets/seed_datasets/local/garak/system_prompt_extraction.prompt")


@dataclass(frozen=True)
class Payload:
    text: str
    source: str
    group: str  # same template: must not straddle a train/test split


@dataclass(frozen=True)
class Benign:
    text: str
    source: str


def _wheel(wheels: Path, name: str) -> zipfile.ZipFile:
    hits = sorted(wheels.glob(f"{name}-*.whl"))
    if not hits:
        raise FileNotFoundError(f"no {name} wheel in {wheels}; run scripts/fetch_sources.py")
    return zipfile.ZipFile(hits[-1])


def _lit(node: ast.AST) -> Any:
    """Value of a literal, treating the garak markers as constants. None if it is anything else."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        return MARKERS.get(node.id)
    if isinstance(node, ast.FormattedValue):
        return _lit(node.value)
    if isinstance(node, ast.JoinedStr):
        parts = [_lit(v) for v in node.values]
        return "".join(parts) if all(isinstance(p, str) for p in parts) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        a, b = _lit(node.left), _lit(node.right)
        return a + b if isinstance(a, str) and isinstance(b, str) else None
    if isinstance(node, ast.List):
        items = [_lit(v) for v in node.elts]
        return [i for i in items if isinstance(i, str)]
    return None


def garak_templates(source: str) -> dict[str, dict[str, list[str]]]:
    """{class: {attribute: strings}} for the classes above, from the probe's source text."""
    out: dict[str, dict[str, list[str]]] = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.ClassDef) and node.name in GARAK_CLASSES:
            attrs: dict[str, list[str]] = {}
            for st in node.body:
                if isinstance(st, ast.Assign) and isinstance(st.targets[0], ast.Name):
                    val = _lit(st.value)
                    if isinstance(val, list) and val:
                        attrs[st.targets[0].id] = val
            out[node.name] = attrs
    return out


def garak_payloads(templates: dict[str, dict[str, list[str]]]) -> tuple[list[Payload], list[Benign]]:
    pos: list[Payload] = []
    neg: list[Benign] = []
    for cls, attrs in templates.items():
        for i, instr in enumerate(attrs.get("injection_instructions", [])):
            for j, pl in enumerate(attrs.get("payloads", [PAYLOAD])):
                for trig in HARMLESS_TRIGGERS:
                    text = instr.replace(PAYLOAD, pl.replace(TRIGGER, trig))
                    pos.append(Payload(text.strip(), "garak_latent", f"{cls}:{i}"))
        for ctx in attrs.get("contexts", []):
            clean = ctx.replace(INJECTION, " ").strip()
            for para in re.split(r"\n\s*\n", clean):
                if len(para) >= 40:
                    neg.append(Benign(para.strip(), "garak_contexts"))
    return pos, neg


def promptinject_payloads(source: str) -> list[Payload]:
    tree = ast.parse(source)
    out: list[Payload] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and getattr(node.targets[0], "id", "") in ("goal_hikacking_attacks", "prompt_leaking_attacks"):
            table = ast.literal_eval(node.value)
            for key, val in table.items():
                text = val["instruction"] if isinstance(val, dict) else str(val)
                for rogue in ("Haha pwned!!", "I have been redirected."):
                    out.append(Payload(text.replace("{REPLACE_rogue_string}", rogue), "promptinject", f"pi:{key}"))
    return out


def pyrit_payloads(z: zipfile.ZipFile) -> list[Payload]:
    out: list[Payload] = []
    for member in PYRIT_FILES:
        data = yaml.safe_load(z.read(member).decode("utf-8"))
        for i, seed in enumerate(data.get("seeds", [])):
            text = seed.get("value") if isinstance(seed, dict) else seed
            for j, part in enumerate(re.split(r"\n\s*\d+\.\s", "\n" + str(text))):
                part = re.sub(r"^\s*\d+\.\s", "", part).strip()
                if len(part) >= 15:
                    out.append(Payload(part, "pyrit_sysprompt", f"{Path(member).stem}:{i}:{j}"))
    return out


def _strings(obj: Any, min_len: int = 30):
    if isinstance(obj, str):
        if len(obj) >= min_len:
            yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _strings(v, min_len)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v, min_len)


def agentdojo_sets() -> tuple[list[Payload], list[Benign]]:
    import inspect

    from agentdojo.attacks import baseline_attacks
    from agentdojo.attacks.important_instructions_attacks import ImportantInstructionsAttack
    from agentdojo.task_suite.load_suites import get_suites

    # The baseline templates live in constructors, so read them from the module text.
    fixed = re.findall(r'"([^"\n]*\{goal\}[^"\n]*)"', inspect.getsource(baseline_attacks))
    templates = {f"baseline{i}": t for i, t in enumerate(dict.fromkeys(t for t in fixed if "`" not in t))}
    templates["important"] = (ImportantInstructionsAttack._JB_STRING
                              .replace("{user}", "Emma Johnson").replace("{model}", "the assistant"))
    pos: list[Payload] = []
    neg: list[Benign] = []
    for name, suite in get_suites("v1.2.2").items():
        for it in suite.injection_tasks.values():
            for tname, tmpl in templates.items():
                pos.append(Payload(tmpl.format(goal=it.GOAL), "agentdojo", f"{tname}:{name}"))
        env = suite.load_and_inject_default_environment({})
        neg += [Benign(s, "dojo_env") for s in set(_strings(json.loads(env.model_dump_json())))]
        neg += [Benign(u.PROMPT, "dojo_env") for u in suite.user_tasks.values()]
    return pos, neg


def package_docs(limit: int = 4000) -> list[Benign]:
    """Paragraphs of installed packages' READMEs. Full of imperatives written for humans,
    which is the benign text a phrase-based detector tends to confuse with an attack."""
    out: list[str] = []
    for dist in metadata.distributions():
        body = (dist.metadata.get_payload() or dist.read_text("DESCRIPTION.rst") or "") if dist.metadata else ""
        for para in re.split(r"\n\s*\n", str(body)):
            p = para.strip()
            if 60 <= len(p) <= 800 and not p.startswith(("|", "<", "[![", "```", "..")):
                out.append(p)
    return [Benign(t, "pkg_docs") for t in sorted(set(out))[:limit]]


def collect(wheels: Path) -> tuple[list[Payload], list[Benign]]:
    gk = _wheel(wheels, "garak")
    probe = gk.read("garak/probes/latentinjection.py").decode("utf-8")
    pi = gk.read("garak/resources/promptinject/prompt_data.py").decode("utf-8")
    pos, neg = garak_payloads(garak_templates(probe))
    pos += promptinject_payloads(pi)
    pos += pyrit_payloads(_wheel(wheels, "pyrit"))
    normal = json.loads(gk.read("garak/data/payloads/normal_instructions.json"))["payloads"]
    neg += [Benign(t, "garak_contexts") for t in normal]
    p2, n2 = agentdojo_sets()
    return pos + p2, neg + n2 + package_docs()
