# Progress log

## 2026-11-05: first run

### Done

- Chose two competitions (below) and built a project for each, in Python and R.
- **Name That LLM:** data checks, grouped CV, leakage checks, four sklearn models and a blend,
  prompt-bootstrap CIs, leaderboard-noise simulation, within-prompt assignment with a stress test,
  failure report, submission writer and validator, offline Kaggle kernel, transformer track, three
  R scripts. See `name-that-llm/NOTES.md`.
- **NFL Big Data Bowl:** smoothed kinematics from x/y, reliability (ICC), out-of-player transfer
  test with a permutation null, BH correction, shrinkage, selection check, fake data with a planted
  effect, one R script combining lme4 and tidymodels.

### What was actually verified

| Thing | Status |
| --- | --- |
| Name That LLM tests | 45 pass, on Python 3.12 with torch |
| NFL tests | 15 pass |
| Lint | `ruff` clean on both projects |
| R scripts | All four ran on fake data in R 4.4 |
| Python/R metric agreement | Same 0.7988 from an independent recomputation |
| Kaggle kernel | Ran in a simulated `/kaggle` layout on fake data, offline packaging included |
| Transformer loop | Tiny random BERT on CPU only; no real model has been trained |
| Dockerfile | **Not built**, no Docker daemon was available |
| `ci/kaggle-tests.yml` | **Never run**, and inactive until moved to `.github/workflows/` |
| Kaggle CLI scripts | **Not run**, they need your credentials |
| Real competition data | **Never seen.** Every score in this folder is synthetic |

### Competitions

Kaggle's own pages returned no readable content to this run, and scripted access to kaggle.com was
blocked. Details below come from reconscribe.com's guides, with Name That LLM's prize, model count
and entry date also matched by a digg.com summary. **Check them on the competition pages.**

| Competition | Prize | Entry deadline | Final deadline | Data |
| --- | --- | --- | --- | --- |
| [Name That LLM](https://www.kaggle.com/competitions/name-that-llm) | $50,000: ten prizes of $5,000 for places 1–10 | 6 Jan 2027 | 13 Jan 2027, 23:59 UTC (overview countdown reportedly shows 14 Jan; plan for the 13th) | Text |
| [NFL Big Data Bowl 2027](https://www.kaggle.com/competitions/nfl-big-data-bowl-2027) | $100,000: Open Track $45k (3 × $10k, 3 × $5k), University Track $45k (undergraduates only), Grand Prize $10k | 6 Jan 2027 | 6 Jan 2027, 23:59 UTC | Tracking, write-up |

Considered and skipped:

- **RSNA Knee Abnormality Detection** ($77k, images + text): closed 22 Oct 2026.
- **ARC Prize 2026:** finished; results due 4 Dec 2026.
- **Gemma 4 Developer Agent** ($100k + $35k paper track): final deadline 2 Dec 2026, 22 GB data, too
  little runway.

I found no open image, audio or video competition with a later deadline. The search could not see
Kaggle's live list, so one may exist. Worth a two-minute look.

### Prioritised TODO

1. **Name That LLM, real data:** run the full CV and leakage report, then replace NOTES.md's numbers.
2. Fill in `lab_of` with the real model names and report lab-level vs model-level accuracy.
3. Run `R/01_eda_stylometry.R` on real data to find which style features are about author, not topic.
4. Train the transformer track on GPU, with a model snapshot attached as a Kaggle dataset, then
   blend by OOF.
5. Try a hierarchical model: lab first, then sibling within lab.
6. Check the assignment checklist in NOTES.md, then one submission with and one without it.
7. **Big Data Bowl:** fix `schema.py`, pick comparable drills, compute reliability per drill.
8. Draft that write-up early, since it shares the 6 Jan date with the Name That LLM entry deadline.
9. If there's only time for one, choose Name That LLM: it closes a week later and suits this lab
   better. Big Data Bowl rewards clear statistics, but it also needs football judgement.

### Needs Baris

- [ ] **Read both rule pages before the next push of competition code.** This repo is public.
  Kaggle's usual rules allow public sharing of competition code only if it is also shared on that
  competition's forum or notebooks, and the Big Data Bowl summary says public code must carry an
  OSI licence allowing commercial use. I couldn't read the actual rules. Options if they apply:
  post the baseline on the competition forum, or move the competition-specific code to a private
  repo until the deadline. The repo has no LICENSE file yet either.
- [ ] Accept the rules on both competitions (the entry deadline for both is 6 Jan 2027).
- [ ] Set up Kaggle credentials, then run each `scripts/download_data.sh`.
- [ ] Run `name-that-llm/scripts/package_source.sh YOUR_KAGGLE_USERNAME` and the printed commands.
- [ ] Submit by hand from the competition page, and pick final submissions yourself.
- [ ] To turn on CI, copy `ci/kaggle-tests.yml` to `.github/workflows/`.
- [ ] Choose Big Data Bowl's Open Track. University Track is for undergraduates only.

### Earning money: honest odds

| Idea | Realistic? | Notes |
| --- | --- | --- |
| Name That LLM prize | Low | $5k for each of the top 10, so a solo first-timer's odds are small, though the flat payout helps. The value is mostly the write-up and possibly a medal. |
| Big Data Bowl prize | Low to modest | No leaderboard, and judges reward clarity, so careful statistics can beat raw compute. Still six paid finalist slots in the Open Track worldwide. |
| Model-attribution audit tool | Speculative | "Which model wrote this?" could interest benchmark auditors, but accuracy on short text, model churn and misuse risk are all real problems. Test demand before building. Train only on data you may use commercially, and check the competition data's licence. |
| Small validation consulting | Modest, slow | "I find leakage in your ML pipeline" is a real service. The repeated-measures trap in NOTES.md makes a good demo. Finding clients is the hard part. |
| Tutorial or course on grouped CV traps | Low income, cheap to try | A blog post costs little and helps the lab's profile more than the wallet. |
| Selling anything built on Big Data Bowl data | No | CC BY-NC 4.0 rules out commercial use. |
