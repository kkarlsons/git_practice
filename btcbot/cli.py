"""Command-line interface for btcbot.

Subcommands:
    signal      Latest BUY/SELL/HOLD recommendation with reasoning.
    backtest    Evaluate one strategy vs buy-and-hold.
    compare     Backtest every strategy and rank them.
    history     Print recent signals bar-by-bar.
    strategies  List all available strategies.
    paper       Paper-trade (simulated, no real money): replay history or poll live.

Data source: --source {live,synthetic} or --csv PATH.
Strategy:    --strategy NAME (see `btcbot strategies`).
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from . import data as datamod
from .backtest import compare_strategies, run_backtest
from .features import Features
from .paper import PaperTrader, Portfolio
from .strategies import (
    BUY,
    DEFAULT_STRATEGY,
    HOLD,
    SELL,
    StrategyConfig,
    available,
    build,
    describe,
)

_COLORS = {BUY: "\033[92m", SELL: "\033[91m", HOLD: "\033[93m"}
_RESET = "\033[0m"


def _use_color(args) -> bool:
    return sys.stdout.isatty() and not args.no_color


def _fmt_action(action: str, color: bool) -> str:
    return f"{_COLORS.get(action, '')}{action}{_RESET}" if color else action


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


def _config(args) -> StrategyConfig:
    cfg = StrategyConfig()
    if getattr(args, "rsi_period", 0):
        cfg.rsi_period = args.rsi_period
    return cfg


def cmd_signal(args) -> int:
    candles = _load_candles(args)
    strat = build(args.strategy, Features(candles), _config(args))
    sig = strat.latest()
    color = _use_color(args)

    print(f"\n  {candles.symbol}  @  {sig.price:,.2f}   ({_fmt_time(sig.time)})")
    print(f"  strategy: {strat.name}")
    print("  " + "-" * 52)
    print(f"  Recommendation: {_fmt_action(sig.action, color)}   "
          f"score={sig.score:+.2f}  confidence={sig.confidence:.0%}\n")
    print("  Why:")
    for r in sorted(sig.reasons, key=lambda x: -abs(x.vote * (x.weight or 1))):
        arrow = "↑" if r.vote > 0.05 else "↓" if r.vote < -0.05 else "→"
        print(f"    {arrow} {r.name:<16} {r.detail}")
    print("\n  Not financial advice. Backtest before trusting any signal.\n")
    return 0


def cmd_backtest(args) -> int:
    candles = _load_candles(args)
    result = run_backtest(candles, args.strategy, _config(args), fee_rate=args.fee)
    print(f"\n  Backtest on {candles.symbol} ({len(candles)} bars, fee={args.fee:.2%})")
    print("  " + "-" * 52)
    for line in result.summary().splitlines():
        print("  " + line)
    verdict = "beat" if result.total_return > result.buy_hold_return else "trailed"
    print(f"\n  The strategy {verdict} buy-and-hold on this dataset.\n")
    return 0


def cmd_compare(args) -> int:
    candles = _load_candles(args)
    results = compare_strategies(candles, fee_rate=args.fee)
    bh = results[0].buy_hold_return if results else 0.0
    print(f"\n  Strategy comparison on {candles.symbol} "
          f"({len(candles)} bars, fee={args.fee:.2%})")
    print(f"  Buy & hold benchmark: {bh:+.1%}")
    print("  " + "-" * 64)
    print(f"  {'strategy':<16}{'return':>10}{'edge':>10}{'maxDD':>9}{'trades':>8}")
    print("  " + "-" * 64)
    for r in results:
        mark = "*" if r.total_return > r.buy_hold_return else " "
        print(f" {mark}{r.strategy:<16}{r.total_return:>9.1%}{r.edge:>10.1%}"
              f"{r.max_drawdown:>9.1%}{r.n_trades:>8}")
    print("  " + "-" * 64)
    print("  '*' = beat buy-and-hold on this dataset. Past results != future results.\n")
    return 0


def cmd_history(args) -> int:
    candles = _load_candles(args)
    strat = build(args.strategy, Features(candles), _config(args))
    color = _use_color(args)
    n = min(args.rows, len(candles) - strat.warmup)
    if n <= 0:
        print("\n  Not enough data for this strategy's warm-up period.\n")
        return 0
    print(f"\n  Last {n} signals for {candles.symbol} (strategy: {strat.name}):")
    print("  " + "-" * 52)
    for i in range(len(candles) - n, len(candles)):
        sig = strat.evaluate(i)
        if args.signals_only and sig.action == HOLD:
            continue
        print(f"  {_fmt_time(sig.time)}  {sig.price:>11,.2f}  "
              f"{_fmt_action(sig.action, color):<6}  score={sig.score:+.2f}")
    print()
    return 0


def cmd_strategies(args) -> int:
    print("\n  Available strategies:")
    print("  " + "-" * 60)
    for name, desc in describe():
        tag = "  (default)" if name == DEFAULT_STRATEGY else ""
        print(f"  {name:<16} {desc}{tag}")
    print()
    return 0


def cmd_paper(args) -> int:
    portfolio = Portfolio(cash=args.cash, fee_rate=args.fee)
    if args.state and args.resume:
        try:
            portfolio = Portfolio.load(args.state)
            print(f"  Resumed portfolio from {args.state}")
        except FileNotFoundError:
            pass
    trader = PaperTrader(strategy=args.strategy, config=_config(args), portfolio=portfolio)

    if args.live:
        trader.live(
            symbol=args.symbol, interval=args.interval,
            poll_seconds=args.poll, limit=args.limit,
            max_iterations=args.iterations, state_path=args.state,
        )
    else:
        candles = _load_candles(args)
        trader.replay(candles)
        if args.state:
            portfolio.save(args.state)
            print(f"  Journal saved to {args.state}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="btcbot", description="Technical-analysis Bitcoin signal & paper-trading bot")
    p.add_argument("--source", choices=["live", "synthetic"], default="synthetic",
                   help="Data source (default: synthetic; 'live' pulls real Binance data)")
    p.add_argument("--csv", help="Load OHLCV from a CSV file instead of --source")
    p.add_argument("--symbol", default="BTCUSDT", help="Trading pair for live data")
    p.add_argument("--interval", default="1d", choices=["1h", "4h", "1d"], help="Candle interval")
    p.add_argument("--limit", type=int, default=365, help="Number of candles/bars to load")
    p.add_argument("--strategy", default=DEFAULT_STRATEGY, choices=available(),
                   help=f"Strategy to use (default: {DEFAULT_STRATEGY})")
    p.add_argument("--rsi-period", type=int, default=0, help="Override RSI period")
    p.add_argument("--no-color", action="store_true", help="Disable colored output")

    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("signal", help="Latest buy/sell/hold recommendation").set_defaults(func=cmd_signal)

    b = sub.add_parser("backtest", help="Evaluate one strategy vs buy-and-hold")
    b.add_argument("--fee", type=float, default=0.001, help="Per-fill fee rate (default 0.001)")
    b.set_defaults(func=cmd_backtest)

    c = sub.add_parser("compare", help="Backtest and rank every strategy")
    c.add_argument("--fee", type=float, default=0.001, help="Per-fill fee rate (default 0.001)")
    c.set_defaults(func=cmd_compare)

    h = sub.add_parser("history", help="Print recent bar-by-bar signals")
    h.add_argument("--rows", type=int, default=20, help="How many recent bars to show")
    h.add_argument("--signals-only", action="store_true", help="Hide HOLD rows")
    h.set_defaults(func=cmd_history)

    sub.add_parser("strategies", help="List available strategies").set_defaults(func=cmd_strategies)

    pa = sub.add_parser("paper", help="Paper-trade (simulated money, no real risk)")
    pa.add_argument("--live", action="store_true", help="Poll a live exchange instead of replaying history")
    pa.add_argument("--cash", type=float, default=10_000.0, help="Starting paper cash")
    pa.add_argument("--fee", type=float, default=0.001, help="Per-fill fee rate")
    pa.add_argument("--poll", type=int, default=3600, help="Live poll interval in seconds")
    pa.add_argument("--iterations", type=int, default=None, help="Max live poll cycles (default: unlimited)")
    pa.add_argument("--state", help="Path to save/load the paper portfolio JSON")
    pa.add_argument("--resume", action="store_true", help="Resume from --state if it exists")
    pa.set_defaults(func=cmd_paper)

    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
