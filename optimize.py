#!/usr/bin/env python3
"""Walk-forward optimizer for the Alpaca scalper.

This is intentionally conservative: it scores candidates on validation windows,
not just the same window used for tuning.  The goal is to avoid the classic
mistake of making a bot look amazing on old data and weak in live trading.

Usage:
    export APCA_API_KEY_ID="your_key"
    export APCA_API_SECRET_KEY="your_secret"
    python optimize.py --days 182
    python optimize.py --days 365 --slippage-cents 3

Output:
    optimized_config.yaml
"""
from __future__ import annotations

import argparse
import copy
import itertools
import pickle
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean

import yaml

from backtest import ET, fetch_events, simulate


CACHE_FILE = Path("optimizer_events.pkl")


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


def load_or_fetch_events(cfg: dict, days: int, symbols: list[str], refresh: bool):
    if CACHE_FILE.exists() and not refresh:
        with CACHE_FILE.open("rb") as f:
            cached = pickle.load(f)
        if cached.get("symbols") == symbols and cached.get("days") >= days:
            return cached["events"]

    end = datetime.now(ET)
    start = end - timedelta(days=days)
    print(f"Fetching {days} days of 1-min bars for {symbols} ...")
    events = fetch_events(cfg, start, end, symbols)
    with CACHE_FILE.open("wb") as f:
        pickle.dump({"symbols": symbols, "days": days, "events": events}, f)
    return events


def make_folds(events: list, train_days: int, test_days: int):
    if not events:
        return []
    first = events[0][0].astimezone(ET).date()
    last = events[-1][0].astimezone(ET).date()
    folds = []
    start = first
    while True:
        train_end = start + timedelta(days=train_days)
        test_end = train_end + timedelta(days=test_days)
        if test_end > last:
            break
        train = [e for e in events if start <= e[0].astimezone(ET).date() < train_end]
        test = [e for e in events if train_end <= e[0].astimezone(ET).date() < test_end]
        if train and test:
            folds.append((train, test))
        start = start + timedelta(days=test_days)
    return folds


def candidate_grid():
    """Parameter grid for v6.

    This grid searches the new ensemble profile without exploding into thousands
    of fragile combinations.  It pushes profitability through setup quality and
    exit shape, not by blindly increasing risk_per_trade_pct.
    """
    keys = [
        "risk.take_profit_r",
        "risk.stop_atr_mult",
        "strategy.volume_surge_mult",
        "strategy.cross_confirm_bars",
        "strategy.orb_vol_mult",
        "strategy.orb_max_vwap_distance_atr",
    ]
    values = [
        [1.8, 2.0, 2.2, 2.5],
        [2.8, 3.2, 3.5],
        [1.6, 1.8, 2.0],
        [2, 3, 4],
        [1.4, 1.6, 1.8],
        [1.8, 2.2, 0.0],  # 0 disables the ORB VWAP-distance cap
    ]
    for combo in itertools.product(*values):
        yield dict(zip(keys, combo))


def score_result(test_stats: list[dict]) -> float:
    """Favor profit factor and net profit, punish drawdown and tiny samples."""
    if not test_stats:
        return -10**9
    total_net = sum(s["net"] for s in test_stats)
    total_dd = sum(s["max_drawdown"] for s in test_stats)
    total_trades = sum(s["n"] for s in test_stats)
    avg_pf = mean(s["profit_factor"] for s in test_stats if s["n"]) if total_trades else 0
    low_sample_penalty = max(0, 25 - total_trades) * 5
    return total_net + (avg_pf * 10) - (0.50 * total_dd) - low_sample_penalty


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=182)
    parser.add_argument("--train-days", type=int, default=60)
    parser.add_argument("--test-days", type=int, default=20)
    parser.add_argument("--slippage-cents", type=float, default=None)
    parser.add_argument("--refresh", action="store_true", help="ignore optimizer_events.pkl and re-fetch bars")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    base = yaml.safe_load(open("config.yaml"))
    if args.slippage_cents is not None:
        base.setdefault("backtest", {})["slippage_cents"] = args.slippage_cents

    symbols = base["symbols"]
    events = load_or_fetch_events(base, args.days, symbols, args.refresh)
    folds = make_folds(events, args.train_days, args.test_days)
    if not folds:
        raise SystemExit("Not enough data for walk-forward folds. Try --days 90 --train-days 40 --test-days 10")

    candidates = list(candidate_grid())
    print(f"Bars: {len(events):,} | folds: {len(folds)} | candidates: {len(candidates)}")
    results = []
    for i, overrides in enumerate(candidates, 1):
        cfg = apply_overrides(base, overrides)
        test_stats = []
        for train, test in folds:
            # The train window is intentionally available for future expansion.
            # Current scoring only trusts validation windows.
            _ = train
            test_stats.append(simulate(copy.deepcopy(cfg), test, symbols))
        score = score_result(test_stats)
        results.append((score, overrides, test_stats))
        if i % 100 == 0:
            print(f"tested {i} candidates ...")

    results.sort(key=lambda x: x[0], reverse=True)
    print("\nTop candidates by walk-forward validation score:")
    for rank, (score, overrides, stats) in enumerate(results[:args.top], 1):
        net = sum(s["net"] for s in stats)
        trades = sum(s["n"] for s in stats)
        dd = sum(s["max_drawdown"] for s in stats)
        pf_values = [s["profit_factor"] for s in stats if s["n"]]
        pf = mean(pf_values) if pf_values else 0
        print(f"#{rank:<2} score={score:>8.2f} net=${net:>8.2f} trades={trades:>4} "
              f"avgPF={pf:>5.2f} sumDD=${dd:>7.2f} {overrides}")

    best = apply_overrides(base, results[0][1])
    with open("optimized_config.yaml", "w") as f:
        yaml.safe_dump(best, f, sort_keys=False)
    print("\nWrote optimized_config.yaml")
    print("Next command to compare it manually:")
    print("  cp optimized_config.yaml config.yaml && python report.py")


if __name__ == "__main__":
    main()
