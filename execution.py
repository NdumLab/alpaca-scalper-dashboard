"""Order execution against the Alpaca Trading API (alpaca-py SDK).

Entries are bracket orders: a single submission that carries the
take-profit and stop-loss with it, so the position is never naked —
even if the bot crashes a second after the fill, the exits live
server-side at Alpaca.
"""
from __future__ import annotations

import logging

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce, OrderClass
from alpaca.trading.requests import (
    LimitOrderRequest,
    TakeProfitRequest,
    StopLossRequest,
)

log = logging.getLogger("exec")


class Executor:
    def __init__(self, trading: TradingClient, cfg: dict):
        self.trading = trading
        self.rcfg = cfg["risk"]
        self.ecfg = cfg.get("execution", {})

    def enter_long_bracket(self, symbol: str, qty: int, entry: float, atr: float):
        """Marketable limit entry with attached TP and SL."""
        stop = round(entry - atr * self.rcfg["stop_atr_mult"], 2)
        risk = entry - stop
        tp = round(entry + risk * self.rcfg["take_profit_r"], 2)
        max_offset = self.ecfg.get("entry_limit_offset_cents", 3) / 100.0
        limit = round(entry + max_offset, 2)

        if stop >= entry or tp <= entry:
            log.error("Invalid bracket math for %s (entry=%.2f stop=%.2f tp=%.2f)",
                      symbol, entry, stop, tp)
            return None

        req = LimitOrderRequest(
            symbol=symbol,
            qty=qty,
            side=OrderSide.BUY,
            time_in_force=TimeInForce.DAY,
            limit_price=limit,
            order_class=OrderClass.BRACKET,
            take_profit=TakeProfitRequest(limit_price=tp),
            stop_loss=StopLossRequest(stop_price=stop),
        )
        order = self.trading.submit_order(req)
        log.info("BRACKET SUBMITTED %s qty=%d limit=%.2f tp=%.2f sl=%.2f (R=%.2f)",
                 symbol, qty, limit, tp, stop, risk)
        return {"order": order, "entry": entry, "stop": stop, "tp": tp, "qty": qty}

    def flatten_all(self):
        """Cancel everything and close all positions — end-of-day or kill switch."""
        try:
            self.trading.cancel_orders()
        except Exception as e:
            log.warning("cancel_orders: %s", e)
        try:
            self.trading.close_all_positions(cancel_orders=True)
            log.info("All positions flattened.")
        except Exception as e:
            log.warning("close_all_positions: %s", e)

    def open_position_count(self) -> int:
        try:
            return len(self.trading.get_all_positions())
        except Exception as e:
            log.warning("get_all_positions: %s", e)
            return 0
