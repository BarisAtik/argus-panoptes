#!/usr/bin/env bash
# Get the first real numbers on your own machine, in order of effort. Safe to rerun.
#
#   bash scripts/first_results.sh text    # CPU, minutes: DBRD audit + TF-IDF baseline
#   bash scripts/first_results.sh clip    # about 1 GB of COCO, then two CLIP models (GPU helps)
#   bash scripts/first_results.sh asr     # needs MDC_API_KEY and accepted dataset terms
#
# Output goes to runs/ (gitignored). Read report.md, then copy curated reports to results/.
set -euo pipefail
cd "$(dirname "$0")/.."

case "${1:-}" in
  text)
    python -m text_nl.cli --out runs/baseline --baseline-only
    ;;
  clip)
    python -m clip_search.coco --out runs/coco
    python -m clip_search.cli --coco runs/coco --out runs/clip \
      --model hf:openai/clip-vit-base-patch32 \
      --model openclip:xlm-roberta-base-ViT-B-32:laion5b_s13b_b90k
    ;;
  asr)
    : "${MDC_API_KEY:?Set MDC_API_KEY first: see asr_nl/README.md}"
    python -m asr_nl.fetch_common_voice --n 1000 --out runs/cv_nl
    python -m asr_nl.cli audit --manifest runs/cv_nl/manifest_test_1000.jsonl
    python -m asr_nl.cli run --config asr_nl/configs/laptop.yaml
    ;;
  *)
    sed -n '2,7p' "$0"
    exit 2
    ;;
esac
