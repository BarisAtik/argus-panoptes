# 🗡️ The Trials: AI red teaming

Argus had a hundred eyes, and some were always open. This folder is about what an AI agent does
when someone else gets to write part of what it reads, and how to tell whether a defense works.

Everything here is local and benign: mock tools, fake canary tokens and reserved `.test` addresses.
Write-ups focus on **classes of weakness and how to build safer systems**, not copy-paste exploits.
Anything a platform asks to keep private stays private.

## Projects

| Project | What it is | Status |
| --- | --- | --- |
| [`gauntlet/`](gauntlet/) | Evaluation harness: 41 scenarios plus a blind holdout of 32, 17 defenses, MCP transport, AgentDojo bridge, task router, exhaustive stack search, statistics, reports | Working, tested. Worst-case runs done; real model run still to do |
| [`mcp-lens/`](mcp-lens/) | Static scanner for MCP tool manifests, with SARIF output and pinning | Working, tested. Evaluation shows its limits; semantic review to do |
| [`tripwire/`](tripwire/) | PyTorch prompt-injection detector, built to measure how such detectors fail: source shift, rewriting, calibration | Working, tested, full results in |
| [`hermes/`](hermes/) | A2A trust lab: real SDK transport, 782-cell factorial, 17 protocol-surface attacks, capabilities, three label schemes, 4,096-stack frontier, card linter | Working, tested. Pre-registered, benign holdout scored; attack holdout not done, no model yet |
| [`writeups/`](writeups/README.md) | What each weakness class is and how to mitigate it, tied to evidence, plus posts on [dev scores](writeups/dev-scores.md) and the [split trifecta](writeups/split-trifecta.md) | Updated, posts ready to read |
| [`arena-notebook/`](arena-notebook/) | Template and rules for competition notes | Ready, no entries yet |
| [`programs.md`](programs.md) | Current competitions and bounties, with a note on how realistic each is | Checked 6 Nov 2026 |

## Five findings so far

1. **Rules on actions beat filters on text.** With an agent assumed fully hijacked, a phrase filter stops
   2 of 28 scenarios, an egress allowlist stops 15 and layered policies stop 25. A blind holdout agreed:
   22 of 24. On the independent AgentDojo benchmark, a gold tool list plus a contact-book check takes
   attack success from 100% to 4.4% and keeps 96.9% of benign tasks. A realistic task router gets 11.3%
   and 93.8%. No language model was involved in any of these, which is the point: these controls hold
   whatever the model does.
2. **Security has a bill.** That same layered stack passes only 23% of the hard control tasks. Running all
   8,192 defense subsets showed two defenses reach 29% attack success with 92% of controls passing. Stacks
   picked on dev then lost up to 13 points on the holdout.
3. **A detector's score depends on who wrote the test.** Tripwire gets 93% recall at 1% FPR on held-out
   templates, 58% at 11% FPR on a held-out publisher, and stops 2 of 28 scenarios in the Gauntlet, no better
   than the regex. mcp-lens scored 100% on dev and 5–8% on fresh, adversarial holdouts, twice.
4. **Evaluators have bugs too.** A naive canary check would have called 6 of 84 successful attacks
   stopped, and a benchmark's trace-based checks counted blocked calls as successes until that was
   handled. Recall under rewriting also misled: a detector "caught" 74% of base64 payloads and flagged 87%
   of base64 benign text.

5. **Single-agent rules stop at the first hop.** A trifecta rule stops every direct one-agent exfiltration and none of 748
   cells once the legs sit in different agents. One rogue relay beats labels in metadata and gateway context links,
   102 of 102. Per-agent marks hold, and cost most of the ordinary work. On tasks a separate session wrote blind, a stack
   that kept 98.6% of my own tasks passed 9 of 16.

## Challenges

| Challenge | Target behaviour | Lesson learned |
| --- | --- | --- |
| _none yet_ | | |

## Picking this up

[`CLAUDE.md`](CLAUDE.md) has the rules and how to run things. [`PROGRESS.md`](PROGRESS.md) has what
is done, what is next, and ideas for earning money.
