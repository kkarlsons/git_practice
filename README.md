# btcbot — a Bitcoin technical-analysis signal bot

`btcbot` analyzes Bitcoin price data with classic technical indicators and tells
you when it thinks you should **BUY**, **SELL**, or **HOLD** — with a confidence
score and a plain-English explanation of *why*. It also includes a fee-aware
**backtester** so you can measure whether a strategy would actually have made
money, instead of taking anyone's word for it.

> ⚠️ **Honest disclaimer.** No bot can guarantee profits, and this one doesn't
> try to. Markets are noisy and adversarial; any tool promising "guaranteed
> gains" is a scam. `btcbot` gives you a disciplined, transparent, *backtestable*
> reading of the chart. **It is not financial advice.** Validate on history,
> start in paper/simulation, and never risk money you can't afford to lose.

## Features

- **17 pure-Python indicators** (no pandas/numpy): SMA, EMA, WMA, HMA, RSI,
  Stochastic RSI, MACD, Bollinger Bands, ATR, Stochastic, Williams %R, CCI, ROC,
  Momentum, OBV, MFI, ADX/+DI/-DI, Donchian, Keltner, Parabolic SAR, VWAP.
- **18 pluggable strategies** spanning trend-following, momentum, oscillators,
  and volatility — plus a **consensus** meta-strategy that polls every other
  strategy and votes, and a hand-weighted **ensemble**. Every recommendation
  shows exactly which signals drove it.
- **Backtester** that compares any strategy against buy-and-hold (fees,
  drawdown, trade count), plus a **`compare`** command that ranks all strategies.
- **Paper trading** (simulated money, zero real-world risk): replay history or
  poll a live exchange, with a saveable trade journal.
- **Three data sources**: live exchange data (Binance public API), a local CSV
  file, or a built-in deterministic synthetic generator for offline demos/tests.
- **Zero required dependencies** — `requests` is only needed for live data.

> **Risk posture:** this bot **does not place real-money orders.** It generates
> signals and trades a *paper* portfolio only. Wiring it to a real exchange for
> live execution is intentionally left out.

## Quick start

```bash
# No install needed for the demo (uses built-in synthetic data):
python main.py signal                      # latest recommendation (consensus of all strategies)
python main.py strategies                  # list all 18 strategies
python main.py compare                      # backtest & rank every strategy vs buy-and-hold
python main.py backtest --strategy macd     # backtest a single strategy
python main.py history --rows 40 --signals-only   # recent bar-by-bar signals

# Paper trading (simulated money, no real risk):
python main.py --strategy ema_cross paper --state journal.json   # replay history
python main.py paper --live --interval 1h --poll 3600            # poll a live exchange
```

Pick any strategy with `--strategy NAME` on any command (default: `consensus`).

### Using real Bitcoin data

When you run on a machine with internet access, pull live candles from Binance:

```bash
pip install requests
python main.py --source live --interval 1d --limit 365 signal
python main.py --source live --interval 4h --limit 500 backtest
```

If the network is unavailable, the bot prints a warning and falls back to
synthetic data so it never hard-crashes.

### Using your own CSV

Provide a CSV with headers `time,open,high,low,close,volume` (`time` may be a
unix timestamp or an ISO date; `volume` is optional):

```bash
python main.py --csv my_btc_data.csv signal
```

## Example output

```
  BTC-SYNTH  @  54,772.56   (2026-06-04 17:56 UTC)
  ----------------------------------------------------
  Recommendation: BUY   score=+0.37  confidence=100%

  Why:
    ↑ Trend (SMA50)      Price 54,773 is 14.8% above the 50-period SMA
    ↑ EMA cross (12/26)  Fast EMA is 3.0% above slow EMA (bullish)
    ↑ MACD               MACD histogram is positive (rising momentum)
    ↓ Bollinger          Price is riding the upper Bollinger band (stretched up)
```

## How signals work

Every strategy turns indicator readings into weighted votes in `[-1, +1]`
(bearish..bullish). Votes are normalized into a score: above `+0.25` → **BUY**,
below `-0.25` → **SELL**, otherwise **HOLD**. Each strategy reports its reasoning
so nothing is a black box.

The strategies, by family:

| Family            | Strategies                                                        |
|-------------------|-------------------------------------------------------------------|
| Trend-following   | `trend_filter`, `ma_crossover`, `ema_cross`, `adx_trend`, `psar`  |
| Momentum          | `macd`, `roc`                                                     |
| Oscillators       | `rsi_reversion`, `stochastic`, `stoch_rsi`, `williams_r`, `cci`, `mfi` |
| Volatility/channel| `bollinger`, `keltner`, `donchian`                                |
| **Meta**          | `ensemble` (weighted blend), `consensus` (vote across all)        |

The **consensus** strategy (default) polls all 16 single-method strategies and
acts on the aggregate, reporting how many lean bullish vs bearish — broad
agreement across independent methods is a stronger tell than any one indicator.
Tune periods/thresholds via `StrategyConfig` in
[`btcbot/strategies/base.py`](btcbot/strategies/base.py).

## Project layout

```
btcbot/
  indicators.py        # 17 pure-Python TA indicators
  data.py              # live / CSV / synthetic data sources
  features.py          # lazy, cached indicator computation shared by strategies
  strategies/
    base.py            # Strategy base class + Signal/Reason types
    trend.py           # trend-following strategies
    momentum.py        # momentum & oscillator strategies
    volatility.py      # channel/volatility strategies
    ensemble.py        # hand-weighted blend
    consensus.py       # vote-across-all meta-strategy
    __init__.py        # strategy registry (build / available / compare)
  backtest.py          # long/flat backtester + multi-strategy comparison
  paper.py             # paper-trading engine (replay + live poll)
  strategy.py          # backward-compatible shim
  cli.py               # command-line interface
main.py                # entry point
tests/                 # 24 unit tests (no external deps)
```

## Running the tests

```bash
python tests/test_indicators.py
python tests/test_strategy.py
python tests/test_extended.py
# or, if you have pytest:
python -m pytest -q
```

## Roadmap ideas

- Position sizing / stop-loss & take-profit via ATR.
- Walk-forward / out-of-sample optimization of strategy parameters.
- Risk metrics: Sharpe, Sortino, win rate, profit factor.
- Optional alerting (email/Telegram) when a new signal fires.

## Disclaimer

This software is for educational purposes only and is **not financial advice**.
Trading cryptocurrencies carries substantial risk. The authors accept no
liability for any losses. Do your own research.
