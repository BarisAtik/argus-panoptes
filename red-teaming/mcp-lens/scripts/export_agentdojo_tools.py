#!/usr/bin/env python3
"""Export the tool definitions of AgentDojo's suites (MIT) as manifests in corpus/real/.

These were written by other authors for a different purpose, so they make an honest
test for false positives. Reads the installed package; runs none of its tools.
"""

import json
from pathlib import Path

from agentdojo.task_suite.load_suites import get_suites

out = Path(__file__).resolve().parent.parent / "corpus" / "real"
out.mkdir(exist_ok=True)
for name, suite in get_suites("v1.2.2").items():
    tools = [{"name": f.name, "description": f.description, "inputSchema": f.parameters.model_json_schema()}
             for f in suite.tools]
    (out / f"agentdojo-{name}.json").write_text(json.dumps({"server": f"agentdojo-{name}", "tools": tools}, indent=1))
    print(name, len(tools))
