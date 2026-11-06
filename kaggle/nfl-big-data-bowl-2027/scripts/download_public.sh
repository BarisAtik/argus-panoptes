#!/usr/bin/env bash
# Public tables for the stand-in in reports/public_proxy_plan.md. Read the plan's status note first:
# nflverse gives no licence for this data, so whether to use it is your call. Stays out of git.
set -euo pipefail
base=https://github.com/nflverse/nflverse-data/releases/download
mkdir -p data/public
for f in combine/combine.csv nextgen_stats/ngs_receiving.csv.gz players/players.csv; do
  curl -fsSL -o "data/public/$(basename "$f")" "$base/$f"
done
ls -la data/public
