#!/usr/bin/env python3
"""Offline market-regime gate smoke test."""
from __future__ import annotations

import copy
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import yaml

from backtest import simulate

ET = ZoneInfo("America/New_York")


def make_bar(ts, price, volume=20_000):
    return SimpleNamespace(
        timestamp=ts,
        open=price - 0.03,
        high=price + 0.08,
        low=price - 0.08,
        close=price,
        volume=volume,
    )


def build_events(regime_up: bool = True):
    start = datetime(2026, 6, 8, 9, 36, tzinfo=ET)
    events = []
    test_px = 100.0
    spy_px = 500.0
    qqq_px = 450.0
    for i in range(110):
        ts = start + timedelta(minutes=i)
        drift = 0.05 if regime_up else -0.05
        spy_px += drift
        qqq_px += drift
        events.append((ts, "SPY", make_bar(ts, spy_px)))
        events.append((ts, "QQQ", make_bar(ts, qqq_px)))

        vol = 10_000
        if i < 35:
            test_px += 0.01
        elif i < 45:
            test_px -= 0.25
        elif i < 58:
            test_px += 0.50
            vol = 45_000
        else:
            test_px += 0.15
        events.append((ts, "TEST", make_bar(ts, test_px, vol)))
    return events


def cfg_base() -> dict:
    cfg = yaml.safe_load(open("config.yaml"))
    cfg["symbols"] = ["SPY", "QQQ", "TEST"]
    cfg["risk"]["max_daily_trades"] = 10
    cfg["risk"]["take_profit_r"] = 1.5
    cfg["risk"]["stop_atr_mult"] = 1.5
    cfg["strategy"]["mode"] = "momentum"
    cfg["strategy"]["bar_minutes"] = 1
    cfg["strategy"]["volume_surge_mult"] = 1.5
    cfg["strategy"]["rsi_max_entry"] = 99
    cfg["strategy"]["min_atr_pct"] = 0
    cfg["strategy"]["max_atr_pct"] = 0
    cfg["strategy"]["min_ema_spread_atr"] = 0
    cfg["strategy"]["max_vwap_distance_atr"] = 0
    cfg["strategy"]["blocked_time_ranges"] = []
    cfg["market_regime"] = {
        "enabled": True,
        "symbols": ["SPY", "QQQ"],
        "min_symbols_passing": 2,
        "min_bars": 30,
        "require_fast_above_slow": True,
        "require_close_above_slow": True,
        "require_close_above_vwap": False,
        "regime_strategies": {
            "bullish": "momentum",
            "mixed": "block",
            "bearish": "block",
        },
    }
    return cfg


def main() -> None:
    cfg = cfg_base()
    up = simulate(copy.deepcopy(cfg), build_events(True), cfg["symbols"])
    down = simulate(copy.deepcopy(cfg), build_events(False), cfg["symbols"])
    assert up["n"] >= 1, "up-regime should allow the synthetic momentum trade"
    assert down["n"] == 0, f"down-regime should block entries, got {down['n']}"
    assert down["regime_blocked_entries"] > 0, "expected regime block counter"
    print(
        "PASS — market regime gate allowed up-regime trades and blocked "
        f"down-regime checks ({down['regime_blocked_entries']} blocked)"
    )


if __name__ == "__main__":
    main()
