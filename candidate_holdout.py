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


def run_period(label, base, start, end, symbols, max_pos):
    print(f"\nFetching {label}: {start.date()} to {end.date()} ...")
    events = fetch_events(base, start, end, symbols)
    print(f"Got {len(events):,} bars.")

    print(f"{'Label':<18}{'Slip':>6}{'MaxPos':>8}{'Trades':>8}{'Win%':>8}{'PF':>8}{'MaxDD':>11}{'Net':>12}{'Return':>10}")
    print("-" * 95)

    for slip in [3, 5, 7]:
        cfg = apply_overrides(base, {
            "backtest.slippage_cents": slip,
            "risk.max_position_pct": max_pos,
            "risk.take_profit_r": 3.0,
            "risk.stop_atr_mult": 3.4,
        })

        stats = simulate(cfg, events, symbols)
        ret = (stats["end_equity"] / stats["start_equity"] - 1) * 100

        print(
            f"{label:<18}"
            f"{slip:>6}"
            f"{max_pos:>7}%"
            f"{stats['n']:>8}"
            f"{stats['win_rate']:>7.1f}%"
            f"{fmt_pf(stats['profit_factor']):>8}"
            f"${stats['max_drawdown']:>10.2f}"
            f"${stats['net']:>+11.2f}"
            f"{ret:>9.2f}%"
        )


base = yaml.safe_load(open("config.yaml"))

# Base v6 ORB settings
base["strategy"]["orb_vol_mult"] = 1.8
base["strategy"]["orb_max_vwap_distance_atr"] = 1.8
base["account"]["starting_equity"] = 2000

symbols = base["symbols"]

end = datetime.now(ET)
mid = end - timedelta(days=91)
start = end - timedelta(days=182)

print("=" * 95)
print("HOLDOUT TEST FOR PREFERRED 180% PROFILE")
print("=" * 95)

run_period("First 91 days", base, start, mid, symbols, 180)
run_period("Last 91 days", base, mid, end, symbols, 180)

print("\nDecision:")
print("Both halves should be profitable.")
print("If only one half makes all the money, the profile may be regime-dependent.")
