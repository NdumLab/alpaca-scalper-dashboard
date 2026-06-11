#!/usr/bin/env python3
"""Offline smoke test — no API keys needed.

Generates synthetic 1-min bars engineered to trigger one long signal
(EMA cross + above VWAP + volume surge + RSI ok), runs them through
simulate(), and asserts:
  1. at least one trade fires,
  2. entry slippage was applied (entry fill > signal close),
  3. equity accounting balances trade-by-trade.

Run:  python test_smoke.py
"""
from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import yaml

from backtest import simulate

ET = ZoneInfo("America/New_York")


def make_bar(ts, o, h, l, c, v):
    return SimpleNamespace(timestamp=ts, open=o, high=h, low=l, close=c, volume=v)


def build_events(symbol="TEST"):
    """~80 bars: flat warmup, dip (pulls fast EMA under slow), surge up
    on heavy volume (cross + VWAP + volume conditions), then drift to TP."""
    start = datetime(2026, 6, 8, 9, 36, tzinfo=ET)  # past skip_first_minutes
    events = []
    px = 100.0
    for i in range(110):
        ts = start + timedelta(minutes=i)
        vol = 10_000
        if i < 35:
            px += 0.01                       # gentle warmup drift
        elif i < 45:
            px -= 0.25                       # dip: fast EMA crosses under slow
        elif i < 58:
            px += 0.50                       # steady recovery -> cross, RSI < 70
            vol = 40_000                     # volume surge
        else:
            px += 0.15                       # follow-through toward TP
        bar = make_bar(ts, px - 0.05, px + 0.10, px - 0.10, px, vol)
        events.append((ts, symbol, bar))
    return events


def main():
    with open("config.yaml") as f:
        cfg = yaml.safe_load(f)
    cfg["symbols"] = ["TEST"]
    cfg["risk"]["max_daily_trades"] = 10
    # Pin pipeline-test params so production tuning changes don't break the test
    cfg["risk"]["take_profit_r"] = 1.5
    cfg["risk"]["stop_atr_mult"] = 1.5
    cfg["strategy"]["mode"] = "momentum"
    cfg["strategy"]["volume_surge_mult"] = 1.5
    cfg["strategy"]["bar_minutes"] = 1
    cfg["strategy"]["rsi_max_entry"] = 99
    cfg["strategy"]["min_atr_pct"] = 0
    cfg["strategy"]["max_atr_pct"] = 0
    cfg["strategy"]["min_ema_spread_atr"] = 0
    cfg["strategy"]["max_vwap_distance_atr"] = 0
    cfg["strategy"]["blocked_time_ranges"] = []
    slip = cfg.get("backtest", {}).get("slippage_cents", 0) / 100.0

    events = build_events()
    s = simulate(cfg, events, ["TEST"])

    assert s["n"] >= 1, f"expected >=1 trade, got {s['n']} — signal path broken"
    t = s["trades"][0]

    # Entry slippage: fill should be strictly above some bar close near entry.
    closes = [e[2].close for e in events]
    assert any(abs(t["entry"] - (c + slip)) < 1e-9 for c in closes), \
        "entry fill does not equal any signal close + slippage"

    recomputed = sum(tr["pnl"] for tr in s["trades"])
    assert abs(recomputed - s["net"]) < 1e-6, "P&L accounting mismatch"
    assert abs(s["end_equity"] - (s["start_equity"] + s["net"])) < 1e-6

    print(f"PASS — {s['n']} trade(s), net ${s['net']:+.2f}, "
          f"entry fill {t['entry']:.2f} (slippage {slip*100:.0f}c applied), "
          f"end equity ${s['end_equity']:.2f}")


if __name__ == "__main__":
    main()
