#!/usr/bin/env python3
"""Backtest the scalp strategy on historical 1-minute bars from Alpaca.

Usage:
    python backtest.py --days 30
    python backtest.py --days 60 --symbols SPY QQQ

Replays bars through the exact same indicator + strategy + sizing code
the live bot uses, simulating bracket exits bar-by-bar. Daily trade
limits (and the optional self-imposed day-trade cap, if enabled) are
enforced the same way as live.
"""
from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta, time as dtime, date
from zoneinfo import ZoneInfo

import yaml

from indicators import Bar, SymbolIndicators
from strategy import ScalpStrategy
from market_events import EventRisk
from market_regime import MarketRegime

ET = ZoneInfo("America/New_York")


def business_days_ago(d: date, n: int) -> date:
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def _resample_events(events: list, minutes: int) -> list:
    """Aggregate 1-min (ts, sym, bar) events into N-min buckets, stamped at
    bucket close — identical convention to the live aggregator in main.py."""
    from collections import namedtuple
    RBar = namedtuple("RBar", "timestamp open high low close volume")
    buckets, order = {}, []
    for ts, sym, b in events:
        et = ts.astimezone(ET)
        bstart = et.replace(minute=(et.minute // minutes) * minutes,
                            second=0, microsecond=0)
        key = (sym, bstart)
        cur = buckets.get(key)
        if cur is None:
            buckets[key] = [b.open, b.high, b.low, b.close, b.volume]
            order.append(key)
        else:
            cur[1] = max(cur[1], b.high); cur[2] = min(cur[2], b.low)
            cur[3] = b.close; cur[4] += b.volume
    out = []
    for sym, bstart in order:
        o, h, l, c, v = buckets[(sym, bstart)]
        end = bstart + timedelta(minutes=minutes)
        out.append((end, sym, RBar(end, o, h, l, c, v)))
    out.sort(key=lambda e: e[0])
    return out


def _research_entry_guard_blocks(guard: dict, sym: str, ts_et: datetime, context: dict) -> bool:
    """Optional backtest-only guard for targeted research harnesses.

    This is intentionally wired through the ``backtest`` config namespace so it
    cannot affect live trading. Runtime code does not call simulate().
    """
    if not guard.get("enabled", False):
        return False

    apply_symbols = guard.get("symbols")
    if apply_symbols and sym not in set(apply_symbols):
        return False

    minute = ts_et.hour * 60 + ts_et.minute
    for start, end in guard.get("blocked_entry_minutes", []) or []:
        if int(start) <= minute <= int(end):
            return True

    max_vwap_distance = guard.get("max_vwap_distance_atr")
    if max_vwap_distance is not None:
        value = context.get("entry_vwap_distance_atr")
        if value is not None and value > float(max_vwap_distance):
            return True

    max_volume_ratio = guard.get("max_volume_ratio")
    if max_volume_ratio is not None:
        value = context.get("entry_volume_ratio")
        if value is not None and value > float(max_volume_ratio):
            return True

    return False


def _research_position_scale_multiplier(scale_cfg: dict, sym: str, ts_et: datetime, context: dict) -> float:
    """Optional backtest-only size shaping for targeted research harnesses."""
    if not scale_cfg.get("enabled", False):
        return 1.0

    multiplier = 1.0
    for rule in scale_cfg.get("rules", []) or []:
        apply_symbols = rule.get("symbols")
        if apply_symbols and sym not in set(apply_symbols):
            continue

        minute = ts_et.hour * 60 + ts_et.minute
        ranges = rule.get("entry_minutes", []) or []
        if ranges and not any(int(start) <= minute <= int(end) for start, end in ranges):
            continue

        min_vwap_distance = rule.get("min_vwap_distance_atr")
        if min_vwap_distance is not None:
            value = context.get("entry_vwap_distance_atr")
            if value is None or value < float(min_vwap_distance):
                continue

        min_volume_ratio = rule.get("min_volume_ratio")
        if min_volume_ratio is not None:
            value = context.get("entry_volume_ratio")
            if value is None or value < float(min_volume_ratio):
                continue

        min_atr_pct = rule.get("min_atr_pct")
        if min_atr_pct is not None:
            value = context.get("entry_atr_pct")
            if value is None or value < float(min_atr_pct):
                continue

        multiplier = min(multiplier, max(0.0, min(1.0, float(rule.get("multiplier", 1.0)))))

    return multiplier


def _research_rule_matches(rule: dict, sym: str, entry_minute: int | None, context: dict) -> bool:
    apply_symbols = rule.get("symbols")
    if apply_symbols and sym not in set(apply_symbols):
        return False

    ranges = rule.get("entry_minutes", []) or []
    if ranges:
        if entry_minute is None:
            return False
        if not any(int(start) <= entry_minute <= int(end) for start, end in ranges):
            return False

    min_vwap_distance = rule.get("min_vwap_distance_atr")
    if min_vwap_distance is not None:
        value = context.get("entry_vwap_distance_atr")
        if value is None or value < float(min_vwap_distance):
            return False

    min_volume_ratio = rule.get("min_volume_ratio")
    if min_volume_ratio is not None:
        value = context.get("entry_volume_ratio")
        if value is None or value < float(min_volume_ratio):
            return False

    min_atr_pct = rule.get("min_atr_pct")
    if min_atr_pct is not None:
        value = context.get("entry_atr_pct")
        if value is None or value < float(min_atr_pct):
            return False

    return True


def _research_exit_rules(exit_cfg: dict, position: dict) -> list[dict]:
    """Return matching backtest-only exit management rules for an open trade."""
    if not exit_cfg.get("enabled", False):
        return []
    context = {
        "entry_rsi": position.get("entry_rsi"),
        "entry_atr_pct": position.get("entry_atr_pct"),
        "entry_volume_ratio": position.get("entry_volume_ratio"),
        "entry_vwap_distance_atr": position.get("entry_vwap_distance_atr"),
        "entry_ema_spread_atr": position.get("entry_ema_spread_atr"),
    }
    return [
        rule for rule in exit_cfg.get("rules", []) or []
        if _research_rule_matches(
            rule,
            position["symbol"],
            position.get("entry_minute"),
            context,
        )
    ]


def simulate(cfg: dict, events: list, symbols: list[str]) -> dict:
    n_min = cfg["strategy"].get("bar_minutes", 1)
    if n_min > 1:
        events = _resample_events(events, n_min)
    """Replay pre-fetched (timestamp, symbol, bar) events. Returns stats dict."""
    strategy = ScalpStrategy(cfg)
    event_risk = EventRisk(cfg)
    market_regime = MarketRegime(cfg)
    rcfg = cfg["risk"]
    scfg = cfg["strategy"]
    pdt_max = cfg["pdt"]["max_day_trades_per_5_days"]
    bcfg = cfg.get("backtest", {})
    slip = bcfg.get("slippage_cents", 0) / 100.0
    tp_haircut = bcfg.get("take_profit_haircut_cents", 0) / 100.0
    daily_profit_target_pct = bcfg.get("research_daily_profit_target_pct", 0) or 0
    research_guard = bcfg.get("research_entry_guard", {}) or {}
    research_position_scale = bcfg.get("research_position_scale", {}) or {}
    research_exit_management = bcfg.get("research_exit_management", {}) or {}

    equity = float(cfg["account"]["starting_equity"])
    start_equity = equity
    no_new_after = dtime.fromisoformat(scfg["no_new_entries_after"])
    flatten_at = dtime.fromisoformat(scfg["flatten_at"])
    open_after = (datetime.combine(date.today(), dtime(9, 30))
                  + timedelta(minutes=scfg["skip_first_minutes"])).time()

    trades = []
    day_trade_dates: list[date] = []
    indicators = {s: SymbolIndicators.from_config(scfg) for s in symbols}
    position = None
    daily_pnl = 0.0
    daily_trades = 0
    cur_day = None
    halted = False
    peak = equity
    max_dd = 0.0
    event_blocked_entries = 0
    regime_blocked_entries = 0
    research_guard_blocked_entries = 0
    research_scaled_entries = 0
    research_exit_adjusted_trades = 0

    for ts, sym, raw in events:
        ts_et = ts.astimezone(ET)
        t = ts_et.time()
        d = ts_et.date()

        if d != cur_day:
            cur_day = d
            daily_pnl = 0.0
            daily_trades = 0
            halted = False
            for ind in indicators.values():
                ind.vwap.reset()

        bar = Bar(ts, raw.open, raw.high, raw.low, raw.close, raw.volume)
        ind = indicators[sym]
        ind.update(bar)

        if position and position["symbol"] == sym:
            exit_price = None
            exit_reason = None
            position["bars_held"] = position.get("bars_held", 0) + 1
            research_exit_rules = _research_exit_rules(research_exit_management, position)
            trail_m = rcfg.get("trail_atr_mult", 0) or 0
            tstop = rcfg.get("time_stop_bars", 0) or 0
            if trail_m and ind.atr.value:
                # Activate once the trade is 1R in profit, then ratchet the
                # stop up under price; never loosen it.
                if not position.get("trail_on") and bar.high >= position["entry"] + position["per_share"]:
                    position["trail_on"] = True
                if position.get("trail_on"):
                    position["stop"] = max(position["stop"],
                                           round(bar.close - trail_m * ind.atr.value, 2))
            for rule in research_exit_rules:
                breakeven_r = rule.get("breakeven_after_r")
                if breakeven_r is not None and bar.high >= position["entry"] + position["per_share"] * float(breakeven_r):
                    position["stop"] = max(position["stop"], round(position["entry"], 2))
            if bar.low <= position["stop"]:
                exit_price = position["stop"] - slip   # stop-market: slips against you
                exit_reason = "stop"
            elif bar.high >= position["tp"]:
                exit_price = position["tp"] - tp_haircut
                exit_reason = "take_profit"
            if exit_price is None:
                for rule in research_exit_rules:
                    bars_held = position.get("bars_held", 0)
                    loser_bars = rule.get("cut_loser_after_bars")
                    loser_r = rule.get("cut_loser_below_r")
                    if loser_bars is not None and loser_r is not None and bars_held >= int(loser_bars):
                        if bar.close <= position["entry"] - position["per_share"] * float(loser_r):
                            exit_price = bar.close - slip
                            exit_reason = "research_loser_cut"
                            break

                    time_bars = rule.get("time_stop_bars")
                    if time_bars is not None and bars_held >= int(time_bars):
                        exit_price = bar.close - slip
                        exit_reason = "research_time_stop"
                        break
            if exit_price is None and t >= flatten_at:
                exit_price = bar.close - slip          # market flatten
                exit_reason = "flatten"
            elif exit_price is None and tstop and position["bars_held"] >= tstop:
                exit_price = bar.close - slip          # time stop: dead trade
                exit_reason = "time_stop"
            if exit_price is not None:
                pnl = (exit_price - position["entry"]) * position["qty"]
                equity += pnl
                daily_pnl += pnl
                daily_trades += 1
                if position["entry_date"] == d:
                    day_trade_dates.append(d)
                trades.append({"date": d, "symbol": sym, "pnl": pnl,
                               "entry_time": position.get("entry_time"),
                               "entry": position["entry"], "exit": exit_price,
                               "qty": position["qty"],
                               "exit_reason": exit_reason,
                               "entry_hour": position.get("entry_hour"),
                               "entry_minute": position.get("entry_minute"),
                               "entry_rsi": position.get("entry_rsi"),
                               "entry_atr_pct": position.get("entry_atr_pct"),
                               "entry_volume_ratio": position.get("entry_volume_ratio"),
                               "entry_vwap_distance_atr": position.get("entry_vwap_distance_atr"),
                               "entry_ema_spread_atr": position.get("entry_ema_spread_atr"),
                               "entry_size_multiplier": position.get("entry_size_multiplier"),
                               "reason": position.get("reason", "")})
                if exit_reason in ("research_loser_cut", "research_time_stop") or research_exit_rules:
                    research_exit_adjusted_trades += 1
                position = None
                peak = max(peak, equity)
                max_dd = max(max_dd, peak - equity)
                if daily_pnl <= -start_equity * rcfg["max_daily_loss_pct"] / 100:
                    halted = True
                if daily_profit_target_pct and daily_pnl >= (equity - daily_pnl) * daily_profit_target_pct / 100:
                    halted = True
            continue

        if position or halted:
            continue
        if not (open_after <= t <= no_new_after) or ts_et.weekday() >= 5:
            continue
        if daily_trades >= rcfg["max_daily_trades"]:
            continue
        if event_risk.blocks_entry(ts_et, sym):
            event_blocked_entries += 1
            continue
        regime_decision = market_regime.decision(indicators)
        if not regime_decision["allowed"]:
            regime_blocked_entries += 1
            continue
        cutoff = business_days_ago(d, 5)
        used = sum(1 for dt_ in day_trade_dates if dt_ > cutoff)
        if cfg["pdt"]["enforce"] and used >= pdt_max:
            continue

        sig = strategy.evaluate(sym, bar, ind, mode_override=regime_decision.get("strategy_mode"))
        if not sig:
            continue
        stop = sig.price - sig.atr * rcfg["stop_atr_mult"]
        risk_dollars = equity * rcfg["risk_per_trade_pct"] / 100
        per_share = sig.price - stop
        if per_share <= 0:
            continue
        qty = int(min(risk_dollars / per_share,
                      equity * rcfg["max_position_pct"] / 100 / sig.price))
        if qty < 1:
            continue
        if rcfg.get("trail_atr_mult", 0):
            tp = sig.price + per_share * 1e6           # trailing mode: no fixed TP
        else:
            tp = sig.price + per_share * rcfg["take_profit_r"]
        entry_fill = sig.price + slip                  # market entry: slips against you
        entry_rsi = ind.rsi.value
        entry_atr_pct = ind.atr.value / bar.close if bar.close > 0 else None
        entry_volume_ratio = bar.volume / ind.prev_avg_volume if ind.prev_avg_volume else None
        entry_vwap_distance_atr = (
            (bar.close - ind.vwap.value) / ind.atr.value
            if ind.vwap.value is not None and ind.atr.value
            else None
        )
        entry_ema_spread_atr = (
            (ind.ema_fast.value - ind.ema_slow.value) / ind.atr.value
            if ind.ema_fast.value is not None and ind.ema_slow.value is not None and ind.atr.value
            else None
        )
        entry_context = {
            "entry_rsi": entry_rsi,
            "entry_atr_pct": entry_atr_pct,
            "entry_volume_ratio": entry_volume_ratio,
            "entry_vwap_distance_atr": entry_vwap_distance_atr,
            "entry_ema_spread_atr": entry_ema_spread_atr,
        }
        if _research_entry_guard_blocks(research_guard, sym, ts_et, entry_context):
            research_guard_blocked_entries += 1
            continue
        size_multiplier = _research_position_scale_multiplier(
            research_position_scale, sym, ts_et, entry_context
        )
        if size_multiplier <= 0:
            research_guard_blocked_entries += 1
            continue
        if size_multiplier < 1.0:
            research_scaled_entries += 1
            qty = int(qty * size_multiplier)
            if qty < 1:
                continue

        position = {"symbol": sym, "qty": qty, "entry": entry_fill,
                    "stop": round(stop, 2), "tp": round(tp, 2), "entry_date": d,
                    "entry_time": ts_et, "entry_hour": ts_et.hour,
                    "entry_minute": ts_et.hour * 60 + ts_et.minute,
                    "entry_size_multiplier": size_multiplier,
                    **entry_context,
                    "reason": sig.reason,
                    "per_share": per_share}

    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_w = sum(t["pnl"] for t in wins)
    gross_l = abs(sum(t["pnl"] for t in losses))
    return {
        "trades": trades,
        "n": len(trades),
        "win_rate": len(wins) / len(trades) * 100 if trades else 0.0,
        "profit_factor": (gross_w / gross_l) if gross_l else (float("inf") if gross_w else 0.0),
        "net": sum(t["pnl"] for t in trades),
        "end_equity": equity,
        "start_equity": start_equity,
        "max_drawdown": max_dd,
        "event_blocked_entries": event_blocked_entries,
        "regime_blocked_entries": regime_blocked_entries,
        "research_guard_blocked_entries": research_guard_blocked_entries,
        "research_scaled_entries": research_scaled_entries,
        "research_exit_adjusted_trades": research_exit_adjusted_trades,
    }


def fetch_events(cfg: dict, start: datetime, end: datetime, symbols: list[str]) -> list:
    """Fetch 1-min bars from Alpaca and return a time-sorted list of
    (timestamp, symbol, bar) events, the format simulate() expects."""
    key = os.environ.get("APCA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY")
    if not key or not secret:
        print("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY env vars.")
        sys.exit(1)

    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(key, secret)
    # Free data plans block SIP data from the last 15 min; clamp the window.
    now_utc = datetime.now(ZoneInfo("UTC"))
    if end.astimezone(ZoneInfo("UTC")) > now_utc - timedelta(minutes=16):
        end = now_utc - timedelta(minutes=16)
    try:
        req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Minute,
                               start=start, end=end)
        barset = client.get_stock_bars(req)
    except Exception as e:
        if "subscription" not in str(e).lower():
            raise
        print("SIP feed not permitted on this plan — falling back to IEX feed.")
        from alpaca.data.enums import DataFeed
        req = StockBarsRequest(symbol_or_symbols=symbols, timeframe=TimeFrame.Minute,
                               start=start, end=end, feed=DataFeed.IEX)
        barset = client.get_stock_bars(req)

    events = []
    for sym in symbols:
        for raw in barset.data.get(sym, []):
            events.append((raw.timestamp, sym, raw))
    events.sort(key=lambda e: e[0])
    return events


def run_backtest(cfg: dict, days: int, symbols: list[str]) -> dict:
    end = datetime.now(ET)
    start = end - timedelta(days=days)
    print(f"Fetching {days} days of 1-min bars for {symbols} ...")
    events = fetch_events(cfg, start, end, symbols)
    s = simulate(cfg, events, symbols)

    print("\n" + "=" * 60)
    print(f"BACKTEST RESULTS  ({days} calendar days, {len(symbols)} symbols)")
    print("=" * 60)
    if not s["n"]:
        print("No trades generated — the entry filters are selective by design. "
              "Try more days or more symbols.")
        return s
    print(f"Trades:        {s['n']}")
    print(f"Win rate:      {s['win_rate']:.1f}%")
    print(f"Profit factor: {s['profit_factor']:.2f}")
    print(f"Max drawdown:  ${s['max_drawdown']:.2f}")
    print(f"Net P&L:       ${s['net']:+.2f}")
    print(f"Ending equity: ${s['end_equity']:.2f}  (started ${s['start_equity']:.2f}, "
          f"{(s['end_equity']/s['start_equity']-1)*100:+.2f}%)")
    sc = cfg.get("backtest", {}).get("slippage_cents", 0)
    print(f"\nNOTE: market fills modeled with {sc}c/share slippage; spread,")
    print("partial fills, and queue position are not. Still optimistic.")
    for t in s["trades"][-10:]:
        print(f"  {t['date']} {t['symbol']:5s} qty {t['qty']:>4d} "
              f"{t['entry']:.2f} -> {t['exit']:.2f}  ${t['pnl']:+.2f}")
    return s


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--days", type=int, default=30)
    p.add_argument("--symbols", nargs="*", default=None)
    args = p.parse_args()
    with open(os.path.join(os.path.dirname(__file__) or ".", "config.yaml")) as f:
        cfg = yaml.safe_load(f)
    run_backtest(cfg, args.days, args.symbols or cfg["symbols"])
