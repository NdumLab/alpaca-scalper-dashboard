#!/usr/bin/env python3
"""Targeted entry-guard research from Cycle 9 diagnostics.

This is a small candidate set, not an optimizer. It tests whether blocking
specific momentum-entry contexts improves the one-year weak months without
damaging the accepted trailing 182-day edge.
"""
from __future__ import annotations

import copy
from collections import defaultdict
from datetime import date

import yaml

from backtest import ET, simulate
from loop_evaluate import DEFAULT_SPLIT_DATE, fmt_pf, with_override
from trade_diagnostics import DEFAULT_FOCUS_MONTHS, load_events


LATE_MORNING = [10 * 60 + 30, 11 * 60 + 59]
FOCUS_SYMBOLS = ["AAPL", "AMZN", "AMD"]


def with_guard(base: dict, guard: dict | None) -> dict:
    cfg = copy.deepcopy(base)
    if guard:
        cfg.setdefault("backtest", {})["research_entry_guard"] = {
            "enabled": True,
            **guard,
        }
    else:
        cfg.setdefault("backtest", {}).pop("research_entry_guard", None)
    return cfg


def focus_net(stats: dict, focus_months: set[str]) -> float:
    return sum(t["pnl"] for t in stats["trades"] if str(t["date"])[:7] in focus_months)


def other_net(stats: dict, focus_months: set[str]) -> float:
    return sum(t["pnl"] for t in stats["trades"] if str(t["date"])[:7] not in focus_months)


def negative_months(stats: dict) -> tuple[int, str, float]:
    monthly = defaultdict(float)
    for trade in stats["trades"]:
        monthly[str(trade["date"])[:7]] += trade["pnl"]
    negatives = [net for net in monthly.values() if net < 0]
    if not monthly:
        return 0, "", 0.0
    worst_month, worst_net = min(monthly.items(), key=lambda item: item[1])
    return len(negatives), worst_month, worst_net


def top_symbol_share(stats: dict) -> float:
    total = stats["net"]
    if total <= 0:
        return 0.0
    rows = defaultdict(float)
    for trade in stats["trades"]:
        rows[trade["symbol"]] += trade["pnl"]
    return max(rows.values()) / total * 100 if rows else 0.0


def summarize(label: str, cfg: dict, events_365: list, events_182: list,
              symbols: list[str], focus_months: set[str], split_date: date) -> dict:
    stats_365 = simulate(copy.deepcopy(cfg), events_365, symbols)
    stats_182 = simulate(copy.deepcopy(cfg), events_182, symbols)
    is_events = [e for e in events_182 if e[0].astimezone(ET).date() < split_date]
    oos_events = [e for e in events_182 if e[0].astimezone(ET).date() >= split_date]
    stats_is = simulate(copy.deepcopy(cfg), is_events, symbols)
    stats_oos = simulate(copy.deepcopy(cfg), oos_events, symbols)
    stats_10c = simulate(with_override(cfg, "backtest.slippage_cents", 10), events_182, symbols)
    neg_count, worst_month, worst_net = negative_months(stats_365)
    return {
        "label": label,
        "365": stats_365,
        "182": stats_182,
        "is": stats_is,
        "oos": stats_oos,
        "10c": stats_10c,
        "focus_net": focus_net(stats_365, focus_months),
        "other_net": other_net(stats_365, focus_months),
        "negative_months": neg_count,
        "worst_month": worst_month,
        "worst_net": worst_net,
        "top_symbol_share": top_symbol_share(stats_365),
        "blocked_365": stats_365.get("research_guard_blocked_entries", 0),
        "blocked_182": stats_182.get("research_guard_blocked_entries", 0),
    }


def print_row(row: dict, baseline: dict) -> None:
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
        f"{row['blocked_365']:>8}"
    )


def print_detail(row: dict) -> None:
    print(
        f"- {row['label']}: 365 maxDD ${row['365']['max_drawdown']:.2f}, "
        f"negative_months={row['negative_months']}, "
        f"worst={row['worst_month']} {row['worst_net']:+.2f}, "
        f"top_symbol_share={row['top_symbol_share']:.1f}%, "
        f"182 IS ${row['is']['net']:+.2f}, OOS ${row['oos']['net']:+.2f}, "
        f"10c ${row['10c']['net']:+.2f}, blocked182={row['blocked_182']}"
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
        ("cap VWAP distance <= 1.5 ATR", {"max_vwap_distance_atr": 1.5}),
        ("cap volume surge <= 5x", {"max_volume_ratio": 5.0}),
        ("block 10:30-11:59 entries", {"blocked_entry_minutes": [LATE_MORNING]}),
        (
            "cap VWAP<=1.5 + volume<=5x",
            {"max_vwap_distance_atr": 1.5, "max_volume_ratio": 5.0},
        ),
        (
            "AAPL/AMZN/AMD cap VWAP+volume",
            {
                "symbols": FOCUS_SYMBOLS,
                "max_vwap_distance_atr": 1.5,
                "max_volume_ratio": 5.0,
            },
        ),
        (
            "AAPL/AMZN/AMD cap+late block",
            {
                "symbols": FOCUS_SYMBOLS,
                "max_vwap_distance_atr": 1.5,
                "max_volume_ratio": 5.0,
                "blocked_entry_minutes": [LATE_MORNING],
            },
        ),
    ]

    rows = [
        summarize(label, with_guard(base, guard), events_365, events_182, symbols, focus_months, split_date)
        for label, guard in candidates
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
        f"{'OOS':>10}{'10c182':>11}{'Block365':>8}"
    )
    print("-" * 149)
    for row in rows:
        print_row(row, baseline)

    print("\nValidation detail")
    for row in rows:
        print_detail(row)

    viable = []
    for row in rows[1:]:
        improves_365 = row["365"]["net"] > baseline["365"]["net"]
        improves_focus = row["focus_net"] > baseline["focus_net"]
        preserves_182 = row["182"]["net"] >= baseline["182"]["net"]
        preserves_oos = row["oos"]["net"] >= baseline["oos"]["net"]
        stress_ok = row["10c"]["net"] >= baseline["10c"]["net"]
        if improves_365 and improves_focus and preserves_182 and preserves_oos and stress_ok:
            viable.append(row["label"])

    print("\nDecision screen")
    if viable:
        print("Candidates passing strict screen:")
        for label in viable:
            print(f"- {label}")
    else:
        print("No candidate passed the strict screen.")


if __name__ == "__main__":
    main()
