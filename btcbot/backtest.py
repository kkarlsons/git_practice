"""A simple long/flat backtester to evaluate the strategy on historical data.

Rules: start in cash; go fully long on BUY, return to cash on SELL, do nothing
on HOLD. A configurable fee is charged on every fill. The point is not to be a
production execution simulator but to give an honest, fee-aware read on whether
the signals would have beaten simply buying and holding.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .data import Candles
from .strategy import BUY, SELL, Signal, Strategy, StrategyConfig


@dataclass
class Trade:
    side: str  # BUY or SELL
    time: int
    price: float
    equity: float


@dataclass
class BacktestResult:
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
        edge = self.total_return - self.buy_hold_return
        return (
            f"Strategy return : {self.total_return:+.1%}\n"
            f"Buy & hold      : {self.buy_hold_return:+.1%}\n"
            f"Edge vs hold    : {edge:+.1%}\n"
            f"Max drawdown    : {self.max_drawdown:.1%}\n"
            f"Trades          : {self.n_trades}\n"
            f"Bars evaluated  : {self.n_bars}"
        )


def run_backtest(
    candles: Candles,
    config: Optional[StrategyConfig] = None,
    start_equity: float = 10_000.0,
    fee_rate: float = 0.001,  # 0.1% per fill, typical exchange taker fee
) -> BacktestResult:
    strat = Strategy(candles, config)
    cash = start_equity
    units = 0.0  # units of BTC held
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

    # Buy & hold benchmark over the same evaluated window.
    first_price = candles.closes[start]
    buy_hold_equity = start_equity * (end_price / first_price)

    return BacktestResult(
        start_equity=start_equity,
        end_equity=end_equity,
        buy_hold_equity=buy_hold_equity,
        trades=trades,
        equity_curve=equity_curve,
        n_bars=len(candles) - start,
    )
