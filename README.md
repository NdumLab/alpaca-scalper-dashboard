
# Alpaca Scalper Bot — Paper + Dashboard Ready

A paper-trading scalper bot for Alpaca with ORB/VWAP logic, ATR-based risk management, historical warmup preload, trade journaling, Podman/Docker support, and a lightweight dashboard.

This version is configured for Alpaca paper trading by default.

## Current strategy profile

Current trading universe:

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

Current strategy settings:

- 15-minute bars
- ORB/VWAP strategy
- Historical warmup preload
- ATR-based stop
- 3R take profit
- Paper mode enabled by default

Current risk profile:

```yaml
risk:
  max_position_pct: 180
  take_profit_r: 3.0
  stop_atr_mult: 3.4
  max_daily_loss_pct: 5.0
  max_daily_trades: 8
  max_concurrent_positions: 1
