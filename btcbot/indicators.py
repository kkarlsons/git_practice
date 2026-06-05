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


# --------------------------------------------------------------------------- #
# Extended indicator set
# --------------------------------------------------------------------------- #

def wma(values: Sequence[float], period: int) -> List[Number]:
    """Weighted Moving Average (linear weights 1..period, newest heaviest)."""
    if period <= 0:
        raise ValueError("period must be positive")
    out: List[Number] = [None] * len(values)
    denom = period * (period + 1) / 2
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        out[i] = sum(w * v for w, v in enumerate(window, start=1)) / denom
    return out


def hma(values: Sequence[float], period: int) -> List[Number]:
    """Hull Moving Average - fast, low-lag trend line."""
    if period <= 1:
        raise ValueError("period must be > 1")
    half = max(1, period // 2)
    sqrt_p = max(1, int(period ** 0.5))
    wma_half = wma(values, half)
    wma_full = wma(values, period)
    raw: List[float] = []
    idx: List[int] = []
    for i in range(len(values)):
        if wma_half[i] is not None and wma_full[i] is not None:
            raw.append(2 * wma_half[i] - wma_full[i])
            idx.append(i)
    smoothed = wma(raw, sqrt_p)
    out: List[Number] = [None] * len(values)
    for offset, i in enumerate(idx):
        out[i] = smoothed[offset]
    return out


def rolling_std(values: Sequence[float], period: int) -> List[Number]:
    """Rolling population standard deviation."""
    out: List[Number] = [None] * len(values)
    means = sma(values, period)
    for i in range(period - 1, len(values)):
        window = values[i - period + 1 : i + 1]
        mean = means[i]
        var = sum((x - mean) ** 2 for x in window) / period
        out[i] = var ** 0.5
    return out


def roc(values: Sequence[float], period: int = 12) -> List[Number]:
    """Rate of Change as a percentage vs the value ``period`` bars ago."""
    out: List[Number] = [None] * len(values)
    for i in range(period, len(values)):
        prev = values[i - period]
        if prev != 0:
            out[i] = (values[i] - prev) / prev * 100.0
    return out


def momentum(values: Sequence[float], period: int = 10) -> List[Number]:
    """Absolute price momentum: value now minus value ``period`` bars ago."""
    out: List[Number] = [None] * len(values)
    for i in range(period, len(values)):
        out[i] = values[i] - values[i - period]
    return out


def stochastic(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    k_period: int = 14,
    d_period: int = 3,
) -> tuple[List[Number], List[Number]]:
    """Stochastic oscillator. Returns (%K, %D), both 0-100."""
    k: List[Number] = [None] * len(closes)
    for i in range(k_period - 1, len(closes)):
        hh = max(highs[i - k_period + 1 : i + 1])
        ll = min(lows[i - k_period + 1 : i + 1])
        rng = hh - ll
        k[i] = 100.0 * (closes[i] - ll) / rng if rng else 50.0
    # %D is an SMA of %K over the defined region.
    defined = [v for v in k if v is not None]
    start = next((i for i, v in enumerate(k) if v is not None), None)
    d: List[Number] = [None] * len(closes)
    if start is not None:
        d_smoothed = sma(defined, d_period)
        for offset, v in enumerate(d_smoothed):
            d[start + offset] = v
    return k, d


def stoch_rsi(values: Sequence[float], rsi_period: int = 14, stoch_period: int = 14) -> List[Number]:
    """Stochastic RSI (0-100): a stochastic applied to the RSI series."""
    r = rsi(values, rsi_period)
    out: List[Number] = [None] * len(values)
    defined_idx = [i for i, v in enumerate(r) if v is not None]
    for pos in range(stoch_period - 1, len(defined_idx)):
        window_idx = defined_idx[pos - stoch_period + 1 : pos + 1]
        window = [r[j] for j in window_idx]
        hh, ll = max(window), min(window)
        i = defined_idx[pos]
        out[i] = 100.0 * (r[i] - ll) / (hh - ll) if hh != ll else 50.0
    return out


def williams_r(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> List[Number]:
    """Williams %R (-100..0). Near -100 = oversold, near 0 = overbought."""
    out: List[Number] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        rng = hh - ll
        out[i] = -100.0 * (hh - closes[i]) / rng if rng else -50.0
    return out


def cci(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
) -> List[Number]:
    """Commodity Channel Index. Typically +/-100 marks the trading band."""
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    tp_sma = sma(tp, period)
    out: List[Number] = [None] * len(closes)
    for i in range(period - 1, len(closes)):
        window = tp[i - period + 1 : i + 1]
        mean = tp_sma[i]
        mad = sum(abs(x - mean) for x in window) / period
        out[i] = (tp[i] - mean) / (0.015 * mad) if mad else 0.0
    return out


def obv(closes: Sequence[float], volumes: Sequence[float]) -> List[Number]:
    """On-Balance Volume: cumulative volume signed by price direction."""
    out: List[Number] = [0.0] * len(closes)
    for i in range(1, len(closes)):
        if closes[i] > closes[i - 1]:
            out[i] = out[i - 1] + volumes[i]
        elif closes[i] < closes[i - 1]:
            out[i] = out[i - 1] - volumes[i]
        else:
            out[i] = out[i - 1]
    return out


def mfi(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
    period: int = 14,
) -> List[Number]:
    """Money Flow Index (0-100): a volume-weighted RSI."""
    tp = [(highs[i] + lows[i] + closes[i]) / 3 for i in range(len(closes))]
    raw_flow = [tp[i] * volumes[i] for i in range(len(closes))]
    out: List[Number] = [None] * len(closes)
    for i in range(period, len(closes)):
        pos = neg = 0.0
        for j in range(i - period + 1, i + 1):
            if tp[j] > tp[j - 1]:
                pos += raw_flow[j]
            elif tp[j] < tp[j - 1]:
                neg += raw_flow[j]
        if neg == 0:
            out[i] = 100.0
        else:
            ratio = pos / neg
            out[i] = 100.0 - (100.0 / (1.0 + ratio))
    return out


def vwap(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    volumes: Sequence[float],
) -> List[Number]:
    """Cumulative Volume-Weighted Average Price."""
    out: List[Number] = [None] * len(closes)
    cum_pv = 0.0
    cum_v = 0.0
    for i in range(len(closes)):
        tp = (highs[i] + lows[i] + closes[i]) / 3
        cum_pv += tp * volumes[i]
        cum_v += volumes[i]
        out[i] = cum_pv / cum_v if cum_v else tp
    return out


def donchian(
    highs: Sequence[float],
    lows: Sequence[float],
    period: int = 20,
) -> tuple[List[Number], List[Number], List[Number]]:
    """Donchian channel: (lower, middle, upper) over ``period`` bars."""
    lower: List[Number] = [None] * len(highs)
    upper: List[Number] = [None] * len(highs)
    middle: List[Number] = [None] * len(highs)
    for i in range(period - 1, len(highs)):
        hh = max(highs[i - period + 1 : i + 1])
        ll = min(lows[i - period + 1 : i + 1])
        upper[i] = hh
        lower[i] = ll
        middle[i] = (hh + ll) / 2
    return lower, middle, upper


def keltner(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 20,
    atr_period: int = 10,
    mult: float = 2.0,
) -> tuple[List[Number], List[Number], List[Number]]:
    """Keltner channel: EMA center +/- mult * ATR. Returns (lower, mid, upper)."""
    mid = ema(closes, period)
    atr_v = atr(highs, lows, closes, atr_period)
    lower: List[Number] = [None] * len(closes)
    upper: List[Number] = [None] * len(closes)
    for i in range(len(closes)):
        if mid[i] is not None and atr_v[i] is not None:
            lower[i] = mid[i] - mult * atr_v[i]
            upper[i] = mid[i] + mult * atr_v[i]
    return lower, mid, upper


def adx(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> tuple[List[Number], List[Number], List[Number]]:
    """Average Directional Index. Returns (adx, plus_di, minus_di).

    ADX measures trend *strength* (not direction); +DI/-DI give direction.
    Values above ~25 typically indicate a meaningful trend.
    """
    n = len(closes)
    plus_dm = [0.0] * n
    minus_dm = [0.0] * n
    tr = [0.0] * n
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )

    plus_di: List[Number] = [None] * n
    minus_di: List[Number] = [None] * n
    adx_out: List[Number] = [None] * n
    if n <= 2 * period:
        return adx_out, plus_di, minus_di

    # Wilder-smoothed sums seeded at index `period`.
    sm_tr = sum(tr[1 : period + 1])
    sm_plus = sum(plus_dm[1 : period + 1])
    sm_minus = sum(minus_dm[1 : period + 1])
    dx_series: List[float] = []
    dx_index: List[int] = []
    for i in range(period, n):
        if i > period:
            sm_tr = sm_tr - sm_tr / period + tr[i]
            sm_plus = sm_plus - sm_plus / period + plus_dm[i]
            sm_minus = sm_minus - sm_minus / period + minus_dm[i]
        pdi = 100.0 * sm_plus / sm_tr if sm_tr else 0.0
        mdi = 100.0 * sm_minus / sm_tr if sm_tr else 0.0
        plus_di[i] = pdi
        minus_di[i] = mdi
        denom = pdi + mdi
        dx = 100.0 * abs(pdi - mdi) / denom if denom else 0.0
        dx_series.append(dx)
        dx_index.append(i)

    # ADX = Wilder-smoothed average of DX.
    if len(dx_series) >= period:
        first = sum(dx_series[:period]) / period
        adx_out[dx_index[period - 1]] = first
        prev = first
        for k in range(period, len(dx_series)):
            prev = (prev * (period - 1) + dx_series[k]) / period
            adx_out[dx_index[k]] = prev
    return adx_out, plus_di, minus_di


def psar(
    highs: Sequence[float],
    lows: Sequence[float],
    step: float = 0.02,
    max_step: float = 0.2,
) -> List[Number]:
    """Parabolic SAR (stop-and-reverse). Below price = uptrend, above = downtrend."""
    n = len(highs)
    out: List[Number] = [None] * n
    if n < 2:
        return out
    uptrend = True
    af = step
    ep = highs[0]
    sar = lows[0]
    out[0] = sar
    for i in range(1, n):
        prev_sar = sar
        sar = prev_sar + af * (ep - prev_sar)
        if uptrend:
            sar = min(sar, lows[i - 1], lows[i - 2] if i >= 2 else lows[i - 1])
            if highs[i] > ep:
                ep = highs[i]
                af = min(af + step, max_step)
            if lows[i] < sar:  # reverse to downtrend
                uptrend = False
                sar = ep
                ep = lows[i]
                af = step
        else:
            sar = max(sar, highs[i - 1], highs[i - 2] if i >= 2 else highs[i - 1])
            if lows[i] < ep:
                ep = lows[i]
                af = min(af + step, max_step)
            if highs[i] > sar:  # reverse to uptrend
                uptrend = True
                sar = ep
                ep = highs[i]
                af = step
        out[i] = sar
    return out
