# Hostinger VPS Deployment

This bot runs on a Hostinger **VPS** (KVM plans) exactly like it runs on EC2:
Docker Compose, dashboard bound to `localhost`, SSH tunnel to view it. It will
NOT run on Hostinger shared or web-hosting plans (no Docker, no long-running
processes).

## Pick The VPS

- Plan: **KVM 2 (4 GB RAM)** or larger. The live bot is light, but the weekly
  health check replays a year of 1-minute bars and needs the memory; 1-2 GB
  plans will OOM the report.
- Location: a **US data center** (Alpaca's API and data feed are US-based).
- OS template: **Ubuntu 24.04 LTS** (plain) or Hostinger's
  "Ubuntu with Docker" template — the bootstrap script handles either.
- Disk: 50 GB is plenty (image ~320 MB, bar caches ~1.5 GB).
- Firewall: allow SSH `22` from your IP only. No inbound rule for `8081`;
  the dashboard stays on localhost and is reached via SSH tunnel.

## Get The Code Onto The VPS

Option A — clone from GitHub (recommended). On the VPS:

```bash
ssh-keygen -t ed25519 -C "hostinger-alpaca-scalper" -N ""
cat ~/.ssh/id_ed25519.pub
```

Add that public key on GitHub (deploy key with read access is enough:
repo Settings -> Deploy keys), then:

```bash
git clone git@github.com:NdumLab/alpaca-scalper-dashboard.git ~/alpaca-scalper
cd ~/alpaca-scalper
```

Option B — rsync from your current machine (same as the EC2 flow):

```bash
./scripts/aws/deploy_to_ec2.sh root@VPS_IP
```

## Bootstrap

On the VPS, from the repo directory:

```bash
bash scripts/hostinger/bootstrap_vps.sh
```

This installs Docker, builds the image, creates `.env` from the template,
creates `runtime/ logs/ results/`, and installs the
`alpaca-weekly-check` systemd timer (Sunday 18:00 ET: cache refresh +
forward-tracking report into `results/`). It does **not** start the bot.

Then put your **paper** Alpaca keys in `.env`:

```bash
nano .env    # APCA_API_KEY_ID / APCA_API_SECRET_KEY
```

## Bar Caches (for the weekly report; the live bot doesn't need them)

Copy from the old host (fast):

```bash
rsync -av ec2-user@EC2_IP:~/alpaca-scalper/period_events_{365,182}.pkl ~/alpaca-scalper/
```

Or rebuild from Alpaca (slow — fetches a year of 1-min bars):

```bash
docker compose run --rm --no-deps -v "$PWD:/app" alpaca-bot python period_breakdown.py 365
docker compose run --rm --no-deps -v "$PWD:/app" alpaca-bot python period_breakdown.py 182
```

## Cutover — One Bot At A Time

Two bots on the same Alpaca account place duplicate orders and corrupt the
trade log. Always stop the old host first:

```bash
# on the OLD host (EC2)
cd ~/alpaca-scalper && docker compose stop alpaca-bot dashboard
sudo systemctl disable --now alpaca-weekly-check.timer

# on the VPS
cd ~/alpaca-scalper
docker compose run --rm --no-deps -v "$PWD:/app" alpaca-bot python runtime_safety_check.py
docker compose up -d alpaca-bot dashboard
docker compose ps
docker compose logs -f alpaca-bot   # expect "subscribed to bars: [...]"
cat runtime/heartbeat.json          # status: running, mode: paper
```

Leave the old host stopped but intact for a week as rollback: if anything
misbehaves, `docker compose stop` on the VPS and `docker compose up -d` on EC2
puts you right back.

## Dashboard

From your local machine:

```bash
ssh -L 8081:127.0.0.1:8081 root@VPS_IP
```

Then open `http://localhost:8081`.

## Updating

```bash
cd ~/alpaca-scalper
git pull
docker compose up --build -d alpaca-bot dashboard
```

## Weekly Health Check

Installed by the bootstrap; verify with:

```bash
systemctl list-timers alpaca-weekly-check.timer
```

Reports land in `results/weekly_YYYY-MM-DD.txt`; any `WARN:` lines are copied
to `results/ALERTS_YYYY-MM-DD.txt` (stale heartbeat = bot down, negative
rolling 30-day sim = regime turn, live-vs-sim drift once paper trades exist).

## Notes

- `.env` never leaves the host and is git-ignored. Paper keys only, unless you
  have intentionally reviewed risk controls for live trading.
- `runtime/` holds bot state and the live trade log; it is not touched by
  `git pull` or the rsync deploy script.
- The repo's `CLAUDE.md`/`OPTIMIZATION_LOOP.md` conventions apply on the new
  host unchanged; update the "active host" note in `CLAUDE.md` after cutover.
