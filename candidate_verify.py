from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml
import math

from backtest import fetch_events, simulate

ET = ZoneInfo("America/New_York")


def set_nested(cfg, dotted_key, value):
    parts = dotted_key.split(".")
    cur = cfg
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def apply_overrides(base, overrides):
    cfg = deepcopy(base)
    for k, v in overrides.items():
        set_nested(cfg, k, v)
    return cfg


def fmt_pf(x):
    if x == float("inf"):
        return "inf"
    if x is None:
        return "0.00"
    try:
        if math.isnan(x):
            return "0.00"
    except Exception:
        pass
    return f"{x:.2f}"


base = yaml.safe_load(open("config.yaml"))

# Base v6 ORB settings
base["strategy"]["orb_vol_mult"] = 1.8
base["strategy"]["orb_max_vwap_distance_atr"] = 1.8
base["account"]["starting_equity"] = 2000

symbols = base["symbols"]
end = datetime.now(ET)
start = end - timedelta(days=182)

print(f"Fetching 182 days of bars for {symbols} ...")
events = fetch_events(base, start, end, symbols)
print(f"Got {len(events):,} bars. Verifying candidates...\n")

candidates = [
    ("Balanced 160", 160, 3.0, 3.4),
    ("Preferred 180", 180, 3.0, 3.4),
    ("High 190", 190, 3.0, 3.4),
    ("Max 200", 200, 3.0, 3.4),
]

print("=" * 115)
print(f"{'Candidate':<16}{'Slip':>6}{'MaxPos':>8}{'TP_R':>8}{'StopATR':>9}{'Trades':>8}{'Win%':>8}{'PF':>8}{'MaxDD':>11}{'Net':>12}{'Return':>10}")
print("-" * 115)

for name, max_pos, tp_r, stop_atr in candidates:
    for slip in [3, 5, 7, 10]:
        cfg = apply_overrides(base, {
            "backtest.slippage_cents": slip,
            "risk.max_position_pct": max_pos,
            "risk.take_profit_r": tp_r,
            "risk.stop_atr_mult": stop_atr,
        })

        stats = simulate(cfg, events, symbols)
        ret = (stats["end_equity"] / stats["start_equity"] - 1) * 100

        print(
            f"{name:<16}"
            f"{slip:>6}"
            f"{max_pos:>7}%"
            f"{tp_r:>8.1f}"
            f"{stop_atr:>9.1f}"
            f"{stats['n']:>8}"
            f"{stats['win_rate']:>7.1f}%"
            f"{fmt_pf(stats['profit_factor']):>8}"
            f"${stats['max_drawdown']:>10.2f}"
            f"${stats['net']:>+11.2f}"
            f"{ret:>9.2f}%"
        )

print("=" * 115)
print("Watch the 10c slippage row. If it collapses, the profile may be too fragile.")
