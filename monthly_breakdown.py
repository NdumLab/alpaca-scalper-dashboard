from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml

from backtest import fetch_events, simulate

ET = ZoneInfo("America/New_York")

cfg = yaml.safe_load(open("config.yaml"))

symbols = cfg["symbols"]
end = datetime.now(ET)
start = end - timedelta(days=182)

print(f"Fetching 182 days of bars for {symbols} ...")
events = fetch_events(cfg, start, end, symbols)
print(f"Got {len(events):,} bars. Running monthly breakdown...\n")

stats = simulate(cfg, events, symbols)
trades = stats["trades"]

monthly = defaultdict(list)

for t in trades:
    key = str(t["date"])[:7]
    monthly[key].append(t)

print("=" * 80)
print(f"{'Month':<10}{'Trades':>8}{'Wins':>8}{'Losses':>8}{'Win%':>8}{'Net P&L':>12}")
print("-" * 80)

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

print("=" * 80)
print(f"Total trades: {stats['n']}")
print(f"Total net: ${stats['net']:+.2f}")
print(f"Profit factor: {stats['profit_factor']:.2f}")
print(f"Max drawdown: ${stats['max_drawdown']:.2f}")
