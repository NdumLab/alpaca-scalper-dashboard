#!/usr/bin/env python3
"""Compare profit-push profiles on the same historical pull.

Usage:
    export APCA_API_KEY_ID="your_key"
    export APCA_API_SECRET_KEY="your_secret"
    python profit_research.py --days 182
    python profit_research.py --days 182 --slippage-cents 5

This is the fastest way to answer: "Did v6 actually improve over v5 style?"
It fetches bars once, then tests multiple profiles using the same data window.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timedelta

import yaml

from backtest import ET, fetch_events, simulate


def set_dotted(cfg: dict, dotted: str, value):
    node = cfg
    keys = dotted.split(".")
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value


def apply_overrides(base: dict, overrides: dict) -> dict:
    cfg = copy.deepcopy(base)
    for key, value in overrides.items():
        set_dotted(cfg, key, value)
    return cfg


def event_subset(events: list, symbols: list[str]) -> list:
    keep = set(symbols)
    return [e for e in events if e[1] in keep]


def fmt_pf(value: float, n: int) -> str:
    if not n:
        return "—"
    if value == float("inf"):
        return "inf"
    return f"{value:.2f}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=182)
    parser.add_argument("--slippage-cents", type=float, default=None)
    args = parser.parse_args()

    base = yaml.safe_load(open("config.yaml"))
    if args.slippage_cents is not None:
        base.setdefault("backtest", {})["slippage_cents"] = args.slippage_cents

    end = datetime.now(ET)
    start = end - timedelta(days=args.days)
    symbols = base["symbols"]
    print(f"Fetching {args.days} days of bars for {symbols} ...")
    events = fetch_events(base, start, end, symbols)
    print(f"Got {len(events):,} bars. Running profiles...\n")

    profiles = [
        (
            "v5-style momentum",
            {
                "symbols": ["SPY", "QQQ", "AAPL", "NVDA", "AMD", "TSLA"],
                "strategy.mode": "momentum",
                "strategy.volume_surge_mult": 2.0,
                "strategy.rsi_max_entry": 70,
                "risk.stop_atr_mult": 3.5,
                "risk.take_profit_r": 2.0,
                "risk.max_daily_trades": 6,
            },
        ),
        (
            "v6 ensemble default",
            {},
        ),
        (
            "v6 tighter ORB",
            {
                "strategy.orb_vol_mult": 1.8,
                "strategy.orb_max_vwap_distance_atr": 1.8,
                "risk.stop_atr_mult": 3.2,
                "risk.take_profit_r": 2.2,
            },
        ),
        (
            "v6 bigger target",
            {
                "risk.stop_atr_mult": 3.2,
                "risk.take_profit_r": 2.5,
                "strategy.volume_surge_mult": 1.8,
            },
        ),
        (
            "v6 faster exits",
            {
                "risk.stop_atr_mult": 2.8,
                "risk.take_profit_r": 2.0,
                "strategy.volume_surge_mult": 1.6,
                "strategy.orb_vol_mult": 1.6,
            },
        ),
    ]

    rows = []
    for name, overrides in profiles:
        cfg = apply_overrides(base, overrides)
        syms = cfg.get("symbols", symbols)
        ev = event_subset(events, syms)
        s = simulate(cfg, ev, syms)
        rows.append((name, s))

    print("=" * 86)
    print(f"{'Profile':<22}{'Trades':>7}{'Win %':>8}{'PF':>8}{'Max DD':>11}{'Net P&L':>12}{'Return':>10}")
    print("-" * 86)
    for name, s in rows:
        ret = (s["end_equity"] / s["start_equity"] - 1) * 100
        print(f"{name:<22}{s['n']:>7}{s['win_rate']:>7.1f}%{fmt_pf(s['profit_factor'], s['n']):>8}"
              f"${s['max_drawdown']:>10.2f}${s['net']:>+11.2f}{ret:>+9.2f}%")
    print("=" * 86)
    print("Winner should not be selected by Net P&L only. Prefer the profile that")
    print("stays profitable at 3c and 5c slippage, with acceptable drawdown.")


if __name__ == "__main__":
    main()
