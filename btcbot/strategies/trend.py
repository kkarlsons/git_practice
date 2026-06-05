"""Trend-following strategies: ride sustained directional moves."""

from __future__ import annotations

from typing import List

from .base import Reason, Strategy, clamp


class MACrossover(Strategy):
    name = "ma_crossover"
    description = "Fast vs slow SMA crossover (golden/death cross)"

    @property
    def warmup(self) -> int:
        return self.cfg.slow_ema

    def votes(self, i: int) -> List[Reason]:
        fast = self.f.sma(self.cfg.fast_ema)[i]
        slow = self.f.sma(self.cfg.slow_ema)[i]
        if fast is None or slow is None:
            return []
        gap = (fast - slow) / slow
        vote = clamp(gap / 0.03)
        side = "above" if gap >= 0 else "below"
        return [Reason(
            "SMA cross", vote, 1.0,
            f"Fast SMA is {abs(gap):.1%} {side} slow SMA "
            f"({'bullish' if gap >= 0 else 'bearish'})",
        )]


class EMACross(Strategy):
    name = "ema_cross"
    description = "Fast vs slow EMA crossover (lower lag than SMA)"

    @property
    def warmup(self) -> int:
        return self.cfg.slow_ema

    def votes(self, i: int) -> List[Reason]:
        fast = self.f.ema(self.cfg.fast_ema)[i]
        slow = self.f.ema(self.cfg.slow_ema)[i]
        if fast is None or slow is None:
            return []
        gap = (fast - slow) / slow
        return [Reason(
            "EMA cross", clamp(gap / 0.03), 1.0,
            f"Fast EMA is {abs(gap):.1%} {'above' if gap >= 0 else 'below'} slow EMA",
        )]


class ADXTrend(Strategy):
    name = "adx_trend"
    description = "Directional movement: trade direction only when ADX confirms a trend"

    @property
    def warmup(self) -> int:
        return self.cfg.adx_period * 3

    def votes(self, i: int) -> List[Reason]:
        adx_v, pdi, mdi = self.f.adx(self.cfg.adx_period)
        a, p, m = adx_v[i], pdi[i], mdi[i]
        if a is None or p is None or m is None:
            return []
        if a < self.cfg.adx_trend_min:
            return [Reason("ADX", 0.0, 1.0, f"ADX {a:.0f} < {self.cfg.adx_trend_min:.0f}: no clear trend")]
        direction = 1.0 if p > m else -1.0
        strength = clamp((a - self.cfg.adx_trend_min) / 30.0)
        vote = direction * (0.4 + 0.6 * strength)
        return [Reason(
            "ADX", clamp(vote), 1.0,
            f"ADX {a:.0f} confirms a {'bullish' if direction > 0 else 'bearish'} trend "
            f"(+DI {p:.0f} / -DI {m:.0f})",
        )]


class PSARTrend(Strategy):
    name = "psar"
    description = "Parabolic SAR trend/stop following"

    @property
    def warmup(self) -> int:
        return 5

    def votes(self, i: int) -> List[Reason]:
        sar = self.f.psar()[i]
        price = self.candles.closes[i]
        if sar is None:
            return []
        bullish = price > sar
        gap = abs(price - sar) / price
        vote = clamp(gap / 0.04) * (1.0 if bullish else -1.0)
        return [Reason(
            "PSAR", vote, 1.0,
            f"Price is {'above' if bullish else 'below'} SAR "
            f"({'uptrend' if bullish else 'downtrend'})",
        )]


class TrendFilter(Strategy):
    name = "trend_filter"
    description = "Price position relative to a long moving average"

    @property
    def warmup(self) -> int:
        return self.cfg.trend_sma

    def votes(self, i: int) -> List[Reason]:
        sma_v = self.f.sma(self.cfg.trend_sma)[i]
        price = self.candles.closes[i]
        if sma_v is None:
            return []
        gap = (price - sma_v) / sma_v
        side = "above" if gap >= 0 else "below"
        return [Reason(
            f"Trend SMA{self.cfg.trend_sma}", clamp(gap / 0.05), 1.0,
            f"Price is {abs(gap):.1%} {side} the {self.cfg.trend_sma}-period SMA",
        )]
