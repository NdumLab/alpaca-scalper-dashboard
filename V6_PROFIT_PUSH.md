# v6 Profit Push

This version tries to improve profit potential without simply turning risk higher.

## What changed from v5

1. **Ensemble mode is now the default**
   - v5 mostly traded one idea: 15-minute momentum after EMA cross.
   - v6 can trade two ideas:
     - `ORB` = opening range breakout
     - `momentum` = EMA cross + VWAP + volume surge

2. **Expanded liquid universe**
   - v5: `SPY QQQ AAPL NVDA AMD TSLA`
   - v6: adds `IWM MSFT AMZN META SMH`
   - Why: more clean setups can appear without forcing one symbol to trade too much.

3. **More profit-focused default exits**
   - v5: `stop_atr_mult: 3.5`, `take_profit_r: 2.0`
   - v6: `stop_atr_mult: 3.2`, `take_profit_r: 2.2`
   - Why: slightly tighter risk and slightly larger reward target.

4. **Historical warmup preload for live mode**
   - v5 could start cold and miss most of the first day because 30 warmup bars × 15 minutes = 450 minutes.
   - v6 preloads recent historical bars before live streaming.

5. **Pending order protection**
   - v5 checked Alpaca open positions.
   - v6 also counts submitted bracket orders in memory.
   - Why: a pending order may not show as an open position yet, so v5 could accidentally submit more than one bracket.

6. **New profile research command**
   - `profit_research.py` compares v5-style momentum against v6 ensemble profiles on the same data pull.

## Main commands

Run the offline smoke test:

```bash
python test_smoke.py
```

Expected result:

```text
PASS — 1 trade(s) ...
```

Run v6 multi-period report:

```bash
python report.py
```

Expected result:

```text
Period          Trades   Win %     PF    Max DD    Net P&L   Return
Today              ...
Last week          ...
Last month         ...
Last 6 months      ...
```

Compare v5-style versus v6 profiles:

```bash
python profit_research.py --days 182 --slippage-cents 3
```

Expected result:

```text
Profile                 Trades   Win %      PF     Max DD     Net P&L    Return
v5-style momentum          ...
v6 ensemble default        ...
v6 tighter ORB             ...
v6 bigger target           ...
v6 faster exits            ...
```

Stress test with harsher slippage:

```bash
python profit_research.py --days 182 --slippage-cents 5
```

Expected: P&L should drop. If v6 still wins at 5 cents slippage, that is a stronger sign.

Run optimizer:

```bash
python optimize.py --days 182 --slippage-cents 3 --refresh
```

Expected: it prints top walk-forward candidates and writes:

```text
optimized_config.yaml
```

Apply best optimizer candidate:

```bash
cp optimized_config.yaml config.yaml
python report.py
```

## Files added

```text
profit_research.py       Compares v5-style and v6 profiles
config_v5_style.yaml     Previous v5-style baseline config
config_live_safe.yaml    Lower-risk config for future small live tests
V6_PROFIT_PUSH.md        This note
```

## Important note

This version is more aggressive as a research/paper profile. For live money, use `config_live_safe.yaml` first.

To switch to the safer live-test profile:

```bash
cp config_live_safe.yaml config.yaml
python report.py
```

Expected: profit will probably be smaller, but drawdown should be more survivable.
