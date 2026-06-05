"""Strategy registry.

Import a strategy by name with :func:`build`, or list everything available with
:func:`available`. ``ensemble`` and ``consensus`` are meta-strategies; the rest
are single-method strategies.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Type

from ..features import Features
from .base import BUY, HOLD, SELL, Reason, Signal, Strategy, StrategyConfig
from .consensus import COMPONENT_CLASSES, ConsensusStrategy
from .ensemble import EnsembleStrategy

# Single-method strategies come from the consensus component list (single source
# of truth), with the two meta-strategies appended.
ALL_STRATEGIES: List[Type[Strategy]] = list(COMPONENT_CLASSES) + [EnsembleStrategy, ConsensusStrategy]
REGISTRY: Dict[str, Type[Strategy]] = {cls.name: cls for cls in ALL_STRATEGIES}

DEFAULT_STRATEGY = "consensus"


def available() -> List[str]:
    """Strategy names in a stable, human-friendly order."""
    return [cls.name for cls in ALL_STRATEGIES]


def describe() -> List[tuple]:
    return [(cls.name, cls.description) for cls in ALL_STRATEGIES]


def build(name: str, features: Features, config: Optional[StrategyConfig] = None) -> Strategy:
    if name not in REGISTRY:
        raise ValueError(f"unknown strategy '{name}'. Available: {', '.join(available())}")
    return REGISTRY[name](features, config)


__all__ = [
    "BUY", "SELL", "HOLD", "Reason", "Signal", "Strategy", "StrategyConfig",
    "EnsembleStrategy", "ConsensusStrategy",
    "ALL_STRATEGIES", "REGISTRY", "DEFAULT_STRATEGY",
    "available", "describe", "build",
]
