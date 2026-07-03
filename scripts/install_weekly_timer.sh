#!/usr/bin/env bash
# Install the alpaca-weekly-check systemd service + timer on any host
# (EC2, Hostinger VPS, ...). Idempotent; safe to re-run after moving the repo.
# The timer runs scripts/weekly_check.sh every Sunday 18:00 ET.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_USER="${SUDO_USER:-$USER}"

sudo tee /etc/systemd/system/alpaca-weekly-check.service > /dev/null << EOF
[Unit]
Description=Alpaca scalper weekly health check (cache refresh + forward tracking)
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
User=${RUN_USER}
WorkingDirectory=${REPO_DIR}
ExecStart=${REPO_DIR}/scripts/weekly_check.sh
EOF

sudo tee /etc/systemd/system/alpaca-weekly-check.timer > /dev/null << 'EOF'
[Unit]
Description=Run alpaca weekly health check Sunday 18:00 ET

[Timer]
OnCalendar=Sun 18:00 America/New_York
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now alpaca-weekly-check.timer
systemctl list-timers alpaca-weekly-check.timer --no-pager
echo "Weekly check timer installed (user=${RUN_USER}, repo=${REPO_DIR})."
