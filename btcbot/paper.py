"""Paper trading - simulated trading with fake money, zero real-world risk.

Two modes:

* :meth:`PaperTrader.replay` walks through historical candles one bar at a time
  as if they were arriving live, acting on each signal. Great for the sandbox
  and for a quick "what would it have done lately" journal.
* :meth:`PaperTrader.live` polls a real exchange for fresh candles on an
  interval and trades a paper portfolio against them. Needs network access; it
  never touches real funds.

State (cash, holdings, trade journal) is kept in a :class:`Portfolio` and can be
written to a JSON file so a long-running paper session survives restarts.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from . import data as datamod
from .data import Candles
from .features import Features
from .strategies import DEFAULT_STRATEGY, BUY, SELL, StrategyConfig, build


@dataclass
class JournalEntry:
    time: int
    side: str  # BUY / SELL
    price: float
    units: float
    cash_after: float
    equity_after: float
    reason: str


@dataclass
class Portfolio:
    cash: float = 10_000.0
    units: float = 0.0
    fee_rate: float = 0.001
    journal: List[JournalEntry] = field(default_factory=list)

    @property
    def in_position(self) -> bool:
        return self.units > 0

    def equity(self, price: float) -> float:
        return self.cash + self.units * price

    def buy(self, price: float, ts: int, reason: str) -> Optional[JournalEntry]:
        if self.in_position or self.cash <= 0:
            return None
        self.units = (self.cash * (1 - self.fee_rate)) / price
        self.cash = 0.0
        entry = JournalEntry(ts, BUY, price, self.units, self.cash, self.equity(price), reason)
        self.journal.append(entry)
        return entry

    def sell(self, price: float, ts: int, reason: str) -> Optional[JournalEntry]:
        if not self.in_position:
            return None
        self.cash = self.units * price * (1 - self.fee_rate)
        self.units = 0.0
        entry = JournalEntry(ts, SELL, price, 0.0, self.cash, self.cash, reason)
        self.journal.append(entry)
        return entry

    def save(self, path: str) -> None:
        with open(path, "w") as fh:
            json.dump({
                "cash": self.cash,
                "units": self.units,
                "fee_rate": self.fee_rate,
                "journal": [asdict(e) for e in self.journal],
            }, fh, indent=2)

    @classmethod
    def load(cls, path: str) -> "Portfolio":
        with open(path) as fh:
            raw = json.load(fh)
        p = cls(cash=raw["cash"], units=raw["units"], fee_rate=raw.get("fee_rate", 0.001))
        p.journal = [JournalEntry(**e) for e in raw.get("journal", [])]
        return p


def _fmt(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


class PaperTrader:
    def __init__(
        self,
        strategy: str = DEFAULT_STRATEGY,
        config: Optional[StrategyConfig] = None,
        portfolio: Optional[Portfolio] = None,
        verbose: bool = True,
    ):
        self.strategy_name = strategy
        self.config = config
        self.portfolio = portfolio or Portfolio()
        self.verbose = verbose

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def _act(self, action: str, price: float, ts: int, reason: str) -> None:
        if action == BUY:
            entry = self.portfolio.buy(price, ts, reason)
            if entry:
                self._log(f"  {_fmt(ts)}  BUY  {price:>11,.2f}  -> {entry.units:.6f} units")
        elif action == SELL:
            entry = self.portfolio.sell(price, ts, reason)
            if entry:
                self._log(f"  {_fmt(ts)}  SELL {price:>11,.2f}  -> ${entry.cash_after:,.2f} cash")

    def replay(self, candles: Candles) -> Portfolio:
        """Process historical candles as if they arrived live."""
        features = Features(candles)
        strat = build(self.strategy_name, features, self.config)
        self._log(f"\n  Paper-trading replay: {self.strategy_name} on {candles.symbol} "
                  f"({len(candles)} bars)")
        self._log("  " + "-" * 52)
        for i in range(strat.warmup, len(candles)):
            sig = strat.evaluate(i)
            self._act(sig.action, candles.closes[i], candles.times[i], sig.summary())
        final_price = candles.last_price() or 0.0
        eq = self.portfolio.equity(final_price)
        ret = eq / 10_000.0 - 1.0 if self.portfolio.journal else eq / 10_000.0 - 1.0
        self._log("  " + "-" * 52)
        self._log(f"  Final equity: ${eq:,.2f}  ({ret:+.1%})   trades: {len(self.portfolio.journal)}")
        return self.portfolio

    def live(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
        poll_seconds: int = 3600,
        limit: int = 200,
        max_iterations: Optional[int] = None,
        state_path: Optional[str] = None,
    ) -> Portfolio:  # pragma: no cover - requires network + long-running
        """Poll a live exchange and paper-trade against fresh candles.

        Runs until interrupted (Ctrl-C) or ``max_iterations`` is reached. Acts on
        the most recent *closed* bar each cycle. Never trades real money.
        """
        self._log(f"  Live paper trading {symbol} {interval} every {poll_seconds}s "
                  f"(Ctrl-C to stop). Strategy: {self.strategy_name}")
        last_acted_time: Optional[int] = None
        iterations = 0
        try:
            while max_iterations is None or iterations < max_iterations:
                iterations += 1
                try:
                    candles = datamod.fetch_live(symbol=symbol, interval=interval, limit=limit)
                except RuntimeError as exc:
                    self._log(f"  [warn] fetch failed: {exc}")
                    time.sleep(poll_seconds)
                    continue
                features = Features(candles)
                strat = build(self.strategy_name, features, self.config)
                i = len(candles) - 1
                sig = strat.evaluate(i)
                ts = candles.times[i]
                if ts != last_acted_time:
                    self._log(f"  {_fmt(ts)}  {sig.action:<4} @ {candles.closes[i]:,.2f}  "
                              f"({sig.summary()})  equity=${self.portfolio.equity(candles.closes[i]):,.2f}")
                    self._act(sig.action, candles.closes[i], ts, sig.summary())
                    last_acted_time = ts
                    if state_path:
                        self.portfolio.save(state_path)
                if max_iterations is None or iterations < max_iterations:
                    time.sleep(poll_seconds)
        except KeyboardInterrupt:
            self._log("\n  Stopped. Final journal saved." if state_path else "\n  Stopped.")
        return self.portfolio
