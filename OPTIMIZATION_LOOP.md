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

## Cycle 6

Status: accepted infrastructure improvement; no trading-profile change.

Date: 2026-06-16.

Goal: start the event-aware trading app in the safest useful form: a planned
market-event risk layer that can block new entries around known high-impact
events, while keeping the current Cycle 5 technical profile unchanged until a
specific event calendar/blocking rule survives validation.

Plan:
1. Add a deterministic local planned-event schema before integrating external
   news/calendar APIs.
2. Wire event blocks into backtest and live entry gating.
3. Surface event-risk status on the dashboard and runtime safety check.
4. Keep `event_risk.enabled: false` by default so current trading behavior does
   not change.
5. Validate that disabled event risk reproduces the accepted Cycle 5 backtest,
   and that a synthetic high-impact event can suppress entries in an offline
   smoke test.

Changes made:
- Added `market_events.py` with:
  - `PlannedEvent` definitions.
  - `EventRisk.blocks_entry()` / `active_blocks()` for symbol-aware event
    windows.
  - `status()` / `upcoming()` helpers for dashboard/runtime reporting.
- Added `event_risk` config block to `config.yaml`:
  - `enabled: false`.
  - `block_new_entries: true`.
  - `min_impact: high`.
  - `default_pre_minutes: 30`.
  - `default_post_minutes: 15`.
  - empty `planned_events`.
- Wired `EventRisk` into:
  - `backtest.simulate()` before signal evaluation.
  - `main.ScalpBot.on_bar()` before live signal evaluation.
  - dashboard `/api/status` and the dashboard Market Events panel.
  - `runtime_safety_check.py` config summary.
- Added `test_event_risk.py`, which proves a synthetic FOMC-style block can
  suppress an otherwise valid synthetic momentum trade.
- Updated `AGENTS.md` and `CLAUDE.md` to reflect the accepted Cycle 5
  `stop_atr_mult=3.6` baseline.

Validation results:
- `python3 test_event_risk.py`: pass; planned event block suppressed entries
  with 110 blocked checks.
- `python3 test_smoke.py`: pass; 1 synthetic momentum trade, net +$30.10.
- `python3 test_orb_smoke.py`: pass; ORB synthetic trade fired, net +$126.14.
- `python3 -m compileall -q .`: pass.
- `python3 runtime_safety_check.py`: pass; paper mode true,
  `max_concurrent_positions=1`, `max_daily_loss_pct=5`, and
  `event_risk_enabled=False`.
- Host `python3 loop_evaluate.py --days 182` did not run because the host
  Python cannot unpickle the Docker-created Alpaca cache (`pydantic_core`
  missing). Used the supported Docker evaluator instead.
- `docker compose run --rm --no-deps alpaca-bot python loop_evaluate.py --days 182`:
  pass, no safety flags.
  - Bars: 934,115 total; 571,057 IS; 363,058 OOS.
  - Full window: 78 trades, 67.9% win, PF 3.79, max DD $123.37,
    net +$1,945.48, return +97.27%.
  - IS before 2026-04-10: 49 trades, 67.3% win, PF 3.14,
    net +$895.50.
  - OOS from 2026-04-10: 28 trades, 71.4% win, PF 5.70,
    net +$762.91.
  - Slippage stress: 3c +$1,945.48; 5c +$1,863.20; 7c +$1,814.46;
    10c +$1,735.35.
  - Take-profit haircut stress: 0c +$1,945.48; 1c +$1,945.25;
    3c +$1,944.79; 5c +$1,944.33.
  - Monthly net: 2025-12 +$35.57, 2026-01 +$251.13,
    2026-02 +$351.29, 2026-03 +$92.88, 2026-04 +$525.62,
    2026-05 +$307.20, 2026-06 +$381.80.
  - Symbol concentration: AMD 32.4% of net.
  - Safety flags: none.

Decision:
- Accept the event-risk infrastructure.
- Do not enable event blocking in `config.yaml` yet.
- No live container was recreated and no runtime trading behavior was changed.

Rationale:
- This creates the first layer of the event-aware app without introducing
  unvalidated predictive logic.
- The current accepted technical profile is unchanged when `event_risk.enabled`
  is false.
- Event blocks are deterministic and backtestable, so the next cycle can test
  specific FOMC/CPI/NFP/earnings windows before any runtime enablement.

Operational warnings / next ideas:
- External event/calendar ingestion is not implemented yet. Planned events must
  be entered locally under `event_risk.planned_events`.
- Do not treat news/personality NLP as a trading signal until there is a
  timestamped event dataset and OOS validation showing it improves the current
  profile.
- Next targeted cycle: add a small curated high-impact macro event calendar for
  the current 182-day window, then compare block windows such as 30/15,
  60/30, and flatten-before-event against the accepted Cycle 5 profile.

## Cycle 7

Status: rejected trading-profile change; accepted research/dashboard support.

Date: 2026-06-16.

Goal: test whether planned high-impact macro-event blocking improves the
accepted Cycle 5 technical profile before enabling `event_risk` for runtime.

Sources checked:
- Federal Reserve FOMC calendar page for 2026 policy-decision dates:
  `https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm`.
- BLS CPI release schedule:
  `https://www.bls.gov/schedule/news_release/cpi.htm`.
- BLS Employment Situation release schedule:
  `https://www.bls.gov/schedule/news_release/empsit.htm`.
- BLS PPI release schedule:
  `https://www.bls.gov/schedule/news_release/ppi.htm`.
- BEA release schedule checked for Personal Income and Outlays/PCE context:
  `https://www.bea.gov/news/schedule`.

Changes made:
- Added `macro_event_research.py`, a targeted harness that tests curated macro
  event-block profiles against the accepted baseline. It reuses the existing
  cached event loader and reports full-window, IS, OOS, 10c stress, and blocked
  entry checks.
- Added recent/upcoming planned macro events to `config.yaml` for dashboard
  visibility:
  - Employment Situation May 2026, 2026-06-05 08:30 ET.
  - CPI May 2026, 2026-06-10 08:30 ET.
  - PPI May 2026, 2026-06-11 08:30 ET.
  - FOMC decision June 2026, 2026-06-17 14:00 ET.
- Kept `event_risk.enabled: false`, so these rows do not affect trading.
- Updated `.dockerignore` to exclude generated research/cache files:
  `*.pkl`, `sweep_rev.json`, and `optimized_config.yaml`. This avoids sending
  large market-data caches into future Docker build contexts.

Macro-event research set:
- 22 events in the 182-day test scope:
  - BLS Employment Situation releases from January through June 2026.
  - BLS CPI releases from January through June 2026.
  - BLS PPI releases from January through June 2026.
  - FOMC policy decisions on 2026-01-28, 2026-03-18, and 2026-04-29.
- Tested only a small set of candidate block profiles:
  - all macro, 0 minutes before / 90 minutes after.
  - all macro, 0 / 120.
  - all macro, 30 / 120.
  - FOMC only, 60 / 120.
  - CPI + Employment Situation only, 0 / 120.

Validation command:
- `docker compose run --build --rm --no-deps alpaca-bot python macro_event_research.py`.

Results:
- Baseline: 80 trades, PF 3.79, max DD $123.37, net +$2,020.81,
  IS +$946.55, OOS +$762.91, 10c net +$1,788.91.
- `macro open 0/90`: 80 trades, PF 2.85, max DD $199.03,
  net +$1,710.27, delta -$310.54, IS +$902.70, OOS +$597.26,
  10c net +$1,522.70.
- `macro open 0/120`: 78 trades, PF 3.79, max DD $122.33,
  net +$1,933.22, delta -$87.59, IS +$852.01, OOS +$737.05,
  10c net +$1,718.07.
- `macro wide 30/120`: same result as 0/120; delta -$87.59.
- `FOMC 60/120 only`: unchanged from baseline; no trade-impacting edge.
- `CPI+NFP 0/120`: 78 trades, PF 3.87, max DD $123.37,
  net +$1,985.50, delta -$35.31, IS +$900.76, OOS +$736.24,
  10c net +$1,775.87.

Decision:
- Reject enabling planned macro-event blocking for the trading profile.
- Keep `event_risk.enabled: false`.
- Accept `macro_event_research.py` and the dashboard-visible planned-event
  rows as research/context support.

Rationale:
- Every event-blocking profile either reduced net/OOS/10c stress or had no
  trade-impacting effect.
- The worst candidate (`macro open 0/90`) materially increased max drawdown
  from $123.37 to $199.03 while cutting net by $310.54.
- The best near-miss (`CPI+NFP 0/120`) improved PF slightly but still reduced
  net, IS, OOS, and 10c stress. That is not enough to change a working runtime
  profile.

Verification:
- `python3 test_event_risk.py`: pass.
- `python3 test_smoke.py`: pass.
- `python3 test_orb_smoke.py`: pass.
- `python3 -m compileall -q .`: pass.

Operational warnings / next ideas:
- The event layer is useful as context and a dashboard alert, but it should not
  block trades automatically yet.
- The next event-related improvement should probably be observational first:
  tag trades by nearby macro events and inspect realized trade behavior, rather
  than blocking blindly.
- External news/personality tracking should remain alert-only until a
  timestamped dataset proves incremental OOS value.

## Cycle 8

Status: rejected trading-profile change; accepted disabled regime-strategy
infrastructure and research harness.

Date: 2026-06-16.

Goal: make the bot capable of being regime-aware, including different
strategies in different regimes, then test whether a simple SPY/QQQ regime map
improves the one-year weakness without destroying the accepted recent edge.

Changes made:
- Added `market_regime.py`.
  - Classifies broad-market state from configured symbols, default `SPY` and
    `QQQ`.
  - Current states: `bullish`, `mixed`, `bearish`.
  - Supports state-to-strategy mapping, e.g. `bullish: momentum`,
    `mixed: reversion`, `bearish: block`.
- Added `market_regime` config block to `config.yaml`, disabled by default:
  - `enabled: false`.
  - `symbols: [SPY, QQQ]`.
  - `min_symbols_passing: 2`.
  - default strategy map: bullish momentum, mixed block, bearish block.
- Updated `strategy.evaluate()` to accept an optional `mode_override`, so the
  regime layer can select `momentum`, `reversion`, `orb`, or `block` without
  mutating global strategy config.
- Wired market-regime decisions into:
  - `backtest.simulate()`.
  - `main.ScalpBot.on_bar()`.
  - dashboard Market Regime panel.
  - heartbeat/status payload.
  - `runtime_safety_check.py`.
- Added `test_market_regime.py` to prove the gate allows synthetic up-regime
  trades and blocks synthetic down-regime checks.
- Added `regime_research.py`, a targeted harness that compares disabled
  baseline against a small set of regime maps over 365 days and trailing
  182 days.

Research candidates:
- Baseline, market regime disabled.
- `2-index bull else block`: both SPY and QQQ must pass, otherwise block.
- `1-index bull else block`: at least one of SPY/QQQ must pass.
- `2-index mixed=reversion`: both pass -> momentum; mixed -> reversion;
  bearish -> block.
- `1-index mixed=reversion`: one pass -> momentum; bearish -> block.
- `2-index + vwap`: both pass and close above VWAP.
- `1-index + vwap`: one pass and close above VWAP.

Validation command:
- `docker compose run --rm --no-deps -v /home/ec2-user/alpaca-scalper:/app alpaca-bot python regime_research.py`.

365-day results:
- Baseline: 164 trades, PF 1.99, max DD $417.21, net +$1,475.40,
  10c net +$1,032.29.
- `2-index bull else block`: 112 trades, PF 1.17, max DD $300.67,
  net +$167.57, delta -$1,307.82, 10c net +$36.01.
- `1-index bull else block`: 133 trades, PF 1.24, max DD $276.25,
  net +$266.21, delta -$1,209.18, 10c net +$106.12.
- `2-index mixed=reversion`: 146 trades, PF 0.92, max DD $558.54,
  net -$119.73, delta -$1,595.13, 10c net -$266.31.
- `1-index mixed=reversion`: same as the one-index block profile in this
  candidate set, net +$266.21.
- `2-index + vwap`: 113 trades, PF 1.13, max DD $328.84,
  net +$132.42, delta -$1,342.97, 10c net -$17.11.
- `1-index + vwap`: 132 trades, PF 1.23, max DD $261.98,
  net +$255.82, delta -$1,219.58, 10c net +$90.47.

Trailing 182-day results:
- Baseline: 78 trades, PF 3.79, max DD $123.37, net +$1,945.48,
  IS +$895.50, OOS +$762.91, 10c net +$1,735.35.
- `2-index bull else block`: 60 trades, PF 1.88, max DD $147.15,
  net +$457.25, delta -$1,488.24, IS +$526.93, OOS -$32.27,
  10c net +$371.97.
- `1-index bull else block`: 68 trades, PF 1.87, max DD $91.69,
  net +$519.34, delta -$1,426.14, IS +$349.25, OOS +$174.64,
  10c net +$421.17.
- `2-index mixed=reversion`: 73 trades, PF 1.58, max DD $258.13,
  net +$482.76, delta -$1,462.72, IS +$443.10, OOS +$44.16,
  10c net +$368.01.
- `1-index mixed=reversion`: same as one-index block profile in this candidate
  set, net +$519.34.
- `2-index + vwap`: 62 trades, PF 1.88, max DD $152.10,
  net +$459.18, delta -$1,486.30, IS +$502.18, OOS -$34.76,
  10c net +$372.27.
- `1-index + vwap`: 68 trades, PF 1.80, max DD $91.69,
  net +$488.12, delta -$1,457.36, IS +$399.88, OOS +$106.42,
  10c net +$376.90.

Decision:
- Reject enabling the tested SPY/QQQ regime gates.
- Keep `market_regime.enabled: false`.
- Accept the disabled regime-strategy infrastructure and research harness for
  future experiments.

Rationale:
- The simple SPY/QQQ alignment gates reduce trade count and sometimes reduce
  drawdown, but they remove far too much profit.
- The 365-day drawdown improvement is not worth a $1,200-$1,300 net reduction.
- The trailing 182-day cross-check is decisive: every tested regime map damages
  the currently accepted edge, and the strict 2-index profiles turn OOS
  negative.
- Reversion in mixed regimes did not help. It increased drawdown on the
  one-year run and still cut recent-window net by more than $1,400.

Verification:
- `python3 test_market_regime.py`: pass.
- `python3 test_event_risk.py`: pass.
- `python3 test_smoke.py`: pass.
- `python3 test_orb_smoke.py`: pass.
- `python3 -m compileall -q .`: pass.

Operational warnings / next ideas:
- Do not enable `market_regime` in runtime based on these candidates.
- The problem is not that regime awareness is impossible; this broad SPY/QQQ
  trend gate is too blunt for the current intraday momentum edge.
- Better next research: trade-level tagging and diagnostics first. Compare the
  losing 2025-06/07/08/10/11 months against winning 2026 months by:
  entry time, symbol, setup reason, SPY/QQQ intraday slope, opening range
  structure, and realized volatility. Then test a narrower rule that targets
  the actual loss cluster instead of broad market alignment.

## Cycle 9

Status: rejected trading-profile change; accepted trade-diagnostics support.

Date: 2026-06-16.

Goal: follow the Cycle 8 recommendation by tagging trade-level behavior in the
known weak months before testing another rule.

Changes made:
- Added entry-context fields to `backtest.simulate()` trade records:
  `entry_time`, `entry_minute`, `entry_rsi`, `entry_atr_pct`,
  `entry_volume_ratio`, `entry_vwap_distance_atr`, and
  `entry_ema_spread_atr`.
- Added `trade_diagnostics.py`, an observational report that compares focus
  months against the rest of the sample by month, symbol, entry time, setup,
  exit reason, weekday, ATR%, volume surge, VWAP distance, and simple SPY/QQQ
  state at entry.
- No runtime config values were changed.

Validation command:
- `docker compose run --rm --no-deps -v /home/ec2-user/alpaca-scalper:/app alpaca-bot python trade_diagnostics.py --days 365`.

365-day diagnostic results:
- Headline baseline remained 164 trades, PF 1.99, max DD $417.21,
  net +$1,475.40.
- Focus months `2025-06`, `2025-07`, `2025-08`, `2025-10`, and `2025-11`:
  60 trades, PF 0.53, net -$337.49, average -$5.62/trade.
- Other months: 104 trades, PF 3.35, net +$1,812.89,
  average +$17.43/trade.
- Weak-month symbol clusters:
  - `AAPL`: 10 trades, PF 0.20, net -$129.26.
  - `AMZN`: 7 trades, PF 0.28, net -$95.33.
  - `AMD`: 2 trades, PF 0.00, net -$73.08.
- Weak-month time cluster:
  - `09:35-10:29`: 44 trades, PF 0.59, net -$219.44.
  - `10:30-11:59`: 10 trades, PF 0.14, net -$131.93.
- Weak-month context clusters:
  - Volume surge `>=5x`: 40 trades, PF 0.41, net -$293.47.
  - VWAP distance `1.5-1.99 ATR`: 13 trades, PF 0.11, net -$203.34.
  - Entry ATR `0.40-0.79%`: 9 trades, PF 0.20, net -$149.25.
- Simple SPY/QQQ state did not explain the loss cluster:
  - Focus-month trades with both proxies passing still lost -$146.81.
  - Other-month trades were profitable across 0, 1, and 2 proxy pass counts.

Decision:
- Reject a trading-profile change from this cycle. This was diagnostics only.
- Accept `trade_diagnostics.py` and the enriched simulated trade records as
  research support.

Rationale:
- The broad-market tags reinforce the Cycle 8 rejection: a simple SPY/QQQ gate
  is too blunt and would not isolate the weak months cleanly.
- The most promising future tests are narrow and conditional: focus on
  high-volume, extended-above-VWAP momentum entries in the known weak-month
  environment, especially AAPL/AMZN/AMD and the late-morning bucket.
- Any proposed rule still needs full validation through `loop_evaluate.py
  --days 182` plus one-year cross-checks before being accepted.

Verification:
- `python3 test_smoke.py`: pass.
- `python3 test_orb_smoke.py`: pass.
- `python3 test_event_risk.py`: pass.
- `python3 test_market_regime.py`: pass.
- `python3 runtime_safety_check.py`: pass.
- `python3 -m compileall -q .`: pass.

Operational warnings / next ideas:
- Do not enable `market_regime` or `event_risk` from this cycle.
- Do not prune AAPL/AMZN/AMD from runtime solely from the focus-month table;
  the non-focus months show AAPL +$159.93, AMZN +$147.92, and AMD +$571.39.
- Next targeted research should test small candidate guards around
  `entry_vwap_distance_atr`, `entry_volume_ratio`, and late-morning entries,
  then compare against both the 365-day weakness and the accepted 182-day edge.

## Cycle 10

Status: rejected trading-profile change; accepted targeted guard research
harness.

Date: 2026-06-16.

Goal: test the Cycle 9 loss-cluster hypotheses with a small set of candidate
entry guards: extended-above-VWAP entries, extreme volume-surge entries,
late-morning entries, and AAPL/AMZN/AMD-specific variants.

Changes made:
- Added a disabled-by-default `backtest.research_entry_guard` hook inside
  `backtest.simulate()`. It supports:
  - `max_vwap_distance_atr`.
  - `max_volume_ratio`.
  - `blocked_entry_minutes`.
  - optional symbol scoping.
- Added `guard_research.py`, a targeted harness that compares each candidate
  against baseline on:
  - 365-day one-year behavior.
  - known weak focus months: `2025-06`, `2025-07`, `2025-08`, `2025-10`,
    `2025-11`.
  - trailing 182-day accepted-edge window.
  - IS/OOS split using `2026-04-10`.
  - 10c slippage stress on the 182-day window.
- No runtime config values were changed.

Validation command:
- `docker compose run --rm --no-deps -v /home/ec2-user/alpaca-scalper:/app alpaca-bot python guard_research.py`.

Candidate results:
- Baseline:
  - 365 days: 164 trades, PF 1.99, net +$1,475.40, focus -$337.49,
    other +$1,812.89.
  - 182 days: 79 trades, PF 3.86, net +$1,994.24, OOS +$796.83,
    10c net +$1,778.91.
- `cap VWAP distance <= 1.5 ATR`:
  - 365 net +$991.50, delta -$483.90, focus -$172.35.
  - 182 net +$1,269.40, delta -$724.84, OOS +$416.66,
    10c +$1,123.54.
- `cap volume surge <= 5x`:
  - 365 net +$124.49, delta -$1,350.90, focus -$76.52.
  - 182 net +$147.37, delta -$1,846.88, OOS -$167.70,
    10c +$55.50.
- `block 10:30-11:59 entries`:
  - 365 net +$892.78, delta -$582.62, focus -$258.81.
  - 182 net +$1,325.37, delta -$668.87, OOS +$611.20,
    10c +$1,137.91.
- `cap VWAP <= 1.5 + volume <= 5x`:
  - 365 net +$208.12, delta -$1,267.28, focus -$172.91.
  - 182 net +$219.65, delta -$1,774.59, OOS -$36.44,
    10c +$159.19.
- `AAPL/AMZN/AMD cap VWAP+volume`:
  - 365 net +$1,095.90, delta -$379.49, focus -$151.23.
  - 182 net +$1,146.85, delta -$847.39, OOS +$441.79,
    10c +$1,001.07.
- `AAPL/AMZN/AMD cap+late block`:
  - 365 net +$921.32, delta -$554.08, focus -$160.95.
  - 182 net +$1,071.89, delta -$922.35, OOS +$481.69,
    10c +$930.35.

Decision:
- Reject all tested entry-guard candidates.
- Accept `guard_research.py` and the backtest-only research guard hook for
  future controlled experiments.

Rationale:
- Some guards improved the known weak-month loss cluster or reduced one-year
  max drawdown, but every candidate reduced total 365-day net and damaged the
  accepted trailing 182-day edge.
- The volume cap and combined guards are especially destructive: they remove
  too much of the current edge and turn OOS weak or negative.
- The symbol-scoped AAPL/AMZN/AMD guard is the closest diagnostic near-miss,
  but it still cuts 182-day net by $847.39 and 10c stress by $777.84, which is
  not acceptable.

Verification:
- `python3 -m compileall -q backtest.py guard_research.py`: pass.
- `python3 test_smoke.py`: pass.
- `python3 test_event_risk.py`: pass.
- `python3 test_orb_smoke.py`: pass.
- `python3 test_market_regime.py`: pass.
- `python3 runtime_safety_check.py`: pass.
- `python3 -m compileall -q .`: pass.

Operational warnings / next ideas:
- Do not enable any tested guard in runtime.
- Do not convert these diagnostics into symbol pruning or late-morning blocking
  without a candidate that preserves the 182-day edge.
- The evidence now says the simple observable loss clusters are descriptive,
  not directly tradable filters. The next useful research should likely move
  from hard filters to position/exposure shaping, such as smaller size on
  specific high-risk contexts, but that still must be tested under the same
  validation discipline before acceptance.

## Cycle 11

Status: rejected trading-profile change; accepted position-size research
harness.

Date: 2026-06-16.

Goal: test whether exposure shaping works better than hard entry blocking in
the high-risk contexts identified by Cycles 9 and 10.

Changes made:
- Added a disabled-by-default `backtest.research_position_scale` hook inside
  `backtest.simulate()`. It supports rule-based size multipliers scoped by:
  - symbols.
  - entry minute ranges.
  - minimum VWAP distance in ATR.
  - minimum volume ratio.
  - minimum ATR percent.
- Added `size_research.py`, a targeted harness that compares half-size and
  quarter-size variants against baseline on:
  - 365-day one-year behavior.
  - known weak focus months: `2025-06`, `2025-07`, `2025-08`, `2025-10`,
    `2025-11`.
  - trailing 182-day accepted-edge window.
  - IS/OOS split using `2026-04-10`.
  - 10c slippage stress on the 182-day window.
- No runtime config values were changed.

Validation command:
- `docker compose run --rm --no-deps -v /home/ec2-user/alpaca-scalper:/app alpaca-bot python size_research.py`.

Candidate results:
- Baseline:
  - 365 days: 164 trades, PF 1.99, net +$1,475.40, focus -$337.49,
    other +$1,812.89.
  - 182 days: 79 trades, PF 3.86, net +$1,994.24, OOS +$796.83,
    10c net +$1,778.91.
- `half size VWAP>=1.5 ATR`:
  - 365 net +$1,352.14, delta -$123.26, focus -$210.05.
  - 182 net +$1,722.57, delta -$271.67, OOS +$697.55,
    10c +$1,516.82.
- `half size volume>=5x`:
  - 365 net +$897.86, delta -$577.54, focus -$195.21.
  - 182 net +$1,180.68, delta -$813.57, OOS +$439.71,
    10c +$1,065.64.
- `half size late morning`:
  - 365 net +$1,369.66, delta -$105.73, focus -$277.14.
  - 182 net +$1,797.85, delta -$196.39, OOS +$749.05,
    10c +$1,574.73.
  - This was the only near-miss, but it still failed the strict screen.
- `half size VWAP>=1.5 or volume>=5`:
  - 365 net +$775.16, delta -$700.24, focus -$234.65.
  - 182 net +$1,117.70, delta -$876.54, OOS +$438.48,
    10c +$975.41.
- `half size focus symbols risky`:
  - 365 net +$1,281.11, delta -$194.29, focus -$228.68.
  - 182 net +$1,561.98, delta -$432.27, OOS +$581.14,
    10c +$1,410.12.
- `quarter size focus symbols risky`:
  - 365 net +$1,220.20, delta -$255.19, focus -$168.49.
  - 182 net +$1,370.16, delta -$624.08, OOS +$481.77,
    10c +$1,218.86.
- `half size focus risky+late`:
  - 365 net +$1,226.33, delta -$249.07, focus -$231.47.
  - 182 net +$1,498.98, delta -$495.26, OOS +$610.59,
    10c +$1,344.42.
- `half size high ATR>=0.40%`:
  - 365 net +$811.58, delta -$663.82, focus -$272.37.
  - 182 net +$1,177.55, delta -$816.69, OOS +$423.58,
    10c +$1,029.65.

Decision:
- Reject all tested position-size candidates as trading-profile changes.
- Accept `size_research.py` and the backtest-only size-scaling hook as
  research support.

Rationale:
- Size shaping performed better than hard blocking in the least invasive case:
  `half size late morning` reduced 365-day net by only $105.73 and reduced
  182-day net by $196.39, while keeping OOS positive.
- However, every candidate still reduced 365-day net, 182-day net, and 10c
  stress versus baseline. That fails the accepted validation discipline.
- The broader context scalers, especially volume and ATR scalers, remove too
  much of the current profitable edge.

Verification:
- `python3 -m compileall -q backtest.py size_research.py`: pass.
- `python3 test_smoke.py`: pass.
- `python3 test_event_risk.py`: pass.
- `python3 test_orb_smoke.py`: pass.
- `python3 test_market_regime.py`: pass.
- `python3 runtime_safety_check.py`: pass.
- `python3 -m compileall -q .`: pass.

Operational warnings / next ideas:
- Do not enable any tested size-scaling rule in runtime.
- The strongest near-miss is late-morning half-size; if revisited, test a
  narrower time window than `10:30-11:59` rather than applying broad scaling.
- At this point, hard filters and simple size scalers both mostly trade away
  current edge. The next research should be either:
  - narrower late-morning timing segmentation, or
  - exit-management research for losing contexts instead of entry suppression.

## Cycle 12

Status: rejected trading-profile change; accepted exit-management research
harness.

Date: 2026-06-16.

Goal: test whether conditional exit management can improve the weak contexts
without suppressing entries or reducing initial position size.

Changes made:
- Added a disabled-by-default `backtest.research_exit_management` hook inside
  `backtest.simulate()`. It supports rule-based exit behavior scoped by:
  - symbols.
  - entry minute ranges.
  - minimum VWAP distance in ATR.
  - minimum volume ratio.
  - minimum ATR percent.
- Supported research-only exit actions:
  - `breakeven_after_r`.
  - `cut_loser_after_bars` plus `cut_loser_below_r`.
  - `time_stop_bars`.
- Added `exit_research.py`, a targeted harness that compares breakeven stops,
  stale-loser cuts, late-morning variants, and focus-symbol variants against
  baseline on:
  - 365-day one-year behavior.
  - known weak focus months: `2025-06`, `2025-07`, `2025-08`, `2025-10`,
    `2025-11`.
  - trailing 182-day accepted-edge window.
  - IS/OOS split using `2026-04-10`.
  - 10c slippage stress on the 182-day window.
- No runtime config values were changed.

Validation command:
- `docker compose run --rm --no-deps -v /home/ec2-user/alpaca-scalper:/app alpaca-bot python exit_research.py`.

Candidate results:
- Baseline:
  - 365 days: 164 trades, PF 1.99, net +$1,475.40, focus -$337.49,
    other +$1,812.89.
  - 182 days: 79 trades, PF 3.86, net +$1,994.24, OOS +$796.83,
    10c net +$1,778.91.
- `breakeven after 0.5R all`:
  - 365 net -$259.65, delta -$1,735.05, focus -$427.93.
  - 182 net +$204.04, delta -$1,790.20, OOS +$92.72,
    10c +$140.12.
- `breakeven after 1.0R all`:
  - 365 net +$844.13, delta -$631.27, focus -$325.45.
  - 182 net +$1,299.15, delta -$695.09, OOS +$401.93,
    10c +$1,077.80.
- `late morning breakeven 0.5R`:
  - 365 net +$1,434.54, delta -$40.86, focus unchanged at -$337.49.
  - 182 net +$1,923.35, delta -$70.89, OOS +$780.33,
    10c +$1,707.77.
  - This was the least invasive near-miss, but it still failed the strict
    screen.
- `VWAP>=1.5 breakeven 0.5R`:
  - 365 net +$931.84, delta -$543.56, focus -$294.34.
  - 182 net +$1,358.77, delta -$635.47, OOS +$470.85,
    10c +$1,254.11.
- `focus risky breakeven 0.5R`:
  - 365 net +$659.84, delta -$815.56, focus -$401.82.
  - 182 net +$1,268.32, delta -$725.92, OOS +$620.91,
    10c +$1,074.78.
- `cut loser 2 bars below -0.25R`:
  - 365 net +$490.39, delta -$985.00, focus -$245.53.
  - 182 net +$868.71, delta -$1,125.53, OOS +$395.64,
    10c +$638.51.
- `cut loser 3 bars below entry`:
  - 365 net +$215.92, delta -$1,259.47, focus -$143.30.
  - 182 net +$459.60, delta -$1,534.64, OOS +$212.12,
    10c +$323.80.
- `late morning loser cut 2 bars`:
  - 365 net +$1,271.72, delta -$203.68, focus -$323.50.
  - 182 net +$1,851.60, delta -$142.64, OOS +$808.89,
    10c +$1,621.32.
- `focus risky loser cut 2 bars`:
  - 365 net +$809.98, delta -$665.42, focus -$387.11.
  - 182 net +$1,473.23, delta -$521.01, OOS +$651.14,
    10c +$1,240.52.
- `late morning time stop 3 bars`:
  - 365 net +$1,032.72, delta -$442.68, focus -$293.22.
  - 182 net +$1,564.57, delta -$429.67, OOS +$655.49,
    10c +$1,326.44.
- `focus risky BE+loser cut`:
  - 365 net +$356.63, delta -$1,118.77, focus -$375.65.
  - 182 net +$918.64, delta -$1,075.60, OOS +$490.39,
    10c +$730.19.

Decision:
- Reject all tested exit-management candidates as trading-profile changes.
- Accept `exit_research.py` and the backtest-only exit-management hook as
  research support.

Rationale:
- None of the candidates preserved baseline 365-day net, 182-day net, OOS, and
  10c stress.
- Broad breakeven and stale-loser exits are destructive. They cut winners too
  early and materially reduce recent-window edge.
- The least invasive result is `late morning breakeven 0.5R`, but it does not
  improve the focus-month loss cluster and still reduces net under every major
  validation window.
- `late morning loser cut 2 bars` slightly improves OOS versus baseline
  (+$808.89 vs +$796.83), but it still reduces 365-day net, 182-day net, and
  10c stress, so it is not acceptable.

Verification:
- `python3 -m compileall -q backtest.py exit_research.py`: pass.
- `python3 test_smoke.py`: pass.
- `python3 test_event_risk.py`: pass.
- `python3 test_orb_smoke.py`: pass.
- `python3 test_market_regime.py`: pass.
- `python3 runtime_safety_check.py`: pass.
- `python3 -m compileall -q .`: pass.

Operational warnings / next ideas:
- Do not enable any tested exit-management rule in runtime.
- The current profile has repeatedly beaten broad filters, size scalers, and
  exit overlays. That is useful negative evidence: simple reactive controls are
  mostly removing the edge.
- Future research should be more structural, not another broad overlay:
  consider a small symbol/setup attribution pass around the most profitable
  recent trades, or pause optimization and collect live/paper forward data
  under the accepted profile.

## Cycle 13

Status: reporting/research only; no trading-profile change proposed or
accepted.

Date: 2026-07-03.

Goal: operator asked for a 1-year backtest of a plan that "targets 1-2% of
total portfolio and exits the market on a daily basis". Evaluated both
readings: (a) a daily profit-target halt at +1%/+2% of start-of-day equity,
and (b) 1%/2% risk-per-trade sizing. All variants keep the existing daily
flat exit (`flatten_at 15:55`; no overnight holds).

Changes made:
- Added a disabled-by-default `backtest.research_daily_profit_target_pct`
  hook inside `backtest.simulate()` (backtest namespace only; runtime cannot
  read it). When set, new entries halt for the rest of the day once daily
  P&L reaches the given percent of start-of-day equity.
- Added `daily_target_research.py` reporting harness (uses the cached
  `period_events_365.pkl` window 2025-06-16 -> 2026-06-16).

Results (365-day window, start equity $2,000, 3c slippage):
- A. Baseline accepted profile: 164 trades, 56.7% win, PF 1.99,
  net +$1,475.40 (+73.8%), max DD $417.21. 156 active days, 56% green,
  avg day +0.37%; 30% of active days reach +1% of portfolio, 14% reach +2%.
- B. Baseline + halt at +1% daily target: 163 trades, PF 1.98,
  net +$1,449.96 (+72.5%). Removed exactly one trade all year.
- C. Baseline + halt at +2% daily target: identical to B.
- D. Risk 1%/trade: 164 trades, PF 1.49, net +$382.35 (+19.1%),
  max DD $194.54.
- E. Risk 2%/trade: 164 trades, PF 1.58, net +$766.98 (+38.3%),
  max DD $322.82.
- F. Risk 2%/trade + halt at +2%: net +$748.20 (+37.4%).

Interpretation:
- A daily profit-target halt is a no-op on this profile: with
  max_concurrent_positions 1 and few trades/day, big up days come from a
  single trade, so halting after the target almost never removes a trade
  (B/C differ from baseline by one trade over the full year).
- Hitting +1-2% of portfolio per day is not a realistic steady expectation:
  even the accepted profile reaches +1% on only ~30% of active days and
  averages +0.37% per active day.
- The 1-2% risk-per-trade reading cuts return roughly in proportion
  (+19%/+38% vs +73.8%) while max DD as a fraction of start equity falls
  from ~21% to ~10-16%. PF also drops (1.49/1.58 vs 1.99) because smaller
  compounding shrinks the weight of the strong late-window months.

Decision:
- No runtime config change. Baseline remains as accepted in Cycle 12 era.
- Accept `daily_target_research.py` and the daily-profit-target hook as
  research support.

Verification:
- `python -m compileall -q backtest.py daily_target_research.py`: pass.
- `python test_smoke.py`: pass.
- `python test_orb_smoke.py`: pass.
- `python runtime_safety_check.py`: pass (paper mode, 1 concurrent
  position, daily loss cap <= 5%).

Operational warnings / next ideas:
- If the operator wants true 1-2%/trade risk sizing live, expect roughly
  half to a quarter of the baseline return; it is a risk-preference change,
  not an edge change, and per project policy it needs explicit operator
  sign-off before touching config.
- The cached 365-day window ends 2026-06-16; a refresh fetch is needed to
  cover the most recent ~2.5 weeks.

## Cycle 14

Status: reporting only; no trading-profile change.

Date: 2026-07-03.

Goal: operator re-asked for the 1-year "1-2% of portfolio, exit daily"
backtest specifying the 15-minute timeframe. Confirmed the accepted profile
already runs on 15-minute bars (`strategy.bar_minutes: 15`; simulate()
resamples the 1-min feed identically to the live aggregator), so all Cycle 13
results are 15-min results. Added a timeframe sensitivity check.

Results (365-day cached window, baseline profile, only bar_minutes varied):
- 5-min: 251 trades, 41.8% win, PF 0.89, net -$314.38 (-15.7%), DD $550.00.
- 15-min: 164 trades, 56.7% win, PF 1.99, net +$1,475.40 (+73.8%), DD $417.21.
- 30-min: 149 trades, 50.3% win, PF 0.81, net -$295.36 (-14.8%), DD $495.13.

Interpretation:
- The edge is specific to the 15-minute aggregation; both 5-min and 30-min
  are net losers over the same year with the same entries/exits/sizing
  rules. Treat bar_minutes as load-bearing and do not drift it without a
  full validation pass.
- Caveat: warmup/indicator periods are denominated in bars, so changing
  bar_minutes also rescales indicator horizons; this is a sensitivity probe,
  not a tuned per-timeframe comparison.

Verification:
- One-off harness (not committed): baseline simulate() with bar_minutes in
  {5, 15, 30} over period_events_365.pkl.

## Cycle 15

Status: research complete; one candidate passes the formal screen but is not
accepted autonomously — flagged for operator decision. No config change.

Date: 2026-07-03.

Goal: operator asked whether the bot can be pushed to be more profitable.
Followed the Cycle 12 handoff: structural attribution pass, then a small
bounded candidate set (data-driven symbol drops; trailing ATR stops, which
were an untested live-code path).

Changes made:
- Added `profit_push_research.py` (attribution + candidate screen over the
  cached 365d and 182d windows; same four-gate screen as prior cycles).

Attribution findings (365-day baseline):
- Profit is concentrated: AMD +$498 and NVDA +$467 are 65% of net; SPY is
  the only net-negative symbol (24 trades, 41.7% win, -$13.15).
- Almost all profit exits via the 15:55 flatten (129 trades, +$2,227); the
  3R take-profit filled only twice all year; stops cost -$948. The system
  is effectively "first-hour momentum entry, hold to the close".
- Entry hours 9-10 contribute +$1,343 of +$1,475. Friday is ~flat (-$29).

Candidate results (gates: 365 net >= +$1,475.40, 182 net >= +$1,994.24,
OOS >= +$796.83, 10c >= +$1,778.91, n >= 50):
- drop SPY: 365 net +$1,486.66, 182 net +$2,076.55, OOS +$850.91,
  10c +$1,819.67 -> formal PASS. loop_evaluate 182 excl SPY: safety flags
  none, top symbol AMD 31.7% of net.
- trailing stop 1.5x/2.0x/2.5x ATR (replacing fixed 3R TP): 365 nets
  +$952/+$838/+$874 -> all fail every gate. Consistent with the flatten
  exit doing the work; trailing gives back the close-out gains.

Decision:
- Reject trailing stops definitively.
- Hold drop-SPY as operator-decision-only, despite the formal pass:
  - 365-day delta is +$11.26 (~0.8%), inside noise for 164 trades.
  - Monthly consistency worsens: drop-SPY is slightly worse in 8 of 13
    months; the entire gain comes from one month (2026-04, +$106 delta,
    slot freed for a better trade).
  - DD rises ($430.72 vs $417.21), PF dips (1.95 vs 1.99), focus months
    slightly worse (-$352.68 vs -$337.49).
  - The recent-window gains (182/OOS/10c all improve ~3-5%) are real but
    small; this is a slot-allocation effect, not a new edge.

Verification:
- `python -m compileall -q profit_push_research.py`: pass.
- `python test_smoke.py`: pass.

Operational notes / next ideas:
- The honest levers for materially more profit are capital and risk
  appetite, not entry/exit tweaks: the profile compounds ~1.7x/year, and
  every reactive overlay tested across Cycles 8-15 removed edge.
- If the operator wants drop-SPY applied, remove SPY from `symbols` (it
  stays available to the disabled market_regime block, which reads its own
  symbol list) and re-run `loop_evaluate.py --days 182` post-change.
- Untested-but-plausible future idea: since TP almost never fills, test
  removing the TP leg entirely (pure stop + flatten) — mechanically near
  identical to baseline, may simplify live order handling.

## Cycle 16

Status: operational/monitoring work accepted; no trading-profile change.

Date: 2026-07-03.

Context: operator reported the bot was down for ~3 weeks (since ~2026-06-13);
it was restarted 2026-07-03. Decision from Cycle 15 stands: stop optimizing,
start forward validation.

Changes made:
- `scripts/refresh_cache.py`: gap-fetches 1-min bars and updates
  `period_events_365.pkl`, `period_events_182.pkl`, and `optimizer_events.pkl`
  in place (trimmed to window). Run via docker compose (needs .env keys).
- `forward_tracking.py`: forward-validation report — heartbeat staleness
  (catches silent downtime like the 3-week outage), rolling 30-day sim health
  (regime-turn alarm), and live-vs-sim trade matching with entry-slippage and
  P&L drift once `runtime/trades.csv` has rows. Alert surface = `WARN:` lines.
- `scripts/weekly_check.sh` + systemd units `alpaca-weekly-check.{service,timer}`
  (enabled, Sun 18:00 ET, Persistent=true): refresh caches, run tracking,
  write `results/weekly_YYYY-MM-DD.txt`, copy warnings to
  `results/ALERTS_YYYY-MM-DD.txt`, keep last 12 reports.

First run results (2026-07-03):
- Caches refreshed: 365d window now 2025-07-03 -> 2026-07-02 (+87,447 bars).
- Refreshed 365d baseline: 164 trades, PF 2.03, net +$1,639.49 — the edge
  held through the outage weeks (window also rolled off weak 2025-06).
- Rolling 30d sim: 11 trades, PF 2.87, net +$263.02 — approximate
  opportunity cost of the 3-week downtime.
- No live trades since restart; tracking begins at the first live close.
- No warnings.

Next steps:
- Let the paper bot run untouched; review weekly reports in `results/`.
- Once >=10 live trades exist, use the live-vs-sim drift section to judge
  whether the 3c slippage model is honest before any real-money decision.
- Real-money on-ramp proposal (operator to decide later): 2-3 months of
  paper tracking within tolerance, then start live at 1-2% risk_per_trade
  (not 10%).
