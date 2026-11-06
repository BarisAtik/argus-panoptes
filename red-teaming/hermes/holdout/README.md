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
