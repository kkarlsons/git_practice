"""Unit tests for the pure-Python indicators. Run with: python -m pytest -q
(also runnable without pytest via `python tests/test_indicators.py`).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from btcbot import indicators as ind


def approx(a, b, tol=1e-6):
    return abs(a - b) <= tol


def test_sma_basic():
    out = ind.sma([1, 2, 3, 4, 5], 3)
    assert out[:2] == [None, None]
    assert approx(out[2], 2.0)
    assert approx(out[3], 3.0)
    assert approx(out[4], 4.0)


def test_sma_constant_series():
    out = ind.sma([7] * 10, 4)
    assert all(v is None or approx(v, 7.0) for v in out)


def test_ema_seed_and_length():
    vals = list(range(1, 21))
    out = ind.ema(vals, 5)
    assert len(out) == len(vals)
    assert out[3] is None
    # Seed is SMA of first 5 = mean(1..5) = 3.0
    assert approx(out[4], 3.0)
    # EMA should trend upward on a rising series.
    assert out[-1] > out[5]


def test_rsi_all_gains_is_100():
    vals = list(range(1, 30))  # strictly increasing -> no losses
    out = ind.rsi(vals, 14)
    assert approx(out[-1], 100.0)


def test_rsi_all_losses_is_zero():
    vals = list(range(30, 1, -1))  # strictly decreasing
    out = ind.rsi(vals, 14)
    assert approx(out[-1], 0.0)


def test_rsi_range_bounds():
    vals = [10, 11, 10.5, 12, 11.5, 13, 12, 14, 13.5, 15, 14, 16, 15, 17, 16, 18]
    out = ind.rsi(vals, 14)
    for v in out:
        assert v is None or 0.0 <= v <= 100.0


def test_macd_shapes():
    vals = [float(i) for i in range(1, 60)]
    macd_line, signal, hist = ind.macd(vals, 12, 26, 9)
    assert len(macd_line) == len(signal) == len(hist) == len(vals)
    # On a steadily rising series the MACD line is positive once defined.
    defined = [v for v in macd_line if v is not None]
    assert defined and all(v > 0 for v in defined)


def test_bollinger_bands_order():
    vals = [10 + (i % 5) for i in range(40)]
    lower, mid, upper = ind.bollinger_bands(vals, 20, 2.0)
    for lo, m, up in zip(lower, mid, upper):
        if lo is not None:
            assert lo <= m <= up


def test_atr_positive():
    highs = [10 + i * 0.5 for i in range(40)]
    lows = [9 + i * 0.5 for i in range(40)]
    closes = [9.5 + i * 0.5 for i in range(40)]
    out = ind.atr(highs, lows, closes, 14)
    defined = [v for v in out if v is not None]
    assert defined and all(v > 0 for v in defined)


def _run_all():
    fns = [g for n, g in globals().items() if n.startswith("test_")]
    for fn in fns:
        fn()
        print(f"ok  {fn.__name__}")
    print(f"\n{len(fns)} indicator tests passed.")


if __name__ == "__main__":
    _run_all()
