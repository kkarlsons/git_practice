"""Tests for the strategy and backtest layers using synthetic data."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from btcbot import data as datamod
from btcbot.backtest import run_backtest
from btcbot.strategy import BUY, HOLD, SELL, Strategy


def test_synthetic_is_deterministic():
    a = datamod.synthetic(days=100, seed=7)
    b = datamod.synthetic(days=100, seed=7)
    assert a.closes == b.closes
    c = datamod.synthetic(days=100, seed=8)
    assert a.closes != c.closes


def test_signal_action_valid():
    candles = datamod.synthetic(days=200)
    strat = Strategy(candles)
    sig = strat.latest()
    assert sig.action in (BUY, SELL, HOLD)
    assert -1.0 <= sig.score <= 1.0
    assert 0.0 <= sig.confidence <= 1.0
    assert sig.reasons  # there should be reasoning attached


def test_strong_uptrend_is_not_sell():
    # A monotonically rising market should never produce a SELL on the last bar.
    candles = datamod.Candles(symbol="UP")
    price = 100.0
    for i in range(120):
        price *= 1.01
        candles.times.append(i * 86400)
        candles.opens.append(price)
        candles.highs.append(price * 1.005)
        candles.lows.append(price * 0.995)
        candles.closes.append(price)
        candles.volumes.append(1.0)
    sig = Strategy(candles).latest()
    assert sig.action != SELL


def test_backtest_runs_and_reports():
    candles = datamod.synthetic(days=300)
    result = run_backtest(candles)
    assert result.n_bars > 0
    assert result.equity_curve
    assert result.start_equity == 10_000.0
    # Drawdown is non-positive by definition.
    assert result.max_drawdown <= 0.0
    # Buy-and-hold benchmark is computed.
    assert result.buy_hold_equity > 0


def test_csv_roundtrip(tmp_path=None):
    import tempfile

    candles = datamod.synthetic(days=30)
    d = tempfile.mkdtemp()
    path = os.path.join(d, "ohlcv.csv")
    with open(path, "w") as fh:
        fh.write("time,open,high,low,close,volume\n")
        for i in range(len(candles)):
            fh.write(f"{candles.times[i]},{candles.opens[i]},{candles.highs[i]},"
                     f"{candles.lows[i]},{candles.closes[i]},{candles.volumes[i]}\n")
    loaded = datamod.load_csv(path)
    assert loaded.closes == candles.closes
    assert len(loaded) == len(candles)


def _run_all():
    fns = [(n, g) for n, g in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"ok  {name}")
    print(f"\n{len(fns)} strategy tests passed.")


if __name__ == "__main__":
    _run_all()
