#!/usr/bin/env python3
"""Forward-validation report: live paper trades vs simulator expectations.

Sections:
  1. Bot liveness: heartbeat.json staleness (catches silent downtime).
  2. Rolling 30-day sim health on the refreshed cache (regime deterioration).
  3. Live-vs-sim tracking: matches runtime/trades.csv rows against sim trades
     on the same dates; reports match rate, entry/exit price drift, P&L drift.

Exit code 0 always; lines starting with WARN: are the alert surface for the
weekly cron wrapper. Run inside docker so deps and paths match the bot.
"""
from __future__ import annotations

import csv
import json
import os
import pickle
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from backtest import ET, simulate

REPO = Path(__file__).resolve().parent
RUNTIME = Path(os.environ.get("RUNTIME_DIR", REPO / "runtime"))
CACHE = REPO / "period_events_365.pkl"
HEARTBEAT_STALE_HOURS = 12   # bot writes heartbeat continuously; half a day = down
ENTRY_MATCH_MINUTES = 45     # live/sim entry within this window counts as same trade

warns = []


def warn(msg):
    warns.append(msg)
    print(f"WARN: {msg}")


now = datetime.now(ET)
print(f"Forward tracking report — {now:%Y-%m-%d %H:%M %Z}")
print("=" * 78)

# ---- 1. liveness ----
hb_path = RUNTIME / "heartbeat.json"
if hb_path.exists():
    hb = json.loads(hb_path.read_text())
    hb_time = datetime.fromisoformat(hb["time"])
    age_h = (now - hb_time.astimezone(ET)).total_seconds() / 3600
    print(f"Heartbeat: {hb.get('status')} / {hb.get('mode')} — {age_h:.1f}h old")
    if age_h > HEARTBEAT_STALE_HOURS:
        warn(f"bot heartbeat is {age_h:.0f}h stale — bot may be down")
    if hb.get("mode") != "paper":
        warn(f"bot mode is {hb.get('mode')!r}, expected paper")
else:
    warn("no heartbeat.json — bot has never run on this host or runtime dir moved")

# ---- 2. rolling sim health ----
cfg = yaml.safe_load(open(REPO / "config.yaml"))
if not CACHE.exists():
    warn("bar cache missing — sim sections skipped; build it with "
         "'docker compose run --rm --no-deps -v $PWD:/app alpaca-bot "
         "python period_breakdown.py 365'")
    trades_csv = Path(os.environ.get("TRADE_LOG_PATH", RUNTIME / "trades.csv"))
    n_live = sum(1 for _ in csv.DictReader(trades_csv.open())) if trades_csv.exists() else 0
    print(f"\nLive paper trades logged: {n_live} (no sim comparison without cache)")
    print("\n" + "=" * 78)
    print(f"Result: {len(warns)} WARNING(S) above")
    raise SystemExit(0)
blob = pickle.load(CACHE.open("rb"))
events = blob["events"]
data_end = events[-1][0].astimezone(ET)
if (now - data_end).days > 5:
    warn(f"cache is stale (ends {data_end:%Y-%m-%d}) — run scripts/refresh_cache.py")
stats = simulate(cfg, events, cfg["symbols"])
sim_trades = stats["trades"]
cut30 = (now - timedelta(days=30)).date()
last30 = [t for t in sim_trades if t["date"] >= cut30]
wins = [t for t in last30 if t["pnl"] > 0]
gross_w = sum(t["pnl"] for t in wins)
gross_l = -sum(t["pnl"] for t in last30 if t["pnl"] <= 0)
pf30 = gross_w / gross_l if gross_l else float("inf")
net30 = sum(t["pnl"] for t in last30)
print(f"\nSim, full cached year: {stats['n']} trades, PF {stats['profit_factor']:.2f}, "
      f"net ${stats['net']:+,.2f}")
print(f"Sim, rolling 30 days:  {len(last30)} trades, "
      f"PF {'inf' if pf30 == float('inf') else f'{pf30:.2f}'}, net ${net30:+,.2f}")
if last30 and net30 < 0:
    warn(f"rolling 30-day sim net is negative (${net30:+,.2f}) — possible regime turn")
elif last30 and pf30 < 1.0:
    warn(f"rolling 30-day sim PF {pf30:.2f} < 1.0 — possible regime turn")

# ---- 3. live vs sim ----
trades_csv = Path(os.environ.get("TRADE_LOG_PATH", RUNTIME / "trades.csv"))
live = []
if trades_csv.exists():
    for row in csv.DictReader(trades_csv.open()):
        try:
            ts = datetime.fromisoformat(row["time"])
            live.append({"time": ts.astimezone(ET), "symbol": row["symbol"],
                         "qty": int(float(row["qty"])), "entry": float(row["entry"]),
                         "exit": float(row["exit"]), "pnl": float(row["pnl"])})
        except (KeyError, ValueError) as e:
            print(f"  (skipping malformed live row: {e})")

print(f"\nLive paper trades logged: {len(live)}")
if not live:
    print("No live trades yet — tracking will begin at the bot's first close. "
          "(Bot restarted 2026-07-03 after ~3 weeks down; this is expected.)")
else:
    first_day = min(t["time"].date() for t in live)
    sim_window = [t for t in sim_trades if t["date"] >= first_day]
    sim_by_key = defaultdict(list)
    for t in sim_window:
        sim_by_key[(t["date"], t["symbol"])].append(t)
    matched, live_only = [], []
    for lt in live:
        cands = [st for st in sim_by_key.get((lt["time"].date(), lt["symbol"]), [])
                 if st.get("entry_time") is not None and not st.get("_used")
                 and abs((st["entry_time"] - lt["time"]).total_seconds()) / 60
                 <= ENTRY_MATCH_MINUTES + 390]  # live row time = close time; loose gate
        if cands:
            cands[0]["_used"] = True
            matched.append((lt, cands[0]))
        else:
            live_only.append(lt)
    sim_only = [t for t in sim_window if not t.get("_used")]
    live_net = sum(t["pnl"] for t in live)
    sim_net = sum(t["pnl"] for t in sim_window)
    print(f"Window since {first_day}: live {len(live)} trades net ${live_net:+,.2f} | "
          f"sim {len(sim_window)} trades net ${sim_net:+,.2f}")
    print(f"Matched {len(matched)} | live-only {len(live_only)} | sim-only {len(sim_only)}")
    if matched:
        entry_drift = [lt["entry"] - st["entry"] for lt, st in matched]
        pnl_drift = [lt["pnl"] - st["pnl"] for lt, st in matched]
        avg_entry = sum(entry_drift) / len(entry_drift)
        print(f"Avg entry drift live-sim: ${avg_entry:+.3f}/share "
              f"(sim models +$0.030 slippage) | avg P&L drift ${sum(pnl_drift)/len(pnl_drift):+.2f}/trade")
        if avg_entry > 0.05:
            warn(f"live entry fills average {avg_entry*100:.1f}c worse than sim — "
                 "slippage model may be optimistic")
    if len(live) >= 10:
        if sim_net > 0 and live_net < 0.5 * sim_net:
            warn(f"live net (${live_net:+,.2f}) is under half of sim expectation "
                 f"(${sim_net:+,.2f}) over the same window")
        miss = len(live_only) + len(sim_only)
        if miss > 0.4 * max(len(live), len(sim_window)):
            warn("live and sim trade selection diverging (>40% unmatched) — "
                 "check data feed (bot=IEX stream) vs cache, and config drift")

print("\n" + "=" * 78)
print(f"Result: {'OK — no warnings' if not warns else f'{len(warns)} WARNING(S) above'}")
