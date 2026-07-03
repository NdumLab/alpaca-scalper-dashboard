#!/usr/bin/env python3
"""Targeted market-regime research over recent and one-year windows."""
from __future__ import annotations

import copy
import pickle
from datetime import date, timedelta
from pathlib import Path

import yaml

from backtest import ET, simulate
from loop_evaluate import fmt_pf, load_or_fetch_events, with_override


def load_period_events(cfg: dict, days: int) -> list:
    cache = Path(f"period_events_{days}.pkl")
    if cache.exists():
        blob = pickle.load(cache.open("rb"))
        if blob.get("symbols") == cfg["symbols"] and blob.get("days", 0) >= days:
            return blob["events"]
    return load_or_fetch_events(cfg, days, refresh=False)


def with_regime(base: dict, min_passing: int, mixed: str = "block",
                bearish: str = "block", require_vwap: bool = False,
                max_atr_pct: float = 0.0) -> dict:
    cfg = copy.deepcopy(base)
    cfg["market_regime"] = {
        "enabled": True,
        "symbols": ["SPY", "QQQ"],
        "min_symbols_passing": min_passing,
        "min_bars": 30,
        "require_fast_above_slow": True,
        "require_close_above_slow": True,
        "require_close_above_vwap": require_vwap,
        "min_atr_pct": 0,
        "max_atr_pct": max_atr_pct,
        "regime_strategies": {
            "bullish": "momentum",
            "mixed": mixed,
            "bearish": bearish,
        },
    }
    return cfg


def summarize(label: str, cfg: dict, events: list, symbols: list[str],
              split_date: date | None = None) -> dict:
    events = [e for e in events if e[1] in symbols]
    stats = simulate(copy.deepcopy(cfg), events, symbols)
    stress = simulate(with_override(cfg, "backtest.slippage_cents", 10), events, symbols)
    row = {"label": label, "all": stats, "stress_10c": stress}
    if split_date:
        is_events = [e for e in events if e[0].astimezone(ET).date() < split_date]
        oos_events = [e for e in events if e[0].astimezone(ET).date() >= split_date]
        row["is"] = simulate(copy.deepcopy(cfg), is_events, symbols)
        row["oos"] = simulate(copy.deepcopy(cfg), oos_events, symbols)
    return row


def print_rows(title: str, rows: list[dict]) -> None:
    base_net = rows[0]["all"]["net"]
    print("\n" + title)
    has_split = "is" in rows[0]
    if has_split:
        print(f"{'Profile':<30}{'Trades':>7}{'PF':>8}{'DD':>9}{'Net':>10}{'Delta':>10}{'IS':>10}{'OOS':>10}{'10c':>10}{'Blocked':>9}")
        print("-" * 113)
    else:
        print(f"{'Profile':<30}{'Trades':>7}{'PF':>8}{'DD':>9}{'Net':>10}{'Delta':>10}{'10c':>10}{'Blocked':>9}")
        print("-" * 89)
    for row in rows:
        stats = row["all"]
        stress = row["stress_10c"]
        blocked = stats.get("regime_blocked_entries", 0)
        prefix = (
            f"{row['label']:<30}"
            f"{stats['n']:>7}"
            f"{fmt_pf(stats['profit_factor']):>8}"
            f"${stats['max_drawdown']:>8.2f}"
            f"${stats['net']:>+9.2f}"
            f"${stats['net'] - base_net:>+9.2f}"
        )
        if has_split:
            print(prefix + f"${row['is']['net']:>+9.2f}${row['oos']['net']:>+9.2f}${stress['net']:>+9.2f}{blocked:>9}")
        else:
            print(prefix + f"${stress['net']:>+9.2f}{blocked:>9}")


def trailing_days(events: list, days: int) -> list:
    if not events:
        return []
    end = max(e[0].astimezone(ET) for e in events)
    start = end - timedelta(days=days)
    return [e for e in events if e[0].astimezone(ET) >= start]


def main() -> None:
    base = yaml.safe_load(open("config.yaml"))
    symbols = base["symbols"]
    profiles = [
        ("baseline", copy.deepcopy(base)),
        ("2-index bull else block", with_regime(base, 2)),
        ("1-index bull else block", with_regime(base, 1)),
        ("2-index mixed=reversion", with_regime(base, 2, mixed="reversion")),
        ("1-index mixed=reversion", with_regime(base, 1, mixed="reversion")),
        ("2-index + vwap", with_regime(base, 2, require_vwap=True)),
        ("1-index + vwap", with_regime(base, 1, require_vwap=True)),
    ]

    events_365 = load_period_events(base, 365)
    rows_365 = [summarize(label, cfg, events_365, symbols) for label, cfg in profiles]
    print_rows("365-day regime comparison", rows_365)

    events_182 = trailing_days(events_365, 182)
    split_date = date(2026, 4, 10)
    rows_182 = [summarize(label, cfg, events_182, symbols, split_date) for label, cfg in profiles]
    print_rows("182-day regime comparison", rows_182)


if __name__ == "__main__":
    main()
