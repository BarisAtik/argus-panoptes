#!/usr/bin/env bash
# Run this yourself with your own Kaggle credentials, after accepting the rules on the website.
# The data is CC BY-NC 4.0, about 2.3 GB, and must never be committed. git ignores data/.
set -euo pipefail
cd "$(dirname "$0")/.."
COMP=nfl-big-data-bowl-2027
mkdir -p data/raw
kaggle competitions download -c "$COMP" -p data/raw
unzip -o -q "data/raw/$COMP.zip" -d data/raw
rm -f "data/raw/$COMP.zip"
PYTHONPATH=src python -m combinelink.schema data/raw
