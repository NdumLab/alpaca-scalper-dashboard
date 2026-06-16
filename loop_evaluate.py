#!/usr/bin/env python3
"""Optimization-loop validation report.

This is intentionally stricter than a headline backtest. It reuses one market
data pull, then checks the current config across holdout, slippage, monthly
consistency, and symbol concentration.
"""
from __future__ import annotations

import argparse
import copy
import math
import pickle
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from backtest import ET, fetch_events, simulate


CACHE_FILE = Path("optimizer_events.pkl")
DEFAULT_SPLIT_DATE = date(2026, 4, 10)


def fmt_pf(value: float) -> str:
    if value == float("inf"):
        return "inf"
    if value is None:
        return "0.00"
    try:
        if math.isnan(value):
            return "0.00"
    except TypeError:
        pass
    return f"{value:.2f}"


def load_or_fetch_events(cfg: dict, days: int, refresh: bool) -> list:
    symbols = cfg["symbols"]
    if CACHE_FILE.exists() and not refresh:
        with CACHE_FILE.open("rb") as f:
            cached = pickle.load(f)
        if cached.get("symbols") == symbols and cached.get("days", 0) >= days:
            return cached["events"]

    end = datetime.now(ET)
    start = end - timedelta(days=days)
    print(f"Fetching {days} days of 1-min bars for {symbols} ...")
    events = fetch_events(cfg, start, end, symbols)
    with CACHE_FILE.open("wb") as f:
        pickle.dump({"symbols": symbols, "days": days, "events": events}, f)
    return events


def resolve_symbols(config_symbols: list[str], include: list[str] | None, exclude: list[str] | None) -> list[str]:
    symbols = list(include or config_symbols)
    excluded = set(exclude or [])
    symbols = [sym for sym in symbols if sym not in excluded]
    if not symbols:
        raise SystemExit("No symbols left after applying --symbols/--exclude-symbols")
    return symbols


def set_nested(cfg: dict, dotted_key: str, value) -> None:
    node = cfg
    keys = dotted_key.split(".")
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value


def with_override(base: dict, dotted_key: str, value) -> dict:
    cfg = copy.deepcopy(base)
    set_nested(cfg, dotted_key, value)
    return cfg


def apply_set_args(cfg: dict, set_args: list[str] | None) -> dict:
    cfg = copy.deepcopy(cfg)
    for item in set_args or []:
        if "=" not in item:
            raise SystemExit(f"--set value must be dotted.path=value, got: {item}")
        dotted_key, raw_value = item.split("=", 1)
        set_nested(cfg, dotted_key, yaml.safe_load(raw_value))
    return cfg


def print_stats(label: str, stats: dict) -> None:
    ret = (stats["end_equity"] / stats["start_equity"] - 1) * 100
    print(
        f"{label:<24}{stats['n']:>7}"
        f"{stats['win_rate']:>7.1f}%"
        f"{fmt_pf(stats['profit_factor']):>8}"
        f"${stats['max_drawdown']:>10.2f}"
        f"${stats['net']:>+11.2f}"
        f"{ret:>9.2f}%"
    )


def by_symbol(stats: dict) -> list[tuple[float, str, list]]:
    rows = defaultdict(list)
    for trade in stats["trades"]:
        rows[trade["symbol"]].append(trade)
    out = []
    for sym, trades in rows.items():
        out.append((sum(t["pnl"] for t in trades), sym, trades))
    out.sort(reverse=True)
    return out


def monthly_net(stats: dict) -> dict[str, float]:
    monthly = defaultdict(float)
    for trade in stats["trades"]:
        monthly[str(trade["date"])[:7]] += trade["pnl"]
    return dict(sorted(monthly.items()))


def reason_rows(stats: dict) -> list[tuple[float, str, list]]:
    rows = defaultdict(list)
    for trade in stats["trades"]:
        rows[trade.get("exit_reason", "unknown")].append(trade)
    out = []
    for reason, trades in rows.items():
        out.append((sum(t["pnl"] for t in trades), reason, trades))
    out.sort(reverse=True)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=182)
    parser.add_argument("--split-date", default=DEFAULT_SPLIT_DATE.isoformat())
    parser.add_argument("--symbols", nargs="*", default=None, help="override config symbols for this report")
    parser.add_argument("--exclude-symbols", nargs="*", default=None, help="remove symbols for this report")
    parser.add_argument("--set", action="append", default=None, help="temporary dotted override, e.g. strategy.mode=momentum")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    base = apply_set_args(yaml.safe_load(open("config.yaml")), args.set)
    events = load_or_fetch_events(base, args.days, args.refresh)
    symbols = resolve_symbols(base["symbols"], args.symbols, args.exclude_symbols)
    base = copy.deepcopy(base)
    base["symbols"] = symbols
    events = [e for e in events if e[1] in symbols]
    split_date = date.fromisoformat(args.split_date)
    is_events = [e for e in events if e[0].astimezone(ET).date() < split_date]
    oos_events = [e for e in events if e[0].astimezone(ET).date() >= split_date]

    print(f"Bars: {len(events):,} | IS bars: {len(is_events):,} | OOS bars: {len(oos_events):,}")
    print(
        "Config: "
        f"risk={base['risk']['risk_per_trade_pct']}%, "
        f"max_position={base['risk']['max_position_pct']}%, "
        f"stop_atr={base['risk']['stop_atr_mult']}, "
        f"tp_r={base['risk']['take_profit_r']}, "
        f"max_daily_trades={base['risk']['max_daily_trades']}, "
        f"slippage={base.get('backtest', {}).get('slippage_cents', 0)}c"
    )

    print("\nHeadline / holdout")
    print(f"{'Window':<24}{'Trades':>7}{'Win%':>8}{'PF':>8}{'Max DD':>11}{'Net':>12}{'Return':>10}")
    print("-" * 80)
    all_stats = simulate(copy.deepcopy(base), events, symbols)
    is_stats = simulate(copy.deepcopy(base), is_events, symbols)
    oos_stats = simulate(copy.deepcopy(base), oos_events, symbols)
    print_stats("All", all_stats)
    print_stats(f"IS < {split_date}", is_stats)
    print_stats(f"OOS >= {split_date}", oos_stats)

    print("\nSlippage stress")
    print(f"{'Slippage':<24}{'Trades':>7}{'Win%':>8}{'PF':>8}{'Max DD':>11}{'Net':>12}{'Return':>10}")
    print("-" * 80)
    for slip in (3, 5, 7, 10):
        stats = simulate(with_override(base, "backtest.slippage_cents", slip), events, symbols)
        print_stats(f"{slip}c", stats)

    print("\nTake-profit fill haircut stress")
    print(f"{'TP haircut':<24}{'Trades':>7}{'Win%':>8}{'PF':>8}{'Max DD':>11}{'Net':>12}{'Return':>10}")
    print("-" * 80)
    for haircut in (0, 1, 3, 5):
        cfg = with_override(base, "backtest.take_profit_haircut_cents", haircut)
        stats = simulate(cfg, events, symbols)
        print_stats(f"{haircut}c", stats)

    print("\nMonthly net, current config")
    print(f"{'Month':<12}{'Net':>12}")
    print("-" * 24)
    for month, net in monthly_net(all_stats).items():
        print(f"{month:<12}${net:>+11.2f}")

    print("\nExit reason, current config")
    print(f"{'Reason':<14}{'Trades':>8}{'Win%':>8}{'Net':>12}")
    print("-" * 42)
    for net, reason, trades in reason_rows(all_stats):
        wins = sum(1 for t in trades if t["pnl"] > 0)
        win_rate = wins / len(trades) * 100 if trades else 0.0
        print(f"{reason:<14}{len(trades):>8}{win_rate:>7.1f}%${net:>+11.2f}")

    print("\nSymbol concentration, current config")
    print(f"{'Symbol':<8}{'Trades':>8}{'Net':>12}{'Share of Net':>14}")
    print("-" * 46)
    total_net = all_stats["net"]
    for net, sym, trades in by_symbol(all_stats):
        share = net / total_net * 100 if total_net else 0.0
        print(f"{sym:<8}{len(trades):>8}${net:>+11.2f}{share:>13.1f}%")

    print("\nSafety flags")
    flags = []
    if all_stats["n"] < 50:
        flags.append("too few trades over full window")
    symbol_rows = by_symbol(all_stats)
    if total_net > 0 and symbol_rows and symbol_rows[0][0] / total_net > 0.40:
        flags.append(f"top symbol contributes {symbol_rows[0][0] / total_net * 100:.1f}% of net")
    stress_10c = simulate(with_override(base, "backtest.slippage_cents", 10), events, symbols)
    if stress_10c["net"] <= 0 or stress_10c["profit_factor"] < 1.05:
        flags.append("10c slippage stress is weak or negative")
    if oos_stats["net"] <= 0 or oos_stats["profit_factor"] < 1.05:
        flags.append("OOS window is weak or negative")
    if all_stats["max_drawdown"] > all_stats["start_equity"] * 0.15:
        flags.append("full-window max drawdown exceeds 15% of starting equity")
    if flags:
        for flag in flags:
            print(f"- {flag}")
    else:
        print("- none")


if __name__ == "__main__":
    main()
