"""Lazy, cached indicator computation shared across strategies.

Computing the full indicator suite for every strategy on every bar would be
wasteful, especially when the consensus meta-strategy runs many strategies over
the same candles. ``Features`` computes each indicator series at most once and
memoizes it, so all strategies read from the same cache.
"""

from __future__ import annotations

from typing import Callable, List, Tuple

from . import indicators as ind
from .data import Candles
from .indicators import Number


class Features:
    def __init__(self, candles: Candles):
        self.candles = candles
        self.closes = candles.closes
        self.highs = candles.highs
        self.lows = candles.lows
        self.volumes = candles.volumes
        self._cache: dict = {}

    def _get(self, key, fn: Callable):
        if key not in self._cache:
            self._cache[key] = fn()
        return self._cache[key]

    # --- single-series indicators ---
    def sma(self, period: int) -> List[Number]:
        return self._get(("sma", period), lambda: ind.sma(self.closes, period))

    def ema(self, period: int) -> List[Number]:
        return self._get(("ema", period), lambda: ind.ema(self.closes, period))

    def wma(self, period: int) -> List[Number]:
        return self._get(("wma", period), lambda: ind.wma(self.closes, period))

    def hma(self, period: int) -> List[Number]:
        return self._get(("hma", period), lambda: ind.hma(self.closes, period))

    def rsi(self, period: int = 14) -> List[Number]:
        return self._get(("rsi", period), lambda: ind.rsi(self.closes, period))

    def stoch_rsi(self, rsi_p: int = 14, stoch_p: int = 14) -> List[Number]:
        return self._get(("stoch_rsi", rsi_p, stoch_p),
                         lambda: ind.stoch_rsi(self.closes, rsi_p, stoch_p))

    def roc(self, period: int = 12) -> List[Number]:
        return self._get(("roc", period), lambda: ind.roc(self.closes, period))

    def momentum(self, period: int = 10) -> List[Number]:
        return self._get(("mom", period), lambda: ind.momentum(self.closes, period))

    def rolling_std(self, period: int) -> List[Number]:
        return self._get(("std", period), lambda: ind.rolling_std(self.closes, period))

    def obv(self) -> List[Number]:
        return self._get(("obv",), lambda: ind.obv(self.closes, self.volumes))

    # --- multi-series indicators ---
    def macd(self, fast=12, slow=26, signal=9) -> Tuple[List[Number], List[Number], List[Number]]:
        return self._get(("macd", fast, slow, signal),
                         lambda: ind.macd(self.closes, fast, slow, signal))

    def bollinger(self, period=20, num_std=2.0) -> Tuple[List[Number], List[Number], List[Number]]:
        return self._get(("bb", period, num_std),
                         lambda: ind.bollinger_bands(self.closes, period, num_std))

    def atr(self, period: int = 14) -> List[Number]:
        return self._get(("atr", period),
                         lambda: ind.atr(self.highs, self.lows, self.closes, period))

    def stochastic(self, k=14, d=3) -> Tuple[List[Number], List[Number]]:
        return self._get(("stoch", k, d),
                         lambda: ind.stochastic(self.highs, self.lows, self.closes, k, d))

    def williams_r(self, period: int = 14) -> List[Number]:
        return self._get(("wr", period),
                         lambda: ind.williams_r(self.highs, self.lows, self.closes, period))

    def cci(self, period: int = 20) -> List[Number]:
        return self._get(("cci", period),
                         lambda: ind.cci(self.highs, self.lows, self.closes, period))

    def mfi(self, period: int = 14) -> List[Number]:
        return self._get(("mfi", period),
                         lambda: ind.mfi(self.highs, self.lows, self.closes, self.volumes, period))

    def adx(self, period: int = 14) -> Tuple[List[Number], List[Number], List[Number]]:
        return self._get(("adx", period),
                         lambda: ind.adx(self.highs, self.lows, self.closes, period))

    def donchian(self, period: int = 20) -> Tuple[List[Number], List[Number], List[Number]]:
        return self._get(("donch", period),
                         lambda: ind.donchian(self.highs, self.lows, period))

    def keltner(self, period=20, atr_period=10, mult=2.0):
        return self._get(("kelt", period, atr_period, mult),
                         lambda: ind.keltner(self.highs, self.lows, self.closes, period, atr_period, mult))

    def psar(self, step=0.02, max_step=0.2) -> List[Number]:
        return self._get(("psar", step, max_step),
                         lambda: ind.psar(self.highs, self.lows, step, max_step))

    def vwap(self) -> List[Number]:
        return self._get(("vwap",), lambda: ind.vwap(self.highs, self.lows, self.closes, self.volumes))
