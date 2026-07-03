"""Market-regime entry gate.

The scalper is long-momentum biased, so this gate answers one question before a
new entry: are broad-market proxies aligned enough for long momentum?
"""
from __future__ import annotations


class MarketRegime:
    def __init__(self, cfg: dict):
        self.cfg = cfg.get("market_regime", {}) or {}
        self.enabled = bool(self.cfg.get("enabled", False))
        self.symbols = [str(s).upper() for s in self.cfg.get("symbols", ["SPY", "QQQ"])]
        self.min_symbols_passing = int(self.cfg.get("min_symbols_passing", len(self.symbols)))
        self.require_fast_above_slow = bool(self.cfg.get("require_fast_above_slow", True))
        self.require_close_above_vwap = bool(self.cfg.get("require_close_above_vwap", False))
        self.require_close_above_slow = bool(self.cfg.get("require_close_above_slow", True))
        self.max_atr_pct = float(self.cfg.get("max_atr_pct", 0) or 0)
        self.min_atr_pct = float(self.cfg.get("min_atr_pct", 0) or 0)
        self.min_bars = int(self.cfg.get("min_bars", 30))
        self.regime_strategies = self.cfg.get("regime_strategies", {}) or {}

    def _symbol_passes(self, ind) -> tuple[bool, str]:
        last_close = getattr(ind, "last_close", None)
        if ind is None or ind.bars_seen < self.min_bars or last_close is None:
            return False, "not_ready"
        if ind.ema_slow.value is None or ind.ema_fast.value is None or ind.atr.value is None:
            return False, "not_ready"
        if self.require_fast_above_slow and ind.ema_fast.value <= ind.ema_slow.value:
            return False, "fast_below_slow"
        if self.require_close_above_slow and last_close <= ind.ema_slow.value:
            return False, "close_below_slow"
        if self.require_close_above_vwap:
            if ind.vwap.value is None or last_close <= ind.vwap.value:
                return False, "close_below_vwap"
        atr_pct = ind.atr.value / last_close if last_close > 0 else 0.0
        if self.min_atr_pct and atr_pct < self.min_atr_pct:
            return False, "atr_too_low"
        if self.max_atr_pct and atr_pct > self.max_atr_pct:
            return False, "atr_too_high"
        return True, "pass"

    def evaluate(self, indicators: dict) -> dict:
        if not self.enabled:
            return {
                "enabled": False,
                "allowed": True,
                "passing": 0,
                "required": self.min_symbols_passing,
                "symbols": {},
            }

        details = {}
        passing = 0
        for symbol in self.symbols:
            ok, reason = self._symbol_passes(indicators.get(symbol))
            details[symbol] = {"pass": ok, "reason": reason}
            if ok:
                passing += 1
        state = self._state(passing)
        strategy_mode = self._strategy_mode(state)
        return {
            "enabled": True,
            "allowed": strategy_mode not in ("", "block", "none"),
            "state": state,
            "strategy_mode": strategy_mode,
            "passing": passing,
            "required": self.min_symbols_passing,
            "symbols": details,
        }

    def _state(self, passing: int) -> str:
        if passing >= self.min_symbols_passing:
            return "bullish"
        if passing > 0:
            return "mixed"
        return "bearish"

    def _strategy_mode(self, state: str) -> str:
        if not self.regime_strategies:
            return "momentum" if state == "bullish" else "block"
        return str(self.regime_strategies.get(state, "block")).lower()

    def decision(self, indicators: dict) -> dict:
        return self.evaluate(indicators)

    def allows_entry(self, indicators: dict) -> bool:
        return self.decision(indicators)["allowed"]

    def status(self, indicators: dict | None = None) -> dict:
        if indicators is None:
            return {
                "enabled": self.enabled,
                "symbols": self.symbols,
                "min_symbols_passing": self.min_symbols_passing,
            }
        return self.evaluate(indicators)
