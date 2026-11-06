#!/usr/bin/env bash
# The full NER study on CPU, about two hours on two cores. See ner_nl/README.md.
set -euo pipefail
cd "$(dirname "$0")/.."

python -m ner_nl.run audit
python - <<'PY'
from ner_nl.run import splits, word_vectors

word_vectors(splits())
PY
for seed in 0 1 2; do
  python -m ner_nl.run train --seed "$seed"
  python -m ner_nl.run train --seed "$seed" --augment 0.5
done
python -m ner_nl.run evaluate
python -m ner_nl.run names
python -m ner_nl.names_summary
Rscript ner_nl/names_mixed.R runs/ner_nl/names.csv runs/ner_nl/names_mixed.json
python -m ner_nl.run names_why
python -m ner_nl.run baseline_person
python -m ner_nl.run calibrate
python -m ner_nl.run review
python -m ner_nl.run report
