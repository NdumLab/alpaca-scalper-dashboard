#!/usr/bin/env python3
"""Offline ORB smoke test — proves v6 ensemble can fire an ORB signal."""
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
    start = datetime(2026, 6, 8, 9, 30, tzinfo=ET)
    events = []
    px = 100.0
    for i in range(90):
        ts = start + timedelta(minutes=i)
        # First 30 minutes build opening range below 101.
        if i < 30:
            px = 100.0 + (i % 10) * 0.03
            vol = 10_000
        # Breakout window with heavy volume.
        elif i < 45:
            px = 101.40 + (i - 30) * 0.12
            vol = 45_000
        else:
            px += 0.20
            vol = 30_000
        events.append((ts, symbol, make_bar(ts, px - 0.04, px + 0.08, px - 0.08, px, vol)))
    return events


def main():
    cfg = yaml.safe_load(open("config.yaml"))
    cfg["symbols"] = ["TEST"]
    cfg["strategy"]["mode"] = "ensemble"
    cfg["strategy"]["ensemble_modes"] = ["orb"]
    cfg["strategy"]["bar_minutes"] = 15
    cfg["strategy"]["warmup_bars"] = 2
    cfg["strategy"]["atr_period"] = 2
    cfg["strategy"]["rsi_period"] = 2
    cfg["strategy"]["volume_lookback"] = 2
    cfg["strategy"]["orb_minutes"] = 30
    cfg["strategy"]["orb_vol_mult"] = 1.2
    cfg["strategy"]["orb_max_vwap_distance_atr"] = 0
    cfg["strategy"]["orb_rsi_max_entry"] = 101
    cfg["strategy"]["rsi_max_entry"] = 101
    cfg["risk"]["stop_atr_mult"] = 1.5
    cfg["risk"]["take_profit_r"] = 1.5
    cfg["risk"]["max_daily_trades"] = 10

    s = simulate(cfg, build_events(), ["TEST"])
    assert s["n"] >= 1, f"expected ORB trade, got {s['n']}"
    assert "ORB" in s["trades"][0]["reason"], s["trades"][0]["reason"]
    print(f"PASS — ORB fired {s['n']} trade(s), net ${s['net']:+.2f}")


if __name__ == "__main__":
    main()
