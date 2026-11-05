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
