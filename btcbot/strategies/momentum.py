"""Momentum and oscillator strategies."""

from __future__ import annotations

from typing import List

from .base import Reason, Strategy, clamp


class MACDStrategy(Strategy):
    name = "macd"
    description = "MACD histogram momentum"

    @property
    def warmup(self) -> int:
        return self.cfg.slow_ema + 9

    def votes(self, i: int) -> List[Reason]:
        _, _, hist = self.f.macd(self.cfg.fast_ema, self.cfg.slow_ema)
        h = hist[i]
        price = self.candles.closes[i]
        if h is None:
            return []
        vote = clamp((h / price) / 0.01)
        return [Reason(
            "MACD", vote, 1.0,
            f"MACD histogram is {'positive (rising)' if h >= 0 else 'negative (falling)'} momentum",
        )]


class RSIReversion(Strategy):
    name = "rsi_reversion"
    description = "RSI mean-reversion: buy oversold, sell overbought"

    @property
    def warmup(self) -> int:
        return self.cfg.rsi_period + 1

    def votes(self, i: int) -> List[Reason]:
        r = self.f.rsi(self.cfg.rsi_period)[i]
        if r is None:
            return []
        if r <= self.cfg.rsi_oversold:
            vote = clamp((self.cfg.rsi_oversold - r) / self.cfg.rsi_oversold + 0.3)
            detail = f"RSI {r:.0f} oversold (<= {self.cfg.rsi_oversold:.0f}) - bounce likely"
        elif r >= self.cfg.rsi_overbought:
            vote = -clamp((r - self.cfg.rsi_overbought) / (100 - self.cfg.rsi_overbought) + 0.3)
            detail = f"RSI {r:.0f} overbought (>= {self.cfg.rsi_overbought:.0f}) - pullback likely"
        else:
            vote = clamp((r - 50) / 50) * 0.3
            detail = f"RSI {r:.0f} neutral"
        return [Reason("RSI", vote, 1.0, detail)]


class StochasticStrategy(Strategy):
    name = "stochastic"
    description = "Stochastic oscillator %K/%D crosses in overbought/oversold zones"

    @property
    def warmup(self) -> int:
        return self.cfg.stoch_k + self.cfg.stoch_d

    def votes(self, i: int) -> List[Reason]:
        k_series, d_series = self.f.stochastic(self.cfg.stoch_k, self.cfg.stoch_d)
        k, d = k_series[i], d_series[i]
        if k is None or d is None:
            return []
        cross = (k - d) / 100.0  # bullish when %K above %D
        if k <= 20:
            zone = 0.5  # oversold lift
        elif k >= 80:
            zone = -0.5
        else:
            zone = 0.0
        vote = clamp(zone + cross * 2)
        return [Reason(
            "Stochastic", vote, 1.0,
            f"%K {k:.0f} / %D {d:.0f}"
            + (" (oversold)" if k <= 20 else " (overbought)" if k >= 80 else ""),
        )]


class StochRSIStrategy(Strategy):
    name = "stoch_rsi"
    description = "Stochastic RSI: a sharper overbought/oversold oscillator"

    @property
    def warmup(self) -> int:
        return self.cfg.rsi_period * 2

    def votes(self, i: int) -> List[Reason]:
        s = self.f.stoch_rsi(self.cfg.rsi_period, self.cfg.rsi_period)[i]
        if s is None:
            return []
        if s <= 20:
            vote = clamp((20 - s) / 20 + 0.3)
            detail = f"StochRSI {s:.0f} oversold"
        elif s >= 80:
            vote = -clamp((s - 80) / 20 + 0.3)
            detail = f"StochRSI {s:.0f} overbought"
        else:
            vote = clamp((s - 50) / 50) * 0.3
            detail = f"StochRSI {s:.0f} neutral"
        return [Reason("StochRSI", vote, 1.0, detail)]


class WilliamsRStrategy(Strategy):
    name = "williams_r"
    description = "Williams %R overbought/oversold"

    @property
    def warmup(self) -> int:
        return 14

    def votes(self, i: int) -> List[Reason]:
        wr = self.f.williams_r(14)[i]
        if wr is None:
            return []
        # -100..0; <= -80 oversold, >= -20 overbought
        if wr <= -80:
            vote = clamp((-80 - wr) / 20 + 0.3)
            detail = f"Williams %R {wr:.0f} oversold"
        elif wr >= -20:
            vote = -clamp((wr + 20) / 20 + 0.3)
            detail = f"Williams %R {wr:.0f} overbought"
        else:
            vote = clamp((wr + 50) / 50) * 0.3
            detail = f"Williams %R {wr:.0f} neutral"
        return [Reason("Williams %R", vote, 1.0, detail)]


class CCIStrategy(Strategy):
    name = "cci"
    description = "Commodity Channel Index breakouts of the +/-100 band"

    @property
    def warmup(self) -> int:
        return 20

    def votes(self, i: int) -> List[Reason]:
        c = self.f.cci(20)[i]
        if c is None:
            return []
        vote = clamp(c / 200.0)
        if c >= 100:
            detail = f"CCI {c:.0f} above +100 (strong upside)"
        elif c <= -100:
            detail = f"CCI {c:.0f} below -100 (strong downside)"
        else:
            detail = f"CCI {c:.0f} within normal band"
        return [Reason("CCI", vote, 1.0, detail)]


class ROCMomentum(Strategy):
    name = "roc"
    description = "Rate-of-change momentum"

    @property
    def warmup(self) -> int:
        return 12

    def votes(self, i: int) -> List[Reason]:
        r = self.f.roc(12)[i]
        if r is None:
            return []
        vote = clamp(r / 10.0)  # +/-10% over the window -> full vote
        return [Reason(
            "ROC", vote, 1.0,
            f"12-bar rate of change is {r:+.1f}%",
        )]


class MFIStrategy(Strategy):
    name = "mfi"
    description = "Money Flow Index: volume-weighted overbought/oversold"

    @property
    def warmup(self) -> int:
        return 15

    def votes(self, i: int) -> List[Reason]:
        m = self.f.mfi(14)[i]
        if m is None:
            return []
        if m <= 20:
            vote = clamp((20 - m) / 20 + 0.3)
            detail = f"MFI {m:.0f} oversold (money flowing out, exhaustion)"
        elif m >= 80:
            vote = -clamp((m - 80) / 20 + 0.3)
            detail = f"MFI {m:.0f} overbought"
        else:
            vote = clamp((m - 50) / 50) * 0.3
            detail = f"MFI {m:.0f} neutral"
        return [Reason("MFI", vote, 1.0, detail)]
