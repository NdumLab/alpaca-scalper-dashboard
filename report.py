#!/usr/bin/env python3
"""Multi-period backtest report — today / last week / last month / last 6 months.

Usage:
    export APCA_API_KEY_ID="your_key"
    export APCA_API_SECRET_KEY="your_secret"
    python report.py

Fetches 6 months of 1-minute bars ONCE, then replays the exact live-bot
logic over each window so all four results come from the same data pull.
Each window starts fresh at $2,000 (config starting_equity).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import yaml

from backtest import fetch_events, simulate, ET


PERIODS = [
    ("Today",         lambda now: now.replace(hour=0, minute=0, second=0, microsecond=0)),
    ("Last week",     lambda now: now - timedelta(days=7)),
    ("Last month",    lambda now: now - timedelta(days=30)),
    ("Last 6 months", lambda now: now - timedelta(days=182)),
]


def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    symbols = cfg["symbols"]
    now = datetime.now(ET)

    print(f"Fetching 6 months of 1-min bars for {symbols} (one pull, ~may take a minute)...")
    all_events = fetch_events(cfg, now - timedelta(days=182), now, symbols)
    print(f"Got {len(all_events):,} bars.\n")

    rows = []
    for name, start_fn in PERIODS:
        start = start_fn(now)
        window = [e for e in all_events if e[0].astimezone(ET) >= start]
        s = simulate(cfg, window, symbols)
        rows.append((name, s))

    print("=" * 72)
    print(f"{'Period':<15}{'Trades':>7}{'Win %':>8}{'PF':>7}{'Max DD':>10}{'Net P&L':>11}{'Return':>9}")
    print("-" * 72)
    for name, s in rows:
        pf = f"{s['profit_factor']:.2f}" if s["n"] else "—"
        ret = (s["end_equity"] / s["start_equity"] - 1) * 100
        print(f"{name:<15}{s['n']:>7}{s['win_rate']:>7.1f}%{pf:>7}"
              f"{s['max_drawdown']:>9.2f}${s['net']:>+10.2f}{ret:>+8.2f}%")
    print("=" * 72)
    sc = cfg.get("backtest", {}).get("slippage_cents", 0)
    print(f"Caveats: market fills modeled with {sc}c/share slippage (config:")
    print("backtest.slippage_cents); spread/partial fills are not. If stop and")
    print("TP are both touched in one bar, the STOP is assumed to fill first")
    print("(conservative). Short windows ('Today') also")
    print("lose ~30 bars to indicator warmup, so few or zero trades is normal.")
    print("Past performance, simulated or real, does not predict future results.")


if __name__ == "__main__":
    main()
