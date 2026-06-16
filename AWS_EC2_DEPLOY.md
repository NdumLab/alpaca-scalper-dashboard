# AWS EC2 Deployment

This project runs cleanly on a small EC2 instance with Docker Compose. The
recommended setup keeps the dashboard bound to `localhost` on the instance and
uses an SSH tunnel when you need to view it.

## Instance

Recommended starting point:

- Ubuntu 24.04 LTS or Amazon Linux 2023
- `t3.small` or `t3.medium`
- 20 GB gp3 EBS volume
- Security group inbound rules:
  - SSH `22` from your IP only
  - No inbound rule for dashboard port `8081`

The bot uses outbound HTTPS to Alpaca APIs. No public inbound application port is
required.

## Bootstrap A Fresh Instance

SSH into the instance, then run:

```bash
curl -fsSL https://raw.githubusercontent.com/NdumLab/alpaca-scalper-dashboard/main/scripts/aws/bootstrap_ec2.sh | bash
```

Log out and back in after bootstrap so Docker group membership is applied.

If you are not using the GitHub copy of this repo yet, copy
`scripts/aws/bootstrap_ec2.sh` to the server and run it locally:

```bash
bash scripts/aws/bootstrap_ec2.sh
```

## Deploy From This Machine

From the project directory on your local machine:

```bash
./scripts/aws/deploy_to_ec2.sh ubuntu@EC2_PUBLIC_IP
```

If `~/builder.pem` exists, the deploy script uses it automatically. To use a
different key:

```bash
SSH_KEY=/path/to/key.pem ./scripts/aws/deploy_to_ec2.sh ubuntu@EC2_PUBLIC_IP
```

For Amazon Linux, the default SSH user is usually `ec2-user`:

```bash
./scripts/aws/deploy_to_ec2.sh ec2-user@EC2_PUBLIC_IP
```

The deploy script syncs source, config, and Compose files to
`~/alpaca-scalper`. It excludes `.env`, git metadata, caches, logs, runtime
state, and large generated research files.

## Add Secrets On The Instance

On the instance:

```bash
cd ~/alpaca-scalper
cp .env.example .env
nano .env
```

Set paper Alpaca keys:

```bash
APCA_API_KEY_ID=your_paper_key_id
APCA_API_SECRET_KEY=your_paper_secret_key
```

Never commit `.env` or copy live keys unless you have intentionally switched the
bot to live mode and reviewed risk controls.

## Start The Bot

On the instance:

```bash
cd ~/alpaca-scalper
python3 runtime_safety_check.py
docker compose up --build -d alpaca-bot dashboard
docker compose ps
```

Watch logs:

```bash
docker compose logs -f alpaca-bot
```

Run status/journal sync:

```bash
docker compose --profile tools run --rm bot-status
```

## Open The Dashboard

On your local machine:

```bash
ssh -i ~/builder.pem -o IdentitiesOnly=yes -L 8081:127.0.0.1:8081 ubuntu@EC2_PUBLIC_IP
```

Then open:

```text
http://localhost:8081
```

Use `ec2-user@EC2_PUBLIC_IP` instead of `ubuntu@...` for Amazon Linux.

## Update The Instance

From your local machine:

```bash
./scripts/aws/deploy_to_ec2.sh ubuntu@EC2_PUBLIC_IP
```

Then on the instance:

```bash
cd ~/alpaca-scalper
docker compose up --build -d alpaca-bot dashboard
```

## Stop Or Restart

```bash
cd ~/alpaca-scalper
docker compose stop alpaca-bot dashboard
docker compose restart alpaca-bot dashboard
```

## Notes

- `config.yaml` is synced because it is part of the bot behavior. Review it
  before each deployment.
- Runtime files live in `runtime/` on the instance and are not overwritten by
  deploys.
- The dashboard Compose port is bound to `127.0.0.1:8081`, so it is available
  through SSH tunneling but not exposed on the instance public interface.
