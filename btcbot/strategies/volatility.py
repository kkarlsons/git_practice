"""Volatility / channel strategies (Bollinger, Keltner, Donchian)."""

from __future__ import annotations

from typing import List

from .base import Reason, Strategy, clamp


class BollingerStrategy(Strategy):
    name = "bollinger"
    description = "Bollinger Band mean-reversion (fade the bands)"

    @property
    def warmup(self) -> int:
        return self.cfg.bb_period

    def votes(self, i: int) -> List[Reason]:
        lo, _mid, up = self.f.bollinger(self.cfg.bb_period, self.cfg.bb_std)
        low, high = lo[i], up[i]
        price = self.candles.closes[i]
        if low is None or high is None or high <= low:
            return []
        pos = (price - low) / (high - low)  # 0 lower band .. 1 upper band
        vote = clamp((0.5 - pos) * 2)
        if pos <= 0.1:
            detail = "Price riding the lower band (stretched down)"
        elif pos >= 0.9:
            detail = "Price riding the upper band (stretched up)"
        else:
            detail = f"Price at {pos:.0%} of the Bollinger range"
        return [Reason("Bollinger", vote, 1.0, detail)]


class KeltnerStrategy(Strategy):
    name = "keltner"
    description = "Keltner channel breakout (trend continuation)"

    @property
    def warmup(self) -> int:
        return self.cfg.bb_period + 10

    def votes(self, i: int) -> List[Reason]:
        lo, mid, up = self.f.keltner(self.cfg.bb_period, 10, 2.0)
        low, center, high = lo[i], mid[i], up[i]
        price = self.candles.closes[i]
        if low is None or high is None or center is None:
            return []
        if price >= high:
            return [Reason("Keltner", 0.8, 1.0, "Price broke above the upper Keltner channel (bullish breakout)")]
        if price <= low:
            return [Reason("Keltner", -0.8, 1.0, "Price broke below the lower Keltner channel (bearish breakout)")]
        gap = (price - center) / (high - center) if high > center else 0.0
        return [Reason("Keltner", clamp(gap * 0.5), 1.0,
                       f"Price inside the Keltner channel ({'upper' if gap >= 0 else 'lower'} half)")]


class DonchianBreakout(Strategy):
    name = "donchian"
    description = "Donchian channel breakout (classic turtle-style trend entry)"

    @property
    def warmup(self) -> int:
        return 20

    def votes(self, i: int) -> List[Reason]:
        lo, mid, up = self.f.donchian(20)
        low, center, high = lo[i], mid[i], up[i]
        price = self.candles.closes[i]
        if low is None or high is None or center is None or high <= low:
            return []
        pos = (price - low) / (high - low)
        # Breakouts toward the channel edges are momentum signals.
        vote = clamp((pos - 0.5) * 2)
        if pos >= 0.98:
            detail = "Price at the 20-bar high (breakout up)"
        elif pos <= 0.02:
            detail = "Price at the 20-bar low (breakdown)"
        else:
            detail = f"Price at {pos:.0%} of the 20-bar range"
        return [Reason("Donchian", vote, 1.0, detail)]
