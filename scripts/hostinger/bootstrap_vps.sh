#!/usr/bin/env bash
# One-shot setup for a fresh Hostinger VPS (or any Ubuntu/Debian box).
# Run from inside the cloned repo:  bash scripts/hostinger/bootstrap_vps.sh
#
# It installs Docker, builds the image, prepares .env and runtime dirs, and
# installs the weekly health-check timer. It deliberately does NOT start the
# bot: only one bot instance may run against the Alpaca account at a time,
# so the final cutover (stop old host -> start here) is a manual step.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_DIR"

echo "== 1/5 Docker =="
bash scripts/aws/bootstrap_ec2.sh   # OS-detecting installer (ubuntu/debian/amzn)

DOCKER="docker"
if ! docker info >/dev/null 2>&1; then
  DOCKER="sudo docker"   # group membership applies after re-login
fi

echo "== 2/5 Secrets =="
if [[ ! -f .env ]]; then
  cp .env.example .env
  chmod 600 .env
  echo "Created .env from template — YOU MUST EDIT IT with your Alpaca paper keys:"
  echo "    nano $REPO_DIR/.env"
  NEED_KEYS=1
else
  echo ".env already present."
  NEED_KEYS=0
fi

echo "== 3/5 Build image =="
$DOCKER compose build alpaca-bot

echo "== 4/5 Runtime dirs =="
mkdir -p runtime logs results

echo "== 5/5 Weekly health-check timer =="
bash scripts/install_weekly_timer.sh

cat << EOF

==========================================================================
Bootstrap complete. The bot is NOT started yet. Cutover checklist:
==========================================================================
 1. $( [[ $NEED_KEYS -eq 1 ]] && echo "Edit .env with your Alpaca paper keys (nano .env)" || echo ".env keys in place — verify they are the intended paper keys" )
 2. Bar caches (needed by the weekly report, not by the live bot):
      - copy period_events_*.pkl from the old host:
          rsync -av OLDHOST:~/alpaca-scalper/period_events_{365,182}.pkl .
      - or rebuild from Alpaca (slow, ~year of 1-min bars):
          $DOCKER compose run --rm --no-deps -v "\$PWD:/app" alpaca-bot \\
            python period_breakdown.py 365
 3. STOP the bot on the old host first (duplicate bots = duplicate orders):
          ssh OLDHOST 'cd ~/alpaca-scalper && docker compose stop alpaca-bot dashboard'
 4. Safety check, then start here:
          $DOCKER compose run --rm --no-deps -v "\$PWD:/app" alpaca-bot \\
            python runtime_safety_check.py
          $DOCKER compose up -d alpaca-bot dashboard
 5. Verify:
          $DOCKER compose logs -f alpaca-bot     # expect websocket subscribe lines
          cat runtime/heartbeat.json             # status: running, mode: paper
 6. Dashboard (from your laptop):
          ssh -L 8081:127.0.0.1:8081 USER@THIS_VPS_IP   ->  http://localhost:8081
==========================================================================
EOF
