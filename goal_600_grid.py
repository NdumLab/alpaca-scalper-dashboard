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

# Current winning v6 tighter ORB base
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
print(f"Got {len(events):,} bars. Running grid search...\n")

rows = []

for slippage in [3, 5, 7]:
    for max_pos in [150, 160, 170, 180, 190, 200]:
        for take_profit_r in [2.2, 2.4, 2.5, 2.7, 3.0]:
            for stop_atr in [3.0, 3.2, 3.4]:
                cfg = apply_overrides(base, {
                    "backtest.slippage_cents": slippage,
                    "risk.max_position_pct": max_pos,
                    "risk.take_profit_r": take_profit_r,
                    "risk.stop_atr_mult": stop_atr,
                })

                stats = simulate(cfg, events, symbols)
                net = stats["net"]
                ret = (stats["end_equity"] / stats["start_equity"] - 1) * 100

                rows.append({
                    "slippage": slippage,
                    "max_pos": max_pos,
                    "take_profit_r": take_profit_r,
                    "stop_atr": stop_atr,
                    "trades": stats["n"],
                    "win_rate": stats["win_rate"],
                    "pf": stats["profit_factor"],
                    "max_dd": stats["max_drawdown"],
                    "net": net,
                    "ret": ret,
                })

print("=" * 120)
print("Top profiles by 5c slippage result, with 3c/7c sanity checks done separately")
print("=" * 120)

# Show best 5c candidates first
five_c = [r for r in rows if r["slippage"] == 5]
five_c = sorted(five_c, key=lambda r: (r["net"], r["pf"], -r["max_dd"]), reverse=True)

print(f"{'Slip':>5} {'MaxPos':>7} {'TP_R':>6} {'StopATR':>8} {'Trades':>8} {'Win%':>7} {'PF':>7} {'MaxDD':>10} {'Net':>11} {'Return':>9} {'Goal':>7}")
print("-" * 120)

for r in five_c[:25]:
    goal = "YES" if r["net"] >= 600 else "NO"
    print(
        f"{r['slippage']:>5} "
        f"{r['max_pos']:>7}% "
        f"{r['take_profit_r']:>6.1f} "
        f"{r['stop_atr']:>8.1f} "
        f"{r['trades']:>8} "
        f"{r['win_rate']:>6.1f}% "
        f"{fmt_pf(r['pf']):>7} "
        f"${r['max_dd']:>9.2f} "
        f"${r['net']:>+10.2f} "
        f"{r['ret']:>8.2f}% "
        f"{goal:>7}"
    )

print("=" * 120)
print("Goal: find a profile that is >= $600 at 5c slippage without ugly drawdown.")
print("After finding a candidate, compare the same settings at 3c and 7c.")
