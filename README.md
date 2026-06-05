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

- **Pure-Python indicators** (no pandas/numpy): SMA, EMA, RSI, MACD,
  Bollinger Bands, ATR.
- **Transparent signal engine** — a weighted ensemble of trend, momentum, and
  mean-reversion signals. Every recommendation shows the contribution of each
  component.
- **Backtester** that compares the strategy against buy-and-hold, with fees,
  drawdown, and trade count.
- **Three data sources**: live exchange data (Binance public API), a local CSV
  file, or a built-in deterministic synthetic generator for offline demos/tests.
- **Zero required dependencies** — `requests` is only needed for live data.

## Quick start

```bash
# No install needed for the demo (uses built-in synthetic data):
python main.py signal

# Backtest the strategy vs buy-and-hold:
python main.py backtest

# Recent bar-by-bar signals (hide HOLDs):
python main.py history --rows 40 --signals-only
```

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

## How the strategy works

Each bar, five components each cast a vote in `[-1, +1]`:

| Component        | Idea                                            | Type            |
|------------------|-------------------------------------------------|-----------------|
| Trend (SMA-50)   | Price above/below the long mean                 | Trend-following |
| EMA cross 12/26  | Fast EMA above/below slow EMA                    | Trend-following |
| MACD histogram   | Momentum rising/falling                          | Momentum        |
| RSI-14           | Oversold → bullish, overbought → bearish         | Mean-reversion  |
| Bollinger Bands  | Stretched to the lower/upper band                | Mean-reversion  |

Votes are weighted and normalized into a score in `[-1, +1]`. Above
`+0.25` → **BUY**, below `-0.25` → **SELL**, otherwise **HOLD**. Tune the
thresholds, weights, and indicator periods in
[`btcbot/strategy.py`](btcbot/strategy.py) (`StrategyConfig`).

## Project layout

```
btcbot/
  indicators.py   # pure-Python TA indicators
  data.py         # live / CSV / synthetic data sources
  strategy.py     # weighted-ensemble signal engine
  backtest.py     # long/flat backtester with fees
  cli.py          # command-line interface
main.py           # entry point
tests/            # unit tests (no external deps)
```

## Running the tests

```bash
python tests/test_indicators.py
python tests/test_strategy.py
# or, if you have pytest:
python -m pytest -q
```

## Roadmap ideas

- Position sizing / stop-loss via ATR.
- Paper-trading loop that polls live prices and logs signals over time.
- Additional indicators (Stochastic, OBV) and walk-forward optimization.
- Optional alerting (email/Telegram) when a new signal fires.

## Disclaimer

This software is for educational purposes only and is **not financial advice**.
Trading cryptocurrencies carries substantial risk. The authors accept no
liability for any losses. Do your own research.
