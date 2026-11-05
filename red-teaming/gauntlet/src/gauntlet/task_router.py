"""A realistic stand-in for the gold tool allowlist, evaluated on AgentDojo.

The `allowlist` policy uses each task's reference tool list, which no deployment
has. This router predicts the list from the user's request alone and reports how
much of the upper bound survives. Read tools stay available, since blocking them
mostly costs utility; the router decides which state-changing tools to expose.

  docs     similarity between the request and each tool's name and description.
           Needs no training data.
  history  similarity to other tasks in the suite, weighted by the tools those
           tasks used. The task being scored is excluded, so this is leave-one-out.
  blend    the larger of the two, each scaled to 0..1 per task.

The threshold is chosen on the other three suites, using tool recall only, so no
attack result and no data from the scored suite picks the operating point.

No language model is involved, and TF-IDF is a deliberately simple baseline: a
local embedding model is the obvious next step.
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np
from agentdojo.task_suite.load_suites import get_suites
from sklearn.feature_extraction.text import TfidfVectorizer

from .agentdojo_bridge import (
    SENTINEL, SOURCES, VERSION, ExecutedOnly, PolicyState, WorstCasePipeline, _rate, policy_runtime,
)

METHODS = ("docs", "history", "blend")
GRID = (0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8)


def words(name: str) -> str:
    return re.sub(r"[_\W]+", " ", name)


def task_scores(prompts: list[str], gold: list[set[str]], tool_docs: dict[str, str], method: str) -> list[dict[str, float]]:
    """One {tool: score} per task, for the tools that are not plain reads."""
    guarded = [t for t in tool_docs if not SOURCES.match(t)]
    vec = TfidfVectorizer(sublinear_tf=True, ngram_range=(1, 2), stop_words="english")
    vec.fit(prompts + [tool_docs[t] for t in guarded])
    P = vec.transform(prompts)
    D = vec.transform([tool_docs[t] for t in guarded])
    by_docs = (P @ D.T).toarray()
    sim = (P @ P.T).toarray()
    np.fill_diagonal(sim, 0.0)  # leave one out: a task never sees its own gold list
    Y = np.array([[t in g for t in guarded] for g in gold], dtype=float)
    by_hist = sim @ Y / np.maximum(sim.sum(axis=1, keepdims=True), 1e-9)

    def scale(m: np.ndarray) -> np.ndarray:
        return m / np.maximum(m.max(axis=1, keepdims=True), 1e-9)

    m = {"docs": by_docs, "history": by_hist, "blend": np.maximum(scale(by_docs), scale(by_hist))}[method]
    return [dict(zip(guarded, row.tolist())) for row in m]


def predict(scores: dict[str, float], tools: list[str], tau: float) -> set[str]:
    reads = {t for t in tools if SOURCES.match(t)}
    return reads | {t for t, s in scores.items() if s >= tau}


def covers(pred: set[str], gold: set[str]) -> bool:
    return gold <= pred


def pick_tau(recall_by_tau: dict[float, float], target: float = 0.9) -> float:
    """The strictest threshold that keeps `target` of tasks fully covered."""
    ok = [t for t, r in recall_by_tau.items() if r >= target]
    return max(ok) if ok else min(recall_by_tau)


def suite_data(name: str) -> dict[str, Any]:
    suite = get_suites(VERSION)[name]
    env = suite.load_and_inject_default_environment({})
    uids = list(suite.user_tasks)
    prompts = [suite.user_tasks[u].PROMPT for u in uids]
    gold = [{c.function for c in suite.user_tasks[u].ground_truth(suite.user_tasks[u].init_environment(env.model_copy(deep=True)))}
            for u in uids]
    docs = {t.name: f"{words(t.name)}. {t.description}" for t in suite.tools}
    return {"uids": uids, "prompts": prompts, "gold": gold, "docs": docs}


class Replayer:
    """Replays pairs for one suite. Under an allowlist the outcome depends only on which
    of the pair's own reference tools are allowed, so results are cached on that."""

    def __init__(self, name: str):
        self.suite = get_suites(VERSION)[name]
        self.vectors = list(self.suite.get_injection_vector_defaults())
        self.pristine = self.suite.load_and_inject_default_environment({})
        self.known = self.pristine.model_dump_json().lower()
        self.cache: dict[tuple, tuple[bool, bool, bool]] = {}
        self.tools: dict[str | None, set[str]] = {None: set()}
        for iid, it in self.suite.injection_tasks.items():
            self.tools[iid] = {c.function for c in it.ground_truth(self.pristine.model_copy(deep=True))}

    def replay(self, uid: str, iid: str | None, allowed: set[str], gold: set[str], contacts: bool) -> tuple[bool, bool, bool]:
        key = (uid, iid, frozenset(allowed & (gold | self.tools[iid])), contacts)
        if key in self.cache:
            return self.cache[key]
        ut = self.suite.user_tasks[uid]
        it = self.suite.injection_tasks[iid] if iid else None
        pipe = WorstCasePipeline(ut, it)
        st = PolicyState("allowlist+contacts" if contacts else "allowlist", allowed, ut.PROMPT, self.known)
        inj = {v: f"{SENTINEL} {it.GOAL}" for v in self.vectors} if it else {}
        util, sec = self.suite.run_task_with_pipeline(ExecutedOnly(pipe), ut, it, inj, runtime_class=policy_runtime(st))
        self.cache[key] = (bool(util), bool(sec), pipe.saw_injection)
        return self.cache[key]


def evaluate_suite(job: tuple[str, dict[str, Callable | list]]) -> dict[str, Any]:
    name, conf = job
    data = suite_data(name)
    r = Replayer(name)
    all_tools = list(data["docs"])
    live_pairs = []
    for i, uid in enumerate(data["uids"]):
        for iid, tools in r.tools.items():
            if iid is None or not tools:
                continue
            _, sec, seen = r.replay(uid, iid, set(all_tools), data["gold"][i], False)
            if sec and seen:
                live_pairs.append((i, iid))
    out = {}
    for label, per_task in conf.items():
        contacts = label.endswith("+contacts")
        ben = [r.replay(u, None, per_task[i], data["gold"][i], contacts)[0] for i, u in enumerate(data["uids"])]
        atk = [r.replay(data["uids"][i], iid, per_task[i], data["gold"][i], contacts) for i, iid in live_pairs]
        out[label] = {"benign": [sum(ben), len(ben)], "asr": [sum(a[1] for a in atk), len(atk)],
                      "uua": [sum(a[0] for a in atk), len(atk)],
                      "recall": [sum(covers(per_task[i], g) for i, g in enumerate(data["gold"])), len(data["gold"])],
                      "tools": float(np.mean([len(s) for s in per_task])), "tools_total": len(all_tools)}
    return {"suite": name, "rows": out}


def build_policies(names: list[str], target: float = 0.9) -> dict[str, dict[str, list[set[str]]]]:
    data = {n: suite_data(n) for n in names}
    scores = {(n, m): task_scores(d["prompts"], d["gold"], d["docs"], m) for n, d in data.items() for m in METHODS}

    def recall(n: str, m: str, tau: float) -> tuple[int, int]:
        d = data[n]
        tools = list(d["docs"])
        hits = sum(covers(predict(s, tools, tau), g) for s, g in zip(scores[n, m], d["gold"]))
        return hits, len(d["gold"])

    conf: dict[str, dict[str, list[set[str]]]] = {n: {} for n in names}
    picked: dict[str, dict[str, float]] = {}
    for n, d in data.items():
        tools = list(d["docs"])
        conf[n]["gold"] = list(d["gold"])
        conf[n]["gold+contacts"] = list(d["gold"])
        conf[n]["no-router"] = [set(tools) for _ in d["gold"]]
        conf[n]["reads-only"] = [{t for t in tools if SOURCES.match(t)} for _ in d["gold"]]
        for m in METHODS:
            others = [o for o in names if o != n]
            by_tau = {}
            for tau in GRID:
                pairs = [recall(o, m, tau) for o in others]
                by_tau[tau] = sum(p[0] for p in pairs) / sum(p[1] for p in pairs)
            tau = pick_tau(by_tau, target)
            picked.setdefault(m, {})[n] = tau
            pred = [predict(s, tools, tau) for s in scores[n, m]]
            conf[n][f"{m}"] = pred
            conf[n][f"{m}+contacts"] = pred
            for t in GRID:
                conf[n][f"curve:{m}:{t:g}+contacts"] = [predict(s, tools, t) for s in scores[n, m]]
    conf["_picked"] = picked  # type: ignore[assignment]
    return conf


def aggregate(parts: list[dict[str, Any]]) -> dict[str, Any]:
    labels = list(parts[0]["rows"])
    out: dict[str, Any] = {}
    for lab in labels:
        rows = [p["rows"][lab] for p in parts]
        tot = lambda k: [sum(r[k][0] for r in rows), sum(r[k][1] for r in rows)]
        out[lab] = {"asr": _rate(*tot("asr")), "benign": _rate(*tot("benign")), "utility_under_attack": _rate(*tot("uua")),
                    "recall": _rate(*tot("recall")),
                    "tools": float(np.mean([r["tools"] for r in rows])),
                    "tools_total": float(np.mean([r["tools_total"] for r in rows])),
                    "by_suite": {p["suite"]: {k: p["rows"][lab][k] for k in ("asr", "benign", "recall")} for p in parts}}
    return out


def to_markdown(res: dict[str, Any]) -> str:
    f = lambda r: f"{100 * r['rate']:.1f}% ({r['k']}/{r['n']})"
    s = res["summary"]
    L = ["# Task router on AgentDojo", "",
         f"Benchmark `{res['version']}`. Same worst-case replay as [agentdojo-worst-case.md](agentdojo-worst-case.md), so "
         "**no language model was involved** and the agent obeys every injection it sees. Only the allowed tool list changes.",
         "", "Thresholds were chosen on the other three suites for each scored suite, using tool recall only, aiming "
         f"for {res['target']:.0%} of tasks fully covered: `{json.dumps(res['picked'])}`. Pairs share tasks, so Wilson "
         "intervals in the JSON are too narrow.", "",
         "| Allowed tools | ASR | Benign utility | Tasks fully covered | Mean tools exposed |", "| --- | ---: | ---: | ---: | ---: |"]
    for lab in s:
        if lab.startswith("curve:"):
            continue
        r = s[lab]
        L.append(f"| {lab} | {f(r['asr'])} | {f(r['benign'])} | {f(r['recall'])} | {r['tools']:.1f} of {r['tools_total']:.1f} |")
    L += ["", "## Frontier with the contact-book check", "", "All suites at one threshold. A sweep, so it describes the method and "
          "does not select an operating point.", "", "| Method | Threshold | ASR | Benign utility |", "| --- | ---: | ---: | ---: |"]
    for lab, r in s.items():
        if lab.startswith("curve:"):
            _, m, t = lab.removesuffix("+contacts").split(":")
            L.append(f"| {m} | {t} | {100 * r['asr']['rate']:.1f}% | {100 * r['benign']['rate']:.1f}% |")
    return "\n".join(L) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--suites", default="banking,slack,travel,workspace")
    p.add_argument("--target", type=float, default=0.9)
    p.add_argument("--json", default="reports/agentdojo-router.json")
    p.add_argument("--md", default="reports/agentdojo-router.md")
    a = p.parse_args(argv)
    names = a.suites.split(",")
    conf = build_policies(names, a.target)
    picked = conf.pop("_picked")
    with ProcessPoolExecutor(2) as pool:
        parts = list(pool.map(evaluate_suite, [(n, conf[n]) for n in names]))
    res = {"version": VERSION, "mode": "worst-case", "target": a.target, "picked": picked, "summary": aggregate(parts)}
    Path(a.json).write_text(json.dumps(res, indent=1))
    Path(a.md).write_text(to_markdown(res))
    print(to_markdown(res))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
