#!/usr/bin/env python3
"""Targeted planned macro-event block research.

This is not a broad optimizer. It tests a small set of event-risk profiles
against the accepted technical baseline so event blocking earns its way in
before being enabled at runtime.
"""
from __future__ import annotations

import copy
from datetime import date

import yaml

from backtest import ET, simulate
from loop_evaluate import DEFAULT_SPLIT_DATE, fmt_pf, load_or_fetch_events, with_override

MACRO_EVENTS = [
    # BLS Employment Situation, 08:30 ET.
    ("Employment Situation Dec 2025", "2026-01-09T08:30:00-05:00", "bls-empsit"),
    ("Employment Situation Jan 2026", "2026-02-11T08:30:00-05:00", "bls-empsit"),
    ("Employment Situation Feb 2026", "2026-03-06T08:30:00-05:00", "bls-empsit"),
    ("Employment Situation Mar 2026", "2026-04-03T08:30:00-04:00", "bls-empsit"),
    ("Employment Situation Apr 2026", "2026-05-08T08:30:00-04:00", "bls-empsit"),
    ("Employment Situation May 2026", "2026-06-05T08:30:00-04:00", "bls-empsit"),
    # BLS Consumer Price Index, 08:30 ET.
    ("CPI Dec 2025", "2026-01-13T08:30:00-05:00", "bls-cpi"),
    ("CPI Jan 2026", "2026-02-13T08:30:00-05:00", "bls-cpi"),
    ("CPI Feb 2026", "2026-03-11T08:30:00-04:00", "bls-cpi"),
    ("CPI Mar 2026", "2026-04-10T08:30:00-04:00", "bls-cpi"),
    ("CPI Apr 2026", "2026-05-12T08:30:00-04:00", "bls-cpi"),
    ("CPI May 2026", "2026-06-10T08:30:00-04:00", "bls-cpi"),
    # BLS Producer Price Index, 08:30 ET.
    ("PPI Nov 2025", "2026-01-14T08:30:00-05:00", "bls-ppi"),
    ("PPI Dec 2025", "2026-01-30T08:30:00-05:00", "bls-ppi"),
    ("PPI Jan 2026", "2026-02-27T08:30:00-05:00", "bls-ppi"),
    ("PPI Feb 2026", "2026-03-18T08:30:00-04:00", "bls-ppi"),
    ("PPI Mar 2026", "2026-04-14T08:30:00-04:00", "bls-ppi"),
    ("PPI Apr 2026", "2026-05-13T08:30:00-04:00", "bls-ppi"),
    ("PPI May 2026", "2026-06-11T08:30:00-04:00", "bls-ppi"),
    # FOMC policy decisions, 14:00 ET.
    ("FOMC decision Jan 2026", "2026-01-28T14:00:00-05:00", "federalreserve-fomc"),
    ("FOMC decision Mar 2026", "2026-03-18T14:00:00-04:00", "federalreserve-fomc"),
    ("FOMC decision Apr 2026", "2026-04-29T14:00:00-04:00", "federalreserve-fomc"),
]


def planned_events(pre_minutes: int, post_minutes: int, sources: set[str] | None = None) -> list[dict]:
    selected_sources = sources or {event[2] for event in MACRO_EVENTS}
    return [
        {
            "name": name,
            "time": starts_at,
            "impact": "high",
            "symbols": ["*"],
            "pre_minutes": pre_minutes,
            "post_minutes": post_minutes,
            "source": source,
        }
        for name, starts_at, source in MACRO_EVENTS
        if source in selected_sources
    ]


def cfg_with_events(base: dict, pre_minutes: int, post_minutes: int,
                    sources: set[str] | None = None) -> dict:
    cfg = copy.deepcopy(base)
    cfg["event_risk"] = {
        "enabled": True,
        "block_new_entries": True,
        "min_impact": "high",
        "default_pre_minutes": pre_minutes,
        "default_post_minutes": post_minutes,
        "default_action": "block_entries",
        "planned_events": planned_events(pre_minutes, post_minutes, sources),
    }
    return cfg


def summarize(label: str, cfg: dict, events: list, symbols: list[str],
              split_date: date) -> dict:
    is_events = [e for e in events if e[0].astimezone(ET).date() < split_date]
    oos_events = [e for e in events if e[0].astimezone(ET).date() >= split_date]
    all_stats = simulate(copy.deepcopy(cfg), events, symbols)
    is_stats = simulate(copy.deepcopy(cfg), is_events, symbols)
    oos_stats = simulate(copy.deepcopy(cfg), oos_events, symbols)
    stress_10c = simulate(with_override(cfg, "backtest.slippage_cents", 10), events, symbols)
    return {
        "label": label,
        "all": all_stats,
        "is": is_stats,
        "oos": oos_stats,
        "stress_10c": stress_10c,
    }


def print_row(row: dict, baseline_net: float) -> None:
    stats = row["all"]
    is_stats = row["is"]
    oos_stats = row["oos"]
    stress = row["stress_10c"]
    blocked = stats.get("event_blocked_entries", 0)
    print(
        f"{row['label']:<28}"
        f"{stats['n']:>7}"
        f"{fmt_pf(stats['profit_factor']):>8}"
        f"${stats['max_drawdown']:>9.2f}"
        f"${stats['net']:>+10.2f}"
        f"${stats['net'] - baseline_net:>+9.2f}"
        f"${is_stats['net']:>+9.2f}"
        f"${oos_stats['net']:>+9.2f}"
        f"${stress['net']:>+10.2f}"
        f"{blocked:>10}"
    )


def main() -> None:
    base = yaml.safe_load(open("config.yaml"))
    symbols = base["symbols"]
    events = load_or_fetch_events(base, 182, refresh=False)
    events = [e for e in events if e[1] in symbols]
    split_date = DEFAULT_SPLIT_DATE

    rows = [
        summarize("baseline", copy.deepcopy(base), events, symbols, split_date),
        summarize("macro open 0/90", cfg_with_events(base, 0, 90), events, symbols, split_date),
        summarize("macro open 0/120", cfg_with_events(base, 0, 120), events, symbols, split_date),
        summarize("macro wide 30/120", cfg_with_events(base, 30, 120), events, symbols, split_date),
        summarize("FOMC 60/120 only", cfg_with_events(base, 60, 120, {"federalreserve-fomc"}), events, symbols, split_date),
        summarize("CPI+NFP 0/120", cfg_with_events(base, 0, 120, {"bls-cpi", "bls-empsit"}), events, symbols, split_date),
    ]

    baseline_net = rows[0]["all"]["net"]
    print(f"Bars: {len(events):,} | macro events: {len(MACRO_EVENTS)} | split: {split_date}")
    print(
        f"{'Profile':<28}{'Trades':>7}{'PF':>8}{'Max DD':>10}"
        f"{'Net':>11}{'Delta':>10}{'IS':>10}{'OOS':>10}{'10c Net':>11}{'Blocked':>10}"
    )
    print("-" * 124)
    for row in rows:
        print_row(row, baseline_net)


if __name__ == "__main__":
    main()
