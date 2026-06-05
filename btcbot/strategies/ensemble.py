"""Ensemble strategy: a hand-weighted blend of complementary indicators.

Mixes trend-following (so it stays with strong moves), momentum (for timing),
and mean-reversion (for stretched extremes). The weights favor trend/momentum
slightly, since mean-reversion signals fire often but can fight a strong trend.
"""

from __future__ import annotations

from typing import List

from .base import Reason, Strategy, clamp


class EnsembleStrategy(Strategy):
    name = "ensemble"
    description = "Weighted blend of trend, momentum, and mean-reversion indicators"

    @property
    def warmup(self) -> int:
        c = self.cfg
        return max(c.slow_ema + 9, c.trend_sma, c.bb_period, c.rsi_period, c.adx_period * 3)

    def votes(self, i: int) -> List[Reason]:
        c = self.cfg
        price = self.candles.closes[i]
        reasons: List[Reason] = []

        sma_v = self.f.sma(c.trend_sma)[i]
        if sma_v is not None:
            gap = (price - sma_v) / sma_v
            reasons.append(Reason(f"Trend SMA{c.trend_sma}", clamp(gap / 0.05), 1.0,
                                  f"Price {abs(gap):.1%} {'above' if gap >= 0 else 'below'} the long SMA"))

        fe, se = self.f.ema(c.fast_ema)[i], self.f.ema(c.slow_ema)[i]
        if fe is not None and se is not None:
            gap = (fe - se) / se
            reasons.append(Reason("EMA cross", clamp(gap / 0.03), 1.0,
                                  f"Fast EMA {abs(gap):.1%} {'above' if gap >= 0 else 'below'} slow EMA"))

        _, _, hist = self.f.macd(c.fast_ema, c.slow_ema)
        if hist[i] is not None:
            reasons.append(Reason("MACD", clamp((hist[i] / price) / 0.01), 1.0,
                                  f"MACD momentum {'positive' if hist[i] >= 0 else 'negative'}"))

        adx_v, pdi, mdi = self.f.adx(c.adx_period)
        if adx_v[i] is not None and pdi[i] is not None and mdi[i] is not None:
            if adx_v[i] >= c.adx_trend_min:
                direction = 1.0 if pdi[i] > mdi[i] else -1.0
                strength = clamp((adx_v[i] - c.adx_trend_min) / 30.0)
                reasons.append(Reason("ADX", clamp(direction * (0.4 + 0.6 * strength)), 0.8,
                                      f"ADX {adx_v[i]:.0f} confirms {'up' if direction > 0 else 'down'} trend"))

        r = self.f.rsi(c.rsi_period)[i]
        if r is not None:
            if r <= c.rsi_oversold:
                vote, detail = clamp((c.rsi_oversold - r) / c.rsi_oversold + 0.3), f"RSI {r:.0f} oversold"
            elif r >= c.rsi_overbought:
                vote, detail = -clamp((r - c.rsi_overbought) / (100 - c.rsi_overbought) + 0.3), f"RSI {r:.0f} overbought"
            else:
                vote, detail = clamp((r - 50) / 50) * 0.3, f"RSI {r:.0f} neutral"
            reasons.append(Reason("RSI", vote, 0.8, detail))

        lo, _mid, up = self.f.bollinger(c.bb_period, c.bb_std)
        if lo[i] is not None and up[i] is not None and up[i] > lo[i]:
            pos = (price - lo[i]) / (up[i] - lo[i])
            reasons.append(Reason("Bollinger", clamp((0.5 - pos) * 2), 0.6,
                                  f"Price at {pos:.0%} of the Bollinger range"))

        return reasons
