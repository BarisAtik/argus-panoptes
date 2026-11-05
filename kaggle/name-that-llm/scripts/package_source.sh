#!/usr/bin/env bash
# Builds the upload folder for the private `ntl-source` Kaggle dataset and fills in your username.
# Nothing here talks to Kaggle: the commands to run yourself are printed at the end.
set -euo pipefail
cd "$(dirname "$0")/.."
USER_NAME="${1:?usage: package_source.sh YOUR_KAGGLE_USERNAME}"
OUT=kernel/build
mkdir -p "$OUT/source/ntl" "$OUT/kernel"
cp src/ntl/*.py "$OUT/source/ntl/"
sed "s/YOUR_KAGGLE_USERNAME/$USER_NAME/g" kernel/kernel-metadata.template.json \
  > "$OUT/kernel/kernel-metadata.json"
cp kernel/submission_kernel.py "$OUT/kernel/"
cat > "$OUT/source/dataset-metadata.json" <<JSON
{"title": "ntl-source", "id": "$USER_NAME/ntl-source", "licenses": [{"name": "other"}]}
JSON
echo "Now run, with your own credentials:"
echo "  kaggle datasets create -p $OUT/source --dir-mode zip   # or 'datasets version -m update'"
echo "  kaggle kernels push -p $OUT/kernel"
echo "Then submit the kernel's output from the competition page."
