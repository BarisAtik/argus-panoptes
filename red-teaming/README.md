# 🗡️ The Trials: AI red teaming

Argus had a hundred eyes, and some were always open. This folder is about what an AI agent does
when someone else gets to write part of what it reads, and how to tell whether a defense works.

Everything here is local and benign: mock tools, fake canary tokens and reserved `.test` addresses.
Write-ups focus on **classes of weakness and how to build safer systems**, not copy-paste exploits.
Anything a platform asks to keep private stays private.

## Projects

| Project | What it is | Status |
| --- | --- | --- |
| [`gauntlet/`](gauntlet/) | Evaluation harness: 39 scenarios, 14 defenses, MCP transport, AgentDojo bridge, statistics, reports | Working, tested. Worst-case runs done; real model run still to do |
| [`mcp-lens/`](mcp-lens/) | Static scanner for MCP tool manifests, with SARIF output and pinning | Working, tested. Evaluation shows its limits; semantic review to do |
| [`writeups/`](writeups/README.md) | What each weakness class is and how to mitigate it, tied to evidence | First version done |
| [`arena-notebook/`](arena-notebook/) | Template and rules for competition notes | Ready, no entries yet |
| [`programs.md`](programs.md) | Current competitions and bounties, with a note on how realistic each is | Checked Nov 2026 |

## Three findings so far

1. **Rules on actions beat filters on text.** With an agent assumed fully hijacked, a phrase filter stops
   2 of 28 scenarios. An egress allowlist stops 15. Layered policies stop 23.
2. **A scanner's dev score means little.** mcp-lens scored 100% on dev and 5–8% on fresh, adversarial
   holdouts, twice in a row, after improvements that looked successful.
3. **Evaluators have bugs too.** A naive canary check would have called 6 of 84 successful attacks
   stopped, and a benchmark's trace-based checks counted blocked calls as successes until that was
   handled. Neither shows up unless you test the evaluation itself.

## Challenges

| Challenge | Target behaviour | Lesson learned |
| --- | --- | --- |
| _none yet_ | | |

## Picking this up

[`CLAUDE.md`](CLAUDE.md) has the rules and how to run things. [`PROGRESS.md`](PROGRESS.md) has what
is done, what is next, and ideas for earning money.
