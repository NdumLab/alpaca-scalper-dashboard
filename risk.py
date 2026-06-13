"""Risk management — the part of the bot that matters most at $2,000.

Responsibilities:
  * Position sizing from stop distance (risk a fixed % of equity per trade)
  * Daily loss kill switch
  * Max trades/day, max concurrent positions, post-loss cooldown
  * Optional self-imposed day-trade cap

All session dates use America/New_York.  That matters because a server
running in UTC would otherwise reset daily risk around 8 PM ET instead of
at the trading session boundary.
"""
from __future__ import annotations

import csv
import json
import logging
import os
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

log = logging.getLogger("risk")

STATE_FILE = os.environ.get("STATE_PATH", "bot_state.json")
ET = ZoneInfo("America/New_York")


def today_et() -> date:
    return datetime.now(ET).date()


class RiskManager:
    def __init__(self, cfg: dict):
        self.cfg = cfg["risk"]
        self.pdt_cfg = cfg["pdt"]
        self.trade_log = os.environ.get("TRADE_LOG_PATH", cfg["logging"]["trade_log"])
        self.day_trades: list[str] = []      # ISO dates of completed day trades
        self.daily_pnl = 0.0
        self.daily_trade_count = 0
        self.session_date: str = today_et().isoformat()
        self.last_loss_time: datetime | None = None
        self.start_equity_today: float | None = None
        self.halted = False
        self._load_state()

    # ---------------- persistence ----------------
    def _load_state(self):
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    s = json.load(f)
                self.day_trades = s.get("day_trades", [])
                if s.get("session_date") == self.session_date:
                    self.daily_pnl = s.get("daily_pnl", 0.0)
                    self.daily_trade_count = s.get("daily_trade_count", 0)
                    self.halted = s.get("halted", False)
            except Exception as e:
                log.warning("Could not load state: %s", e)
        self._prune_day_trades()

    def _save_state(self):
        Path(STATE_FILE).parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, "w") as f:
            json.dump({
                "day_trades": self.day_trades,
                "session_date": self.session_date,
                "daily_pnl": self.daily_pnl,
                "daily_trade_count": self.daily_trade_count,
                "halted": self.halted,
            }, f, indent=2)

    # ---------------- PDT / discipline cap ----------------
    def _prune_day_trades(self):
        """Keep only day trades within the last 5 business days."""
        cutoff = today_et()
        days = 0
        while days < 5:
            cutoff -= timedelta(days=1)
            if cutoff.weekday() < 5:
                days += 1
        self.day_trades = [d for d in self.day_trades if d >= cutoff.isoformat()]

    def day_trades_used(self) -> int:
        self._prune_day_trades()
        return len(self.day_trades)

    def can_day_trade(self) -> bool:
        if not self.pdt_cfg["enforce"]:
            return True
        return self.day_trades_used() < self.pdt_cfg["max_day_trades_per_5_days"]

    def record_day_trade(self):
        self.day_trades.append(today_et().isoformat())
        self._save_state()
        log.warning("Day trade recorded. Used %d/%d in rolling 5-day window.",
                    self.day_trades_used(),
                    self.pdt_cfg["max_day_trades_per_5_days"])

    # ---------------- daily limits ----------------
    def new_session(self, equity: float):
        today = today_et().isoformat()
        if today != self.session_date:
            self.session_date = today
            self.daily_pnl = 0.0
            self.daily_trade_count = 0
            self.halted = False
            self.last_loss_time = None
        self.start_equity_today = equity
        self._save_state()

    def record_fill_result(self, pnl: float):
        self.daily_pnl += pnl
        self.daily_trade_count += 1
        if pnl < 0:
            self.last_loss_time = datetime.now(ET)
        if self.start_equity_today:
            loss_limit = self.start_equity_today * self.cfg["max_daily_loss_pct"] / 100
            if self.daily_pnl <= -loss_limit:
                self.halted = True
                log.error("DAILY LOSS LIMIT HIT (%.2f). Trading halted for today.",
                          self.daily_pnl)
        self._save_state()

    # ---------------- entry gating ----------------
    def can_enter(self, open_positions: int) -> tuple[bool, str]:
        if self.halted:
            return False, "daily loss limit hit — halted"
        if self.daily_trade_count >= self.cfg["max_daily_trades"]:
            return False, f"max daily trades ({self.cfg['max_daily_trades']}) reached"
        if open_positions >= self.cfg["max_concurrent_positions"]:
            return False, "max concurrent positions reached"
        if not self.can_day_trade():
            return False, "self-imposed day-trade cap reached"
        if self.last_loss_time:
            cooldown = timedelta(minutes=self.cfg["cooldown_minutes_after_loss"])
            if datetime.now(ET) - self.last_loss_time < cooldown:
                return False, "in post-loss cooldown"
        return True, "ok"

    # ---------------- sizing ----------------
    def position_size(self, equity: float, buying_power: float,
                      entry: float, stop: float) -> int:
        risk_dollars = equity * self.cfg["risk_per_trade_pct"] / 100
        per_share_risk = entry - stop
        if per_share_risk <= 0:
            return 0
        qty_by_risk = int(risk_dollars / per_share_risk)
        max_notional = buying_power * self.cfg["max_position_pct"] / 100
        qty_by_bp = int(max_notional / entry)
        qty = max(0, min(qty_by_risk, qty_by_bp))
        log.info("Sizing: equity=%.2f risk$=%.2f stop_dist=%.3f -> qty_by_risk=%d, "
                 "qty_by_bp=%d, final=%d", equity, risk_dollars, per_share_risk,
                 qty_by_risk, qty_by_bp, qty)
        return qty

    # ---------------- trade log ----------------
    def log_trade(self, row: dict):
        Path(self.trade_log).parent.mkdir(parents=True, exist_ok=True)
        exists = os.path.exists(self.trade_log)
        with open(self.trade_log, "a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(row.keys()))
            if not exists:
                w.writeheader()
            w.writerow(row)
