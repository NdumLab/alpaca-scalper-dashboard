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


def subset_events(events, symbols):
    wanted = set(symbols)
    return [e for e in events if e[1] in wanted]


base = yaml.safe_load(open("config.yaml"))

# Current aggressive winner
base["strategy"]["orb_vol_mult"] = 1.8
base["strategy"]["orb_max_vwap_distance_atr"] = 1.8
base["risk"]["max_position_pct"] = 180
base["risk"]["take_profit_r"] = 3.0
base["risk"]["stop_atr_mult"] = 3.4
base["account"]["starting_equity"] = 2000

full_symbols = base["symbols"]

end = datetime.now(ET)
start = end - timedelta(days=182)

print(f"Fetching 182 days of bars for {full_symbols} ...")
events = fetch_events(base, start, end, full_symbols)
print(f"Got {len(events):,} bars. Running symbol pruning research...\n")

profiles = [
    ("full universe", full_symbols),
    ("remove TSLA", [s for s in full_symbols if s != "TSLA"]),
    ("remove META", [s for s in full_symbols if s != "META"]),
    ("remove QQQ", [s for s in full_symbols if s != "QQQ"]),
    ("remove TSLA META", [s for s in full_symbols if s not in ["TSLA", "META"]]),
    ("remove TSLA QQQ", [s for s in full_symbols if s not in ["TSLA", "QQQ"]]),
    ("remove META QQQ", [s for s in full_symbols if s not in ["META", "QQQ"]]),
    ("remove TSLA META QQQ", [s for s in full_symbols if s not in ["TSLA", "META", "QQQ"]]),
    ("top 7 only", ["AMD", "AAPL", "NVDA", "MSFT", "AMZN", "IWM", "SPY"]),
    ("top 5 only", ["AMD", "AAPL", "NVDA", "MSFT", "AMZN"]),
    ("top 3 only", ["AMD", "AAPL", "NVDA"]),
]

print("=" * 115)
print(f"{'Profile':<24}{'Symbols':>8}{'Slip':>6}{'Trades':>8}{'Win%':>8}{'PF':>8}{'MaxDD':>11}{'Net':>12}{'Return':>10}")
print("-" * 115)

for name, symbols in profiles:
    for slip in [3, 5, 7]:
        cfg = deepcopy(base)
        cfg["symbols"] = symbols
        cfg["backtest"]["slippage_cents"] = slip

        ev = subset_events(events, symbols)
        stats = simulate(cfg, ev, symbols)
        ret = (stats["end_equity"] / stats["start_equity"] - 1) * 100

        print(
            f"{name:<24}"
            f"{len(symbols):>8}"
            f"{slip:>6}"
            f"{stats['n']:>8}"
            f"{stats['win_rate']:>7.1f}%"
            f"{fmt_pf(stats['profit_factor']):>8}"
            f"${stats['max_drawdown']:>10.2f}"
            f"${stats['net']:>+11.2f}"
            f"{ret:>9.2f}%"
        )

print("=" * 115)
print("Decision rule:")
print("1. Prefer higher 5c and 7c net.")
print("2. Prefer PF >= 1.60.")
print("3. Prefer lower max drawdown.")
print("4. Do not remove a symbol unless the portfolio improves after removal.")
