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

## Second blind holdout

**Benign half only.** `06_blind_controls_2.yaml` comes from a separate author. Controls were frozen for it at commit
`33a516c`, before I saw the file, and I have not read it. `make holdout2` scores it once and writes `reports/holdout2.*`.
It refuses to overwrite them. There is still no blind attack set, and whether to have one is the owner's decision.

Limits: the same as above, and the `_fwd` stacks can only differ from their base stacks if the file declares `input`
types. The report prints how many agents do.
