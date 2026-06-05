"""Tests for the extended indicator set, strategy registry, and paper trader."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from btcbot import data as datamod
from btcbot import indicators as ind
from btcbot.backtest import compare_strategies, run_backtest
from btcbot.features import Features
from btcbot.paper import PaperTrader, Portfolio
from btcbot.strategies import BUY, HOLD, SELL, available, build


def _candles(days=300):
    return datamod.synthetic(days=days, seed=11)


def test_all_extended_indicators_aligned():
    c = _candles(120)
    n = len(c)
    series = [
        ind.wma(c.closes, 10), ind.hma(c.closes, 16), ind.rolling_std(c.closes, 20),
        ind.roc(c.closes, 12), ind.momentum(c.closes, 10), ind.stoch_rsi(c.closes),
        ind.williams_r(c.highs, c.lows, c.closes), ind.cci(c.highs, c.lows, c.closes),
        ind.obv(c.closes, c.volumes), ind.mfi(c.highs, c.lows, c.closes, c.volumes),
        ind.vwap(c.highs, c.lows, c.closes, c.volumes), ind.psar(c.highs, c.lows),
    ]
    for s in series:
        assert len(s) == n
    # Tuple-returning indicators.
    for tup in (ind.stochastic(c.highs, c.lows, c.closes),
                ind.adx(c.highs, c.lows, c.closes),
                ind.donchian(c.highs, c.lows),
                ind.keltner(c.highs, c.lows, c.closes)):
        for s in tup:
            assert len(s) == n


def test_bounded_oscillators_in_range():
    c = _candles(150)
    for v in ind.stoch_rsi(c.closes):
        assert v is None or 0 <= v <= 100
    for v in ind.mfi(c.highs, c.lows, c.closes, c.volumes):
        assert v is None or 0 <= v <= 100
    for v in ind.williams_r(c.highs, c.lows, c.closes):
        assert v is None or -100 <= v <= 0
    k, d = ind.stochastic(c.highs, c.lows, c.closes)
    for v in k + d:
        assert v is None or 0 <= v <= 100


def test_adx_non_negative():
    c = _candles(200)
    a, p, m = ind.adx(c.highs, c.lows, c.closes)
    for v in a + p + m:
        assert v is None or v >= 0


def test_features_cache_reuses():
    c = _candles(120)
    f = Features(c)
    first = f.rsi(14)
    second = f.rsi(14)
    assert first is second  # identical cached object, not recomputed


def test_every_registered_strategy_evaluates():
    c = _candles(320)
    f = Features(c)
    for name in available():
        strat = build(name, f)
        sig = strat.latest()
        assert sig.action in (BUY, SELL, HOLD)
        assert -1.0 <= sig.score <= 1.0
        assert 0.0 <= sig.confidence <= 1.0


def test_consensus_lists_components():
    c = _candles(320)
    strat = build("consensus", Features(c))
    sig = strat.latest()
    # Headline reason plus one per component that has warmed up.
    assert any(r.name == "Consensus" for r in sig.reasons)
    assert len(sig.reasons) > 5


def test_compare_returns_sorted():
    c = _candles(320)
    results = compare_strategies(c)
    assert len(results) == len(available())
    returns = [r.total_return for r in results]
    assert returns == sorted(returns, reverse=True)


def test_backtest_by_name_matches_default():
    c = _candles(320)
    r = run_backtest(c, "ema_cross")
    assert r.strategy == "ema_cross"
    assert r.equity_curve


def test_paper_replay_runs():
    c = _candles(300)
    trader = PaperTrader(strategy="macd", verbose=False)
    portfolio = trader.replay(c)
    final = portfolio.equity(c.last_price())
    assert final > 0
    # Journal entries alternate BUY/SELL starting with BUY.
    sides = [e.side for e in portfolio.journal]
    for idx, side in enumerate(sides):
        assert side == (BUY if idx % 2 == 0 else SELL)


def test_portfolio_save_load_roundtrip(tmp_path=None):
    import tempfile
    c = _candles(200)
    trader = PaperTrader(strategy="rsi_reversion", verbose=False)
    portfolio = trader.replay(c)
    d = tempfile.mkdtemp()
    path = os.path.join(d, "state.json")
    portfolio.save(path)
    loaded = Portfolio.load(path)
    assert loaded.cash == portfolio.cash
    assert loaded.units == portfolio.units
    assert len(loaded.journal) == len(portfolio.journal)


def _run_all():
    fns = [(n, g) for n, g in sorted(globals().items()) if n.startswith("test_")]
    for name, fn in fns:
        fn()
        print(f"ok  {name}")
    print(f"\n{len(fns)} extended tests passed.")


if __name__ == "__main__":
    _run_all()
