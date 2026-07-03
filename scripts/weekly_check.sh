#!/usr/bin/env bash
# Weekly health check: refresh bar caches, then run the forward-tracking
# report (liveness, rolling 30-day sim health, live-vs-sim drift).
# Output lands in results/weekly_YYYY-MM-DD.txt; WARN: lines are the alert
# surface. Wired to systemd timer alpaca-weekly-check.timer (Sun 18:00 ET).
set -uo pipefail
cd "$(dirname "$0")/.."
REPORT="results/weekly_$(date +%F).txt"
{
  echo "== cache refresh =="
  docker compose run --rm --no-deps -T -v "$PWD:/app" alpaca-bot \
    python scripts/refresh_cache.py 2>&1
  echo
  echo "== forward tracking =="
  docker compose run --rm --no-deps -T -v "$PWD:/app" alpaca-bot \
    python forward_tracking.py 2>&1
} | tee "$REPORT"

if grep -q "^WARN:" "$REPORT"; then
  # surface warnings where the operator will see them
  grep "^WARN:" "$REPORT" > "results/ALERTS_$(date +%F).txt"
  echo "Warnings written to results/ALERTS_$(date +%F).txt"
fi
# keep the last 12 weekly reports
ls -1t results/weekly_*.txt 2>/dev/null | tail -n +13 | xargs -r rm --
