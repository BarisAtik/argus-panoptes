# 📝 text_nl: a small Dutch classifier, evaluated harder than it was trained

Fine-tunes a Dutch transformer for sentiment on the Dutch Book Reviews Dataset. The model isn't
the interesting part. The interesting part is whether its accuracy can be believed, and
what it does with Dutch it didn't train on.

Status: **pipeline tested, no real results yet.** See the [model card](MODEL_CARD.md).

## What a run produces

- **Data audit, before anything trains.** Exact and MinHash near-duplicates, test texts leaking
  from train, duplicates with conflicting labels, language contamination, promotional texts, and
  whether text length alone predicts the label.
- **A leak-free split.** Duplicate groups never straddle train and validation.
- **A baseline that has to be beaten.** TF-IDF + logistic regression, compared with exact McNemar.
- **Calibration.** ECE, NLL and Brier, raw and temperature-scaled (fit on validation only).
- **Selective prediction.** Error rate if the model only answers its most confident 50/80/90%.
- **Robustness.** Accuracy change and label-flip rate under typos, lowercase, dropped punctuation.
- **86 hand-written behavioural tests** in [`challenge/`](challenge/behaviour_nl.jsonl): negation,
  understatement (`niet onaardig`), sarcasm, contrast clauses, informal spelling, Flemish usage,
  other domains, and topics that shouldn't decide sentiment.
- **Label-error candidates.** Out-of-fold disagreements to review by hand.

## Run it

```bash
pip install -e ".[text,dev]"
python -m text_nl.cli --out runs/baseline --baseline-only        # CPU, minutes
python -m text_nl.cli --out runs/quick --max-train 4000 --epochs 2  # quick laptop GPU run
python -m text_nl.cli --out runs/text                             # full experiment
```

Use your own data with `--train-jsonl` and `--test-jsonl` (`{"text": ..., "label": 0|1}`).
