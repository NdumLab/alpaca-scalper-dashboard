from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml

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
    return f"{x:.2f}"


base = yaml.safe_load(open("config.yaml"))

# Make sure base uses the current winning v6 tighter ORB profile
base["strategy"]["orb_vol_mult"] = 1.8
base["strategy"]["orb_max_vwap_distance_atr"] = 1.8
base["risk"]["stop_atr_mult"] = 3.2
base["risk"]["take_profit_r"] = 2.2
base["account"]["starting_equity"] = 2000

symbols = base["symbols"]
end = datetime.now(ET)
start = end - timedelta(days=182)

print(f"Fetching 182 days of bars for {symbols} ...")
events = fetch_events(base, start, end, symbols)
print(f"Got {len(events):,} bars. Running $600 target research...\n")

profiles = [
    (
        "current winner",
        {},
    ),
    (
        "more trades",
        {
            "risk.max_daily_trades": 8,
            "strategy.orb_vol_mult": 1.6,
        },
    ),
    (
        "bigger target 2.5R",
        {
            "risk.take_profit_r": 2.5,
            "risk.stop_atr_mult": 3.2,
        },
    ),
    (
        "bigger target 3.0R",
        {
            "risk.take_profit_r": 3.0,
            "risk.stop_atr_mult": 3.2,
        },
    ),
    (
        "tighter stop 2.8 ATR",
        {
            "risk.stop_atr_mult": 2.8,
            "risk.take_profit_r": 2.2,
        },
    ),
    (
        "more size 120 pct",
        {
            "risk.max_position_pct": 120,
        },
    ),
    (
        "more size 150 pct",
        {
            "risk.max_position_pct": 150,
        },
    ),
    (
        "more size 180 pct",
        {
            "risk.max_position_pct": 180,
        },
    ),
    (
        "more trades + 150 pct",
        {
            "risk.max_daily_trades": 8,
            "strategy.orb_vol_mult": 1.6,
            "risk.max_position_pct": 150,
        },
    ),
]

print("=" * 104)
print(f"{'Profile':<24}{'Trades':>8}{'Win %':>8}{'PF':>8}{'Max DD':>12}{'Net P&L':>12}{'Avg/Mo':>12}{'Return':>10}{'Goal?':>8}")
print("-" * 104)

for name, overrides in profiles:
    cfg = apply_overrides(base, overrides)
    stats = simulate(cfg, events, cfg["symbols"])

    net = stats["net"]
    avg_month = net / 6
    ret = (stats["end_equity"] / stats["start_equity"] - 1) * 100
    goal = "YES" if net >= 600 else "NO"

    print(
        f"{name:<24}"
        f"{stats['n']:>8}"
        f"{stats['win_rate']:>7.1f}%"
        f"{fmt_pf(stats['profit_factor']):>8}"
        f"${stats['max_drawdown']:>11.2f}"
        f"${net:>+11.2f}"
        f"${avg_month:>+11.2f}"
        f"{ret:>9.2f}%"
        f"{goal:>8}"
    )

print("=" * 104)
print("Goal: +$600 in 6 months on $2,000 = +30% return = about +$100/month.")
print("Do not pick only by Net P&L. Watch profit factor and max drawdown.")
