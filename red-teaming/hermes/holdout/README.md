# Blind holdout

**Benign half only.** 16 everyday tasks, written by a separate author session barred from `controls.py`, the
factorial, the reports and the pre-registration. It checked them only against the `none` stack and needed no edits.
Controls were frozen at commit `535f33d`. The oracle changed after that (it now reads every argument, not just the body),
which did not alter a single experiment number and does not touch controls. One task has a single agent, below the brief,
and stays as written. Committed before any defended stack ran on it, then scored once with `hermes holdout`.

**There is no attack holdout.** The first author session was stopped by an automated safety check while writing the
attack file. Nothing was saved. That content was not retried, reworded or delegated again, so the attack side has only dev
results. See "Needs Baris" in `../../PROGRESS.md`.

Limits: the author is the same kind of system as me, so this is blind, not independent. It also chose its own grants.

## Second set: `06_blind_controls_2.yaml`

20 benign mesh controls (`blind2-` ids) of ordinary multi-agent work: research delegated to a helper, a writer sending the
result to a named contact, chains of two to three agents, routed lookups, typed replies, and work that spans two tasks.

Written by a separate blind author session (Claude). It read only `docs/DSL.md`, `scenario.py`, `core.py` and `oracle.py`.
It did not read `controls.py`, `frontier.py`, reports, `PREREGISTRATION.md`, project READMEs, this README,
`05_blind_controls.yaml` or any holdout result.

Checked for solvability only: 20 of 20 pass with `hermes run --stacks none`. No other stack has been run. Not yet scored.

## Scoring the second set

Controls are frozen at commit `33a516c`. The order matters, so here it is: the set arrived in `dfd39d5` at 07:06, before the
addendum to the pre-registration (`651f95a`, 07:07) and before the freeze (07:13). So the file was not written after the
freeze. What the freeze protects is that the set stays unseen and unscored: I did not open it at any point, and its author
could not see the new controls, which did not exist yet. `make holdout2` scores it once and writes `reports/holdout2.*`,
and refuses to overwrite them. There is still no blind attack set, and whether to have one is the owner's decision.

Limits: the same as above. `input` types and `parallel` did not exist when the set was written, so I expect it to use
neither. If so, the `_fwd` stacks cannot differ from their base stacks and it cannot test typed forwards or false links.
It can only show what the new label scheme costs on ordinary sequential work. The report prints how many agents declare
an `input` type.
