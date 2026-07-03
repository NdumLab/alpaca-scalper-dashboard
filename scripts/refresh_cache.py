#!/usr/bin/env python3
"""Refresh the cached 1-min bar event pickles by fetching only the gap.

Updates period_events_365.pkl and period_events_182.pkl in place (append gap,
trim to window), and rewrites optimizer_events.pkl from the refreshed 365-day
events so loop_evaluate.py also sees current data. Requires Alpaca API keys in
the environment (run via docker compose, which loads .env).
"""
from __future__ import annotations

import pickle
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backtest import ET, fetch_events  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
cfg = yaml.safe_load(open(REPO / "config.yaml"))
symbols = cfg["symbols"]
now = datetime.now(ET)

gap_events = None
for days in (365, 182):
    path = REPO / f"period_events_{days}.pkl"
    if not path.exists():
        print(f"{path.name}: missing, skipping (run period_breakdown.py {days} to build)")
        continue
    blob = pickle.load(path.open("rb"))
    if blob.get("symbols") != symbols:
        print(f"{path.name}: symbol basket changed, needs full re-fetch — skipping")
        continue
    events = blob["events"]
    last_ts = events[-1][0]
    if gap_events is None:
        start = last_ts - timedelta(minutes=5)
        print(f"Fetching gap {start.astimezone(ET):%Y-%m-%d %H:%M} -> now for {len(symbols)} symbols ...")
        gap_events = fetch_events(cfg, start, now, symbols)
    fresh = [e for e in gap_events if e[0] > last_ts]
    cutoff = now - timedelta(days=days)
    merged = [e for e in events if e[0] >= cutoff] + fresh
    merged.sort(key=lambda e: e[0])
    pickle.dump({"symbols": symbols, "days": days, "events": merged}, path.open("wb"))
    print(f"{path.name}: {len(events):,} -> {len(merged):,} events "
          f"(+{len(fresh):,} new, window {merged[0][0].astimezone(ET):%Y-%m-%d} "
          f"-> {merged[-1][0].astimezone(ET):%Y-%m-%d})")
    if days == 365:
        pickle.dump({"symbols": symbols, "days": 365, "events": merged},
                    (REPO / "optimizer_events.pkl").open("wb"))
        print("optimizer_events.pkl: rewritten from refreshed 365d events")
print("Refresh complete.")
