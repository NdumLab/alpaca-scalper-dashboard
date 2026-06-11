# Profit Push Notes

## Changes made

- Fixed volume surge logic so the current bar is compared to the previous average volume.
- Added ATR, EMA-spread, VWAP-distance, weekday, and blocked-time filters.
- Added configurable entry slippage cap through `execution.entry_limit_offset_cents`.
- Fixed live P&L accounting to use actual Alpaca BUY fill price.
- Fixed session/date logic to use New York time.
- Added overnight session reset so the bot does not carry stale daily state.
- Added `optimize.py` for walk-forward parameter testing.
- Made offline smoke testing work without importing Alpaca SDK.

## Why these changes may improve profitability

The original strategy already had a thin simulated edge. The biggest practical improvements are not from forcing more trades. The better route is:

1. Remove low-quality trades.
2. Avoid bad fills.
3. Track actual fills correctly.
4. Re-optimize only with walk-forward validation.
5. Stress-test with higher slippage before trusting results.

## Commands to establish whether this version is actually better

Run the smoke test:

```bash
python test_smoke.py
```

Expected result: `PASS` with at least one synthetic trade.

Run a 60-day backtest:

```bash
python backtest.py --days 60
```

Expected result: a backtest summary with trades, win rate, profit factor, max drawdown, and net P&L.

Run a harsher slippage report:

```bash
python optimize.py --days 182 --slippage-cents 3
```

Expected result: the top walk-forward candidates and a new `optimized_config.yaml`.

Apply the best candidate and compare:

```bash
cp optimized_config.yaml config.yaml
python report.py
```

Expected result: the report table should show whether the candidate holds up across multiple periods.

## What not to do

Do not simply increase `risk_per_trade_pct` to make the backtest look better. That increases both profit and loss. A better candidate should improve profit factor, reduce max drawdown, or both.
