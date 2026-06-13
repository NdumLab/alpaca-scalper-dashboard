#!/usr/bin/env python3
"""Alpaca 1-minute scalping bot — main entrypoint.

Usage:
    export APCA_API_KEY_ID="your_key"
    export APCA_API_SECRET_KEY="your_secret"
    python main.py                # uses config.yaml (paper by default)

Architecture:
    StockDataStream  -> 1-min bars -> indicators -> strategy -> risk gate -> bracket order
    TradingStream    -> fill/close events -> P&L tracking, PDT counting, kill switch
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from alpaca.data.live import StockDataStream
from alpaca.trading.client import TradingClient
from alpaca.trading.stream import TradingStream

from indicators import Bar, SymbolIndicators
from strategy import ScalpStrategy
from risk import RiskManager
from execution import Executor

ET = ZoneInfo("America/New_York")
RUNTIME_DIR = Path(os.environ.get("RUNTIME_DIR", "runtime"))
HEARTBEAT_FILE = RUNTIME_DIR / "heartbeat.json"
PAUSE_FILE = RUNTIME_DIR / "paused"
RESTART_FILE = RUNTIME_DIR / "restart_requested"
LOG_FILE = Path(os.environ.get("LOG_PATH", "bot.log"))
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)-8s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler(LOG_FILE)],
)
log = logging.getLogger("main")


class ScalpBot:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        key = os.environ.get("APCA_API_KEY_ID")
        secret = os.environ.get("APCA_API_SECRET_KEY")
        if not key or not secret:
            log.error("Set APCA_API_KEY_ID and APCA_API_SECRET_KEY env vars.")
            sys.exit(1)

        paper = cfg["alpaca"]["paper"]
        if not paper:
            log.warning("=" * 60)
            log.warning("LIVE TRADING MODE — real money. Ctrl+C now if unintended.")
            log.warning("=" * 60)

        self.trading = TradingClient(key, secret, paper=paper)
        self.data_stream = StockDataStream(key, secret)
        self.trade_stream = TradingStream(key, secret, paper=paper)

        self.symbols = cfg["symbols"]
        self.strategy = ScalpStrategy(cfg)
        self.risk = RiskManager(cfg)
        self.executor = Executor(self.trading, cfg)
        self.indicators: dict[str, SymbolIndicators] = {
            s: SymbolIndicators.from_config(cfg["strategy"]) for s in self.symbols
        }
        self.open_trades: dict[str, dict] = {}   # symbol -> bracket info
        self.entry_dates: dict[str, str] = {}    # symbol -> ISO date of entry
        self._flattened_today = False
        self._session_date = self.now_et().date().isoformat()

        scfg = cfg["strategy"]
        self.flatten_at = dtime.fromisoformat(scfg["flatten_at"])
        self.no_new_after = dtime.fromisoformat(scfg["no_new_entries_after"])
        self.skip_first = scfg["skip_first_minutes"]
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------- session helpers ----------------
    def now_et(self) -> datetime:
        return datetime.now(ET)

    def in_entry_window(self) -> bool:
        n = self.now_et()
        if n.weekday() >= 5:
            return False
        open_dt = datetime.combine(n.date(), dtime(9, 30), ET)
        start = (open_dt + timedelta(minutes=self.skip_first)).time()
        return start <= n.time() <= self.no_new_after

    def past_flatten_time(self) -> bool:
        return self.now_et().time() >= self.flatten_at

    def is_paused(self) -> bool:
        return PAUSE_FILE.exists()

    def check_restart_requested(self):
        if RESTART_FILE.exists():
            try:
                RESTART_FILE.unlink()
            except OSError:
                pass
            log.warning("Dashboard restart requested — exiting for Compose restart.")
            sys.exit(0)

    def write_heartbeat(self, status: str = "running"):
        payload = {
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "time_et": self.now_et().isoformat(timespec="seconds"),
            "status": status,
            "paused": self.is_paused(),
            "mode": "paper" if self.cfg["alpaca"]["paper"] else "live",
            "symbols": self.symbols,
        }
        tmp = HEARTBEAT_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(HEARTBEAT_FILE)

    async def heartbeat_loop(self):
        while True:
            self.check_restart_requested()
            self.write_heartbeat("paused" if self.is_paused() else "running")
            await asyncio.sleep(15)

    def refresh_session_if_needed(self):
        """Reset once per New York trading date if the bot runs overnight."""
        today = self.now_et().date().isoformat()
        if today == self._session_date:
            return
        acct = self.trading.get_account()
        self.risk.new_session(float(acct.equity))
        self._session_date = today
        self._flattened_today = False
        self.open_trades.clear()
        self.entry_dates.clear()
        for ind in self.indicators.values():
            ind.vwap.reset()
        log.info("New session detected — risk counters and VWAP reset for %s", today)

    # ---------------- historical warmup preload ----------------
    def preload_history(self):
        """Seed indicators with recent historical bars before live streaming.

        Without this, a 15-minute strategy with 30 warmup bars may need most of
        a trading day before the first valid live signal.  Preloading lets the
        bot start the day with EMA/ATR/RSI/VWAP context already available.
        """
        scfg = self.cfg["strategy"]
        bar_minutes = max(1, int(scfg.get("bar_minutes", 1)))
        warmup_bars = int(scfg.get("warmup_bars", 30))
        volume_lookback = int(scfg.get("volume_lookback", 20))
        lookback_minutes = bar_minutes * (warmup_bars + volume_lookback + 10)

        # Calendar padding handles nights/weekends.  We only keep regular-session
        # bars after the fetch, but asking for several days avoids starting cold
        # on Monday morning.
        end = self.now_et() - timedelta(minutes=20)
        start = end - timedelta(days=max(5, lookback_minutes // 390 + 4))
        log.info("Preloading historical bars from %s to %s ...", start, end)

        try:
            from alpaca.data.historical import StockHistoricalDataClient
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame
            client = StockHistoricalDataClient(
                os.environ["APCA_API_KEY_ID"],
                os.environ["APCA_API_SECRET_KEY"],
            )
            try:
                req = StockBarsRequest(symbol_or_symbols=self.symbols,
                                       timeframe=TimeFrame.Minute,
                                       start=start, end=end)
                barset = client.get_stock_bars(req)
            except Exception as e:
                if "subscription" not in str(e).lower():
                    raise
                log.info("SIP feed not permitted on this plan — using IEX feed for preload.")
                from alpaca.data.enums import DataFeed
                req = StockBarsRequest(symbol_or_symbols=self.symbols,
                                       timeframe=TimeFrame.Minute,
                                       start=start, end=end, feed=DataFeed.IEX)
                barset = client.get_stock_bars(req)
        except Exception as e:
            log.warning("Historical preload skipped: %s", e)
            return

        events = []
        for sym in self.symbols:
            for raw in barset.data.get(sym, []):
                events.append((raw.timestamp, sym, raw))
        events.sort(key=lambda e: e[0])

        last_day: dict[str, object] = {}
        completed = 0
        for ts, sym, raw in events:
            ts_et = ts.astimezone(ET)
            # Keep regular session context only.
            if ts_et.weekday() >= 5 or not (dtime(9, 30) <= ts_et.time() <= dtime(16, 0)):
                continue
            if last_day.get(sym) != ts_et.date():
                self.indicators[sym].vwap.reset()
                last_day[sym] = ts_et.date()
            out = self._aggregate(sym, raw)
            if out is None:
                continue
            self.indicators[sym].update(out)
            completed += 1
        log.info("Historical preload complete: %d completed strategy bars seeded.", completed)

    # ---------------- bar handler ----------------
    def _aggregate(self, symbol, bar):
        """Roll incoming 1-min bars into strategy.bar_minutes buckets.
        Returns a completed Bar when a bucket closes, else None.
        The completed bar is stamped at bucket CLOSE time, matching the
        backtest's resampling convention exactly."""
        from datetime import timedelta
        n = self.cfg["strategy"].get("bar_minutes", 1)
        if n <= 1:
            return Bar(bar.timestamp, bar.open, bar.high, bar.low, bar.close, bar.volume)
        if not hasattr(self, "_buckets"):
            self._buckets = {}
        et = bar.timestamp.astimezone(ET)
        bstart = et.replace(minute=(et.minute // n) * n, second=0, microsecond=0)
        cur = self._buckets.get(symbol)
        out = None
        if cur is not None and cur["start"] != bstart:
            out = Bar(cur["start"] + timedelta(minutes=n),
                      cur["o"], cur["h"], cur["l"], cur["c"], cur["v"])
            cur = None
        if cur is None:
            self._buckets[symbol] = {"start": bstart, "o": bar.open, "h": bar.high,
                                     "l": bar.low, "c": bar.close, "v": bar.volume}
        else:
            cur["h"] = max(cur["h"], bar.high); cur["l"] = min(cur["l"], bar.low)
            cur["c"] = bar.close; cur["v"] += bar.volume
        return out

    async def on_bar(self, bar):
        self.check_restart_requested()
        self.write_heartbeat("paused" if self.is_paused() else "running")
        self.refresh_session_if_needed()
        symbol = bar.symbol

        # End-of-day flatten must run on RAW 1-min cadence, never wait for
        # a 15-min bucket to close.
        if self.past_flatten_time() and not self._flattened_today:
            log.info("Flatten time reached — closing everything.")
            self.executor.flatten_all()
            self._flattened_today = True
            return

        b = self._aggregate(symbol, bar)
        if b is None:
            return   # bucket still filling
        ind = self.indicators[symbol]

        # Reset VWAP at the first bar of a new session
        ts_et = bar.timestamp.astimezone(ET)
        if ts_et.time() <= dtime(9, 31) and ind.vwap.cum_vol > 0:
            ind.vwap.reset()

        ind.update(b)

        if self.is_paused():
            return

        if not self.in_entry_window():
            return

        signal = self.strategy.evaluate(symbol, b, ind)
        if not signal:
            return
        if symbol in self.open_trades:
            return

        # Count submitted-but-not-filled brackets too. Alpaca positions may still
        # show 0 while an entry order is pending; without this guard, fast signals
        # across multiple symbols could bypass max_concurrent_positions.
        open_count = max(self.executor.open_position_count(), len(self.open_trades))
        ok, why = self.risk.can_enter(open_count)
        if not ok:
            log.info("Signal on %s skipped: %s", symbol, why)
            return

        # An entry today + the bracket exit today = 1 day trade.
        # Only enter if we have a day trade available to spend.
        acct = self.trading.get_account()
        equity = float(acct.equity)
        buying_power = float(acct.buying_power)

        stop = signal.price - signal.atr * self.cfg["risk"]["stop_atr_mult"]
        qty = self.risk.position_size(equity, buying_power, signal.price, stop)
        if qty < 1:
            log.info("Signal on %s skipped: computed qty < 1 "
                     "(price too high for account size — consider removing "
                     "high-priced symbols or using notional sizing)", symbol)
            return

        result = self.executor.enter_long_bracket(symbol, qty, signal.price, signal.atr)
        if result:
            result["reason"] = signal.reason
            self.open_trades[symbol] = result
            self.entry_dates[symbol] = self.now_et().date().isoformat()

    # ---------------- trade update handler ----------------
    async def on_trade_update(self, data):
        ev = data.event
        order = data.order
        symbol = order.symbol
        log.info("TRADE UPDATE %s %s %s", symbol, ev, order.side)

        if ev != "fill":
            return

        trade = self.open_trades.get(symbol)
        side = str(order.side).lower()

        # The signal close is only an estimate.  Once Alpaca confirms the BUY fill,
        # store the real filled average price so live P&L and risk logs are honest.
        if trade and side.endswith("buy"):
            filled_price = float(order.filled_avg_price or trade["entry"])
            filled_qty = int(float(order.filled_qty or trade["qty"]))
            trade["entry"] = filled_price
            trade["qty"] = filled_qty
            log.info("ENTRY FILLED %s qty=%d avg=%.2f", symbol, filled_qty, filled_price)
            return

        # A SELL fill on a symbol we entered = bracket leg closed the position
        if trade and side.endswith("sell"):
            entry = trade["entry"]
            qty = int(float(order.filled_qty or trade["qty"]))
            exit_price = float(order.filled_avg_price or 0)
            pnl = (exit_price - entry) * qty
            self.risk.record_fill_result(pnl)

            # Same-day round trip = day trade
            if self.entry_dates.get(symbol) == self.now_et().date().isoformat():
                self.risk.record_day_trade()

            self.risk.log_trade({
                "time": self.now_et().isoformat(),
                "symbol": symbol,
                "qty": qty,
                "entry": entry,
                "exit": exit_price,
                "pnl": round(pnl, 2),
                "daily_pnl": round(self.risk.daily_pnl, 2),
                "day_trades_used": self.risk.day_trades_used(),
                "reason": trade.get("reason", ""),
            })
            log.info("CLOSED %s: entry %.2f -> exit %.2f, P&L %.2f (day P&L %.2f)",
                     symbol, entry, exit_price, pnl, self.risk.daily_pnl)
            self.open_trades.pop(symbol, None)
            self.entry_dates.pop(symbol, None)

            if self.risk.halted:
                log.error("Kill switch active — flattening and standing down.")
                self.executor.flatten_all()

    # ---------------- run ----------------
    async def run(self):
        acct = self.trading.get_account()
        equity = float(acct.equity)
        self.risk.new_session(equity)

        log.info("=" * 60)
        log.info("Scalp bot starting | %s mode | equity $%.2f",
                 "PAPER" if self.cfg["alpaca"]["paper"] else "LIVE", equity)
        log.info("Symbols: %s", ", ".join(self.symbols))
        if self.cfg["pdt"]["enforce"]:
            log.info("Optional self-imposed day-trade cap active: %d per 5 days.",
                     self.cfg["pdt"]["max_day_trades_per_5_days"])
        else:
            log.info("PDT rule retired (June 2026) — no day-trade cap. Intraday "
                     "buying power is governed by Alpaca's real-time margin excess; "
                     "an unmet intraday margin deficit can still freeze the account, "
                     "so daily trade/loss limits below remain your safety net.")
        log.info("=" * 60)

        self.preload_history()

        self.data_stream.subscribe_bars(self.on_bar, *self.symbols)
        self.trade_stream.subscribe_trade_updates(self.on_trade_update)

        await asyncio.gather(
            self.heartbeat_loop(),
            self.data_stream._run_forever(),
            self.trade_stream._run_forever(),
        )


def main():
    with open(os.path.join(os.path.dirname(__file__) or ".", "config.yaml")) as f:
        cfg = yaml.safe_load(f)
    bot = ScalpBot(cfg)
    try:
        asyncio.run(bot.run())
    except KeyboardInterrupt:
        log.info("Interrupted — flattening positions before exit.")
        bot.executor.flatten_all()


if __name__ == "__main__":
    main()
