from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml
import math
import time

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


def run_one(base, events, symbols, slippage, max_pos, take_profit_r, stop_atr):
    cfg = apply_overrides(base, {
        "backtest.slippage_cents": slippage,
        "risk.max_position_pct": max_pos,
        "risk.take_profit_r": take_profit_r,
        "risk.stop_atr_mult": stop_atr,
    })

    stats = simulate(cfg, events, symbols)

    ret = (stats["end_equity"] / stats["start_equity"] - 1) * 100

    return {
        "slippage": slippage,
        "max_pos": max_pos,
        "take_profit_r": take_profit_r,
        "stop_atr": stop_atr,
        "trades": stats["n"],
        "win_rate": stats["win_rate"],
        "pf": stats["profit_factor"],
        "max_dd": stats["max_drawdown"],
        "net": stats["net"],
        "ret": ret,
    }


base = yaml.safe_load(open("config.yaml"))

# Current v6 tighter ORB base
base["strategy"]["orb_vol_mult"] = 1.8
base["strategy"]["orb_max_vwap_distance_atr"] = 1.8
base["risk"]["stop_atr_mult"] = 3.2
base["risk"]["take_profit_r"] = 2.2
base["account"]["starting_equity"] = 2000

symbols = base["symbols"]

end = datetime.now(ET)
start = end - timedelta(days=182)

print(f"Fetching 182 days of bars for {symbols} ...", flush=True)
events = fetch_events(base, start, end, symbols)
print(f"Got {len(events):,} bars. Running FAST grid search...\n", flush=True)

max_positions = [160, 170, 180, 190, 200]
take_profit_rs = [2.2, 2.5, 2.7, 3.0]
stop_atrs = [3.0, 3.2, 3.4]

total = len(max_positions) * len(take_profit_rs) * len(stop_atrs)
rows_5c = []

print("=" * 120)
print("PHASE 1: Searching only 5c slippage candidates")
print("=" * 120)
print(f"{'Done':>6} {'MaxPos':>7} {'TP_R':>6} {'StopATR':>8} {'Trades':>8} {'Win%':>7} {'PF':>7} {'MaxDD':>10} {'Net':>11} {'Return':>9} {'Goal':>7}")
print("-" * 120, flush=True)

count = 0
started = time.time()

for max_pos in max_positions:
    for take_profit_r in take_profit_rs:
        for stop_atr in stop_atrs:
            count += 1

            r = run_one(
                base=base,
                events=events,
                symbols=symbols,
                slippage=5,
                max_pos=max_pos,
                take_profit_r=take_profit_r,
                stop_atr=stop_atr,
            )

            rows_5c.append(r)
            goal = "YES" if r["net"] >= 600 else "NO"

            print(
                f"{count:>3}/{total:<2} "
                f"{r['max_pos']:>7}% "
                f"{r['take_profit_r']:>6.1f} "
                f"{r['stop_atr']:>8.1f} "
                f"{r['trades']:>8} "
                f"{r['win_rate']:>6.1f}% "
                f"{fmt_pf(r['pf']):>7} "
                f"${r['max_dd']:>9.2f} "
                f"${r['net']:>+10.2f} "
                f"{r['ret']:>8.2f}% "
                f"{goal:>7}",
                flush=True,
            )

elapsed = time.time() - started

print("=" * 120)
print(f"Finished phase 1 in {elapsed:.1f} seconds.", flush=True)

rows_5c_sorted = sorted(
    rows_5c,
    key=lambda r: (r["net"], r["pf"], -r["max_dd"]),
    reverse=True,
)

print("\n" + "=" * 120)
print("TOP 10 CANDIDATES AT 5c SLIPPAGE")
print("=" * 120)
print(f"{'Rank':>5} {'MaxPos':>7} {'TP_R':>6} {'StopATR':>8} {'Trades':>8} {'Win%':>7} {'PF':>7} {'MaxDD':>10} {'Net':>11} {'Return':>9} {'Goal':>7}")
print("-" * 120)

for i, r in enumerate(rows_5c_sorted[:10], start=1):
    goal = "YES" if r["net"] >= 600 else "NO"
    print(
        f"{i:>5} "
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

print("\n" + "=" * 120)
print("PHASE 2: Rechecking top 5 candidates at 3c, 5c, and 7c slippage")
print("=" * 120)
print(f"{'Candidate':>9} {'Slip':>5} {'MaxPos':>7} {'TP_R':>6} {'StopATR':>8} {'Trades':>8} {'Win%':>7} {'PF':>7} {'MaxDD':>10} {'Net':>11} {'Return':>9} {'Goal':>7}")
print("-" * 120)

for i, best in enumerate(rows_5c_sorted[:5], start=1):
    for slippage in [3, 5, 7]:
        r = run_one(
            base=base,
            events=events,
            symbols=symbols,
            slippage=slippage,
            max_pos=best["max_pos"],
            take_profit_r=best["take_profit_r"],
            stop_atr=best["stop_atr"],
        )

        goal = "YES" if r["net"] >= 600 else "NO"

        print(
            f"{i:>9} "
            f"{slippage:>5} "
            f"{r['max_pos']:>7}% "
            f"{r['take_profit_r']:>6.1f} "
            f"{r['stop_atr']:>8.1f} "
            f"{r['trades']:>8} "
            f"{r['win_rate']:>6.1f}% "
            f"{fmt_pf(r['pf']):>7} "
            f"${r['max_dd']:>9.2f} "
            f"${r['net']:>+10.2f} "
            f"{r['ret']:>8.2f}% "
            f"{goal:>7}",
            flush=True,
        )

print("=" * 120)

print("\nDecision rule:")
print("1. Strong candidate: 5c net >= $600.")
print("2. Better candidate: 7c still profitable with acceptable drawdown.")
print("3. Avoid profiles where max drawdown becomes ugly.")
print("4. Do not choose only by net P&L.")
