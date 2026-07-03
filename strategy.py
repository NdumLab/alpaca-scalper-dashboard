"""Signal generation for the Alpaca scalper.

Default v6 profile = controlled profit push:
  * Momentum setup: EMA cross + VWAP + volume surge + RSI ceiling.
  * ORB setup: opening-range breakout with volume confirmation.
  * Optional ensemble mode lets the bot take the first valid setup from a
    configured list instead of being locked into only one signal family.

The purpose is not to force trades.  The purpose is to add a second,
explainable edge source so the bot has more ways to make money when the
market is moving cleanly.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta, time as dtime
from zoneinfo import ZoneInfo

from indicators import Bar, SymbolIndicators

log = logging.getLogger("strategy")
ET = ZoneInfo("America/New_York")


@dataclass
class Signal:
    symbol: str
    side: str            # "buy"
    price: float         # last close at signal time
    atr: float           # for stop sizing
    reason: str


class ScalpStrategy:
    def __init__(self, cfg: dict):
        self.cfg = cfg["strategy"]
        self._bars_since_cross: dict[str, int] = {}
        self._blocked_ranges = [self._parse_range(x) for x in self.cfg.get("blocked_time_ranges", [])]
        self._orb: dict[tuple[str, object], tuple[float, float]] = {}
        self._orb_done: set[tuple[str, object]] = set()

    @staticmethod
    def _parse_range(value: str) -> tuple[dtime, dtime]:
        start, end = value.split("-", 1)
        return dtime.fromisoformat(start.strip()), dtime.fromisoformat(end.strip())

    def _time_allowed(self, bar: Bar) -> bool:
        ts_et = bar.timestamp.astimezone(ET)
        allowed_weekdays = self.cfg.get("allowed_weekdays")
        if allowed_weekdays is not None and ts_et.weekday() not in allowed_weekdays:
            return False
        t = ts_et.time()
        for start, end in self._blocked_ranges:
            if start <= t < end:
                return False
        return True

    def evaluate(self, symbol: str, bar: Bar, ind: SymbolIndicators,
                 mode_override: str | None = None) -> Signal | None:
        c = self.cfg
        if not self._time_allowed(bar):
            return None

        mode = mode_override or c.get("mode", "momentum")
        if mode == "ensemble":
            # Try setup families in priority order.  A conservative default is
            # ORB first, then momentum, because ORB only has one shot per day
            # while momentum can appear later in the session.
            for child in c.get("ensemble_modes", ["orb", "momentum"]):
                if child == "orb":
                    sig = self._evaluate_orb(symbol, bar, ind)
                elif child == "reversion":
                    sig = self._evaluate_reversion(symbol, bar, ind)
                else:
                    sig = self._evaluate_momentum(symbol, bar, ind)
                if sig:
                    sig.reason = f"{child.upper()} ensemble | {sig.reason}"
                    return sig
            return None
        if mode == "reversion":
            return self._evaluate_reversion(symbol, bar, ind)
        if mode == "orb":
            return self._evaluate_orb(symbol, bar, ind)
        return self._evaluate_momentum(symbol, bar, ind)

    # ---------------- common helpers ----------------
    def _ready(self, ind: SymbolIndicators, required: tuple) -> bool:
        c = self.cfg
        if ind.bars_seen < c["warmup_bars"]:
            return False
        if any(x is None for x in required):
            return False
        if ind.atr.value is None or ind.atr.value <= 0:
            return False
        return True

    def _passes_common_volatility_filters(self, bar: Bar, ind: SymbolIndicators) -> tuple[bool, float]:
        if ind.atr.value is None or bar.close <= 0:
            return False, 0.0
        c = self.cfg
        atr_pct = ind.atr.value / bar.close
        min_atr_pct = c.get("min_atr_pct", 0) or 0
        max_atr_pct = c.get("max_atr_pct", 0) or 0
        if min_atr_pct and atr_pct < min_atr_pct:
            return False, atr_pct
        if max_atr_pct and atr_pct > max_atr_pct:
            return False, atr_pct
        return True, atr_pct

    def _passes_trend_filter(self, bar: Bar, ind: SymbolIndicators) -> bool:
        # Optional regime filter: trade only when the symbol is above a rising
        # trend EMA.  Disabled unless strategy.trend_ema is set.
        if ind.ema_trend is None:
            return True
        if ind.ema_trend.value is None or ind.prev_ema_trend is None:
            return False
        return bar.close > ind.ema_trend.value and ind.ema_trend.value > ind.prev_ema_trend

    def _volume_ratio(self, bar: Bar, ind: SymbolIndicators) -> float:
        avg_vol = ind.prev_avg_volume or 0
        return bar.volume / avg_vol if avg_vol > 0 else 0.0

    # ---------------- momentum setup ----------------
    def _evaluate_momentum(self, symbol: str, bar: Bar, ind: SymbolIndicators) -> Signal | None:
        c = self.cfg
        if not self._ready(ind, (
            ind.ema_fast.value, ind.ema_slow.value, ind.prev_ema_fast,
            ind.prev_ema_slow, ind.rsi.value, ind.atr.value, ind.vwap.value,
        )):
            return None
        ok, atr_pct = self._passes_common_volatility_filters(bar, ind)
        if not ok or not self._passes_trend_filter(bar, ind):
            return None

        crossed_up = (
            ind.prev_ema_fast <= ind.prev_ema_slow
            and ind.ema_fast.value > ind.ema_slow.value
        )
        if crossed_up:
            self._bars_since_cross[symbol] = 0
        elif symbol in self._bars_since_cross:
            if ind.ema_fast.value > ind.ema_slow.value:
                self._bars_since_cross[symbol] += 1
            else:
                del self._bars_since_cross[symbol]

        recent_cross = (
            symbol in self._bars_since_cross
            and self._bars_since_cross[symbol] <= c["cross_confirm_bars"]
        )

        above_vwap = bar.close > ind.vwap.value
        avg_vol = ind.prev_avg_volume or 0
        volume_ratio = self._volume_ratio(bar, ind)
        volume_surge = avg_vol > 0 and volume_ratio > c["volume_surge_mult"]
        not_overbought = ind.rsi.value < c["rsi_max_entry"]

        ema_spread_atr = (ind.ema_fast.value - ind.ema_slow.value) / ind.atr.value
        min_ema_spread_atr = c.get("min_ema_spread_atr", 0) or 0
        if min_ema_spread_atr and ema_spread_atr < min_ema_spread_atr:
            return None

        vwap_distance_atr = (bar.close - ind.vwap.value) / ind.atr.value
        max_vwap_distance_atr = c.get("max_vwap_distance_atr", 0) or 0
        if max_vwap_distance_atr and vwap_distance_atr > max_vwap_distance_atr:
            return None

        if recent_cross and above_vwap and volume_surge and not_overbought:
            reason = (
                f"EMA{c['ema_fast']}x{c['ema_slow']} cross-up | "
                f"close {bar.close:.2f} > VWAP {ind.vwap.value:.2f} "
                f"({vwap_distance_atr:.2f} ATR) | "
                f"vol {bar.volume:.0f} = {volume_ratio:.2f}x prev avg {avg_vol:.0f} | "
                f"EMA spread {ema_spread_atr:.2f} ATR | "
                f"ATR {atr_pct*100:.2f}% | RSI {ind.rsi.value:.1f}"
            )
            log.info("SIGNAL %s LONG — %s", symbol, reason)
            self._bars_since_cross.pop(symbol, None)  # one entry per cross
            return Signal(symbol=symbol, side="buy", price=bar.close,
                          atr=ind.atr.value, reason=reason)
        return None

    # ---------------- reversion setup ----------------
    def _evaluate_reversion(self, symbol: str, bar: Bar, ind: SymbolIndicators) -> Signal | None:
        """VWAP mean-reversion: buy capitulation dips below session VWAP.

        Long when: close < VWAP - dev*ATR  (stretched below fair value)
                   AND RSI < rsi_min_entry (short-term oversold)
        Exit via the same bracket mechanics as momentum mode.
        """
        c = self.cfg
        if not self._ready(ind, (ind.rsi.value, ind.atr.value, ind.vwap.value)):
            return None
        ok, atr_pct = self._passes_common_volatility_filters(bar, ind)
        if not ok:
            return None
        stretched = bar.close < ind.vwap.value - c.get("vwap_dev_atr", 1.5) * ind.atr.value
        oversold = ind.rsi.value < c.get("rsi_min_entry", 35)
        if stretched and oversold:
            reason = (f"reversion: close {bar.close:.2f} < VWAP {ind.vwap.value:.2f} "
                      f"- {c.get('vwap_dev_atr', 1.5)}*ATR | RSI {ind.rsi.value:.1f} | "
                      f"ATR {atr_pct*100:.2f}%")
            log.info("SIGNAL %s LONG — %s", symbol, reason)
            return Signal(symbol=symbol, side="buy", price=bar.close,
                          atr=ind.atr.value, reason=reason)
        return None

    # ---------------- opening range breakout setup ----------------
    def _evaluate_orb(self, symbol: str, bar: Bar, ind: SymbolIndicators) -> Signal | None:
        """Opening Range Breakout.

        Buy when price breaks above the first N-minute range on a volume surge.
        This gives v6 a second profit source: clean opening continuation days.
        """
        c = self.cfg
        ts_et = bar.timestamp.astimezone(ET)
        d = ts_et.date()
        key = (symbol, d)
        n = c.get("orb_minutes", 30)
        bar_minutes = max(1, int(c.get("bar_minutes", 1)))
        bucket_start = ts_et - timedelta(minutes=bar_minutes)
        mins_from_open = (bucket_start.hour - 9) * 60 + bucket_start.minute - 30

        # Build the opening range even while ATR/RSI/EMA are still warming up.
        # Otherwise an ORB setup can never form on short sessions or synthetic
        # tests because the warmup gate would block the range collection itself.
        if 0 <= mins_from_open < n:
            hi, lo = self._orb.get(key, (0.0, 1e12))
            self._orb[key] = (max(hi, bar.high), min(lo, bar.low))
            return None
        if key not in self._orb or key in self._orb_done or mins_from_open < n:
            return None

        if not self._ready(ind, (ind.atr.value, ind.vwap.value, ind.rsi.value)):
            return None
        ok, atr_pct = self._passes_common_volatility_filters(bar, ind)
        if not ok or not self._passes_trend_filter(bar, ind):
            return None

        hi, lo = self._orb[key]
        avg_vol = ind.prev_avg_volume or 0
        volume_ratio = self._volume_ratio(bar, ind)
        surge = avg_vol > 0 and volume_ratio > c.get("orb_vol_mult", 1.5)
        above_vwap = bar.close > ind.vwap.value
        not_overbought = ind.rsi.value < c.get("orb_rsi_max_entry", c.get("rsi_max_entry", 75))
        vwap_distance_atr = (bar.close - ind.vwap.value) / ind.atr.value
        max_dist = c.get("orb_max_vwap_distance_atr", 0) or 0
        not_too_stretched = True if not max_dist else vwap_distance_atr <= max_dist

        if bar.close > hi and surge and above_vwap and not_overbought and not_too_stretched:
            self._orb_done.add(key)
            reason = (f"ORB: close {bar.close:.2f} broke {n}-min high {hi:.2f} | "
                      f"vol {volume_ratio:.2f}x prev avg {avg_vol:.0f} | "
                      f"VWAP distance {vwap_distance_atr:.2f} ATR | "
                      f"ATR {atr_pct*100:.2f}% | RSI {ind.rsi.value:.1f}")
            log.info("SIGNAL %s LONG — %s", symbol, reason)
            return Signal(symbol=symbol, side="buy", price=bar.close,
                          atr=ind.atr.value, reason=reason)
        return None
