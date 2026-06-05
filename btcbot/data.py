"""Market-data sources for the bot.

Three interchangeable sources, all returning the same ``Candles`` structure:

* :func:`fetch_live`    - real OHLCV from a public exchange API (needs network).
* :func:`load_csv`      - OHLCV from a local CSV file.
* :func:`synthetic`     - a deterministic random-walk generator for demos/tests
                          and for sandboxes without network access.

Keeping a single shared shape means the strategy/backtest layers don't care
where the candles came from.
"""

from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


@dataclass
class Candles:
    """Column-oriented OHLCV series. All lists share the same length/index."""

    times: List[int] = field(default_factory=list)  # unix seconds
    opens: List[float] = field(default_factory=list)
    highs: List[float] = field(default_factory=list)
    lows: List[float] = field(default_factory=list)
    closes: List[float] = field(default_factory=list)
    volumes: List[float] = field(default_factory=list)
    symbol: str = "BTC"

    def __len__(self) -> int:
        return len(self.closes)

    def last_price(self) -> Optional[float]:
        return self.closes[-1] if self.closes else None


# Map a friendly interval to Binance's kline interval + seconds-per-bar.
_INTERVALS = {
    "1h": ("1h", 3600),
    "4h": ("4h", 14400),
    "1d": ("1d", 86400),
}


def fetch_live(symbol: str = "BTCUSDT", interval: str = "1d", limit: int = 365) -> Candles:
    """Fetch real OHLCV candles from Binance's public REST API.

    Requires the ``requests`` package and outbound network access. Raises a
    ``RuntimeError`` with a friendly message if either is missing so callers can
    fall back to :func:`synthetic`.
    """
    try:
        import requests  # imported lazily so the bot works without it
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "The 'requests' package is required for live data. "
            "Install it with: pip install requests"
        ) from exc

    if interval not in _INTERVALS:
        raise ValueError(f"interval must be one of {sorted(_INTERVALS)}")
    binance_interval, _ = _INTERVALS[interval]

    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": binance_interval, "limit": limit}
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        rows = resp.json()
    except Exception as exc:  # pragma: no cover - network dependent
        raise RuntimeError(
            f"Could not fetch live data from Binance ({exc}). "
            "Check your network/allowlist, or use --source synthetic / --csv."
        ) from exc

    candles = Candles(symbol=symbol)
    for row in rows:
        # Binance kline: [openTime, open, high, low, close, volume, ...]
        candles.times.append(int(row[0]) // 1000)
        candles.opens.append(float(row[1]))
        candles.highs.append(float(row[2]))
        candles.lows.append(float(row[3]))
        candles.closes.append(float(row[4]))
        candles.volumes.append(float(row[5]))
    return candles


def load_csv(path: str, symbol: str = "BTC") -> Candles:
    """Load OHLCV from a CSV with headers: time,open,high,low,close,volume.

    ``time`` may be a unix timestamp (seconds) or an ISO-8601 date string.
    Missing volume defaults to 0.
    """
    candles = Candles(symbol=symbol)
    with open(path, newline="") as fh:
        reader = csv.DictReader(fh)
        cols = {c.lower(): c for c in (reader.fieldnames or [])}
        required = {"time", "open", "high", "low", "close"}
        missing = required - set(cols)
        if missing:
            raise ValueError(f"CSV missing required columns: {sorted(missing)}")
        for row in reader:
            candles.times.append(_parse_time(row[cols["time"]]))
            candles.opens.append(float(row[cols["open"]]))
            candles.highs.append(float(row[cols["high"]]))
            candles.lows.append(float(row[cols["low"]]))
            candles.closes.append(float(row[cols["close"]]))
            vol = row[cols["volume"]] if "volume" in cols else None
            candles.volumes.append(float(vol) if vol else 0.0)
    return candles


def _parse_time(raw: str) -> int:
    raw = raw.strip()
    try:
        return int(float(raw))
    except ValueError:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())


def synthetic(
    days: int = 365,
    start_price: float = 30000.0,
    seed: int = 42,
    interval_seconds: int = 86400,
) -> Candles:
    """Generate a deterministic, BTC-like random walk for demos and tests.

    Uses geometric Brownian motion with a mild upward drift plus an injected
    multi-week cycle, so trend-following and mean-reversion signals both have
    something realistic to react to. Same ``seed`` always yields same data.
    """
    rng = random.Random(seed)
    candles = Candles(symbol="BTC-SYNTH")
    price = start_price
    now = int(datetime.now(tz=timezone.utc).timestamp())
    start_time = now - days * interval_seconds

    daily_drift = 0.0003  # ~11%/yr upward bias
    daily_vol = 0.03  # ~3% daily volatility

    for i in range(days):
        cycle = 0.012 * math.sin(i / 18.0)  # slow ~18-bar oscillation
        shock = rng.gauss(0, 1) * daily_vol
        ret = daily_drift + cycle + shock
        open_p = price
        close_p = max(1.0, open_p * (1 + ret))
        high_p = max(open_p, close_p) * (1 + abs(rng.gauss(0, 1)) * 0.006)
        low_p = min(open_p, close_p) * (1 - abs(rng.gauss(0, 1)) * 0.006)
        vol = abs(rng.gauss(1000, 250))

        candles.times.append(start_time + i * interval_seconds)
        candles.opens.append(round(open_p, 2))
        candles.highs.append(round(high_p, 2))
        candles.lows.append(round(low_p, 2))
        candles.closes.append(round(close_p, 2))
        candles.volumes.append(round(vol, 2))
        price = close_p

    return candles
