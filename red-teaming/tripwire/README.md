# 🪤 Tripwire

A small PyTorch prompt-injection detector, built less to catch things than to measure how such detectors
fail. It trains a byte-level CNN on injection text from four public sources, with a TF-IDF model and a
regex as baselines, and tests them under progressively harsher splits.

All payloads are benign: moving a fake canary or printing a harmless string. Only injection and
system-prompt-extraction material is read from garak and PyRIT, never their harmful-content sets, and
wheels are opened as zip files, never run. Nothing collected is committed. Full tables:
[`reports/experiment.md`](reports/experiment.md).

## Results

Three seeds, threshold set on validation data from the training sources, aiming for 1% FPR.

| Test | Regex recall | TF-IDF recall / FPR | CNN recall / FPR |
| --- | ---: | ---: | ---: |
| Naive random split | 17% | 95% / 1.5% | 94% / 1.0% |
| Whole templates held out | 8% | 94% / 0.5% | 93% / 1.1% |
| Whole publisher held out (mean of 12 pairs) | 25% | 64% / 10.0% | 58% / 10.6% |

Frozen final model, on data it never saw ([`scenario-lines.json`](reports/scenario-lines.json),
[`external-mcp-lens.json`](reports/external-mcp-lens.json)):

| Test | Result |
| --- | --- |
| Gauntlet dev, worst-case agent | Stops 2 of 28 attacks, same as the regex, and passes all 13 controls ([report](../gauntlet/reports/tripwire-dev.md)) |
| Gauntlet blind holdout | Stops 1 of 24, regex stops 0, passes all 8 controls ([report](../gauntlet/reports/tripwire-holdout.md)) |
| Gauntlet world lines | AUROC 0.58 dev, 0.70 holdout. Little signal, so a new threshold would not save it |
| mcp-lens poisoned tool descriptions | AUROC 0.70 to 0.80, recall 5–14% at 0% FPR. A different task, so this measures transfer |

What this says:

- **Source shift is the main effect.** Splitting by template barely moved scores, despite 94% of payloads
  leaking in a naive split. Holding out a publisher cost about 35 points of recall and raised FPR tenfold
  past its target. Performance on known attack styles says little about the next author.
- **A threshold is a claim about one distribution.** The 1% target missed by a factor of ten.
- **The simple baseline was as good.** TF-IDF matched or beat the CNN on most splits. The CNN stays because
  PyTorch was the point of the exercise, not because the numbers demand it.
- **Do not use this as a defense.** Treat it as weak telemetry at best. Controls on actions do the real work.
  See the [Gauntlet](../gauntlet/).

## Rewriting ([table](reports/experiment.md#recall-under-rewriting), [GLMM](reports/robustness-glmm.txt))

Held-out payloads are respelled mechanically and the threshold stays fixed.

| CNN variant | Clean | Zero-width | Look-alikes | Upper case | Base64 | FPR on upper-cased benign | FPR on zero-width benign |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| plain | 93% | 72% | 53% | 91% | 74% | 80% | 2.1% |
| augmented in training | 78% | 100% | 100% | 99% | 81% | 99.5% | 99.9% |
| normalised | 93% | 93% | 93% | 91% | 76% | 81% | 1.5% |
| canonical (normalised + case-folded) | 92% | 92% | 92% | 92% | 35% | 0.9% | 0.8% |

- **Recall under rewriting means nothing without FPR under the same rewriting.** The augmented model looks
  perfect until you see that it flags almost everything with those characters. It learned "odd characters
  mean attack". The plain CNN's 74% on base64 comes with 87% FPR on benign text given the same rewrite.
- **Normalise before you train.** A few lines of canonicalisation beat data augmentation at no cost.
- **Leet stayed around 55% and TF-IDF fell to 1%** on leet and 0% on base64. Nobody planned for those.

Caveats: percentages weight documents, so large templates count more. Averaged per template, the plain
CNN's base64 recall is 57%, not 74%, and canonical leet recall is 33%, not 57%, and both are in the JSON.
`canonical` was added after seeing the upper-case row, so that row is post-hoc on this test data.
The base64 rewrite prepends a request to act on the note, to benign text too, so its FPR is partly fair.
The GLMM pools recall and so inherits the shortcut above. Read it next to the FPR table.

## Limits

- Only 74 templates sit behind 362 payloads, and one source (`promptinject`) has 10. Intervals resample
  templates (in the JSON), but the population of attack styles is unknown.
- Benign `pkg_docs` text comes from READMEs of whatever is installed, so that source changes between
  environments. Published numbers came from the conda environment below. Pin it before comparing runs.
- English-heavy data. Other languages have not been tested beyond the Gauntlet's few scenarios.

## Running it

```bash
pip install -e ".[dev]"  # or see CLAUDE.md for a CPU-only conda route
make test
make fetch               # pinned garak and PyRIT wheels, read as zip files
make experiment          # about 20 minutes on two cores
make robustness          # about 10 minutes
make final               # weights go in data/, never committed
make external
python scripts/scenario_lines.py
Rscript analysis/robustness.R reports/robustness_groups.json > reports/robustness-glmm.txt
```

The Gauntlet can use the final model as a defense: `gauntlet run --defenses tripwire`.
