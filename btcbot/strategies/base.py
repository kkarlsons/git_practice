"""Strategy base class and shared signal types.

Every strategy turns indicator readings at a bar into a :class:`Signal`. A
strategy emits a set of weighted votes (:class:`Reason`), each in [-1, +1]
(bearish..bullish); the base class normalizes them into a score and maps that to
BUY / SELL / HOLD. This keeps every strategy consistent and directly comparable
in the backtester and consensus engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from ..features import Features

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
    action: str
    score: float  # -1..+1
    confidence: float  # 0..1
    price: float
    time: int
    strategy: str
    reasons: List[Reason] = field(default_factory=list)

    def summary(self) -> str:
        return f"{self.action} (score={self.score:+.2f}, confidence={self.confidence:.0%})"


@dataclass
class StrategyConfig:
    """Shared, strategy-agnostic knobs. Individual strategies read what they use."""
    buy_threshold: float = 0.25
    sell_threshold: float = -0.25
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    fast_ema: int = 12
    slow_ema: int = 26
    trend_sma: int = 50
    bb_period: int = 20
    bb_std: float = 2.0
    stoch_k: int = 14
    stoch_d: int = 3
    adx_period: int = 14
    adx_trend_min: float = 20.0


def clamp(x: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


class Strategy:
    """Base class. Subclasses implement :meth:`votes` and :attr:`warmup`."""

    name: str = "base"
    description: str = ""

    def __init__(self, features: Features, config: Optional[StrategyConfig] = None):
        self.f = features
        self.cfg = config or StrategyConfig()
        self.candles = features.candles

    @property
    def warmup(self) -> int:
        """Bars to skip before the strategy has enough data. Override as needed."""
        return 0

    def votes(self, i: int) -> List[Reason]:  # pragma: no cover - abstract
        raise NotImplementedError

    def evaluate(self, i: int) -> Signal:
        reasons = self.votes(i)
        total_w = sum(r.weight for r in reasons)
        score = sum(r.vote * r.weight for r in reasons) / total_w if total_w else 0.0
        if score >= self.cfg.buy_threshold:
            action = BUY
        elif score <= self.cfg.sell_threshold:
            action = SELL
        else:
            action = HOLD
        confidence = min(1.0, abs(score) / max(self.cfg.buy_threshold, 1e-9))
        return Signal(
            action=action,
            score=score,
            confidence=confidence,
            price=self.candles.closes[i],
            time=self.candles.times[i],
            strategy=self.name,
            reasons=reasons,
        )

    def latest(self) -> Signal:
        return self.evaluate(len(self.candles) - 1)
