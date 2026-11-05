# 🔍 mcp-lens

A static scanner for [MCP](https://modelcontextprotocol.io) tool manifests. Tool descriptions and
schemas go straight into an agent's context, so a malicious server can steer the agent before any
tool is called. mcp-lens reads the definitions without calling a model or a tool, and reports
hidden characters, instruction overrides, concealment, grabs for secrets, shadowing of other
tools, parameters shaped for exfiltration, name collisions, and changes since a tool was pinned.

```bash
pip install -e ".[dev]"
mcp-lens scan tools.json                        # a saved tools/list result
mcp-lens scan --stdio "python -m my_server"     # start a local server and read its tools
mcp-lens scan tools.json --format sarif > lens.sarif     # for GitHub code scanning
mcp-lens pin tools.json --lock mcp-lens.lock.json        # pin definitions now
mcp-lens scan tools.json --lock mcp-lens.lock.json       # later: catches a rug pull
```

Exit code is 1 at `--fail-on` severity or above (default `high`), so it fits in CI.

## How good is it? Less than the dev score suggests

This is the most useful result in the project, so it comes first.

| Version | Dev recall | Fresh holdout recall | Holdout precision | Third-party tools flagged |
| --- | ---: | ---: | ---: | ---: |
| 0.1 | 100% (21/21) | **8%** (2/25) | 100% | 1 of 74 |
| 0.2 | 100% (21/21), 88% (22/25) on the old holdout | **5%** (1/20) | 100% | 1 of 74 |

Each row was scored once on a holdout written after the rules were frozen. After 0.1 failed, that
holdout was used for development and 0.2 went up to 88% on it, which looks like a big win. On a new
holdout it fell back to 5%. The patterns chase the last set of examples they saw.

Read that with care. The holdouts are small, written by one author, and deliberately adversarial
(paraphrase, polite framing, output steering, rare encodings), so 5% is not a rate for attacks in
the wild. Blunt or copy-pasted poisoning, invisible Unicode, HTML comments, known secret paths and
rug pulls are caught well. Precision stayed high and the false-positive rate on 74 tool definitions
from a third party (AgentDojo) is low. So:

- It is a cheap hygiene check, and pinning catches silent changes whatever the wording.
- It is not a defense against someone who knows it exists. Do not ship it as one.
- More regexes are the wrong next step. The right one is a semantic review (does this description
  ask for anything beyond the tool's stated job?), scored on a holdout the same way.

Numbers: [`reports/`](reports/). Reproduce with `python scripts/export_agentdojo_tools.py` and
`python scripts/evaluate.py --show`. The evaluation script now covers all corpora; earlier scores
are frozen in the JSON files.

`scripts/harvest.py` snapshots tool lists from public MCP servers for a wider false-positive test.
It starts those packages, so run it yourself inside a throwaway container. It has not been run,
which means the numbers above have not been checked against real MCP servers yet.

## Rules

| Rule | Severity | Looks for |
| --- | --- | --- |
| ML001 | high | Invisible Unicode (tag block, zero-width, bidi) |
| ML002 | high | Instruction overrides, in a few languages |
| ML003 | high | Hiding things from the user |
| ML004 | high | Secrets, sensitive paths, the conversation itself |
| ML005 | medium | Mandatory steps unrelated to the tool |
| ML006 | medium | Changing how other tools or outgoing mail behave |
| ML007 | medium | Naming another tool |
| ML008 | medium | Parameters shaped to carry context |
| ML009 | medium | Encoded blobs |
| ML010 | low | Outside addresses |
| ML011 | high/medium | Look-alike and colliding tool names |
| ML012 | low | Schemas that accept anything |
| ML013 | low | Very long descriptions |
| ML014 | low | A set combining third-party input, private data and egress |
| ML015 | high/medium/low | Changed, new or removed tools against a lock file |
| ML016 | medium | Instructions to the agent about data or destinations |
| ML017 | high | Text in HTML comments |

Before normalising, every field a client may show a model is walked (descriptions, titles, defaults,
enums), and cheap evasions are undone: NFKC, confusables, leetspeak, s p a c e d text, short base64,
and phrases split across two fields.

Other MCP scanners exist, Invariant's `mcp-scan` being the best known. This one exists to learn from
and to carry an honest evaluation, so compare before relying on it.
