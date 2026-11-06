# Blind holdout

32 scenarios (24 attacks, 8 controls) written by a separate author session that was barred from reading
`defenses.py`, the reports, the write-ups and the other scenario files. It saw the schema, the mock tools,
the oracles, the scripted agent and one scenario file for format.

Procedure, fixed before scoring:

1. Defenses frozen at commit `34c31cc`.
2. This set committed before any defense was run on it. The author only ran the `none` stack.
3. Scored once with `make holdout-run`: `none`, `injection_filter`, `egress`, `dlp`, `provenance`, `layered`,
   `strict`, 3 seeds, compromised agent, with benign-agent control utility from the same run.
4. Failures are reported as they are. Tuning a defense on them turns this set into dev data, so the next
   comparison needs a new holdout.

Limits: the author is the same kind of system as the defense author, so this is blind but not independent
in any stronger sense. It also saw one dev scenario file, and `trusted_destinations` are its own choices.

## Second set: `06_ordinary_benign.yaml`

30 controls (`ord-` ids) of plain office work: reading and summarizing, replying to colleagues, paying regular invoices,
scheduling notes, looking something up for whoever asked, multi-step reads, updating notes and memory, and public web
lookups. Unlike `03_controls.yaml`, these are not hard negatives and were not designed to trip anything.

Written by a separate blind author session (Claude). It read only the scenario schema, `world.py`, `oracle.py`, `cli.py`
and, for format, `03_controls.yaml`. It did not read any defense code, `frontier.py`, `task_router.py`, reports, write-ups,
project READMEs, this README, the `01_`, `02_` or `04_` scenario files, or any holdout result.

Checked for solvability only: 30 of 30 pass with the scripted benign agent and defense `none`. No other stack has been
run. Not yet scored.
