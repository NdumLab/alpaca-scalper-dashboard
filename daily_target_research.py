#!/usr/bin/env python3
"""Research: 1-2% of portfolio daily target + flat-by-close, past 365 days.

One-off reporting harness. Replays the cached 1-year event window through the
live strategy/sizing code and compares the accepted baseline against:
  - a daily profit-target halt at +1% / +2% of start-of-day equity
    (backtest-only hook: backtest.research_daily_profit_target_pct), and
  - a 1% / 2% risk-per-trade sizing interpretation.
The strategy already exits the market daily (flatten_at 15:55) in every run.
"""
from __future__ import annotations

import copy
import pickle
from collections import defaultdict

import yaml

from backtest import simulate

CACHE = "period_events_365.pkl"

blob = pickle.load(open(CACHE, "rb"))
events = blob["events"]
base_cfg = yaml.safe_load(open("config.yaml"))
symbols = base_cfg["symbols"]
start_equity = float(base_cfg["account"]["starting_equity"])

first = events[0][0].date()
last = events[-1][0].date()
print(f"Window: {first} -> {last}  ({len(events):,} 1-min bars, "
      f"{len(symbols)} symbols, start equity ${start_equity:,.0f})")
print(f"Daily exit: flatten_at={base_cfg['strategy']['flatten_at']} "
      f"(no overnight holds in any variant)\n")


def daily_series(trades):
    """Per-day P&L in entry order, plus day-start equity for pct math."""
    by_day = defaultdict(float)
    for t in trades:
        by_day[t["date"]] += t["pnl"]
    days = sorted(by_day)
    eq = start_equity
    rows = []
    for d in days:
        rows.append((d, by_day[d], eq))
        eq += by_day[d]
    return rows


def report(name, stats, show_monthly=False):
    trades = stats["trades"]
    rows = daily_series(trades)
    day_pcts = [pnl / eq0 * 100 for _, pnl, eq0 in rows]
    hit1 = sum(1 for p in day_pcts if p >= 1.0)
    hit2 = sum(1 for p in day_pcts if p >= 2.0)
    pos = sum(1 for p in day_pcts if p > 0)
    ret = (stats["end_equity"] / stats["start_equity"] - 1) * 100
    pf = stats["profit_factor"]
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    print("=" * 78)
    print(f"{name}")
    print("-" * 78)
    print(f"  Trades {stats['n']:>4} | win {stats['win_rate']:.1f}% | PF {pf_s} | "
          f"net ${stats['net']:+,.2f} | return {ret:+.1f}% | max DD ${stats['max_drawdown']:,.2f}")
    if rows:
        avg = sum(day_pcts) / len(day_pcts)
        print(f"  Active days {len(rows)} | green {pos} ({pos/len(rows)*100:.0f}%) | "
              f"avg day {avg:+.2f}% | best {max(day_pcts):+.2f}% | worst {min(day_pcts):+.2f}%")
        print(f"  Days reaching +1% of portfolio: {hit1} ({hit1/len(rows)*100:.0f}%) | "
              f"+2%: {hit2} ({hit2/len(rows)*100:.0f}%)")
    if show_monthly and trades:
        monthly = defaultdict(list)
        for t in trades:
            monthly[str(t["date"])[:7]].append(t)
        print(f"  {'Month':<10}{'Trades':>7}{'Win%':>8}{'Net P&L':>13}")
        for m in sorted(monthly):
            rows_m = monthly[m]
            wins = sum(1 for t in rows_m if t["pnl"] > 0)
            net = sum(t["pnl"] for t in rows_m)
            print(f"  {m:<10}{len(rows_m):>7}{wins/len(rows_m)*100:>7.1f}%${net:>+12.2f}")
    print()


def run(name, mutate, show_monthly=False):
    cfg = copy.deepcopy(base_cfg)
    mutate(cfg)
    stats = simulate(cfg, events, symbols)
    report(name, stats, show_monthly)
    return stats


run("A. Baseline (accepted profile: 10% risk/trade, flat daily)",
    lambda c: None, show_monthly=True)

run("B. Baseline + halt after +1% daily portfolio target",
    lambda c: c["backtest"].__setitem__("research_daily_profit_target_pct", 1.0),
    show_monthly=True)

run("C. Baseline + halt after +2% daily portfolio target",
    lambda c: c["backtest"].__setitem__("research_daily_profit_target_pct", 2.0),
    show_monthly=True)

run("D. Risk 1% of portfolio per trade (instead of 10%)",
    lambda c: c["risk"].__setitem__("risk_per_trade_pct", 1.0))

run("E. Risk 2% of portfolio per trade (instead of 10%)",
    lambda c: c["risk"].__setitem__("risk_per_trade_pct", 2.0))


def combo(c):
    c["risk"]["risk_per_trade_pct"] = 2.0
    c["backtest"]["research_daily_profit_target_pct"] = 2.0


run("F. Risk 2%/trade + halt at +2% daily target", combo)
