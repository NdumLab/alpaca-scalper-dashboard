#!/usr/bin/env python3
"""Experiment harness for strategy research.

Loads cached 6-month bars, splits in-sample (first 4 months) vs
out-of-sample (last 2 months), runs simulate() with config overrides,
and prints diagnostics. OOS is only for final validation — never tune on it.
"""
from __future__ import annotations

import copy
import pickle
from collections import defaultdict, namedtuple
from datetime import date

import yaml

from backtest import simulate, ET

SPLIT_DATE = date(2026, 4, 10)   # IS: < this date.  OOS: >= this date.

PBar = namedtuple("PBar", "timestamp open high low close volume")


def load_events():
    with open("events_6mo_flat.pkl", "rb") as f:
        flat = pickle.load(f)
    return [(ts, sym, PBar(ts, o, h, l, c, v)) for ts, sym, o, h, l, c, v in flat]


def split(events):
    is_ev = [e for e in events if e[0].astimezone(ET).date() < SPLIT_DATE]
    oos_ev = [e for e in events if e[0].astimezone(ET).date() >= SPLIT_DATE]
    return is_ev, oos_ev


def base_cfg(**overrides):
    cfg = yaml.safe_load(open("config.yaml"))
    for dotted, val in overrides.items():
        node = cfg
        keys = dotted.split(".")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = val
    return cfg


def run(cfg, events, symbols=None):
    symbols = symbols or cfg["symbols"]
    events = [e for e in events if e[1] in symbols]
    return simulate(copy.deepcopy(cfg), events, symbols)


def summary(name, s):
    pf = f"{s['profit_factor']:.2f}" if s["n"] else "—"
    print(f"{name:<34}{s['n']:>5} tr  {s['win_rate']:>5.1f}%  PF {pf:>5}  "
          f"DD ${s['max_drawdown']:>7.2f}  net ${s['net']:>+9.2f}")
    return s


def diagnostics(s, label):
    by_sym, by_hour, by_dow = defaultdict(float), defaultdict(float), defaultdict(float)
    n_sym = defaultdict(int)
    for t in s["trades"]:
        by_sym[t["symbol"]] += t["pnl"]
        n_sym[t["symbol"]] += 1
        by_dow[t["date"].weekday()] += t["pnl"]
    print(f"\n--- {label}: P&L by symbol ---")
    for sym in sorted(by_sym, key=by_sym.get):
        print(f"  {sym:5s} {n_sym[sym]:>4} trades  ${by_sym[sym]:>+9.2f}")
    print(f"--- {label}: P&L by weekday ---")
    for d in range(5):
        nm = ["Mon", "Tue", "Wed", "Thu", "Fri"][d]
        print(f"  {nm}  ${by_dow[d]:>+9.2f}")


if __name__ == "__main__":
    events = load_events()
    is_ev, oos_ev = split(events)
    print(f"IS bars: {len(is_ev):,}   OOS bars: {len(oos_ev):,}")
    cfg = base_cfg()
    s_is = summary("BASELINE in-sample (Dec-Apr)", run(cfg, is_ev))
    s_oos = summary("BASELINE out-of-sample (Apr-Jun)", run(cfg, oos_ev))
    diagnostics(s_is, "IS baseline")
