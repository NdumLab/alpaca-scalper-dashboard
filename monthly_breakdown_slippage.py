from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml
import math

from backtest import fetch_events, simulate

ET = ZoneInfo("America/New_York")


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

symbols = base["symbols"]
end = datetime.now(ET)
start = end - timedelta(days=182)

print(f"Fetching 182 days of bars for {symbols} ...")
events = fetch_events(base, start, end, symbols)
print(f"Got {len(events):,} bars. Running monthly slippage breakdown...\n")

for slip in [3, 5, 7]:
    cfg = deepcopy(base)
    cfg["backtest"]["slippage_cents"] = slip

    stats = simulate(cfg, events, symbols)
    trades = stats["trades"]

    monthly = defaultdict(list)

    for t in trades:
        key = str(t["date"])[:7]
        monthly[key].append(t)

    print("=" * 90)
    print(f"MONTHLY BREAKDOWN — {slip}c SLIPPAGE")
    print("=" * 90)
    print(f"{'Month':<10}{'Trades':>8}{'Wins':>8}{'Losses':>8}{'Win%':>8}{'Net P&L':>12}")
    print("-" * 90)

    for month in sorted(monthly):
        rows = monthly[month]
        wins = [t for t in rows if t["pnl"] > 0]
        losses = [t for t in rows if t["pnl"] <= 0]
        net = sum(t["pnl"] for t in rows)
        win_rate = len(wins) / len(rows) * 100 if rows else 0

        print(
            f"{month:<10}"
            f"{len(rows):>8}"
            f"{len(wins):>8}"
            f"{len(losses):>8}"
            f"{win_rate:>7.1f}%"
            f"${net:>+11.2f}"
        )

    print("-" * 90)
    print(f"Total trades:  {stats['n']}")
    print(f"Total net:     ${stats['net']:+.2f}")
    print(f"Profit factor: {fmt_pf(stats['profit_factor'])}")
    print(f"Max drawdown:  ${stats['max_drawdown']:.2f}")
    print()
