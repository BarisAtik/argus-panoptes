"""promptfoo custom provider: `python:adapters/promptfoo_provider.py`.

The prompt is a scenario id. The provider runs that scenario and returns its verdict,
so promptfoo's matrix view, caching and sharing work on top of this harness.
"""

import json
import os

from gauntlet.agents import make_agent
from gauntlet.runner import run_trial
from gauntlet.scenario import load_scenarios

SCENARIOS = {s.id: s for s in load_scenarios()}


def call_api(prompt, options, context):
    cfg = (options or {}).get("config", {})
    agent = cfg.get("agent", os.environ.get("GAUNTLET_AGENT", "compromised"))
    defense = cfg.get("defense", "layered")
    sc = SCENARIOS[prompt.strip()]
    t = run_trial(sc, lambda: make_agent(agent), defense, int(cfg.get("seed", 0)), keep_trace=False)
    return {"output": json.dumps({"attack": t.attack, "utility": t.utility, "control": t.control, "reasons": t.reasons})}
