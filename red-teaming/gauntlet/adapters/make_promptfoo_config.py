"""Write a promptfoo config with one test per scenario."""

import yaml

from gauntlet.scenario import load_scenarios

cfg = {
    "description": "argus gauntlet",
    "prompts": ["{{scenario}}"],
    "providers": [{"id": "python:adapters/promptfoo_provider.py", "label": d, "config": {"defense": d}}
                  for d in ("none", "layered")],
    "defaultTest": {"assert": [{"type": "javascript",
                                "value": "(r => (r.control ? r.utility : !r.attack))(JSON.parse(output))"}]},
    "tests": [{"description": s.title, "vars": {"scenario": s.id}} for s in load_scenarios()],
}
with open("promptfooconfig.yaml", "w") as f:
    yaml.safe_dump(cfg, f, sort_keys=False)
