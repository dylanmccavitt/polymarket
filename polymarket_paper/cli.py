from __future__ import annotations

import argparse
from pathlib import Path

from .dashboard import serve_dashboard
from .report import generate_report
from .runner import discover_markets, run_paper_session
from .simulator import QUOTE_MODES


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="polymarket_paper",
        description="Paper-only, read-only Polymarket market-structure research CLI.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    discover = sub.add_parser("discover", help="Fetch public Gamma markets and journal filter decisions.")
    discover.add_argument("--limit", type=int, default=100)
    discover.add_argument("--out", type=Path, required=True)

    run = sub.add_parser("run", help="Run paper-only maker simulation from public orderbook polling.")
    run.add_argument("--minutes", type=float, required=True)
    run.add_argument("--max-markets", type=int, default=10)
    run.add_argument("--max-virtual-exposure", type=float, default=100.0)
    run.add_argument("--quote-size", type=float, default=5.0)
    run.add_argument("--quote-mode", choices=QUOTE_MODES, default="one_tick_inside")
    run.add_argument("--quote-expiry-seconds", type=int, default=30)
    run.add_argument("--max-fills-per-market", type=int, default=8)
    run.add_argument("--max-fills-per-token", type=int, default=4)
    run.add_argument("--maker-only", action="store_true", help="Required guardrail: only maker-style virtual quotes.")
    run.add_argument("--out-dir", type=Path, required=True)
    run.add_argument("--poll-seconds", type=float, default=30.0)

    report = sub.add_parser("report", help="Replay JSONL logs and write summary.md plus dashboard_state.json.")
    report.add_argument("--date", required=False)
    report.add_argument("--data-dir", type=Path, required=True)
    report.add_argument("--dashboard-url", default=None)

    dashboard = sub.add_parser("dashboard", help="Serve a local read-only viewer over JSONL run evidence.")
    dashboard.add_argument("--data-dir", type=Path, required=True)
    dashboard.add_argument("--host", default="127.0.0.1")
    dashboard.add_argument("--port", type=int, default=8765)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "discover":
        count = discover_markets(limit=args.limit, out=args.out)
        print(f"wrote {count} market filter rows to {args.out}")
        return 0
    if args.command == "run":
        if not args.maker_only:
            parser.error("paper runs require --maker-only; no live or taker command path exists")
        state = run_paper_session(
            out_dir=args.out_dir,
            minutes=args.minutes,
            max_markets=args.max_markets,
            max_virtual_exposure=args.max_virtual_exposure,
            quote_size=args.quote_size,
            maker_only=args.maker_only,
            poll_seconds=args.poll_seconds,
            quote_mode=args.quote_mode,
            quote_expiry_seconds=args.quote_expiry_seconds,
            max_fills_per_market=args.max_fills_per_market,
            max_fills_per_token=args.max_fills_per_token,
        )
        print(f"paper run complete: {state['counts']}")
        return 0
    if args.command == "report":
        state = generate_report(args.data_dir, date=args.date, dashboard_url=args.dashboard_url)
        print(f"wrote report for {args.data_dir}: {state['counts']}")
        return 0
    if args.command == "dashboard":
        serve_dashboard(args.data_dir, args.host, args.port)
        return 0
    parser.error("unknown command")
    return 2
