#!/usr/bin/env python3
"""Cycle 15 research: structural profit push via symbol attribution + trailing stops.

Follows the Cycle 12 handoff suggestion: attribution around what actually makes
money, then a small bounded candidate set. Every candidate is screened the
same way as prior cycles: it must preserve or improve ALL of
  - 365-day net,
  - 182-day net,
  - 182-day OOS net (split 2026-04-10),
  - 182-day net under 10c slippage stress,
and keep trade count >= 50 with no increase in per-trade risk or leverage.

Candidates:
  - drop each symbol whose 365-day net is negative (data-driven), plus the
    combo of all such symbols;
  - trailing ATR stop (risk.trail_atr_mult in {1.5, 2.0, 2.5}) replacing the
    fixed 3R take-profit — an existing live-code path never exercised in any
    prior cycle.
"""
from __future__ import annotations

import copy
import pickle
from collections import defaultdict
from datetime import date

import yaml

from backtest import ET, simulate

SPLIT = date(2026, 4, 10)
FOCUS_MONTHS = {"2025-06", "2025-07", "2025-08", "2025-10", "2025-11"}

base = yaml.safe_load(open("config.yaml"))
symbols_all = base["symbols"]

ev365 = pickle.load(open("period_events_365.pkl", "rb"))["events"]
ev182 = pickle.load(open("period_events_182.pkl", "rb"))["events"]
oos182 = [e for e in ev182 if e[0].astimezone(ET).date() >= SPLIT]
print(f"365d bars: {len(ev365):,} | 182d bars: {len(ev182):,} | OOS bars: {len(oos182):,}\n")


def pf_s(v):
    return "inf" if v == float("inf") else f"{v:.2f}"


def run_windows(cfg, drop=()):
    syms = [s for s in symbols_all if s not in drop]
    cfg = copy.deepcopy(cfg)
    cfg["symbols"] = syms

    def filt(evs):
        return [e for e in evs if e[1] in syms] if drop else evs

    s365 = simulate(copy.deepcopy(cfg), filt(ev365), syms)
    s182 = simulate(copy.deepcopy(cfg), filt(ev182), syms)
    soos = simulate(copy.deepcopy(cfg), filt(oos182), syms)
    c10 = copy.deepcopy(cfg)
    c10["backtest"]["slippage_cents"] = 10
    s10 = simulate(c10, filt(ev182), syms)
    focus = sum(t["pnl"] for t in s365["trades"] if str(t["date"])[:7] in FOCUS_MONTHS)
    return {"365": s365, "182": s182, "oos": soos, "10c": s10, "focus": focus}


def report(name, r, baseline=None):
    s365, s182 = r["365"], r["182"]
    line = (f"{name:<34} 365: n={s365['n']:<4} PF={pf_s(s365['profit_factor']):<5} "
            f"net=${s365['net']:>+9.2f} DD=${s365['max_drawdown']:>7.2f} "
            f"focus=${r['focus']:>+8.2f} | 182 net=${s182['net']:>+9.2f} "
            f"OOS=${r['oos']['net']:>+8.2f} 10c=${r['10c']['net']:>+9.2f}")
    if baseline:
        checks = [
            ("365", s365["net"] >= baseline["365"]["net"]),
            ("182", s182["net"] >= baseline["182"]["net"]),
            ("OOS", r["oos"]["net"] >= baseline["oos"]["net"]),
            ("10c", r["10c"]["net"] >= baseline["10c"]["net"]),
            ("n>=50", s365["n"] >= 50),
        ]
        fails = [c for c, ok in checks if not ok]
        line += "  -> " + ("PASS" if not fails else "fail: " + ",".join(fails))
    print(line, flush=True)


print("=" * 130)
baseline = run_windows(base)
report("BASELINE (accepted profile)", baseline)
print("=" * 130)

# ---- attribution on the 365-day baseline ----
tr = baseline["365"]["trades"]
print("\nPer-symbol attribution, 365d (net / focus-month net / rest):")
by_sym = defaultdict(list)
for t in tr:
    by_sym[t["symbol"]].append(t)
neg_syms = []
for sym in sorted(by_sym, key=lambda s: sum(t["pnl"] for t in by_sym[s])):
    rows = by_sym[sym]
    net = sum(t["pnl"] for t in rows)
    focus = sum(t["pnl"] for t in rows if str(t["date"])[:7] in FOCUS_MONTHS)
    wins = sum(1 for t in rows if t["pnl"] > 0)
    print(f"  {sym:<6} n={len(rows):<4} win={wins/len(rows)*100:5.1f}%  "
          f"net=${net:>+9.2f}  focus=${focus:>+8.2f}  rest=${net-focus:>+9.2f}")
    if net < 0:
        neg_syms.append(sym)

print("\nPer-weekday / per-entry-hour / per-exit-reason, 365d:")
for keyfn, label in ((lambda t: t["entry_time"].strftime("%a") if t.get("entry_time") else "?", "weekday"),
                     (lambda t: t.get("entry_hour", "?"), "hour"),
                     (lambda t: t.get("exit_reason", "?"), "exit")):
    agg = defaultdict(list)
    for t in tr:
        agg[keyfn(t)].append(t["pnl"])
    parts = [f"{k}: n={len(v)} ${sum(v):+.0f}" for k, v in sorted(agg.items(), key=lambda kv: -sum(kv[1]))]
    print(f"  {label:<8} " + " | ".join(parts))

print(f"\nNegative-net symbols on 365d: {neg_syms or 'none'}\n")
print("=" * 130)

# ---- candidates ----
for sym in neg_syms:
    report(f"drop {sym}", run_windows(base, drop=(sym,)), baseline)
if len(neg_syms) > 1:
    report(f"drop all: {','.join(neg_syms)}", run_windows(base, drop=tuple(neg_syms)), baseline)

for mult in (1.5, 2.0, 2.5):
    cfg = copy.deepcopy(base)
    cfg["risk"]["trail_atr_mult"] = mult
    report(f"trailing stop {mult}xATR (no fixed TP)", run_windows(cfg), baseline)

print("=" * 130)
print("Done.")
