# Agent Instructions

This repository is the active Alpaca scalper workspace. The durable handoff
between Codex, Claude, and the operator is `OPTIMIZATION_LOOP.md`.

When asked to continue Alpaca work:

1. Read `OPTIMIZATION_LOOP.md` from the bottom up before making changes.
2. Treat the latest accepted cycle as the baseline. As of 2026-06-14, the
   accepted runtime profile is Cycle 3:
   - Paper mode.
   - Symbols: `SPY`, `QQQ`, `IWM`, `AAPL`, `MSFT`, `AMZN`, `META`, `NVDA`,
     `AMD`.
   - `strategy.mode: momentum`.
   - `strategy.allowed_weekdays: [0, 1, 3, 4]`.
   - `risk_per_trade_pct: 10.0`, `max_position_pct: 180`,
     `stop_atr_mult: 3.6`, `take_profit_r: 3.0`, `max_daily_trades: 8`.
   - `backtest.slippage_cents: 3`.
3. Keep Claude and Codex coordinated through `OPTIMIZATION_LOOP.md`. Before
   ending a session, append a concise handoff note with:
   - What was tested or changed.
   - Validation commands and results.
   - The current accepted/rejected decision.
   - Any operational warnings.
4. Do not accept a trading-profile change unless it survives the existing
   validation discipline: full window, IS/OOS, slippage stress, monthly
   consistency, symbol concentration, and safety flags.
5. Prefer `loop_evaluate.py --days 182` for profile validation. Avoid broad
   unbounded grids; use small, targeted candidate sets.
6. Do not increase leverage, risk, or daily trade count unless the operator
   explicitly asks and the change is separately justified in the log.
7. Before assuming the live bot is using a changed config, verify the running
   container config:

   ```bash
   docker compose exec alpaca-bot python -c "import yaml; cfg=yaml.safe_load(open('config.yaml')); print(cfg['symbols']); print(cfg['strategy']); print(cfg['risk']); print(cfg.get('backtest'))"
   ```

8. The EC2 deployment is the migration target. The old VirtualBox bot should
   stay stopped unless the operator intentionally rolls back.

Useful checks:

```bash
python3 runtime_safety_check.py
python3 test_smoke.py
python3 test_orb_smoke.py
python3 -m compileall -q .
docker compose ps
docker compose logs --tail=80 alpaca-bot
```
