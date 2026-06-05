"""btcbot - a technical-analysis Bitcoin signal & paper-trading bot.

Public surface:
    from btcbot import data, indicators
    from btcbot.features import Features
    from btcbot.strategies import build, available, StrategyConfig
    from btcbot.backtest import run_backtest, compare_strategies
    from btcbot.paper import PaperTrader, Portfolio
"""

__version__ = "0.2.0"

from . import data, indicators  # noqa: F401
from .backtest import compare_strategies, run_backtest  # noqa: F401
from .features import Features  # noqa: F401
from .strategies import StrategyConfig, available, build  # noqa: F401
