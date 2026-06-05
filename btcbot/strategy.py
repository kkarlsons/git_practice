"""Signal generation: turn indicators into buy/sell/hold trading tips.

The strategy is a transparent, weighted ensemble of classic technical signals.
Each component votes in [-1, +1] (bearish..bullish); votes are weighted and
summed into a score, which is mapped to BUY / SELL / HOLD with a confidence and
a plain-English explanation of *why*. Nothing here is a guarantee of profit -
it is a disciplined, rules-based reading of the chart that you can backtest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from . import indicators
from .data import Candles

BUY = "BUY"
SELL = "SELL"
HOLD = "HOLD"


@dataclass
class Reason:
    name: str
    vote: float  # -1..+1
    weight: float
    detail: str


@dataclass
class Signal:
    action: str  # BUY / SELL / HOLD
    score: float  # weighted score, -1..+1
    confidence: float  # 0..1
    price: float
    time: int
    reasons: List[Reason]

    def summary(self) -> str:
        return f"{self.action} (score={self.score:+.2f}, confidence={self.confidence:.0%})"


@dataclass
class StrategyConfig:
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    fast_ema: int = 12
    slow_ema: int = 26
    trend_sma: int = 50
    bb_period: int = 20
    bb_std: float = 2.0
    buy_threshold: float = 0.25
    sell_threshold: float = -0.25
    # Component weights (need not sum to 1; score is normalized by total weight).
    w_trend: float = 1.0
    w_macd: float = 1.0
    w_rsi: float = 1.0
    w_bollinger: float = 0.8
    w_ema_cross: float = 1.0


class Strategy:
    """Computes indicator series once, then emits a Signal for any bar index."""

    def __init__(self, candles: Candles, config: Optional[StrategyConfig] = None):
        self.candles = candles
        self.cfg = config or StrategyConfig()
        closes = candles.closes

        self.rsi = indicators.rsi(closes, self.cfg.rsi_period)
        self.fast_ema = indicators.ema(closes, self.cfg.fast_ema)
        self.slow_ema = indicators.ema(closes, self.cfg.slow_ema)
        self.trend_sma = indicators.sma(closes, self.cfg.trend_sma)
        self.macd_line, self.macd_signal, self.macd_hist = indicators.macd(
            closes, self.cfg.fast_ema, self.cfg.slow_ema
        )
        self.bb_lower, self.bb_mid, self.bb_upper = indicators.bollinger_bands(
            closes, self.cfg.bb_period, self.cfg.bb_std
        )

    @property
    def warmup(self) -> int:
        """Number of leading bars without enough data for a full signal."""
        return max(self.cfg.slow_ema, self.cfg.trend_sma, self.cfg.bb_period, self.cfg.rsi_period)

    def evaluate(self, i: int) -> Signal:
        """Produce a trading signal for bar ``i``."""
        cfg = self.cfg
        price = self.candles.closes[i]
        reasons: List[Reason] = []

        # 1) Trend filter: price vs long SMA.
        sma_v = self.trend_sma[i]
        if sma_v is not None:
            gap = (price - sma_v) / sma_v
            vote = _clamp(gap / 0.05)  # +/-5% from the mean -> full vote
            side = "above" if gap >= 0 else "below"
            reasons.append(Reason(
                "Trend (SMA%d)" % cfg.trend_sma, vote, cfg.w_trend,
                f"Price {price:,.0f} is {abs(gap):.1%} {side} the {cfg.trend_sma}-period SMA",
            ))

        # 2) EMA cross: fast vs slow.
        fe, se = self.fast_ema[i], self.slow_ema[i]
        if fe is not None and se is not None:
            gap = (fe - se) / se
            vote = _clamp(gap / 0.03)
            cross = "bullish" if gap >= 0 else "bearish"
            reasons.append(Reason(
                "EMA cross (%d/%d)" % (cfg.fast_ema, cfg.slow_ema), vote, cfg.w_ema_cross,
                f"Fast EMA is {abs(gap):.1%} {'above' if gap >= 0 else 'below'} slow EMA ({cross})",
            ))

        # 3) MACD histogram momentum.
        hist = self.macd_hist[i]
        if hist is not None:
            # Normalize histogram by price so it is comparable across regimes.
            vote = _clamp((hist / price) / 0.01)
            reasons.append(Reason(
                "MACD", vote, cfg.w_macd,
                f"MACD histogram is {'positive' if hist >= 0 else 'negative'} "
                f"({'rising' if hist >= 0 else 'falling'} momentum)",
            ))

        # 4) RSI mean-reversion: oversold is bullish, overbought is bearish.
        r = self.rsi[i]
        if r is not None:
            if r <= cfg.rsi_oversold:
                vote = _clamp((cfg.rsi_oversold - r) / cfg.rsi_oversold + 0.3)
                detail = f"RSI {r:.0f} is oversold (<= {cfg.rsi_oversold:.0f}) - potential bounce"
            elif r >= cfg.rsi_overbought:
                vote = -_clamp((r - cfg.rsi_overbought) / (100 - cfg.rsi_overbought) + 0.3)
                detail = f"RSI {r:.0f} is overbought (>= {cfg.rsi_overbought:.0f}) - potential pullback"
            else:
                # Mild lean toward the midpoint (50).
                vote = _clamp((r - 50) / 50) * 0.3
                detail = f"RSI {r:.0f} is neutral"
            reasons.append(Reason("RSI", vote, cfg.w_rsi, detail))

        # 5) Bollinger Bands mean-reversion.
        lo, up = self.bb_lower[i], self.bb_upper[i]
        if lo is not None and up is not None and up > lo:
            pos = (price - lo) / (up - lo)  # 0 at lower band, 1 at upper band
            vote = _clamp((0.5 - pos) * 2)  # near lower band -> bullish
            if pos <= 0.1:
                detail = "Price is riding the lower Bollinger band (stretched down)"
            elif pos >= 0.9:
                detail = "Price is riding the upper Bollinger band (stretched up)"
            else:
                detail = f"Price sits at {pos:.0%} of the Bollinger range"
            reasons.append(Reason("Bollinger", vote, cfg.w_bollinger, detail))

        # Weighted, normalized score.
        total_w = sum(r.weight for r in reasons)
        score = sum(r.vote * r.weight for r in reasons) / total_w if total_w else 0.0

        if score >= cfg.buy_threshold:
            action = BUY
        elif score <= cfg.sell_threshold:
            action = SELL
        else:
            action = HOLD

        confidence = min(1.0, abs(score) / max(cfg.buy_threshold, 1e-9))
        return Signal(
            action=action,
            score=score,
            confidence=confidence,
            price=price,
            time=self.candles.times[i],
            reasons=reasons,
        )

    def latest(self) -> Signal:
        """Signal for the most recent bar."""
        return self.evaluate(len(self.candles) - 1)


def _clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))
