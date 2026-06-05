"""Backward-compatible shim.

The strategy system now lives in the ``btcbot.strategies`` package. This module
re-exports the common names and provides a ``Strategy`` class that accepts
``Candles`` directly (constructing the indicator cache for you), so older code
and the original ensemble entry point keep working.
"""

from __future__ import annotations

from typing import Optional

from .data import Candles
from .features import Features
from .strategies import BUY, HOLD, SELL, Reason, Signal, StrategyConfig
from .strategies.ensemble import EnsembleStrategy

__all__ = ["BUY", "SELL", "HOLD", "Reason", "Signal", "StrategyConfig", "Strategy"]


class Strategy(EnsembleStrategy):
    """The default (ensemble) strategy, constructible directly from candles."""

    def __init__(self, candles: Candles, config: Optional[StrategyConfig] = None):
        super().__init__(Features(candles), config)
