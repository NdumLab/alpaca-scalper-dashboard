#!/usr/bin/env python3
"""Offline planned-event risk smoke test."""
from __future__ import annotations

import copy
from datetime import datetime
from zoneinfo import ZoneInfo

import yaml

from backtest import simulate
from market_events import EventRisk
from test_smoke import build_events

ET = ZoneInfo("America/New_York")


def test_config() -> dict:
    cfg = yaml.safe_load(open("config.yaml"))
    cfg["symbols"] = ["TEST"]
    cfg["risk"]["max_daily_trades"] = 10
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
    return cfg


def main() -> None:
    events = build_events()
    cfg = test_config()
    base = simulate(copy.deepcopy(cfg), events, ["TEST"])
    assert base["n"] >= 1, "control setup should produce a trade"

    cfg["event_risk"] = {
        "enabled": True,
        "block_new_entries": True,
        "min_impact": "high",
        "default_pre_minutes": 120,
        "default_post_minutes": 120,
        "planned_events": [{
            "name": "Synthetic FOMC",
            "time": "2026-06-08T10:30:00-04:00",
            "impact": "high",
            "symbols": ["*"],
        }],
    }
    blocked = simulate(copy.deepcopy(cfg), events, ["TEST"])
    assert blocked["n"] == 0, f"expected event block to suppress trades, got {blocked['n']}"
    assert blocked["event_blocked_entries"] > 0, "expected event block counter to increment"

    event_risk = EventRisk(cfg)
    assert event_risk.blocks_entry(datetime(2026, 6, 8, 10, 30, tzinfo=ET), "TEST")
    assert not event_risk.blocks_entry(datetime(2026, 6, 8, 15, 0, tzinfo=ET), "TEST")

    print(
        "PASS — planned event block suppressed entries "
        f"({blocked['event_blocked_entries']} blocked checks)"
    )


if __name__ == "__main__":
    main()
