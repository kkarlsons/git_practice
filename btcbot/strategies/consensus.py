"""Consensus meta-strategy: poll every component strategy and vote.

Each component strategy contributes one weighted vote equal to its own score for
the bar. The consensus action is the aggregate, and the reasoning lists how many
strategies leaned bullish vs bearish - a quick read on how broad the agreement
is. Broad agreement across independent methods is a stronger tell than any
single indicator.
"""

from __future__ import annotations

from typing import List, Optional, Type

from ..features import Features
from .base import Reason, Strategy, StrategyConfig
from .momentum import (
    CCIStrategy,
    MACDStrategy,
    MFIStrategy,
    ROCMomentum,
    RSIReversion,
    StochasticStrategy,
    StochRSIStrategy,
    WilliamsRStrategy,
)
from .trend import ADXTrend, EMACross, MACrossover, PSARTrend, TrendFilter
from .volatility import BollingerStrategy, DonchianBreakout, KeltnerStrategy

# The component strategies polled by the consensus. Deliberately spans
# trend, momentum, oscillator, and volatility families for diversity.
COMPONENT_CLASSES: List[Type[Strategy]] = [
    TrendFilter, MACrossover, EMACross, ADXTrend, PSARTrend,
    MACDStrategy, RSIReversion, StochasticStrategy, StochRSIStrategy,
    WilliamsRStrategy, CCIStrategy, ROCMomentum, MFIStrategy,
    BollingerStrategy, KeltnerStrategy, DonchianBreakout,
]


class ConsensusStrategy(Strategy):
    name = "consensus"
    description = "Majority vote across all component strategies"

    def __init__(self, features: Features, config: Optional[StrategyConfig] = None):
        super().__init__(features, config)
        self.components = [cls(features, self.cfg) for cls in COMPONENT_CLASSES]

    @property
    def warmup(self) -> int:
        return max(c.warmup for c in self.components)

    def votes(self, i: int) -> List[Reason]:
        reasons: List[Reason] = []
        bull = bear = neutral = 0
        for comp in self.components:
            if i < comp.warmup:
                continue
            sig = comp.evaluate(i)
            if sig.score > 0.05:
                bull += 1
            elif sig.score < -0.05:
                bear += 1
            else:
                neutral += 1
            reasons.append(Reason(comp.name, sig.score, 1.0, sig.summary()))
        if reasons:
            # Replace the per-strategy spam with one headline reason plus details.
            headline = Reason(
                "Consensus", _avg([r.vote for r in reasons]), 0.0,
                f"{bull} bullish / {bear} bearish / {neutral} neutral across {len(reasons)} strategies",
            )
            return [headline] + reasons
        return []


def _avg(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0
