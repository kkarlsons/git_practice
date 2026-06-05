"""Technical-analysis indicators implemented in pure Python.

No third-party dependencies (no pandas/numpy) so the bot runs anywhere with a
stock Python 3.8+ interpreter. Every function returns a list the same length as
the input, using ``None`` for "warm-up" positions where the indicator is not yet
defined. This keeps every series index-aligned with the original price series,
which makes combining indicators in the strategy layer straightforward.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

Number = Optional[float]


def sma(values: Sequence[float], period: int) -> List[Number]:
    """Simple Moving Average over ``period`` samples."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: List[Number] = [None] * len(values)
    running = 0.0
    for i, v in enumerate(values):
        running += v
        if i >= period:
            running -= values[i - period]
        if i >= period - 1:
            out[i] = running / period
    return out


def ema(values: Sequence[float], period: int) -> List[Number]:
    """Exponential Moving Average, seeded with an SMA of the first ``period``."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: List[Number] = [None] * len(values)
    if len(values) < period:
        return out
    k = 2.0 / (period + 1)
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        prev = values[i] * k + prev * (1 - k)
        out[i] = prev
    return out


def rsi(values: Sequence[float], period: int = 14) -> List[Number]:
    """Relative Strength Index using Wilder's smoothing (0-100)."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: List[Number] = [None] * len(values)
    if len(values) <= period:
        return out

    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = values[i] - values[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    out[period] = _rsi_from(avg_gain, avg_loss)

    for i in range(period + 1, len(values)):
        change = values[i] - values[i - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        out[i] = _rsi_from(avg_gain, avg_loss)
    return out


def _rsi_from(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    values: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[List[Number], List[Number], List[Number]]:
    """Return (macd_line, signal_line, histogram)."""
    if fast >= slow:
        raise ValueError("fast period must be smaller than slow period")
    fast_ema = ema(values, fast)
    slow_ema = ema(values, slow)
    macd_line: List[Number] = [
        (f - s) if (f is not None and s is not None) else None
        for f, s in zip(fast_ema, slow_ema)
    ]

    # The signal line is an EMA of the MACD line, computed only over the region
    # where the MACD line is defined, then re-aligned to full length.
    start = next((i for i, v in enumerate(macd_line) if v is not None), None)
    signal_line: List[Number] = [None] * len(values)
    if start is not None:
        defined = [v for v in macd_line[start:] if v is not None]
        sig = ema(defined, signal)
        for offset, v in enumerate(sig):
            signal_line[start + offset] = v

    hist: List[Number] = [
        (m - s) if (m is not None and s is not None) else None
        for m, s in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, hist


def bollinger_bands(
    values: Sequence[float],
    period: int = 20,
    num_std: float = 2.0,
) -> tuple[List[Number], List[Number], List[Number]]:
    """Return (lower_band, middle_band, upper_band) using population std-dev."""
    middle = sma(values, period)
    lower: List[Number] = [None] * len(values)
    upper: List[Number] = [None] * len(values)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = middle[i]
        variance = sum((x - mean) ** 2 for x in window) / period
        std = variance ** 0.5
        lower[i] = mean - num_std * std
        upper[i] = mean + num_std * std
    return lower, middle, upper


def true_range(highs: Sequence[float], lows: Sequence[float], closes: Sequence[float]) -> List[Number]:
    """True Range per period (None for the first bar)."""
    out: List[Number] = [None] * len(closes)
    for i in range(1, len(closes)):
        prev_close = closes[i - 1]
        out[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - prev_close),
            abs(lows[i] - prev_close),
        )
    return out


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> List[Number]:
    """Average True Range using Wilder's smoothing."""
    tr = true_range(highs, lows, closes)
    out: List[Number] = [None] * len(closes)
    # The first true-range value is at index 1; seed ATR with a simple average.
    if len(closes) <= period:
        return out
    seed = sum(tr[1 : period + 1]) / period  # type: ignore[arg-type]
    out[period] = seed
    prev = seed
    for i in range(period + 1, len(closes)):
        prev = (prev * (period - 1) + tr[i]) / period  # type: ignore[operator]
        out[i] = prev
    return out
