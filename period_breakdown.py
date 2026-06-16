#!/usr/bin/env python3
"""Month-to-month + last-week breakdown for the current config profile.

One-off reporting helper. Fetches a 1-year window once (cached separately from
the optimizer cache), replays it through the live strategy/sizing code, and
prints monthly P&L plus a trailing-7-day summary.
"""
from __future__ import annotations

import pickle
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from backtest import ET, fetch_events, simulate

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 365
CACHE = Path(f"period_events_{DAYS}.pkl")
YEARS = DAYS / 365.0

cfg = yaml.safe_load(open("config.yaml"))
symbols = cfg["symbols"]
end = datetime.now(ET)
start = end - timedelta(days=DAYS)

if CACHE.exists():
    blob = pickle.load(CACHE.open("rb"))
    if blob.get("symbols") == symbols and blob.get("days", 0) >= DAYS:
        events = blob["events"]
    else:
        events = None
else:
    events = None

if events is None:
    print(f"Fetching {DAYS} days of 1-min bars for {symbols} ...")
    events = fetch_events(cfg, start, end, symbols)
    pickle.dump({"symbols": symbols, "days": DAYS, "events": events}, CACHE.open("wb"))

print(f"Bars: {len(events):,} | "
      f"stop_atr_mult={cfg['risk']['stop_atr_mult']} mode={cfg['strategy']['mode']}\n")

stats = simulate(cfg, events, symbols)
trades = stats["trades"]


def summarize(rows):
    wins = [t for t in rows if t["pnl"] > 0]
    net = sum(t["pnl"] for t in rows)
    gross_w = sum(t["pnl"] for t in wins)
    gross_l = -sum(t["pnl"] for t in rows if t["pnl"] <= 0)
    pf = gross_w / gross_l if gross_l else float("inf")
    wr = len(wins) / len(rows) * 100 if rows else 0.0
    return len(rows), wr, pf, net


monthly = defaultdict(list)
for t in trades:
    monthly[str(t["date"])[:7]].append(t)

print("=" * 70)
print(f"{'Month':<10}{'Trades':>8}{'Win%':>8}{'PF':>8}{'Net P&L':>14}")
print("-" * 70)
for month in sorted(monthly):
    n, wr, pf, net = summarize(monthly[month])
    pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
    print(f"{month:<10}{n:>8}{wr:>7.1f}%{pf_s:>8}${net:>+13.2f}")
print("-" * 70)
n, wr, pf, net = summarize(trades)
pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
print(f"{f'{YEARS:.0f}Y TOTAL':<10}{n:>8}{wr:>7.1f}%{pf_s:>8}${net:>+13.2f}")
print(f"{'':<10}{'':>8}{'':>8}{'':>8}  PF {stats['profit_factor']:.2f} | "
      f"max DD ${stats['max_drawdown']:.2f}")

today = end.date()
week_cut = today - timedelta(days=7)
last_week = [t for t in trades if t["date"] >= week_cut]
n, wr, pf, net = summarize(last_week)
pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
print("=" * 70)
print(f"Last 7 days (since {week_cut}): {n} trades, {wr:.1f}% win, "
      f"PF {pf_s}, net ${net:+.2f}")
print("=" * 70)
