# Alpaca Scalper Bot

Paper-trading scalper for Alpaca with ORB/momentum signals, VWAP/ATR context,
bracket orders, local risk controls, journaling, Docker Compose support, and a
lightweight browser dashboard.

The default configuration is paper trading only.

## Current Profile

Trading universe:

- SPY
- QQQ
- IWM
- AAPL
- MSFT
- AMZN
- META
- NVDA
- AMD
- TSLA
- SMH

Strategy defaults:

- 15-minute strategy bars from live 1-minute bars
- Ensemble mode: ORB plus momentum
- Historical warmup preload
- Long-only entries
- No new entries after 15:35 ET
- End-of-day flatten at 15:55 ET

Risk defaults:

```yaml
risk:
  risk_per_trade_pct: 2.0
  max_position_pct: 40
  stop_atr_mult: 3.2
  take_profit_r: 2.2
  max_daily_loss_pct: 2.0
  max_daily_trades: 3
  max_concurrent_positions: 1
  cooldown_minutes_after_loss: 10
```

## Setup

Create `.env` from the example and add Alpaca paper API keys:

```bash
cp .env.example .env
```

Required variables:

```bash
APCA_API_KEY_ID=your_paper_key_id
APCA_API_SECRET_KEY=your_paper_secret_key
```

For local Python use:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run Locally

Start the trading bot:

```bash
python main.py
```

Sync account status and recent Alpaca orders into the journal:

```bash
python bot_status.py
```

Start the dashboard:

```bash
python dashboard.py
```

Then open `http://localhost:8080`.

## Run With Docker Compose

Start the bot and dashboard:

```bash
docker compose up --build -d alpaca-bot dashboard
```

Dashboard URL:

```text
http://localhost:8081
```

Run the status/journal sync tool:

```bash
docker compose --profile tools run --rm bot-status
```

Runtime files are written under `runtime/` and are intentionally ignored by git.

## Dashboard Controls

The dashboard refuses to run against a live Alpaca config. It supports:

- Account, buying power, positions, orders, and P&L views
- Heartbeat/staleness display from the bot
- Pause and resume of new bot entries
- Restart request through the Compose restart policy
- Paper flatten action that cancels orders and closes positions

Pause/resume/restart use marker files in `runtime/`.

## Tests

Offline checks do not need Alpaca credentials:

```bash
python test_smoke.py
python test_orb_smoke.py
python -m compileall -q .
```

`test_smoke.py` validates the synthetic momentum signal path, slippage, and P&L
accounting. `test_orb_smoke.py` validates that ORB mode can produce a trade.

## Safety Notes

- `config.yaml` has `alpaca.paper: true` by default.
- `dashboard.py` refuses live mode.
- `bot_status.py` refuses live mode unless `--allow-live` is passed.
- `main.py` can run live if `config.yaml` is changed. Review risk settings and
  Alpaca account permissions before changing paper mode.
- Bracket exits are submitted server-side at Alpaca, but local risk controls only
  run while the bot process is healthy.

## Important Files

- `main.py`: live bot entrypoint
- `strategy.py`: signal logic
- `risk.py`: position sizing, daily limits, local state
- `execution.py`: Alpaca bracket order submission and flattening
- `backtest.py`: offline simulation
- `bot_status.py`: account/order status and journal sync
- `dashboard.py`: browser dashboard and controls
- `config.yaml`: default paper profile
