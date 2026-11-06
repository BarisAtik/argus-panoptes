# Public stand-in: plan written before looking at any outcome

The competition's tracking data hasn't been seen. This runs the same reliability, transfer and
correction chain on public season tables, to learn how large a link to expect and whether the method
holds up on something real. It is a stand-in: stopwatch and tape results, not 10 Hz tracking, and
season averages, not plays.

At the time of writing I have looked at column names, row counts and target counts only.

**Status: not run.** nflverse states that the data "belong to their respective owners, and are
governed by their terms of use" and gives no data licence, so this lab hasn't analysed it. The tables
were downloaded once to profile columns, then deleted. No outcome was looked at. The code is tested
on synthetic tables and is ready for Baris to run if he is happy with those terms. See
`python -m combinelink.public_proxy --help`.

**Data.** nflverse `combine`, `ngs_receiving` and `players`, joined on `pfr_id` then `gsis_id`.
WR and TE, regular-season tables, seasons 2016 to 2025. 2026 is left out because that season is
unfinished. The table only holds receivers who qualified on targets, which is a selection in itself.

**Outcome.** `avg_separation` per player-season, as public. Secondary: the same with
`avg_intended_air_yards` and `avg_cushion` regressed out. That is a judgement call, because a fast
receiver may earn extra cushion, so adjusting can remove part of the effect being looked for.

**Primary tests, two only, with Benjamini-Hochberg across them.** Tests z-scored within position,
signed so that higher is better, combined as a first principal component:

1. speed and power: 40-yard dash, vertical, broad jump;
2. agility: three-cone, short shuttle.

Complete cases per composite, with missingness reported. Skill is out-of-player R² above a position
baseline. The null shuffles whole players within position, 1,000 permutations.

**Follow-ups, labelled as such.** Each test alone with its own correction, the adjusted outcome,
yards per SD with a player bootstrap, year-to-year reliability of separation as a ceiling, smallest
detectable effect, selection by test quartile, a time split (combines to 2019 against 2020 on), and
whether the composite adds anything beyond draft slot.

**Predictions.** Speed and power links weakly, out-of-player R² under 0.03. Agility is
indistinguishable from zero. Separation repeats moderately from year to year. Anything I find will
shrink further once draft slot is controlled for.
