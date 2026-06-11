# Research Log — Strategy Optimization, June 9 2026

Data: 655,970 one-minute bars, 2025-12-10 → 2026-06-09, six symbols
(SPY, QQQ, AAPL, NVDA, AMD, TSLA), Alpaca SIP feed. All results include
2c/share adverse slippage on market fills (entry, stop, flatten); the
take-profit limit fills at its price. Spread and partial fills are NOT
modeled — every number below is still optimistic.

## Methodology

Train/validation split to control curve-fitting:

- **In-sample (IS):** 2025-12-10 → 2026-04-09 (~427k bars). All tuning here.
- **Out-of-sample (OOS):** 2026-04-10 → 2026-06-09 (~228k bars). Touched
  once, at the end, to validate the chosen config.

Harness: `experiment.py` (loads `events_6mo_flat.pkl` cache, applies
dotted config overrides, runs the exact live `simulate()` path).
Reproduce the cache by re-running the fetch in `backtest.fetch_events`.

## Baseline (original config: 1.5R / 1.5 ATR stop / 1.5x vol / RSI<70)

| Window | Trades | Win% | PF | Max DD | Net |
|---|---|---|---|---|---|
| IS  | 403 | 38.2% | 0.76 | $185 | **−$180.43** |
| OOS | 218 | 48.6% | 1.51 | $26  | +$150.86 |

Conclusion: no edge. The full-period "−$36" result was a losing strategy
rescued by a favorable final two months. Diagnostics: losses spread across
all symbols (NVDA/AMD worst), all weekdays, all hours (11:00–12:00 ET
chop worst, only 13:00 positive). Win rate 38.2% vs the 40% breakeven
required at 1.5R — underwater before costs.

## Experiment 1 — Trend-EMA regime filter: FAILED

Added optional `strategy.trend_ema` (close above a rising N-period EMA
required). IS sweep: 50/100 made it slightly worse, 200 helped marginally
(−$139 vs −$180). Redundant with the existing cross+VWAP conditions.
Code kept (default off).

## Experiment 2 — Momentum economics grid (96 configs): ONE THIN CORNER

Grid: take_profit_r × stop_atr_mult × volume_surge_mult × rsi_max ×
cross_confirm_bars. 93/96 configs negative on IS; worst −$319. Every
positive config required volume_surge_mult = 2.5. Best:
`tp_r=3.0, stop=2.5 ATR, vol=2.5x, RSI<70, confirm=3` → IS +$41.60,
PF 1.19, 75 trades. NOTE: the positive plateau is narrow — adjacent
configs (e.g. RSI<60) drop near zero. Treat with modest confidence.

## Experiment 3 — VWAP mean-reversion family (24 configs): FAILED

New `strategy.mode: reversion` (buy close < VWAP − k·ATR with RSI
oversold; same bracket exits). ALL 24 IS configs negative (best −$21,
worst −$414). Dip-buying does not survive slippage on 1-min bars here.
Code kept in `strategy.py` as a documented dead end — do not re-tune it
on this same data and call the result discovery.

## Experiment 4 — SPY/QQQ-only (a-priori tightest-spread subset): FAILED

Tuned config on SPY+QQQ only: IS −$10.65 (PF 0.80), OOS +$9.75. The
edge, such as it is, comes from the high-beta names (NVDA/AMD/TSLA/AAPL).

## Final validation (the one OOS look)

Tuned config, chosen on IS only:

| Window | Trades | Win% | PF | Max DD | Net |
|---|---|---|---|---|---|
| IS  | 75 | 26.7% | 1.19 | $76 | +$41.60 |
| OOS | 67 | 37.3% | 1.60 | $45 | **+$83.97** |

Positive in both regimes — the only tested configuration with that
property. Adopted into `config.yaml`. Full-period result with tuned
config: 142 trades, PF 1.34, max DD $76, **net +$121.32 (+6.07%)**.
Recent windows: last month +$24, last week −$23, today $0.

## Honest limitations / why tuning stopped here

1. ~32% win rate by design → multi-trade losing streaks are normal and
   last week was negative. Discipline required.
2. One IS/OOS split over one six-month period — not walk-forward, not
   multiple market cycles. The narrow IS plateau is a known overfit risk.
3. Spread, partial fills, and queue effects unmodeled; real results will
   be worse than these numbers.
4. Further parameter search on this same dataset would fit noise.
   Next evidence must come from NEW data: 4–6 weeks of paper trading
   (`python main.py`), comparing live fills to `trades.csv` expectations.

Nothing here is financial advice. Simulated performance does not predict
future results.


# Research Log — Round 2: "profit-push" version test, June 10 2026

Tested a revised build (volume-surge semantics fix, ET timezone fixes,
real-fill P&L accounting, overnight session reset, entry-limit-offset
config, plus a 5-part entry-quality filter pack). Same IS/OOS protocol.

| Variant | IS net (PF) | OOS net (PF) |
|---|---|---|
| Prev tuned (old vol semantics) | +41.60 (1.19) | +83.97 (1.60) |
| Vol fix only, mult=2.5 | +7.76 (1.03) | +32.21 (1.19) |
| Vol fix + full filter pack | +32.85 (1.30) | **−32.72 (0.41)** |
| Vol fix, mult=3.0, no filters | +31.48 (1.16) | +49.03 (1.45) |
| **Vol fix, mult=3.5, no filters (ADOPTED)** | **+68.75 (1.59)** | **+58.89 (1.91)** |

Findings:
1. **Filter pack: REJECTED.** Improved IS, collapsed OOS to 10 trades and
   a 0.41 PF — textbook overfit (thresholds and the 11:00-12:00 block were
   derived from IS diagnostics). All filters disabled in config; code kept.
2. **Volume semantics fix: KEPT, retuned.** The old "bug" (surge bar
   included in its own average) silently acted as a stricter filter. Under
   corrected semantics, 2.5x is too loose; 3.5x restores strictness and
   beats the old version on risk-adjusted basis. 3.0x neighbor also
   positive both windows -> plateau, not a spike.
3. **Infrastructure fixes: KEPT** (timezone, fill accounting, session
   reset, entry limit offset, dtime crash fix, lazy SDK import).

Caveats: the OOS window has now been consulted across multiple variants,
so it is partially "spent" — treat OOS numbers as softer than round 1.
Trade samples are small (39–45 per window). Fresh paper trading remains
the only honest next test.


# Research Log — Round 3: wide exploration, June 10 2026

Protocol upgrade: OOS window from rounds 1-2 is spent, so every candidate
ran the full 6 months and was judged on per-fold consistency across three
2-month folds (Dec-Feb / Feb-Apr / Apr-Jun). Adoption rule (set before
running): beat v2's net AND be positive in all three folds.

Reference — v2 config: 84 tr, PF 1.69, DD $40, net +$127.01,
folds +77.32 / -8.57 / +58.26. Note v2's known weakness: fold 2.

| Candidate | Net | Folds | Verdict |
|---|---|---|---|
| Trailing ATR exit 1.0/1.5/2.5 (no TP) | +$32/+$35/+$54 | fold2 neg | REJECT — trails give back too much on 1-min noise; fixed 3R bracket superior |
| Time-stop 20/40 bars | +$74/+$42 | fold2 neg | REJECT — cuts winners that need time to reach 3R |
| ORB 15/30min x vol 1.5/2.5 | -$70..+$22, DD up to $255 | fold2 -$222 worst | REJECT family — no edge, brutal drawdowns |
| Slow regime EMA(200) | +$122.87, PF 1.74 | +66.54/-2.39/+58.73 | REJECT (narrowly) — best PF and nearly fixes fold 2, but trails v2 net and fold 2 still negative |
| Slow regime EMA(400) | +$78.07 | fold2 neg | REJECT |

Eleven variants across four new mechanism families; the incumbent won
every matchup. Code for all three mechanisms (risk.trail_atr_mult,
risk.time_stop_bars, strategy.mode: orb) is kept, disabled by default.

Structural conclusion: the fold-2 (Feb-Apr) bleed is a LONG-ONLY
limitation — that regime offered nothing to buy. The unexplored frontier
is a short side, which requires simulator and execution surgery plus its
own risk controls (uncapped loss profile, borrow availability). Parameter
search on this dataset is exhausted; do not resume it. Next evidence:
paper trading.


# Research Log — Round 4: timeframe study, June 10 2026

User question: were 5-min and 15-min bars ever tested? They had not been.
Resampled the cached 1-min data (bars stamped at bucket CLOSE) and ran the
identical engine. Same per-fold consistency gate as round 3.

| Timeframe / vol mult | Net | PF | DD | Folds |
|---|---|---|---|---|
| 5-min, 1.5/2.5/3.5x | -$151 / -$5 / -$41 | <=0.99 | up to $310 | fold1+2 deeply neg |
| 15-min, 1.0x | +$159 | 1.28 | $122 | fold2 -$23 |
| **15-min, 1.5x** | **+$185** | 1.35 | $97 | **ALL positive** |
| **15-min, 2.0x (ADOPTED)** | **+$207** | 1.42 | $83 | **ALL positive** |
| 15-min, 2.5x / 3.5x | +$131 / +$197 | 1.27/1.50 | $122/$74 | fold2 neg |
| 30-min, 1.5x | -$18 | 0.96 | $122 | fold1 -$75 |

Findings:
1. 15-min is the sweet spot: moves are large enough that 2c slippage is
   noise, yet intraday structure still exists. 5-min is a dead zone
   (1-min costs without 15-min moves); the edge dies again at 30-min.
2. 1.5x-2.0x is a genuine all-folds-positive plateau; 2.0x adopted
   (+$207.46, PF 1.42, DD $83). First config in the entire project
   positive in the difficult Feb-Apr fold (+$5.38) — the 15-min frame
   filters the chop that bled every 1-min variant.
3. Engineering: live bot aggregates 1-min stream into bar_minutes buckets
   (main.py); simulate() auto-resamples identically, so backtest/report/
   live provably share one pipeline (verified by exact reproduction from
   raw 1-min input). EOD flatten still runs on raw 1-min cadence.

Caveats: this selection used the full dataset with fold results visible —
there is NO untouched holdout left for this choice. Fold-2 profit is
+$5.38, i.e. barely positive. DD doubled vs the 1-min v2 ($83 vs $40).
93 trades. The 15-min config's claim to superiority is regime
consistency, and only fresh (paper) data can confirm it.

## Final config evolution

| Version | Net (6mo) | PF | Max DD | Fold-consistent? |
|---|---|---|---|---|
| Original 1-min | -$36 | 0.96 | $185 | no |
| v2 tuned 1-min | +$127 | 1.69 | $40 | no (fold2 -$8.57) |
| v4 15-min | +$207 | 1.42 | $83 | YES |


# Research Log — Round 5: full version x timeframe matrix, June 10 2026

All three config generations run on 5-min, 15-min, 60-min, and daily bars
(identical engine; daily bars stamped 15:45 ET, informational only since
the live bot is intraday and cannot hold overnight). Net / PF / fold-
consistency per cell:

| Config | 5-min | 15-min | 60-min | Daily |
|---|---|---|---|---|
| original (1.5R/1.5vol) | -$12 (0.99) | -$188 (0.70) | -$43 (0.83) | 0 trades |
| v2-tuned (3R/3.5vol) | -$41 (0.94) | +$197 (1.50) | -$18 (0.63) | 0 trades |
| v4-current (3R/2.0vol/10%) | -$16 (0.98) | **+$239 (1.41) ALL-folds+** | -$93 (0.64) | 0 trades |

Findings:
1. v4-current on 15-min is the ONLY all-folds-positive cell of twelve.
   Champion re-confirmed against the full grid.
2. The edge is a config x timeframe INTERACTION, not a property of either
   alone: the original config on 15-min is the worst cell in the matrix
   (-$188), and v4 params on 60-min lose -$93. Nothing generalizes across
   rows or columns.
3. 60-min: uniformly negative — too few bars per session for the
   cross/VWAP/volume logic (~7 bars/day, warmup eats days).
4. Daily: zero signals in ~96 post-warmup days — EMA cross + volume surge
   never co-occurred. The signal family is intraday by nature.
5. 5-min remains a dead zone for every config.

Implication: do not port these parameters to another timeframe and expect
anything; each frame would need its own research cycle. The deployed
combination stays: 15-min bars, 2.0x volume, 3R/2.5ATR, 10%/90%-capped
sizing, 5% daily stop -> +$239.07 (+11.95%), PF 1.41, DD $91.


# Research Log — Round 6: retrospective re-test of rejected ideas, June 10 2026

User insight: every mechanism rejected in rounds 1-3 was only ever tested
on 1-MIN bars, before the 15-min frame was discovered — and round 5 proved
edges are config x timeframe interactions. Also, v4's R-geometry (3R /
2.5 ATR) was inherited from 1-min tuning, never re-examined at 15-min.
Everything re-tested on 15-min. Gate: beat +$239.07 AND all folds positive.

| Re-tested idea (on 15-min) | Result | Verdict |
|---|---|---|
| Trailing ATR exits 1.5/2.5 | -$1 / +$13 | still dead |
| Time-stop 16 bars (4h) | +$236.52, PF 1.45, DD $80, folds +65/+48/+123 ALL+ | near-miss; kept as documented alternative |
| Reversion mode (3 cfgs, 15m + 2 cfgs 60m) | -$49 to -$263 | dead on every frame |
| Regime EMA 26/50 | +$202 / +$237 ALL+ | no improvement |
| **R-geometry sweep tp{2,3,4} x stop{1.5,2.5,3.5}** | 6-cell ALL+ plateau at stop>=2.5; peak tp=2R/stop=3.5 -> **+$293.93, PF 1.55** | **ADOPTED** |
| Edge check stop=4.5 | +$305.55 but fold2 -$2.59, DD $133 | rejected — breaks consistency; 3.5 is a real boundary |
| Combo tp2/stop3.5 + tstop16 | +$251.05 ALL+, most balanced folds (+41/+63/+146) | documented alternative for smoother equity |

Adopted v5 config: 15-min bars, vol 2.0x, **tp 2.0R, stop 3.5 ATR**,
10% risk (90% cap-bound), 5% daily stop.
Result: 89 trades, win rate 60.7%, PF 1.55, DD $97.50,
**net +$293.93 (+14.70%)**, folds +45/+31/+218 ALL+.
Character change: avg win $15.36 vs avg loss $15.31 at 61% win rate —
a high-win-rate machine, vs the old 35%-win/3R profile. Psychologically
far easier to run.

The user's question was correct on both counts: a discarded idea
(time-stop) works at 15-min where it failed at 1-min, and an unexamined
inheritance (R-geometry) was suboptimal. Caveats: the 6-month dataset is
now extremely well-worn; the plateau + fold-gate + a-priori-gap rationale
mitigate but do not eliminate selection bias. Paper trading is the judge.
