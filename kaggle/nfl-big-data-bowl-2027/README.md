# NFL Big Data Bowl 2027: does Combine movement show up on the field?

Kaggle's analytics contest asks you to link 10 Hz Combine tracking to NFL game performance. The
output is a write-up with a public notebook, so there is no leaderboard, and the data-science score
rests on how carefully you argue. A well-supported null result still counts, according to public
descriptions of the rules.

> **Status:** the statistics are tested on fake data with a planted effect. The real data has not
> been seen, and most tracking column names in `src/combinelink/schema.py` are guesses.

## The argument this code is built for

1. **Measure.** Turn smoothed tracks into peak speed, acceleration, deceleration and lateral load.
2. **Reliability.** Does a player repeat his number across attempts? Attempt-to-attempt ICC caps any
   later correlation, so a metric that fails here is dropped before it can mislead.
3. **Transfer.** Do those numbers predict separation for players the model hasn't seen?
   Folds group by player, skill is measured above a position baseline, and the null shuffles whole
   players within position.
4. **Honesty.** Multiple-testing correction across metrics, empirical-Bayes shrinkage for small
   samples, and a selection check, because rookies who never see targets have no outcome at all.

## Quick start

```bash
pip install -r requirements.txt
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m combinelink.synth --out data/synth
PYTHONPATH=src python -m combinelink.run --data data/synth --out artifacts/synth --perm 50
Rscript R/01_reliability_and_linkage.R data/synth artifacts/synth/player_features.csv

./scripts/download_data.sh    # your credentials; also runs the schema check. Fix schema.py if it complains
```

## The planned analysis: per drill, one primary test

`python -m combinelink.run --by-drill` is what to run on real data. Drills measure different things,
so pooling them turns a drill difference into a fake player difference. For each drill it:

1. keeps metrics whose reliability of the mean is at least 0.7, before touching any game outcome;
2. combines those into one composite (first principal component), since correlated metrics are one
   finding;
3. tests the composite with whole players shuffled within position, then corrects across drills;
4. measures the smallest effect the sample could detect. This is what makes a null result worth
   reading: "no link" means little without "and we would have seen one this big".

On fake data with 0.5 yards per trait SD planted, and 120 players, one drill: out-of-player R² 0.086,
q 0.005, and 80% power from 0.2 yards per SD. A planted pure-noise drill fails the reliability gate
in the tests, and no effect gives R² near zero.

`WRITEUP.md` is the skeleton of the deliverable. `python scripts/check_writeup.py WRITEUP.md` checks
it against the stated limits.

## Results on fake data only

Planted effect (0.5 yards per trait SD), 120 players:

| Metric | Attempt ICC | Out-of-player R² | q-value |
| --- | --- | --- | --- |
| Peak speed | 0.78 | 0.090 | 0.024 |
| Time to 90% peak | 0.69 | 0.083 | 0.024 |
| Peak accel | 0.50 | 0.076 | 0.024 |
| Peak decel | 0.54 | 0.071 | 0.024 |
| Peak lateral | 0.77 | 0.090 | 0.024 |
| Speed kept after peak | 0.00 | 0.000 | 0.216 |

With 50 permutations, the smallest possible p-value is 0.02; use 1,000 or more on real data. The
same run with the effect set to zero gave R² near 0 and every q-value at 0.635 or above, so the
pipeline does not invent a link.

Two lessons carried over from this fake run. Five metrics "work" because they all reflect one trait,
so report them as one finding, not five. R's mixed model agrees: with speed and lateral load both
included, neither coefficient clears zero (speed 0.38, 95% CI −0.01 to 0.78), even though the fake
effect is real. Correlated metrics need to be combined or tested one at a time.

## A public stand-in, ready but not run

`combinelink.public_proxy` runs the same chain on public season tables: stopwatch combine results
against average separation for receivers and tight ends. It would show how big a link to expect
before the real data arrives. The plan and predictions in
[`reports/public_proxy_plan.md`](reports/public_proxy_plan.md) were fixed before any outcome was
seen.

It has **not been run on the real tables**. nflverse gives no licence for the data, which it says
belongs to its owners, so this lab hasn't analysed it. The code is tested on fake tables in the same
format, and it recovers a planted link (0.149 yards per SD against 0.15 planted, R checks 0.148).

```bash
PYTHONPATH=src python -m combinelink.public_proxy --synth --out artifacts/public   # code check only
./scripts/download_public.sh    # your decision, after reading the plan's status note
PYTHONPATH=src python -m combinelink.public_proxy --data data/public --out artifacts/public
Rscript R/02_public_proxy_mixed.R artifacts/public/player_seasons.csv
```

## Scope to check once the data is here

The NFL's page says the data covers the 2023 to 2025 Combines and five position groups: receivers,
tight ends, defensive backs, offensive and defensive linemen. This project's outcome is separation,
which only fits receivers and tight ends, so linemen and defensive backs need another outcome or
need leaving out on purpose. Say which in the write-up.

## Data rules

CC BY-NC 4.0, about 2.3 GB, stays out of git. Non-commercial means no selling anything built on it.
