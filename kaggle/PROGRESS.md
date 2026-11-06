# Progress log

## 2026-11-06: second run

### Done

- **Name That LLM now has real text.** Competition data is still out of reach, so `ntl.proxy` cuts
  public Ghostbuster data (CC BY 3.0) to the competition's shape: same schema, prompt × author
  grid, 7 authors. Nine method experiments ran on it. Full results are in `name-that-llm/NOTES.md`.
- All four R scripts ran on the real text, including a new mixed model of how errors cluster.
- New code: topic-held-out folds, class-share balancing (off by default), a full-cluster option for
  assignment (no use), extra candidate models, and a `USE_BALANCE` switch in the kernel.
- **Big Data Bowl:** planned per-drill analysis with a reliability gate before outcomes, one
  composite per drill, a data-driven minimum detectable effect, a write-up skeleton and a limits
  checker.
- This file's `CLAUDE.md` now tells sessions to work autonomously.

### What the real text changed

| Earlier belief, from fake data | What real text showed |
| --- | --- |
| Random folds can under-report | Confirmed, and large: 0.345 against a real 0.491 |
| Grouped CV is the one to trust | Yes for unseen prompts, within 0.010 of holdout. Blind to a genre change, which halved the score |
| Passages on one prompt are correlated | Not found: prompt variance was zero. Claim corrected in NOTES.md |
| Masked text beats raw TF-IDF | Reversed |
| Blends win by a lot | Small win, about 0.012. The kernel's TF-IDF + masked default is supported. Style adds nothing |
| Accuracy climbs with passage length | Not found |
| Clustering prompts is easy | ARI about 0.6, not 1.0. Assignment gains 0.012 of a possible 0.10 |
| Lab-first hierarchy is worth trying | No gain |

### What was actually verified

| Thing | Status |
| --- | --- |
| Name That LLM tests | 52 pass, 1 skipped (needs torch), Python 3.13 |
| NFL tests | 20 pass |
| Lint | `ruff` clean on both projects |
| R scripts | All four Name That LLM scripts ran on real proxy text in R 4.4 |
| Python/R metric agreement | Same 0.5057 from an independent recomputation on proxy data |
| Proxy submission | `ntl.submit` wrote and validated a file; 0.529 against the proxy's own labels |
| Kernel | `USE_BALANCE` line added, not rerun in the simulated layout this time |
| Big Data Bowl R script | Not rerun; its inputs didn't change |
| Dockerfile | **Not built**, still no Docker daemon |
| `ci/kaggle-tests.yml` | **Never run** |
| Kaggle CLI scripts | **Not run**, they need your credentials |
| Transformer track | **Still untested on a real model.** No weights were reachable |
| Real competition data | **Never seen** |

### Decisions made while you slept

- Ghostbuster's GPT folders are undocumented in its README, so I treat them as sibling
  configurations of one model, not as sibling models.
- Reliability cut-off for Big Data Bowl metrics: 0.7 on the mean of attempts. That is a convention,
  so change it before seeing outcomes if you prefer another.
- `USE_BALANCE` and `USE_ASSIGNMENT` stay off. The kernel default stays TF-IDF + masked.
- Considered adding Google's quantum circuit competition, and skipped it as a third project (below).

### Prioritised TODO

1. **Read the adversarial AUC first** on the real data. This is now the top check, because a genre
   gap is what would hurt most, and CV can't see it.
2. **Name That LLM, real data:** run `ntl.cv --compare-random --topic-folds`, then replace numbers.
3. Repeat candidate comparisons over several grouped-CV seeds, since one split misled on the proxy.
4. Fill in `lab_of` with the real model names, and report family against model accuracy.
5. Train a transformer on Kaggle GPU with attached weights, then blend by OOF. This is the biggest
   untested idea, since all results so far are from sparse linear models.
6. Find out on the forum whether generated training data is allowed. The proxy says more prompts
   beat any model change here, but don't use it until the rules are clear.
7. **Big Data Bowl:** fix `schema.py`, run `--by-drill`, fill in `WRITEUP.md`. Due 6 Jan.
8. Investigate why the longest passages scored worst on the proxy.
9. If there's only time for one, choose Name That LLM. It closes a week later and suits this lab
   better.

## 2026-11-05: first run

Its TODO list is superseded by the one above. Its "Needs Baris" and money sections below are still
current, and were updated in the second run.

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

Kaggle's own pages returned no readable content to either run, and scripted access to kaggle.com
was blocked. Details below come from reconscribe.com's guides, with Name That LLM's prize, model
count and entry date also matched by a digg.com summary. **Check them on the competition pages.**

| Competition | Prize | Entry deadline | Final deadline | Data |
| --- | --- | --- | --- | --- |
| [Name That LLM](https://www.kaggle.com/competitions/name-that-llm) | $50,000: ten prizes of $5,000 for places 1–10 | 6 Jan 2027 | 13 Jan 2027, 23:59 UTC (overview countdown reportedly shows 14 Jan; plan for the 13th) | Text |
| [NFL Big Data Bowl 2027](https://www.kaggle.com/competitions/nfl-big-data-bowl-2027) | $100,000: Open Track $45k (3 × $10k, 3 × $5k), University Track $45k (undergraduates only), Grand Prize $10k | 6 Jan 2027 | 6 Jan 2027, 23:59 UTC | Tracking, write-up |

Considered and skipped:

- **RSNA Knee Abnormality Detection** ($77k, images + text): closed 22 Oct 2026.
- **ARC Prize 2026:** finished; results due 4 Dec 2026.
- **Gemma 4 Developer Agent** ($100k + $35k paper track): final deadline 2 Dec 2026, 22 GB data, too
  little runway.

- **Google Quantum AI: Verifiable Quantum Circuit Compilation** ($150,000, final deadline 20 Jan
  2027, opened 22 Oct, per Quantum Computing Report): compress fault-tolerant circuits with agents or
  heuristics, checked by an open verifier. Agents plus an automatic reward suit this lab, but it
  needs quantum compilation knowledge and has no text, image or audio data. Skipped for now, and
  worth your own look.
- **Kaggriculture** (agents in a farming game) and **NeuroGolf 2026**: no reliable prize or date
  found. A public profile already claims a NeuroGolf place, so it may be over.

Second run: I still found no open image, audio or video competition with a later deadline. The
search can't see Kaggle's live list, so one may exist. Worth a two-minute look.

### Needs Baris

- [ ] **Read both rule pages soon; this one matters.** This repo is public. The Name That LLM guide
  says code shared publicly must be posted on the competition forum or in public Kaggle notebooks,
  and private sharing outside a team is banned. The Big Data Bowl summary says public code must
  carry an OSI licence allowing commercial use. I still couldn't read the actual rules, and I kept
  pushing because this run's instructions said to. If they apply: post the baseline on the forum,
  or take the competition-specific code private until the deadline. The repo has no LICENSE file.
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
| Model-attribution audit tool | Speculative, now weaker | Proxy accuracy was 0.88 for model family but 0.49 for the exact author, and a genre change halved it. So "which vendor" might be sellable, "which exact model" isn't yet. Model churn and misuse risk are real too. Test demand first. Ghostbuster's CC BY 3.0 allows commercial use with credit; check the competition data's licence separately. |
| Small validation consulting | Modest, slow | "I find leakage in your ML pipeline" is a real service, and there is now a demo on public data: random CV off by 0.146, grouped CV by 0.010. Finding clients is the hard part. |
| Google quantum compilation prize | Unknown, probably low | $150k pool, ends 20 Jan 2027. The verifier gives an automatic score, which suits agent search, but specialist teams will enter. Spend an evening before committing. |
| Tutorial or course on grouped CV traps | Low income, cheap to try | A blog post costs little and helps the lab's profile more than the wallet. |
| Selling anything built on Big Data Bowl data | No | CC BY-NC 4.0 rules out commercial use. |
