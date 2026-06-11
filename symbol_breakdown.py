from collections import defaultdict
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml
import math

from backtest import fetch_events, simulate

ET = ZoneInfo("America/New_York")


def fmt_pf(gross_profit, gross_loss):
    if gross_loss == 0:
        return "inf" if gross_profit > 0 else "0.00"
    return f"{gross_profit / abs(gross_loss):.2f}"


cfg = yaml.safe_load(open("config.yaml"))

symbols = cfg["symbols"]
end = datetime.now(ET)
start = end - timedelta(days=182)

print(f"Fetching 182 days of bars for {symbols} ...")
events = fetch_events(cfg, start, end, symbols)
print(f"Got {len(events):,} bars. Running symbol breakdown...\n")

stats = simulate(cfg, events, symbols)
trades = stats["trades"]

by_symbol = defaultdict(list)

for t in trades:
    by_symbol[t["symbol"]].append(t)

rows = []

for sym, ts in by_symbol.items():
    wins = [t for t in ts if t["pnl"] > 0]
    losses = [t for t in ts if t["pnl"] <= 0]
    gross_profit = sum(t["pnl"] for t in wins)
    gross_loss = sum(t["pnl"] for t in losses)
    net = gross_profit + gross_loss
    win_rate = len(wins) / len(ts) * 100 if ts else 0
    pf = fmt_pf(gross_profit, gross_loss)
    rows.append((net, sym, ts, wins, losses, gross_profit, gross_loss, win_rate, pf))

rows.sort(reverse=True)

print("=" * 100)
print(f"{'Symbol':<8}{'Trades':>8}{'Wins':>8}{'Losses':>8}{'Win%':>8}{'Gross+':>12}{'Gross-':>12}{'PF':>8}{'Net':>12}")
print("-" * 100)

for net, sym, ts, wins, losses, gp, gl, win_rate, pf in rows:
    print(
        f"{sym:<8}"
        f"{len(ts):>8}"
        f"{len(wins):>8}"
        f"{len(losses):>8}"
        f"{win_rate:>7.1f}%"
        f"${gp:>+11.2f}"
        f"${gl:>+11.2f}"
        f"{pf:>8}"
        f"${net:>+11.2f}"
    )

print("=" * 100)
print(f"Total net: ${stats['net']:+.2f}")
print(f"Total trades: {stats['n']}")
