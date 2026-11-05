#!/usr/bin/env bash
# Run this yourself: it uses YOUR Kaggle credentials (~/.kaggle/kaggle.json or KAGGLE_API_TOKEN)
# and needs you to have accepted the competition rules on the website first.
# The data lands in data/raw/, which git ignores. Never commit it.
set -euo pipefail
cd "$(dirname "$0")/.."
COMP=name-that-llm
mkdir -p data/raw
kaggle competitions download -c "$COMP" -p data/raw
unzip -o -q "data/raw/$COMP.zip" -d data/raw
rm -f "data/raw/$COMP.zip"
ls -la data/raw
