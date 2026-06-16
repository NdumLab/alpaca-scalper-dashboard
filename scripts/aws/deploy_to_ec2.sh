#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 user@host [remote_dir]" >&2
  echo "Example: $0 ubuntu@203.0.113.10 ~/alpaca-scalper" >&2
  exit 2
fi

remote="${1}"
remote_dir="${2:-~/alpaca-scalper}"
ssh_key="${SSH_KEY:-}"

if [[ -z "${ssh_key}" && -f "${HOME}/builder.pem" ]]; then
  ssh_key="${HOME}/builder.pem"
fi

ssh_cmd=(ssh -F /dev/null -o StrictHostKeyChecking=accept-new)
rsync_ssh=(ssh -F /dev/null -o StrictHostKeyChecking=accept-new)

if [[ -n "${ssh_key}" ]]; then
  if [[ ! -f "${ssh_key}" ]]; then
    echo "SSH key not found: ${ssh_key}" >&2
    exit 1
  fi
  chmod 600 "${ssh_key}"
  ssh_cmd+=(-i "${ssh_key}" -o IdentitiesOnly=yes)
  rsync_ssh+=(-i "${ssh_key}" -o IdentitiesOnly=yes)
fi

if [[ ! -f docker-compose.yml || ! -f Dockerfile || ! -f main.py ]]; then
  echo "Run this script from the alpaca-scalper repository root." >&2
  exit 1
fi

python3 runtime_safety_check.py

"${ssh_cmd[@]}" "${remote}" "mkdir -p ${remote_dir}"

rsync -az --delete \
  -e "$(printf '%q ' "${rsync_ssh[@]}")" \
  --exclude '.git/' \
  --exclude '.env' \
  --exclude '.venv/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  --exclude '*.pyo' \
  --exclude '*.pyd' \
  --exclude '.pytest_cache/' \
  --exclude '.config.yaml.swp' \
  --exclude 'logs/' \
  --exclude 'results/' \
  --exclude 'runtime/' \
  --exclude 'bot.log' \
  --exclude 'bot_state.json' \
  --exclude 'trade_journal.csv' \
  --exclude 'trades.csv' \
  --exclude 'optimizer_events.pkl' \
  --exclude '*.zip' \
  --exclude '*.tar.gz' \
  ./ "${remote}:${remote_dir}/"

"${ssh_cmd[@]}" "${remote}" "cd ${remote_dir} && mkdir -p logs results runtime && chmod +x scripts/aws/*.sh"

cat <<EOF
Deploy complete.

Next on the instance:
  cd ${remote_dir}
  cp .env.example .env   # first deploy only, then edit keys
  docker compose up --build -d alpaca-bot dashboard
  docker compose ps

Dashboard tunnel from local machine:
  ssh${ssh_key:+ -i ${ssh_key} -o IdentitiesOnly=yes} -L 8081:127.0.0.1:8081 ${remote}
EOF
