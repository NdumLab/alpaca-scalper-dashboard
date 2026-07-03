# Claude Instructions

This project coordinates with Codex through `OPTIMIZATION_LOOP.md`.

When asked to continue Alpaca work, first read `OPTIMIZATION_LOOP.md` from the
bottom up and use the latest accepted cycle as the baseline. Append any
material findings, tests, decisions, or handoff notes to that file before
ending the session.

Current accepted profile as of 2026-06-14:

- Paper mode.
- Symbols: `SPY`, `QQQ`, `IWM`, `AAPL`, `MSFT`, `AMZN`, `META`, `NVDA`, `AMD`.
- `strategy.mode: momentum`.
- `strategy.allowed_weekdays: [0, 1, 3, 4]`.
- `risk_per_trade_pct: 10.0`, `max_position_pct: 180`,
  `stop_atr_mult: 3.6`, `take_profit_r: 3.0`, `max_daily_trades: 8`.
- `backtest.slippage_cents: 3`.

Do not accept new trading-profile changes without validating full-window,
IS/OOS, slippage stress, monthly consistency, symbol concentration, and safety
flags. Prefer `python3 loop_evaluate.py --days 182` for validation. Avoid broad
unbounded grids and do not increase risk, leverage, or daily trade count unless
the operator explicitly asks for that risk.

Before assuming the running bot picked up a config change, verify the container
config with Docker.

Active host as of 2026-07-03: the Hostinger VPS (srv1753392) runs the bot,
dashboard, and weekly health-check timer. The EC2 host is stopped standby for
rollback (containers stopped, alpaca-weekly-check.timer disabled) — do not
restart it unless the operator intentionally rolls back. The old VirtualBox
bot stays stopped. Only one bot may run against the Alpaca account at a time.
