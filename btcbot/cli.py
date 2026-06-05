"""Command-line interface for btcbot.

Subcommands:
    signal     Print the latest BUY/SELL/HOLD recommendation with reasoning.
    backtest   Evaluate the strategy against buy-and-hold on the chosen data.
    history    Print recent signals bar-by-bar.

Data source is selected with --source {live,synthetic} or --csv PATH.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import data as datamod
from .backtest import run_backtest
from .strategy import BUY, HOLD, SELL, Strategy, StrategyConfig

_COLORS = {BUY: "\033[92m", SELL: "\033[91m", HOLD: "\033[93m"}
_RESET = "\033[0m"


def _fmt_action(action: str, use_color: bool) -> str:
    if not use_color:
        return action
    return f"{_COLORS.get(action, '')}{action}{_RESET}"


def _fmt_time(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _load_candles(args) -> "datamod.Candles":
    if args.csv:
        return datamod.load_csv(args.csv)
    if args.source == "live":
        try:
            return datamod.fetch_live(symbol=args.symbol, interval=args.interval, limit=args.limit)
        except RuntimeError as exc:
            print(f"[warn] {exc}", file=sys.stderr)
            print("[warn] Falling back to synthetic data.", file=sys.stderr)
            return datamod.synthetic(days=args.limit)
    return datamod.synthetic(days=args.limit)


def _config_from_args(args) -> StrategyConfig:
    cfg = StrategyConfig()
    if args.rsi_period:
        cfg.rsi_period = args.rsi_period
    return cfg


def cmd_signal(args) -> int:
    candles = _load_candles(args)
    strat = Strategy(candles, _config_from_args(args))
    sig = strat.latest()
    use_color = sys.stdout.isatty() and not args.no_color

    print(f"\n  {candles.symbol}  @  {sig.price:,.2f}   ({_fmt_time(sig.time)})")
    print("  " + "-" * 52)
    print(f"  Recommendation: {_fmt_action(sig.action, use_color)}   "
          f"score={sig.score:+.2f}  confidence={sig.confidence:.0%}\n")
    print("  Why:")
    for r in sorted(sig.reasons, key=lambda x: -abs(x.vote * x.weight)):
        arrow = "↑" if r.vote > 0.05 else "↓" if r.vote < -0.05 else "→"
        print(f"    {arrow} {r.name:<18} {r.detail}")
    print("\n  Not financial advice. Backtest before trusting any signal.\n")
    return 0


def cmd_backtest(args) -> int:
    candles = _load_candles(args)
    result = run_backtest(candles, _config_from_args(args), fee_rate=args.fee)
    print(f"\n  Backtest on {candles.symbol} ({len(candles)} bars, fee={args.fee:.2%})")
    print("  " + "-" * 52)
    for line in result.summary().splitlines():
        print("  " + line)
    verdict = "beat" if result.total_return > result.buy_hold_return else "trailed"
    print(f"\n  The strategy {verdict} buy-and-hold on this dataset.\n")
    return 0


def cmd_history(args) -> int:
    candles = _load_candles(args)
    strat = Strategy(candles, _config_from_args(args))
    use_color = sys.stdout.isatty() and not args.no_color
    n = min(args.rows, len(candles) - strat.warmup)
    print(f"\n  Last {n} signals for {candles.symbol}:")
    print("  " + "-" * 52)
    for i in range(len(candles) - n, len(candles)):
        sig = strat.evaluate(i)
        if args.signals_only and sig.action == HOLD:
            continue
        print(f"  {_fmt_time(sig.time)}  {sig.price:>11,.2f}  "
              f"{_fmt_action(sig.action, use_color):<6}  score={sig.score:+.2f}")
    print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="btcbot", description="Technical-analysis Bitcoin signal bot")
    p.add_argument("--source", choices=["live", "synthetic"], default="synthetic",
                   help="Data source (default: synthetic; use 'live' for real Binance data)")
    p.add_argument("--csv", help="Load OHLCV from a CSV file instead of --source")
    p.add_argument("--symbol", default="BTCUSDT", help="Trading pair for live data")
    p.add_argument("--interval", default="1d", choices=["1h", "4h", "1d"], help="Candle interval")
    p.add_argument("--limit", type=int, default=365, help="Number of candles/bars to load")
    p.add_argument("--rsi-period", type=int, default=0, help="Override RSI period")
    p.add_argument("--no-color", action="store_true", help="Disable colored output")

    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("signal", help="Latest buy/sell/hold recommendation")
    s.set_defaults(func=cmd_signal)

    b = sub.add_parser("backtest", help="Evaluate strategy vs buy-and-hold")
    b.add_argument("--fee", type=float, default=0.001, help="Per-fill fee rate (default 0.001)")
    b.set_defaults(func=cmd_backtest)

    h = sub.add_parser("history", help="Print recent bar-by-bar signals")
    h.add_argument("--rows", type=int, default=20, help="How many recent bars to show")
    h.add_argument("--signals-only", action="store_true", help="Hide HOLD rows")
    h.set_defaults(func=cmd_history)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
