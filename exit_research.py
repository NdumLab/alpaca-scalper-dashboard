#!/usr/bin/env python3
"""Targeted exit-management research from Cycle 11.

Entry blocking and size scaling mostly reduced current edge. This harness
keeps entries and size intact, then tests small exit-management variants in
the same high-risk contexts.
"""
from __future__ import annotations

import copy

import yaml

from guard_research import FOCUS_SYMBOLS, LATE_MORNING, print_detail, summarize
from loop_evaluate import DEFAULT_SPLIT_DATE, fmt_pf
from trade_diagnostics import DEFAULT_FOCUS_MONTHS, load_events


def rule(**conditions) -> dict:
    return conditions


def with_exit(base: dict, rules: list[dict] | None) -> dict:
    cfg = copy.deepcopy(base)
    bcfg = cfg.setdefault("backtest", {})
    bcfg.pop("research_entry_guard", None)
    bcfg.pop("research_position_scale", None)
    if rules:
        bcfg["research_exit_management"] = {
            "enabled": True,
            "rules": rules,
        }
    else:
        bcfg.pop("research_exit_management", None)
    return cfg


def adjusted_count(row: dict) -> int:
    return row["365"].get("research_exit_adjusted_trades", 0)


def print_exit_row(row: dict, baseline: dict) -> None:
    s365 = row["365"]
    s182 = row["182"]
    print(
        f"{row['label']:<36}"
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
        f"{adjusted_count(row):>8}"
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
            "breakeven after 0.5R all",
            [rule(breakeven_after_r=0.5)],
        ),
        (
            "breakeven after 1.0R all",
            [rule(breakeven_after_r=1.0)],
        ),
        (
            "late morning breakeven 0.5R",
            [rule(entry_minutes=[LATE_MORNING], breakeven_after_r=0.5)],
        ),
        (
            "VWAP>=1.5 breakeven 0.5R",
            [rule(min_vwap_distance_atr=1.5, breakeven_after_r=0.5)],
        ),
        (
            "focus risky breakeven 0.5R",
            [
                rule(symbols=FOCUS_SYMBOLS, min_vwap_distance_atr=1.5, breakeven_after_r=0.5),
                rule(symbols=FOCUS_SYMBOLS, min_volume_ratio=5.0, breakeven_after_r=0.5),
            ],
        ),
        (
            "cut loser 2 bars below -0.25R",
            [rule(cut_loser_after_bars=2, cut_loser_below_r=0.25)],
        ),
        (
            "cut loser 3 bars below entry",
            [rule(cut_loser_after_bars=3, cut_loser_below_r=0.0)],
        ),
        (
            "late morning loser cut 2 bars",
            [rule(entry_minutes=[LATE_MORNING], cut_loser_after_bars=2, cut_loser_below_r=0.25)],
        ),
        (
            "focus risky loser cut 2 bars",
            [
                rule(symbols=FOCUS_SYMBOLS, min_vwap_distance_atr=1.5, cut_loser_after_bars=2, cut_loser_below_r=0.25),
                rule(symbols=FOCUS_SYMBOLS, min_volume_ratio=5.0, cut_loser_after_bars=2, cut_loser_below_r=0.25),
            ],
        ),
        (
            "late morning time stop 3 bars",
            [rule(entry_minutes=[LATE_MORNING], time_stop_bars=3)],
        ),
        (
            "focus risky BE+loser cut",
            [
                rule(
                    symbols=FOCUS_SYMBOLS,
                    min_vwap_distance_atr=1.5,
                    breakeven_after_r=0.5,
                    cut_loser_after_bars=2,
                    cut_loser_below_r=0.25,
                ),
                rule(
                    symbols=FOCUS_SYMBOLS,
                    min_volume_ratio=5.0,
                    breakeven_after_r=0.5,
                    cut_loser_after_bars=2,
                    cut_loser_below_r=0.25,
                ),
            ],
        ),
    ]

    rows = [
        summarize(label, with_exit(base, rules), events_365, events_182, symbols, focus_months, split_date)
        for label, rules in candidates
    ]
    baseline = rows[0]

    print(
        f"Bars365: {len(events_365):,} | Bars182: {len(events_182):,} | "
        f"split: {split_date} | focus: {', '.join(DEFAULT_FOCUS_MONTHS)}"
    )
    print(
        f"{'Candidate':<36}"
        f"{'365 N':>6}{'365PF':>7}{'365Net':>10}{'365Del':>10}"
        f"{'Focus':>10}{'Other':>10}"
        f"{'182 N':>7}{'182PF':>7}{'182Net':>10}{'182Del':>10}"
        f"{'OOS':>10}{'10c182':>11}{'Adj365':>8}"
    )
    print("-" * 151)
    for row in rows:
        print_exit_row(row, baseline)

    print("\nValidation detail")
    for row in rows:
        print_detail(row)
        print(f"  adjusted365={adjusted_count(row)}, adjusted182={row['182'].get('research_exit_adjusted_trades', 0)}")

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
        elif drawdown_ok and improves_focus and row["182"]["net"] >= baseline["182"]["net"] * 0.95:
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


if __name__ == "__main__":
    main()
