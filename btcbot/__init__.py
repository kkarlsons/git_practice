"""btcbot - a technical-analysis Bitcoin signal bot.

Public surface:
    from btcbot import data, indicators
    from btcbot.strategy import Strategy, StrategyConfig
    from btcbot.backtest import run_backtest
"""

__version__ = "0.1.0"

from . import data, indicators  # noqa: F401
from .backtest import run_backtest  # noqa: F401
from .strategy import Strategy, StrategyConfig  # noqa: F401
