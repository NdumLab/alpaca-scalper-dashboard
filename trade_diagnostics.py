#!/usr/bin/env python3
"""Trade-level diagnostics for loss-cluster research.

This report is deliberately observational. It compares known weak months
against the rest of the sample and tags entries with local setup context plus
simple SPY/QQ state at the entry bar. It does not propose or apply a runtime
profile change.
"""
from __future__ import annotations

import argparse
import copy
import math
import pickle
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from backtest import ET, _resample_events, fetch_events, simulate
from indicators import Bar, SymbolIndicators

DEFAULT_FOCUS_MONTHS = ["2025-06", "2025-07", "2025-08", "2025-10", "2025-11"]


def fmt_money(value: float) -> str:
    return f"${value:+.2f}"


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


def load_events(cfg: dict, days: int, refresh: bool) -> list:
    symbols = cfg["symbols"]
    cache = Path(f"period_events_{days}.pkl")
    if cache.exists() and not refresh:
        with cache.open("rb") as f:
            blob = pickle.load(f)
        if blob.get("symbols") == symbols and blob.get("days", 0) >= days:
            return blob["events"]

    end = datetime.now(ET)
    start = end - timedelta(days=days)
    print(f"Fetching {days} days of 1-min bars for {symbols} ...")
    events = fetch_events(cfg, start, end, symbols)
    with cache.open("wb") as f:
        pickle.dump({"symbols": symbols, "days": days, "events": events}, f)
    return events


def summarize(rows: list[dict]) -> dict:
    wins = [t for t in rows if t["pnl"] > 0]
    losses = [t for t in rows if t["pnl"] <= 0]
    gross_w = sum(t["pnl"] for t in wins)
    gross_l = abs(sum(t["pnl"] for t in losses))
    return {
        "n": len(rows),
        "win_rate": len(wins) / len(rows) * 100 if rows else 0.0,
        "pf": gross_w / gross_l if gross_l else (float("inf") if gross_w else 0.0),
        "net": sum(t["pnl"] for t in rows),
        "avg": sum(t["pnl"] for t in rows) / len(rows) if rows else 0.0,
    }


def print_group(title: str, groups: dict[str, list[dict]], limit: int | None = None) -> None:
    rows = []
    for key, trades in groups.items():
        s = summarize(trades)
        rows.append((s["net"], key, s))
    rows.sort()
    if limit:
        rows = rows[:limit]

    print(f"\n{title}")
    print(f"{'Key':<24}{'Trades':>8}{'Win%':>8}{'PF':>8}{'Net':>12}{'Avg':>10}")
    print("-" * 70)
    for _, key, s in rows:
        print(
            f"{key:<24}{s['n']:>8}{s['win_rate']:>7.1f}%"
            f"{fmt_pf(s['pf']):>8}{fmt_money(s['net']):>12}{fmt_money(s['avg']):>10}"
        )


def group_by(rows: list[dict], keyfn) -> dict[str, list[dict]]:
    out = defaultdict(list)
    for row in rows:
        out[str(keyfn(row))].append(row)
    return out


def month_key(trade: dict) -> str:
    return str(trade["date"])[:7]


def setup_family(trade: dict) -> str:
    reason = trade.get("reason") or ""
    if reason.startswith("ORB") or "ORB ensemble" in reason:
        return "orb"
    if reason.startswith("reversion") or "REVERSION ensemble" in reason:
        return "reversion"
    if reason.startswith("EMA") or "MOMENTUM ensemble" in reason:
        return "momentum"
    return "unknown"


def time_bucket(trade: dict) -> str:
    minute = trade.get("entry_minute")
    if minute is None:
        return "unknown"
    if minute < 10 * 60 + 30:
        return "09:35-10:29"
    if minute < 12 * 60:
        return "10:30-11:59"
    if minute < 14 * 60:
        return "12:00-13:59"
    return "14:00-15:35"


def numeric_bucket(value: float | None, breaks: list[float], labels: list[str]) -> str:
    if value is None:
        return "unknown"
    for cutoff, label in zip(breaks, labels):
        if value < cutoff:
            return label
    return labels[-1]


def atr_bucket(trade: dict) -> str:
    value = trade.get("entry_atr_pct")
    if value is None:
        return "unknown"
    return numeric_bucket(value * 100, [0.2, 0.4, 0.8], ["<0.20%", "0.20-0.39%", "0.40-0.79%", ">=0.80%"])


def volume_bucket(trade: dict) -> str:
    return numeric_bucket(trade.get("entry_volume_ratio"), [2.0, 3.0, 5.0], ["<2x", "2-2.99x", "3-4.99x", ">=5x"])


def vwap_bucket(trade: dict) -> str:
    return numeric_bucket(trade.get("entry_vwap_distance_atr"), [0.5, 1.0, 1.5, 2.0], ["<0.5 ATR", "0.5-0.99 ATR", "1.0-1.49 ATR", "1.5-1.99 ATR", ">=2 ATR"])


def _spy_qqq_snapshot(indicators: dict[str, SymbolIndicators]) -> dict:
    details = {}
    pass_count = 0
    above_vwap = 0
    fast_above_slow = 0
    for symbol in ("SPY", "QQQ"):
        ind = indicators.get(symbol)
        close = getattr(ind, "last_close", None)
        ready = (
            ind is not None and ind.bars_seen >= 30 and close is not None
            and ind.ema_fast.value is not None and ind.ema_slow.value is not None
            and ind.vwap.value is not None and ind.atr.value is not None
        )
        if not ready:
            details[symbol] = {"ready": False}
            continue
        favs = ind.ema_fast.value > ind.ema_slow.value
        avwap = close > ind.vwap.value
        slow = close > ind.ema_slow.value
        passing = favs and avwap and slow
        pass_count += int(passing)
        above_vwap += int(avwap)
        fast_above_slow += int(favs)
        details[symbol] = {
            "ready": True,
            "passing": passing,
            "above_vwap": avwap,
            "fast_above_slow": favs,
            "close_above_slow": slow,
            "atr_pct": ind.atr.value / close if close > 0 else None,
        }
    return {
        "broad_pass_count": pass_count,
        "broad_above_vwap_count": above_vwap,
        "broad_fast_above_slow_count": fast_above_slow,
        "broad_details": details,
    }


def attach_broad_context(cfg: dict, events: list, symbols: list[str], trades: list[dict]) -> None:
    by_key = defaultdict(list)
    for idx, trade in enumerate(trades):
        entry_time = trade.get("entry_time")
        if entry_time is None:
            continue
        by_key[(entry_time, trade["symbol"])].append(idx)
    if not by_key:
        return

    replay_events = _resample_events(events, cfg["strategy"].get("bar_minutes", 1))
    indicators = {s: SymbolIndicators.from_config(cfg["strategy"]) for s in symbols}
    cur_day = None
    for ts, sym, raw in replay_events:
        ts_et = ts.astimezone(ET)
        if ts_et.date() != cur_day:
            cur_day = ts_et.date()
            for ind in indicators.values():
                ind.vwap.reset()

        bar = Bar(ts, raw.open, raw.high, raw.low, raw.close, raw.volume)
        indicators[sym].update(bar)

        for idx in by_key.get((ts_et, sym), []):
            trades[idx].update(_spy_qqq_snapshot(indicators))


def print_worst_trades(rows: list[dict], count: int) -> None:
    print(f"\nWorst {count} focus-month trades")
    print(f"{'Entry':<22}{'Sym':<6}{'Exit':<12}{'P&L':>10}{'Setup':>11}{'Broad':>8}")
    print("-" * 76)
    for trade in sorted(rows, key=lambda t: t["pnl"])[:count]:
        entry = trade.get("entry_time")
        entry_s = entry.strftime("%Y-%m-%d %H:%M") if entry else str(trade["date"])
        broad = trade.get("broad_pass_count", "na")
        print(
            f"{entry_s:<22}{trade['symbol']:<6}{trade.get('exit_reason', ''):<12}"
            f"{fmt_money(trade['pnl']):>10}{setup_family(trade):>11}{str(broad):>8}"
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--focus-months", nargs="*", default=DEFAULT_FOCUS_MONTHS)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    cfg = yaml.safe_load(open("config.yaml"))
    symbols = cfg["symbols"]
    events = load_events(cfg, args.days, args.refresh)
    events = [e for e in events if e[1] in symbols]
    stats = simulate(copy.deepcopy(cfg), events, symbols)
    trades = stats["trades"]
    attach_broad_context(cfg, events, symbols, trades)

    focus_set = set(args.focus_months)
    focus = [t for t in trades if month_key(t) in focus_set]
    non_focus = [t for t in trades if month_key(t) not in focus_set]

    print(f"Bars: {len(events):,} | trades: {len(trades)} | days: {args.days}")
    print(f"Focus months: {', '.join(args.focus_months)}")
    print(
        f"Headline: net {fmt_money(stats['net'])}, PF {fmt_pf(stats['profit_factor'])}, "
        f"max DD ${stats['max_drawdown']:.2f}"
    )

    print_group("Monthly net", group_by(trades, month_key))
    print_group("Focus vs rest", {"focus months": focus, "other months": non_focus})

    for label, rows in (("Focus months", focus), ("Other months", non_focus)):
        print_group(f"{label} by symbol", group_by(rows, lambda t: t["symbol"]))
        print_group(f"{label} by entry time", group_by(rows, time_bucket))
        print_group(f"{label} by setup", group_by(rows, setup_family))
        print_group(f"{label} by exit reason", group_by(rows, lambda t: t.get("exit_reason", "unknown")))
        print_group(f"{label} by weekday", group_by(rows, lambda t: t["date"].strftime("%A")))
        print_group(f"{label} by entry ATR%", group_by(rows, atr_bucket))
        print_group(f"{label} by volume surge", group_by(rows, volume_bucket))
        print_group(f"{label} by VWAP distance", group_by(rows, vwap_bucket))
        print_group(
            f"{label} by SPY/QQQ pass count",
            group_by(rows, lambda t: t.get("broad_pass_count", "unknown")),
        )
        print_group(
            f"{label} by SPY/QQQ above-VWAP count",
            group_by(rows, lambda t: t.get("broad_above_vwap_count", "unknown")),
        )

    print_worst_trades(focus, 12)


if __name__ == "__main__":
    main()
