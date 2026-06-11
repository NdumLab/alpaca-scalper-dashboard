"""Lightweight incremental indicators for 1-minute bars.

No pandas in the hot path — everything is O(1) per bar so the bot
reacts the instant a bar closes.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field


@dataclass
class Bar:
    timestamp: object
    open: float
    high: float
    low: float
    close: float
    volume: float


class EMA:
    def __init__(self, period: int):
        self.period = period
        self.k = 2 / (period + 1)
        self.value: float | None = None
        self._seed: list[float] = []

    def update(self, price: float) -> float | None:
        if self.value is None:
            self._seed.append(price)
            if len(self._seed) >= self.period:
                self.value = sum(self._seed) / len(self._seed)
            return self.value
        self.value = price * self.k + self.value * (1 - self.k)
        return self.value


class RSI:
    """Wilder's RSI, incremental."""

    def __init__(self, period: int = 14):
        self.period = period
        self.avg_gain: float | None = None
        self.avg_loss: float | None = None
        self.prev_close: float | None = None
        self._gains: list[float] = []
        self._losses: list[float] = []
        self.value: float | None = None

    def update(self, close: float) -> float | None:
        if self.prev_close is None:
            self.prev_close = close
            return None
        change = close - self.prev_close
        self.prev_close = close
        gain = max(change, 0.0)
        loss = max(-change, 0.0)

        if self.avg_gain is None:
            self._gains.append(gain)
            self._losses.append(loss)
            if len(self._gains) >= self.period:
                self.avg_gain = sum(self._gains) / self.period
                self.avg_loss = sum(self._losses) / self.period
            else:
                return None
        else:
            self.avg_gain = (self.avg_gain * (self.period - 1) + gain) / self.period
            self.avg_loss = (self.avg_loss * (self.period - 1) + loss) / self.period

        if self.avg_loss == 0:
            self.value = 100.0
        else:
            rs = self.avg_gain / self.avg_loss
            self.value = 100 - (100 / (1 + rs))
        return self.value


class ATR:
    """Wilder's ATR, incremental."""

    def __init__(self, period: int = 14):
        self.period = period
        self.value: float | None = None
        self.prev_close: float | None = None
        self._trs: list[float] = []

    def update(self, bar: Bar) -> float | None:
        if self.prev_close is None:
            tr = bar.high - bar.low
        else:
            tr = max(
                bar.high - bar.low,
                abs(bar.high - self.prev_close),
                abs(bar.low - self.prev_close),
            )
        self.prev_close = bar.close

        if self.value is None:
            self._trs.append(tr)
            if len(self._trs) >= self.period:
                self.value = sum(self._trs) / self.period
            return self.value
        self.value = (self.value * (self.period - 1) + tr) / self.period
        return self.value


class VWAP:
    """Session VWAP — reset() must be called at each market open."""

    def __init__(self):
        self.cum_pv = 0.0
        self.cum_vol = 0.0
        self.value: float | None = None

    def reset(self):
        self.cum_pv = 0.0
        self.cum_vol = 0.0
        self.value = None

    def update(self, bar: Bar) -> float | None:
        typical = (bar.high + bar.low + bar.close) / 3
        self.cum_pv += typical * bar.volume
        self.cum_vol += bar.volume
        if self.cum_vol > 0:
            self.value = self.cum_pv / self.cum_vol
        return self.value


@dataclass
class SymbolIndicators:
    """All indicator state for one symbol."""

    ema_fast: EMA
    ema_slow: EMA
    rsi: RSI
    atr: ATR
    vwap: VWAP
    ema_trend: EMA | None = None
    volumes: deque = field(default_factory=lambda: deque(maxlen=20))
    bars_seen: int = 0
    prev_ema_fast: float | None = None
    prev_ema_slow: float | None = None
    prev_ema_trend: float | None = None
    prev_avg_volume: float | None = None

    @classmethod
    def from_config(cls, scfg: dict) -> "SymbolIndicators":
        ind = cls(
            ema_fast=EMA(scfg["ema_fast"]),
            ema_slow=EMA(scfg["ema_slow"]),
            rsi=RSI(scfg["rsi_period"]),
            atr=ATR(scfg["atr_period"]),
            vwap=VWAP(),
        )
        ind.volumes = deque(maxlen=scfg["volume_lookback"])
        tp = scfg.get("trend_ema", 0)
        ind.ema_trend = EMA(tp) if tp else None
        return ind

    def update(self, bar: Bar):
        self.prev_ema_fast = self.ema_fast.value
        self.prev_ema_slow = self.ema_slow.value
        if self.ema_trend is not None:
            self.prev_ema_trend = self.ema_trend.value
            self.ema_trend.update(bar.close)

        # Important: save the average BEFORE adding the current bar.  A volume
        # surge should be compared against the previous N bars, not against an
        # average that already includes the surge bar itself.
        self.prev_avg_volume = self.avg_volume

        self.ema_fast.update(bar.close)
        self.ema_slow.update(bar.close)
        self.rsi.update(bar.close)
        self.atr.update(bar)
        self.vwap.update(bar)
        self.volumes.append(bar.volume)
        self.bars_seen += 1

    @property
    def avg_volume(self) -> float | None:
        if not self.volumes:
            return None
        return sum(self.volumes) / len(self.volumes)
