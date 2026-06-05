"""Fee-aware long/flat backtester and multi-strategy comparison.

Rules: start in cash; go fully long on BUY, return to cash on SELL, hold
otherwise. A fee is charged on every fill. The goal is an honest, fee-aware read
on whether a strategy's signals would have beaten simply buying and holding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Union

from .data import Candles
from .features import Features
from .strategies import DEFAULT_STRATEGY, BUY, SELL, Signal, Strategy, StrategyConfig, build

StrategyArg = Union[str, Strategy]


@dataclass
class Trade:
    side: str  # BUY or SELL
    time: int
    price: float
    equity: float


@dataclass
class BacktestResult:
    strategy: str
    start_equity: float
    end_equity: float
    buy_hold_equity: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    n_bars: int = 0

    @property
    def total_return(self) -> float:
        return self.end_equity / self.start_equity - 1.0

    @property
    def buy_hold_return(self) -> float:
        return self.buy_hold_equity / self.start_equity - 1.0

    @property
    def edge(self) -> float:
        return self.total_return - self.buy_hold_return

    @property
    def max_drawdown(self) -> float:
        peak = float("-inf")
        worst = 0.0
        for e in self.equity_curve:
            peak = max(peak, e)
            if peak > 0:
                worst = min(worst, e / peak - 1.0)
        return worst

    @property
    def n_trades(self) -> int:
        return len(self.trades)

    def summary(self) -> str:
        return (
            f"Strategy        : {self.strategy}\n"
            f"Strategy return : {self.total_return:+.1%}\n"
            f"Buy & hold      : {self.buy_hold_return:+.1%}\n"
            f"Edge vs hold    : {self.edge:+.1%}\n"
            f"Max drawdown    : {self.max_drawdown:.1%}\n"
            f"Trades          : {self.n_trades}\n"
            f"Bars evaluated  : {self.n_bars}"
        )


def _resolve(strategy: StrategyArg, features: Features, config: Optional[StrategyConfig]) -> Strategy:
    if isinstance(strategy, Strategy):
        return strategy
    return build(strategy, features, config)


def run_backtest(
    candles: Candles,
    strategy: StrategyArg = DEFAULT_STRATEGY,
    config: Optional[StrategyConfig] = None,
    start_equity: float = 10_000.0,
    fee_rate: float = 0.001,
    features: Optional[Features] = None,
) -> BacktestResult:
    features = features or Features(candles)
    strat = _resolve(strategy, features, config)

    cash = start_equity
    units = 0.0
    in_position = False
    trades: List[Trade] = []
    equity_curve: List[float] = []

    start = strat.warmup
    for i in range(start, len(candles)):
        price = candles.closes[i]
        sig: Signal = strat.evaluate(i)
        if sig.action == BUY and not in_position:
            units = (cash * (1 - fee_rate)) / price
            cash = 0.0
            in_position = True
            trades.append(Trade(BUY, candles.times[i], price, units * price))
        elif sig.action == SELL and in_position:
            cash = units * price * (1 - fee_rate)
            units = 0.0
            in_position = False
            trades.append(Trade(SELL, candles.times[i], price, cash))
        equity_curve.append(cash + units * price)

    end_price = candles.closes[-1]
    end_equity = cash + units * end_price
    first_price = candles.closes[start] if start < len(candles) else end_price
    buy_hold_equity = start_equity * (end_price / first_price) if first_price else start_equity

    return BacktestResult(
        strategy=strat.name,
        start_equity=start_equity,
        end_equity=end_equity,
        buy_hold_equity=buy_hold_equity,
        trades=trades,
        equity_curve=equity_curve,
        n_bars=len(candles) - start,
    )


def compare_strategies(
    candles: Candles,
    names: Optional[List[str]] = None,
    config: Optional[StrategyConfig] = None,
    start_equity: float = 10_000.0,
    fee_rate: float = 0.001,
) -> List[BacktestResult]:
    """Backtest several strategies on the same data; returns results sorted by return."""
    from .strategies import available

    names = names or available()
    features = Features(candles)  # shared cache across all strategies
    results = [
        run_backtest(candles, name, config, start_equity, fee_rate, features=features)
        for name in names
    ]
    results.sort(key=lambda r: r.total_return, reverse=True)
    return results
