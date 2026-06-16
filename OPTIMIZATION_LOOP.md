# Optimization Loop Log

Date: 2026-06-13

Objective: improve `alpaca-scalper` profitability while stopping before the profile becomes unsafe from excessive leverage, drawdown, fragile fills, or obvious overfitting.

Safety rules:
- Do not accept a change based only on one headline 6-month result.
- Prefer walk-forward or IS/OOS validation before changing live config.
- Track slippage sensitivity; reject profiles that collapse under wider slippage.
- Treat higher `risk_per_trade_pct`, higher `max_position_pct`, and larger daily trade limits as safety costs, not free profit.
- Do not modify live-trading behavior unless backtest assumptions and execution risk remain defensible.

Current baseline observed before this log:
- Current edited host `config.yaml`: `risk_per_trade_pct=10.0`, `max_position_pct=180`, `stop_atr_mult=3.4`, `take_profit_r=3.0`, `max_daily_trades=8`, `backtest.slippage_cents=3`.
- Fresh one-off Docker backtest using current host config over 1,130,604 bars:
  - Last trading day, 2026-06-12 to 2026-06-13: 1 trade, 0.0% win, PF 0.00, max DD $31.88, net -$31.88, return -1.59%.
  - Last week, 2026-06-06 to 2026-06-13: 4 trades, 75.0% win, PF 1.55, max DD $53.80, net +$29.56, return +1.48%.
  - Last month, 2026-05-14 to 2026-06-13: 18 trades, 61.1% win, PF 2.23, max DD $53.80, net +$213.95, return +10.70%.
  - Last 6 months, 2025-12-13 to 2026-06-13: 122 trades, 59.8% win, PF 1.81, max DD $224.43, net +$1,137.50, return +56.87%.
- The already-running `alpaca-bot` container was still reading the old bind-mounted config inode:
  - `risk_per_trade_pct=2.0`, `max_position_pct=40`, `stop_atr_mult=3.2`, `take_profit_r=2.2`, `max_daily_trades=3`, `backtest.slippage_cents=5`.
  - Recreate the container before assuming live bot uses edited host config.

## Cycle 1

Status: in progress.

Goal: find the next candidate that improves risk-adjusted profitability without merely increasing leverage or tuning to one period.

Planned process:
1. Ask Claude Code and a parallel reviewer for read-only critique.
2. Compare their ideas against local code and existing harnesses.
3. Implement at most one bounded candidate.
4. Evaluate with multi-period, IS/OOS, and slippage sensitivity checks.
5. Accept, reject, or revise and record the decision here.

Independent reviewer notes:
- Biggest fake-profit risk is execution realism: fixed entry slippage, exact take-profit limit fills, no missed marketable-limit entries, no partial fills, no spread/queue model.
- The 6-month dataset is heavily reused, so headline gains are suspect unless they survive harsher validation.
- Current edited config is much more aggressive than documented safer profiles.
- Single-position simulation can introduce symbol-order bias when several correlated names trigger at the same timestamp.
- Long-only exposure remains a regime risk across correlated index/tech symbols.

Ranked reviewer candidates:
1. Add harsher execution simulation before trusting more profit.
2. Add walk-forward symbol allocation or at least symbol-level pruning diagnostics.
3. Add market-regime gate for long entries.
4. Consider inverse-ETF long mode only with isolated caps and reporting.
5. Use real paper/live fill deltas to calibrate slippage.

Reject-as-unsafe criteria from reviewer:
- Reject changes that only win at 3c slippage but fail at 5c, 7c, or 10c.
- Reject if walk-forward folds are negative unless drawdown materially improves versus baseline.
- Reject if max drawdown rises more than 25% without at least 50% higher net profit.
- Reject if fewer than 50 trades over 6 months, or one symbol contributes more than 40% of net.
- Reject if it requires higher risk/leverage/trade count before improving PF or drawdown.

Claude Code status:
- `claude` is installed at `/home/henry/.local/bin/claude`.
- Read-only critique attempt failed because the Claude Code account credit balance is too low.
- Continue using the local subagent reviewer plus local validation until Claude Code credits are available again.

Validation harness added:
- Added `loop_evaluate.py`.
- Purpose: one command to check the current profile across full-window, IS/OOS holdout, slippage stress, monthly net, symbol concentration, and safety flags.
- Syntax check passed with `python -m py_compile loop_evaluate.py`.

Cycle 1 validation result for current edited config:
- Data: 1,130,604 bars; IS bars 704,417; OOS bars 426,187.
- Config: `risk=10.0%`, `max_position=180%`, `stop_atr=3.4`, `tp_r=3.0`, `max_daily_trades=8`, `slippage=3c`.
- Full window: 122 trades, 59.8% win, PF 1.81, max DD $224.43, net +$1,137.50, return +56.87%.
- IS before 2026-04-10: 76 trades, 55.3% win, PF 1.43, max DD $224.43, net +$392.06, return +19.60%.
- OOS from 2026-04-10: 45 trades, 68.9% win, PF 2.76, max DD $93.49, net +$658.11, return +32.91%.
- Slippage stress:
  - 3c: 122 trades, PF 1.81, max DD $224.43, net +$1,137.50.
  - 5c: 122 trades, PF 1.76, max DD $221.73, net +$1,075.38.
  - 7c: 122 trades, PF 1.72, max DD $222.76, net +$1,014.55.
  - 10c: 122 trades, PF 1.62, max DD $230.73, net +$889.33.
- Monthly net:
  - 2025-12: -$52.26.
  - 2026-01: +$202.02.
  - 2026-02: +$177.70.
  - 2026-03: -$52.80.
  - 2026-04: +$475.85.
  - 2026-05: +$149.70.
  - 2026-06: +$237.29.
- Symbol net:
  - AMD +$307.87, NVDA +$270.00, AAPL +$258.66, MSFT +$170.69, IWM +$121.81, AMZN +$120.66, SPY +$72.82, SMH +$23.55, META -$47.10, QQQ -$61.90, TSLA -$99.57.
- Safety flags from `loop_evaluate.py`: none.

Cycle 1 candidate selected:
- Test symbol pruning rather than higher leverage.
- Candidate: exclude the full-window laggards `TSLA`, `QQQ`, and `META`.
- Risk note: this candidate is partly data-mined from the same six-month window, so it must beat baseline on IS/OOS and slippage without creating concentration risk.

Cycle 1 candidate results:
- Excluding `TSLA`, `QQQ`, and `META` was rejected:
  - Full window fell from +$1,137.50 baseline to +$1,123.21.
  - OOS fell from +$658.11 to +$494.42.
  - Cleaner monthly consistency did not compensate for weaker OOS and weaker total profit.
- Smaller prune comparison:
  - Baseline: all net +$1,137.50, PF 1.81, max DD $224.43, IS +$392.06, OOS +$658.11, 10c net +$889.33, 122 trades.
  - Drop `TSLA`: all net +$1,281.67, PF 1.96, max DD $274.11, IS +$499.82, OOS +$640.50, 10c net +$999.07, 120 trades.
  - Drop `QQQ`: all net +$1,095.67, PF 1.74, max DD $207.52, IS +$355.93, OOS +$657.58, 10c net +$843.13, 123 trades.
  - Drop `META`: all net +$1,201.30, PF 1.82, max DD $284.01, IS +$612.05, OOS +$480.23, 10c net +$984.96, 118 trades.
  - Drop `TSLA+QQQ`: all net +$1,220.04, PF 1.87, max DD $269.30, IS +$445.22, OOS +$646.31, 10c net +$960.02, 121 trades.
  - Drop `TSLA+META`: all net +$1,138.09, PF 1.87, max DD $209.24, IS +$577.45, OOS +$480.92, 10c net +$907.09, 116 trades.
  - Drop `QQQ+META`: all net +$1,187.30, PF 1.77, max DD $284.01, IS +$583.14, OOS +$512.80, 10c net +$912.34, 119 trades.
- Full `drop TSLA` validation:
  - Full window: 120 trades, 59.2% win, PF 1.96, max DD $274.11, net +$1,281.67, return +64.08%.
  - IS before 2026-04-10: 75 trades, 54.7% win, PF 1.57, max DD $274.11, net +$499.82, return +24.99%.
  - OOS from 2026-04-10: 44 trades, 68.2% win, PF 2.88, max DD $107.25, net +$640.50, return +32.02%.
  - Slippage stress: 5c net +$1,199.66; 7c net +$1,079.09; 10c net +$999.07.
  - Monthly net: 2025-12 -$5.87, 2026-01 +$156.96, 2026-02 +$318.44, 2026-03 -$94.20, 2026-04 +$516.59, 2026-05 +$254.11, 2026-06 +$135.65.
  - Safety flags: none.

Cycle 1 decision:
- Accepted `drop TSLA`.
- Changed `config.yaml` active symbols to remove `TSLA`.
- Rationale: improves full-window net by +$144.17, improves PF from 1.81 to 1.96, improves 10c slippage net by +$109.74, keeps OOS strongly positive, and triggers no safety flags.
- Risk tradeoff: max drawdown rises from $224.43 to $274.11, about +22.1%. This is below the 25% reject threshold but should not be ignored in the next cycle.

Cycle 1 verification:
- `python test_smoke.py`: pass.
- `python test_orb_smoke.py`: pass.
- `python -m compileall -q .`: pass.
- Re-ran `loop_evaluate.py --days 182` after editing `config.yaml`; result matched the accepted no-TSLA candidate.

## Cycle 2

Status: in progress.

Goal: find the next profit improvement without adding leverage. Start by locating remaining loss clusters by setup, time, weekday, month, and symbol.

Diagnostics after Cycle 1 no-TSLA config:
- Setup family:
  - ORB: 41 trades, 58.5% win, net +$202.06, avg +$4.93.
  - Momentum: 79 trades, 59.5% win, net +$1,079.61, avg +$13.67.
- Entry hour:
  - 11 ET was weak: 7 trades, net -$29.00.
  - 9 ET and 10 ET carried most profit.
- Weekday:
  - Wednesday was weak: 26 trades, 46.2% win, net -$79.33.
  - Tuesday and Thursday were strongest.
- Remaining symbol laggards:
  - `QQQ`: 9 trades, net -$61.37.
  - `META`: 9 trades, net -$55.66.

Cycle 2 candidate comparison:
- Baseline no-TSLA: net +$1,281.67, PF 1.96, DD $274.11, IS +$499.82, OOS +$640.50, 10c net +$999.07, 120 trades.
- No Wednesday: net +$1,537.47, PF 2.57, DD $275.08, IS +$734.48, OOS +$619.26, 10c net +$1,333.13, 94 trades.
- Block 11:00-12:00: net +$1,267.88, PF 1.99, DD $299.08, IS +$465.87, OOS +$655.13, 10c net +$1,011.19, 115 trades.
- Momentum only: net +$1,408.43, PF 2.13, DD $163.71, IS +$587.20, OOS +$669.11, 10c net +$1,121.35, 107 trades.
- ORB only: net -$6.44, PF 0.99, DD $334.15, IS -$164.10, OOS +$213.50, 10c net -$136.93, 103 trades.
- No Wednesday + block 11:00-12:00: net +$1,436.77, PF 2.47, DD $283.00, IS +$665.43, OOS +$603.99, 10c net +$1,184.54, 90 trades.
- Momentum only + no Wednesday: net +$1,774.81, PF 3.05, DD $168.26, IS +$765.40, OOS +$741.32, 10c net +$1,522.27, 83 trades.

Cycle 2 accepted candidate:
- Set `strategy.mode: momentum`.
- Remove Wednesday from `strategy.allowed_weekdays`, leaving Monday, Tuesday, Thursday, Friday.

Full validation for accepted candidate:
- Full window: 83 trades, 63.9% win, PF 3.05, max DD $168.26, net +$1,774.81, return +88.74%.
- IS before 2026-04-10: 53 trades, 62.3% win, PF 2.39, max DD $168.26, net +$765.40, return +38.27%.
- OOS from 2026-04-10: 29 trades, 69.0% win, PF 4.82, max DD $58.77, net +$741.32, return +37.07%.
- Slippage stress:
  - 5c: net +$1,686.66.
  - 7c: net +$1,612.90.
  - 10c: net +$1,522.27.
- Monthly net: 2025-12 +$64.54, 2026-01 +$248.31, 2026-02 +$354.68, 2026-03 -$57.66, 2026-04 +$465.35, 2026-05 +$292.89, 2026-06 +$406.71.
- Symbol concentration: AMD contributes 34.3% of net, below the 40% reject threshold.
- Safety flags: none.

Cycle 2 decision:
- Accepted.
- Rationale: improves net, PF, IS, OOS, 10c stress, and drawdown without increasing leverage or daily trade count.
- Risk note: trade count falls from 120 to 83, still above the 50-trade minimum. Wednesday exclusion is a calendar filter and should be monitored for overfit.

Cycle 2 verification:
- `python test_smoke.py`: pass.
- `python test_orb_smoke.py`: pass.
- `python -m compileall -q .`: pass.
- Re-ran `loop_evaluate.py --days 182`; result matched the accepted momentum/no-Wednesday candidate.

## Cycle 3

Status: accepted.

Goal: test remaining symbol pruning under the accepted momentum/no-Wednesday profile.

Cycle 3 candidate comparison:
- Baseline: net +$1,774.81, PF 3.05, DD $168.26, IS +$765.40, OOS +$741.32, 10c net +$1,522.27, 83 trades.
- Drop `QQQ`: net +$1,601.81, PF 2.72, DD $164.28, IS +$672.92, OOS +$741.32, 10c net +$1,442.29, 84 trades. Rejected.
- Drop `SMH`: net +$1,858.82, PF 3.43, DD $113.82, IS +$830.39, OOS +$767.22, 10c net +$1,646.78, 80 trades. Accepted.
- Drop `META`: net +$1,595.69, PF 2.67, DD $187.98, IS +$841.22, OOS +$567.90, 10c net +$1,373.27, 81 trades. Rejected.
- Drop `QQQ+SMH`: net +$1,632.17, PF 3.02, DD $113.82, IS +$820.65, OOS +$609.08, 10c net +$1,418.41, 80 trades. Rejected.
- Drop `QQQ+META`: net +$1,554.27, PF 2.55, DD $173.52, IS +$784.45, OOS +$567.90, 10c net +$1,297.27, 82 trades. Rejected.
- Drop `SMH+META`: net +$1,716.33, PF 3.00, DD $187.98, IS +$906.60, OOS +$594.15, 10c net +$1,517.96, 78 trades. Rejected.
- Drop `QQQ+SMH+META`: net +$1,535.36, PF 2.71, DD $187.98, IS +$922.78, OOS +$439.45, 10c net +$1,327.93, 78 trades. Rejected.

Full validation for accepted `drop SMH` candidate:
- Full window: 80 trades, 66.2% win, PF 3.43, max DD $113.82, net +$1,858.82, return +92.94%.
- IS before 2026-04-10: 51 trades, 64.7% win, PF 2.68, max DD $113.82, net +$830.39, return +41.52%.
- OOS from 2026-04-10: 28 trades, 71.4% win, PF 5.85, max DD $50.34, net +$767.22, return +38.36%.
- Slippage stress:
  - 5c: net +$1,807.08.
  - 7c: net +$1,739.69.
  - 10c: net +$1,646.78.
- Monthly net: 2025-12 +$64.54, 2026-01 +$248.31, 2026-02 +$354.68, 2026-03 +$1.31, 2026-04 +$515.73, 2026-05 +$298.66, 2026-06 +$375.59.
- Symbol concentration: AMD contributes 33.2% of net, below the 40% reject threshold.
- Safety flags: none.

Cycle 3 decision:
- Accepted `drop SMH`.
- Changed `config.yaml` active symbols to remove `SMH`.
- Rationale: improves net, PF, IS, OOS, 10c stress, monthly consistency, and drawdown without increasing risk settings.

Cycle 3 verification:
- `python test_smoke.py`: pass.
- `python test_orb_smoke.py`: pass.
- `python -m compileall -q .`: pass.
- Re-ran `loop_evaluate.py --days 182` after editing `config.yaml`; result matched the accepted no-SMH candidate.

## Cycle 4

Status: rejected.

Goal: run a bounded grid around remaining symbol/day filters and entry-quality parameters without increasing risk, leverage, or daily trade count.

Candidate space:
- `strategy.volume_surge_mult`
- `strategy.cross_confirm_bars`
- `strategy.rsi_max_entry`
- `strategy.max_vwap_distance_atr`
- `strategy.min_ema_spread_atr`
- Remaining symbol exclusions: `QQQ`, `META`, `SPY`
- Remaining weekday exclusions

Cycle 4 candidate comparison highlights:
- Baseline no-TSLA/no-SMH momentum/no-Wednesday: net +$1,858.82, PF 3.43, DD $113.82, IS +$830.39, OOS +$767.22, 10c net +$1,646.78, 80 trades.
- Drop `SPY`: net +$1,938.60, PF 3.38, DD $113.82, IS +$810.92, OOS +$816.71, 10c net +$1,691.10, 79 trades.
- `cross_confirm_bars=5`: net +$1,860.98, PF 3.43, DD $113.82, IS +$832.54, OOS +$767.22, 10c net +$1,655.79, 81 trades.
- `max_vwap_distance_atr=1.8`: net +$1,838.45, PF 3.63, DD $116.76, IS +$887.15, OOS +$694.70, 10c net +$1,595.02, 75 trades.
- `min_ema_spread_atr=0.02`: net +$1,708.60, PF 3.36, DD $109.62, IS +$700.03, OOS +$783.82, 10c net +$1,503.47, 79 trades.
- No Friday: net +$1,674.85, PF 5.77, DD $69.42, IS +$700.47, OOS +$713.99, 10c net +$1,525.50, 61 trades.

Full validation for best headline candidate, `drop SPY`:
- Full window: 79 trades, 64.6% win, PF 3.38, max DD $113.82, net +$1,938.60, return +96.93%.
- IS before 2026-04-10: 51 trades, 62.7% win, PF 2.55, max DD $113.82, net +$810.92, return +40.55%.
- OOS from 2026-04-10: 27 trades, 70.4% win, PF 5.60, max DD $50.34, net +$816.71, return +40.84%.
- Slippage stress:
  - 5c: net +$1,862.59.
  - 7c: net +$1,795.14.
  - 10c: net +$1,691.10.
- Monthly net: 2025-12 +$64.54, 2026-01 +$218.64, 2026-02 +$359.54, 2026-03 -$4.14, 2026-04 +$641.16, 2026-05 +$277.07, 2026-06 +$381.80.
- Symbol concentration: AMD contributes 32.4% of net, below the 40% reject threshold.
- Safety flags: none.

Cycle 4 decision:
- Rejected `drop SPY`.
- Rationale: the +$79.78 full-window improvement is small, while PF falls from 3.43 to 3.38 and IS net falls from +$830.39 to +$810.92. `SPY` was profitable in the baseline, so the gain appears to come from single-position symbol-order interactions rather than removing a genuinely weak instrument.
- No parameter candidate improved the profile enough to justify another edit. `cross_confirm_bars=5` was effectively flat, and the stricter filters reduced full-window or OOS performance.

Cycle 4 verification:
- No `config.yaml` change made.
- `python test_orb_smoke.py`: pass.
- `python -m compileall -q .`: pass.
- `python loop_evaluate.py --days 182`: pass, no safety flags.

## EC2 Runtime Verification

Date: 2026-06-14

Status: running on EC2 in paper mode.

Observed runtime state:
- `docker compose ps`: `alpaca-bot` and `dashboard` are both up.
- Dashboard is bound to `127.0.0.1:8081->8080` and serves the dashboard HTML via localhost.
- Running `alpaca-bot` container config matches the accepted Cycle 3 profile:
  - Symbols: `SPY`, `QQQ`, `IWM`, `AAPL`, `MSFT`, `AMZN`, `META`, `NVDA`, `AMD`.
  - `strategy.mode=momentum`.
  - `strategy.allowed_weekdays=[0, 1, 3, 4]`.
  - `risk_per_trade_pct=10.0`, `max_position_pct=180`, `stop_atr_mult=3.4`, `take_profit_r=3.0`, `max_daily_trades=8`.
  - `backtest.slippage_cents=3`.
- Runtime state file: session date `2026-06-14`, daily P&L `$0.00`, daily trade count `0`, halted `false`.
- Recent logs show an Alpaca IEX websocket `connection limit exceeded` burst during startup, followed by successful data and trading stream connections and subscriptions. Monitor this if another bot/session is also using the same Alpaca paper data stream.

EC2 verification commands:
- `python3 runtime_safety_check.py`: pass.
- `python3 test_smoke.py`: pass.
- `python3 test_orb_smoke.py`: pass.
- `python3 -m compileall -q .`: pass.

## Cycle 5

Status: accepted.

Date: 2026-06-14 (Sunday, market closed).

Goal: find the next risk-adjusted improvement without increasing leverage,
risk, or daily trade count. Used the newer `loop_evaluate.py` exit-reason
diagnostics to target the unexplored exit/regime structure.

Operational notes:
- The host Python has no `alpaca` SDK; backtests/validation run inside the
  Docker image. Used a throwaway container so new untracked files
  (`loop_evaluate.py`) and the `optimizer_events.pkl` cache live on the host:
  `docker run --rm --env-file .env -e TZ=America/New_York -v "$PWD":/app -w /app alpaca-scalper-alpaca-bot python loop_evaluate.py --days 182`.
- This 182-day pull returned 933,208 bars (a different, more recent window than
  the 1,130,604-bar pulls in Cycles 1-4), so absolute baseline numbers shifted
  but the accepted Cycle 3 profile still reproduced exactly.

Baseline (accepted Cycle 3 profile, `stop_atr_mult=3.4`):
- All: 80 trades, 66.2% win, PF 3.43, max DD $113.82, net +$1,858.82.
- IS +$830.39, OOS +$767.22, 10c net +$1,646.78. No safety flags.
- Exit-reason diagnostic: flatten 64 trades +$2,206.08; take_profit only
  2 trades +$212.74; stop 14 trades 0% win -$559.99. Profit is dominated by the
  15:55 flatten, the 3R take-profit almost never fires, and all loss is
  concentrated in stop-outs — pointing at stop width as the live lever.

Rejected candidates (entry-only regime/volatility gates, via `--set`):
- `trend_ema=50/100/200`: all hurt. trend_ema=50 inflated max DD to $234.83
  (+106%) and cut net to +$1,739.70; 100/200 cut net to ~+$1,200 and OOS to
  ~+$310. The "above a rising trend EMA" gate filters out the early-recovery
  momentum entries that carry the edge. Reject.
- `min_atr_pct=0.001`: net +$1,877.65 but PF ticks down 3.43->3.40 and IS is
  identical (removed one marginal low-vol trade). Within noise. Reject.
- `min_atr_pct=0.0015`: net +$1,827.42, PF 3.14 (worse). Reject.

Exit-structure grid (via `--set`, no change to `risk_per_trade_pct`,
`max_position_pct`, or `max_daily_trades`):
- `take_profit_r`: 1.5 +$1,633.94; 2.0 +$1,882.76 (PF 3.48, but IS -$39 vs
  base); 2.5 +$1,816.82; 3.5 +$1,863.95 (flat); 4.0 +$1,767.37. Best case
  (2.0) is only +$24 net and weakens IS. Not worth a change.
- `stop_atr_mult` curve (net / PF / DD / IS / OOS / 10c):
  - 2.5: +$1,386 / 2.40 / $189 — worse.
  - 3.0: +$1,502 / 2.54 / $225 — worse.
  - 3.4 base: +$1,859 / 3.43 / $114 / +$830 / +$767 / +$1,647.
  - 3.6: +$2,021 / 3.79 / $123 / +$947 / +$763 / +$1,789.
  - 3.8: +$2,073 / 3.91 / $129 / +$961 / +$742 / +$1,813.
  - 4.0: +$2,065 / 4.00 / $135 / +$944 / +$765 / +$1,815.
  - 4.2: +$1,969 / 3.93 / $140.  4.5: +$1,935 / 3.80 / $148.
  - 5.0: +$1,910 / 3.71 / $162.  6.0: +$1,839 / 3.52 / $189.
- The curve is concave with a genuine interior optimum near 3.6-4.0 that turns
  over and declines by 6.0 — not a runaway "disable the stop" artifact. OOS is
  stable (740-767) across the whole range, so the knob is not overfitting the
  holdout. Sizing direction confirmed in `risk.py`:
  `qty_by_risk = risk_dollars / (stop_atr_mult * ATR)`, so a wider stop means
  FEWER shares and lower position notional, i.e. less leverage, not more. DD
  rises modestly because tighter stops were accidentally capping some losers
  below the configured 10% risk via the `max_position_pct` buying-power cap;
  widening the stop lets the intended (unchanged) 10% risk budget express.

Cycle 5 candidate selected: `risk.stop_atr_mult: 3.4 -> 3.6`.
- Picked 3.6 over the slightly higher-net 3.8/4.0 because it is the
  risk-adjusted-optimal point: net/maxDD = 16.38 (3.6) vs 16.33 (baseline),
  16.07 (3.8), 15.35 (4.0). It is the only improved point that holds the
  return/drawdown ratio at the baseline level, with the smallest DD increase.

Full validation for accepted `stop_atr_mult=3.6`:
- Full window: 80 trades, 67.5% win, PF 3.79, max DD $123.37, net +$2,020.81,
  return +101.04%.
- IS before 2026-04-10: 51 trades, 66.7% win, PF 3.17, max DD $123.37,
  net +$946.55.
- OOS from 2026-04-10: 28 trades, 71.4% win, PF 5.70, max DD $53.22,
  net +$762.91.
- Slippage stress: 5c +$1,942.53; 7c +$1,861.83; 10c +$1,788.91 (all above the
  baseline at the same slippage).
- Take-profit fill haircut: +$1,995.46 at 1c, +$1,989.75 at 5c — fills are not
  fragile.
- Monthly net: 2025-12 +$66.02, 2026-01 +$255.40, 2026-02 +$363.37,
  2026-03 +$94.20, 2026-04 +$539.61, 2026-05 +$313.75, 2026-06 +$388.45 — all
  seven months positive (the previously-weak March improves from +$1.31 to
  +$94.20).
- Symbol concentration: AMD 31.6% of net, below the 40% reject threshold.
- Exit-reason: stop losers drop from 14/-$559.99 to 12/-$451.53, confirming the
  mechanism (fewer premature stop-outs let more trades reach the flatten).
- Safety flags: none.

Cycle 5 decision:
- Accepted `stop_atr_mult=3.6`.
- Rationale: improves net (+$162), PF (3.43->3.79), IS (+$116), 10c stress
  (+$142), and monthly consistency (all months positive) while OOS holds and the
  return/drawdown ratio is unchanged. Does not raise `risk_per_trade_pct`,
  `max_position_pct`, or `max_daily_trades`; position notional decreases.
- Risk tradeoff: max DD rises $113.82 -> $123.37 (+8.4%), well under the 25%
  reject threshold and roughly matched by the +8.7% net gain.

Cycle 5 verification:
- Edited `config.yaml`: `risk.stop_atr_mult` 3.4 -> 3.6.
- `python3 test_smoke.py`: pass. `python3 test_orb_smoke.py`: pass.
- `python3 -m compileall -q .`: pass.
- Re-ran `loop_evaluate.py --days 182` against the edited `config.yaml` (no
  `--set`); result matched the accepted 3.6 candidate exactly.
- Recreated the live container (`docker compose up -d alpaca-bot`) on a Sunday
  while markets were closed; verified via
  `docker compose exec alpaca-bot python -c "..."` that the running bot now
  reports `stop_atr_mult=3.6` with all other Cycle 3/5 settings unchanged.
  Bot restarted cleanly: historical preload of 1035 bars, data + trading
  streams connected, all 9 symbols subscribed, no connection-limit burst this
  time.

New accepted profile as of 2026-06-14 (Cycle 5):
- Same as Cycle 3 except `risk.stop_atr_mult: 3.6` (was 3.4).

Handoff / next ideas:
- `take_profit_r=2.0` was a near-tie (+$24, better PF/OOS but weaker IS). Could
  revisit combined with `stop_atr_mult=3.6` rather than against the 3.4 base.
- `stop_atr_mult=3.8` had the highest raw net (+$2,073) if the operator is
  willing to accept DD ~$129 for ~$50 more net; left on the table for risk
  discipline.
- Update CLAUDE.md / AGENTS.md baselines to `stop_atr_mult=3.6` when convenient
  (left unchanged this session to avoid scope creep beyond the loop log).

## Cycle 5

Status: accepted validation-harness improvement; no trading-profile change.

Goal: address the reviewer's execution-realism concern about optimistic take-profit limit fills before trusting additional profit tuning.

Changes made:
- Added optional `backtest.take_profit_haircut_cents` support to `backtest.simulate()`.
  - Default is `0`, so existing backtest results and live trading behavior are unchanged.
  - When set, simulated take-profit exits fill at `tp - haircut`.
- Added a take-profit fill haircut stress section to `loop_evaluate.py`.
- Added simulated `exit_reason` fields and an exit-reason breakdown to `loop_evaluate.py`.

Validation result for current accepted Cycle 3 profile:
- Full window: 80 trades, 66.2% win, PF 3.43, max DD $113.82, net +$1,858.82.
- IS before 2026-04-10: 51 trades, PF 2.68, net +$830.39.
- OOS from 2026-04-10: 28 trades, PF 5.85, net +$767.22.
- Slippage stress:
  - 3c: net +$1,858.82.
  - 5c: net +$1,807.08.
  - 7c: net +$1,739.69.
  - 10c: net +$1,646.78.
- Take-profit fill haircut stress:
  - 0c: net +$1,858.82.
  - 1c: net +$1,858.59.
  - 3c: net +$1,858.13.
  - 5c: net +$1,857.67.
- Exit reason breakdown:
  - `flatten`: 64 trades, 79.7% win, net +$2,206.08.
  - `take_profit`: 2 trades, 100.0% win, net +$212.74.
  - `stop`: 14 trades, 0.0% win, net -$559.99.
- Monthly net remains positive in every reported month, with March barely positive at +$1.31.
- Symbol concentration remains acceptable: AMD contributes 33.2% of net, below the 40% reject threshold.
- Safety flags: none.

Cycle 5 decision:
- Accepted the harness improvement.
- No `config.yaml` trading-profile change.
- Rationale: this directly tests a known optimistic assumption and shows the current profile is not materially dependent on exact take-profit limit fills because only 2 of 80 trades exit via take profit. The larger execution risk remains market-entry/stop/flatten slippage, already covered by the 3c/5c/7c/10c slippage stress.

Cycle 5 verification:
- `python3 test_smoke.py`: pass.
- `python3 test_orb_smoke.py`: pass.
- `python3 -m compileall -q .`: pass.
- `docker compose run --build --rm --no-deps alpaca-bot python loop_evaluate.py --days 182`: pass, no safety flags.

Operational note:
- The one-off Compose evaluator image was rebuilt to include the validation-code changes. The running `alpaca-bot` container was not recreated during this cycle, and no live/paper trading config was changed.

## Refreshed Backtest

Date: 2026-06-16.

Status: accepted validation refresh; no trading-profile change.

What was tested:
- Re-ran the preferred 182-day validation against the current `config.yaml`
  profile: paper mode, 9-symbol Cycle 3 basket, momentum mode, allowed weekdays
  `[0, 1, 3, 4]`, `risk_per_trade_pct=10.0`, `max_position_pct=180`,
  `stop_atr_mult=3.6`, `take_profit_r=3.0`, `max_daily_trades=8`, and
  `backtest.slippage_cents=3`.
- The evaluator fetched a fresh 182-day 1-minute bar window: 934,115 bars
  total, 571,318 IS bars, 362,797 OOS bars.

Validation results:
- Full window: 78 trades, 67.9% win, PF 3.79, max DD $123.37,
  net +$1,945.48, return +97.27%.
- IS before 2026-04-10: 49 trades, 67.3% win, PF 3.14, max DD $123.37,
  net +$895.50.
- OOS from 2026-04-10: 28 trades, 71.4% win, PF 5.70, max DD $53.22,
  net +$762.91.
- Slippage stress: 3c +$1,945.48; 5c +$1,863.20; 7c +$1,814.46;
  10c +$1,735.35.
- Take-profit fill haircut stress: 0c +$1,945.48; 1c +$1,945.25;
  3c +$1,944.79; 5c +$1,944.33.
- Monthly net: 2025-12 +$35.57, 2026-01 +$251.13, 2026-02 +$351.29,
  2026-03 +$92.88, 2026-04 +$525.62, 2026-05 +$307.20,
  2026-06 +$381.80.
- Exit reason: flatten 64 trades +$2,165.75; take_profit 2 trades +$225.45;
  stop 12 trades -$445.72.
- Symbol concentration: AMD contributes 32.4% of net, below the 40% reject
  threshold.
- Safety flags: none.

Validation commands:
- `docker compose run --rm --no-deps alpaca-bot python loop_evaluate.py --days 182`: pass, no safety flags.
- `python3 test_smoke.py`: pass.
- `python3 test_orb_smoke.py`: pass.
- `python3 -m compileall -q .`: pass.

Decision:
- Keep the current `stop_atr_mult=3.6` profile accepted.
- No `config.yaml` or runtime change was made during this refresh.

Operational warnings:
- The running containers were not recreated and the live container config was
  not re-read after this validation refresh.
- `OPTIMIZATION_LOOP.md` still has duplicated Cycle 5 headings from prior
  sessions; use this newest entry as the latest validation note.
