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
print(f"Got {len(events):,} bars. Running daily breakdown...\n")

stats = simulate(cfg, events, symbols)
trades = stats["trades"]

daily = defaultdict(list)

for t in trades:
    daily[str(t["date"])].append(t)

rows = []

for day, ts in daily.items():
    net = sum(t["pnl"] for t in ts)
    wins = len([t for t in ts if t["pnl"] > 0])
    losses = len([t for t in ts if t["pnl"] <= 0])
    rows.append((net, day, len(ts), wins, losses))

rows_sorted = sorted(rows, reverse=True)

print("=" * 80)
print("TOP 15 BEST DAYS")
print("=" * 80)
print(f"{'Date':<12}{'Trades':>8}{'Wins':>8}{'Losses':>8}{'Net P&L':>12}")
print("-" * 80)

for net, day, n, wins, losses in rows_sorted[:15]:
    print(f"{day:<12}{n:>8}{wins:>8}{losses:>8}${net:>+11.2f}")

print("\n" + "=" * 80)
print("TOP 15 WORST DAYS")
print("=" * 80)
print(f"{'Date':<12}{'Trades':>8}{'Wins':>8}{'Losses':>8}{'Net P&L':>12}")
print("-" * 80)

for net, day, n, wins, losses in sorted(rows)[:15]:
    print(f"{day:<12}{n:>8}{wins:>8}{losses:>8}${net:>+11.2f}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Total net: ${stats['net']:+.2f}")
print(f"Total trades: {stats['n']}")
print(f"Days traded: {len(rows)}")

top_5_profit = sum(r[0] for r in rows_sorted[:5])
print(f"Top 5 days net: ${top_5_profit:+.2f}")
print(f"Top 5 days as % of total: {top_5_profit / stats['net'] * 100:.1f}%")
