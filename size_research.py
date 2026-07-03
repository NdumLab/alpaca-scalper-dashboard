#!/usr/bin/env python3
"""Targeted position-size research from Cycle 10.

Hard entry guards helped some weak-month clusters but damaged the accepted
recent edge. This harness tests whether smaller size in those contexts keeps
the trades while improving the risk profile.
"""
from __future__ import annotations

import copy

import yaml

from guard_research import (
    FOCUS_SYMBOLS,
    LATE_MORNING,
    focus_net,
    fmt_pf,
    negative_months,
    other_net,
    print_detail,
    summarize,
    top_symbol_share,
)
from loop_evaluate import DEFAULT_SPLIT_DATE
from trade_diagnostics import DEFAULT_FOCUS_MONTHS, load_events


def rule(multiplier: float, **conditions) -> dict:
    return {"multiplier": multiplier, **conditions}


def with_scale(base: dict, rules: list[dict] | None) -> dict:
    cfg = copy.deepcopy(base)
    cfg.setdefault("backtest", {}).pop("research_entry_guard", None)
    if rules:
        cfg.setdefault("backtest", {})["research_position_scale"] = {
            "enabled": True,
            "rules": rules,
        }
    else:
        cfg.setdefault("backtest", {}).pop("research_position_scale", None)
    return cfg


def scaled_count(row: dict) -> int:
    return row["365"].get("research_scaled_entries", 0)


def print_size_row(row: dict, baseline: dict) -> None:
    s365 = row["365"]
    s182 = row["182"]
    print(
        f"{row['label']:<34}"
        f"{s365['n']:>6}"
        f"{fmt_pf(s365['profit_factor']):>7}"
        f"${s365['net']:>+9.2f}"
        f"${s365['net'] - baseline['365']['net']:>+9.2f}"
        f"${row['focus_net']:>+9.2f}"
        f"${row['other_net']:>+9.2f}"
        f"{s182['n']:>7}"
        f"{fmt_pf(s182['profit_factor']):>7}"
        f"${s182['net']:>+9.2f}"
        f"${s182['net'] - baseline['182']['net']:>+9.2f}"
        f"${row['oos']['net']:>+9.2f}"
        f"${row['10c']['net']:>+10.2f}"
        f"{scaled_count(row):>8}"
    )


def main() -> None:
    base = yaml.safe_load(open("config.yaml"))
    symbols = base["symbols"]
    focus_months = set(DEFAULT_FOCUS_MONTHS)
    events_365 = [e for e in load_events(base, 365, refresh=False) if e[1] in symbols]
    events_182 = [e for e in load_events(base, 182, refresh=False) if e[1] in symbols]
    split_date = DEFAULT_SPLIT_DATE

    candidates = [
        ("baseline", None),
        (
            "half size VWAP>=1.5 ATR",
            [rule(0.50, min_vwap_distance_atr=1.5)],
        ),
        (
            "half size volume>=5x",
            [rule(0.50, min_volume_ratio=5.0)],
        ),
        (
            "half size late morning",
            [rule(0.50, entry_minutes=[LATE_MORNING])],
        ),
        (
            "half size VWAP>=1.5 or volume>=5",
            [
                rule(0.50, min_vwap_distance_atr=1.5),
                rule(0.50, min_volume_ratio=5.0),
            ],
        ),
        (
            "half size focus symbols risky",
            [
                rule(0.50, symbols=FOCUS_SYMBOLS, min_vwap_distance_atr=1.5),
                rule(0.50, symbols=FOCUS_SYMBOLS, min_volume_ratio=5.0),
            ],
        ),
        (
            "quarter size focus symbols risky",
            [
                rule(0.25, symbols=FOCUS_SYMBOLS, min_vwap_distance_atr=1.5),
                rule(0.25, symbols=FOCUS_SYMBOLS, min_volume_ratio=5.0),
            ],
        ),
        (
            "half size focus risky+late",
            [
                rule(0.50, symbols=FOCUS_SYMBOLS, min_vwap_distance_atr=1.5),
                rule(0.50, symbols=FOCUS_SYMBOLS, min_volume_ratio=5.0),
                rule(0.50, symbols=FOCUS_SYMBOLS, entry_minutes=[LATE_MORNING]),
            ],
        ),
        (
            "half size high ATR>=0.40%",
            [rule(0.50, min_atr_pct=0.004)],
        ),
    ]

    rows = [
        summarize(label, with_scale(base, rules), events_365, events_182, symbols, focus_months, split_date)
        for label, rules in candidates
    ]
    baseline = rows[0]

    print(
        f"Bars365: {len(events_365):,} | Bars182: {len(events_182):,} | "
        f"split: {split_date} | focus: {', '.join(DEFAULT_FOCUS_MONTHS)}"
    )
    print(
        f"{'Candidate':<34}"
        f"{'365 N':>6}{'365PF':>7}{'365Net':>10}{'365Del':>10}"
        f"{'Focus':>10}{'Other':>10}"
        f"{'182 N':>7}{'182PF':>7}{'182Net':>10}{'182Del':>10}"
        f"{'OOS':>10}{'10c182':>11}{'Scaled':>8}"
    )
    print("-" * 149)
    for row in rows:
        print_size_row(row, baseline)

    print("\nValidation detail")
    for row in rows:
        print_detail(row)
        print(f"  scaled365={scaled_count(row)}, scaled182={row['182'].get('research_scaled_entries', 0)}")

    viable = []
    near_misses = []
    for row in rows[1:]:
        improves_365 = row["365"]["net"] > baseline["365"]["net"]
        improves_focus = row["focus_net"] > baseline["focus_net"]
        preserves_182 = row["182"]["net"] >= baseline["182"]["net"]
        preserves_oos = row["oos"]["net"] >= baseline["oos"]["net"]
        stress_ok = row["10c"]["net"] >= baseline["10c"]["net"]
        drawdown_ok = row["365"]["max_drawdown"] <= baseline["365"]["max_drawdown"]
        if improves_365 and improves_focus and preserves_182 and preserves_oos and stress_ok:
            viable.append(row["label"])
        elif drawdown_ok and improves_focus and row["182"]["net"] >= baseline["182"]["net"] * 0.90:
            near_misses.append(row["label"])

    print("\nDecision screen")
    if viable:
        print("Candidates passing strict screen:")
        for label in viable:
            print(f"- {label}")
    else:
        print("No candidate passed the strict screen.")
    if near_misses:
        print("Near misses worth future refinement:")
        for label in near_misses:
            print(f"- {label}")

    # Keep imported helpers referenced explicitly so static checks show the
    # same metrics this harness is expected to preserve.
    _ = focus_net, other_net, negative_months, top_symbol_share


if __name__ == "__main__":
    main()
