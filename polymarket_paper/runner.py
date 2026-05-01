from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .adapters import AdapterError, fetch_book_snapshot, fetch_gamma_markets
from .arbitrage import scan_market_from_books
from .filters import journal_market, observation_candidates, selected_market_rows
from .journal import append_jsonl, ensure_run_dir, read_jsonl, write_jsonl
from .report import generate_report
from .risk import RiskState
from .simulator import PaperSimulator
from .timeutils import iso_now, utc_now


def discover_markets(*, limit: int, out: Path) -> int:
    raw_markets = fetch_gamma_markets(limit)
    rows = [journal_market(raw) for raw in raw_markets]
    return write_jsonl(out, rows)


def _load_or_discover(data_dir: Path, limit: int) -> list[dict[str, Any]]:
    markets_path = data_dir / "markets.jsonl"
    rows = read_jsonl(markets_path)
    if rows:
        return rows
    raw_markets = fetch_gamma_markets(limit)
    rows = [journal_market(raw) for raw in raw_markets]
    write_jsonl(markets_path, rows)
    return rows


def _market_dict(row: dict[str, Any]) -> dict[str, Any]:
    normalized = row.get("normalized")
    return normalized if isinstance(normalized, dict) else {}


def run_paper_session(
    *,
    out_dir: Path,
    minutes: float,
    max_markets: int,
    max_virtual_exposure: float,
    quote_size: float,
    maker_only: bool,
    poll_seconds: float = 30.0,
    quote_mode: str = "one_tick_inside",
    quote_expiry_seconds: int = 30,
    max_fills_per_market: int = 8,
    max_fills_per_token: int = 4,
) -> dict[str, Any]:
    if not maker_only:
        raise ValueError("paper run only supports maker-only simulation")
    ensure_run_dir(out_dir)
    started = utc_now()
    append_jsonl(
        out_dir / "risk_events.jsonl",
        {
            "type": "run_started",
            "timestamp": started.isoformat(),
            "minutes": minutes,
            "max_markets": max_markets,
            "max_virtual_exposure": max_virtual_exposure,
            "quote_size": quote_size,
            "quote_mode": quote_mode,
            "quote_expiry_seconds": quote_expiry_seconds,
            "max_fills_per_market": max_fills_per_market,
            "max_fills_per_token": max_fills_per_token,
        },
    )
    append_jsonl(
        out_dir / "risk_events.jsonl",
        {
            "type": "fallback_mode",
            "timestamp": iso_now(),
            "mode": "polling",
            "reason": "websocket_not_required_for_first_scaffold",
        },
    )
    append_jsonl(
        out_dir / "risk_events.jsonl",
        {
            "type": "public_trade_evidence_status",
            "timestamp": iso_now(),
            "status": "book_move_only",
            "reason": "public_trade_tape_integration_deferred_to_keep_paper_smoke_and_offline_tests_unblocked",
        },
    )
    rows = _load_or_discover(out_dir, max(100, max_markets * 5))
    selected_rows = selected_market_rows(rows)
    observation_mode = len(selected_rows) < 3
    if observation_mode:
        reasons: dict[str, int] = {}
        for row in rows:
            if row.get("selected") is False:
                reason = str(row.get("skip_reason") or "unknown")
                reasons[reason] = reasons.get(reason, 0) + 1
        append_jsonl(
            out_dir / "risk_events.jsonl",
            {
                "type": "observation_mode",
                "timestamp": iso_now(),
                "reason": "fewer_than_three_markets_passed_filters",
                "selected_count": len(selected_rows),
                "skip_counts": reasons,
            },
        )
    source_rows = selected_rows if selected_rows else observation_candidates(rows)
    markets = [_market_dict(row) for row in source_rows[:max_markets]]
    risk = RiskState(
        max_total_exposure=max_virtual_exposure,
        max_market_fills=max_fills_per_market,
        max_token_fills=max_fills_per_token,
    )
    simulator = PaperSimulator(
        risk=risk,
        quote_size=quote_size,
        quote_mode=quote_mode,
        quote_expiry_seconds=quote_expiry_seconds,
    )
    books_by_market: dict[str, dict[str, dict[str, Any]]] = {}
    deadline = time.monotonic() + (minutes * 60)
    loops = 0
    while time.monotonic() < deadline:
        loops += 1
        for market in markets:
            market_id = str(market.get("market_id"))
            token_ids = list(market.get("token_ids") or [])
            outcomes = list(market.get("outcomes") or [])
            for index, token_id in enumerate(token_ids):
                outcome = str(outcomes[index]) if index < len(outcomes) else f"outcome_{index}"
                try:
                    snapshot = fetch_book_snapshot(token_id=str(token_id), market_id=market_id, outcome=outcome)
                except AdapterError as exc:
                    append_jsonl(
                        out_dir / "risk_events.jsonl",
                        {
                            "type": "book_fetch_failed",
                            "timestamp": iso_now(),
                            "market_id": market_id,
                            "token_id": token_id,
                            "error": str(exc),
                        },
                    )
                    continue
                row = snapshot.as_dict()
                append_jsonl(out_dir / "books.jsonl", row)
                books_by_market.setdefault(market_id, {})[str(token_id)] = row
                fills, risk_events = simulator.process_snapshot(row)
                for risk_event in risk_events:
                    append_jsonl(out_dir / "risk_events.jsonl", risk_event)
                for fill in fills:
                    append_jsonl(out_dir / "fills.jsonl", fill)
                if not observation_mode and snapshot.best_bid is not None and snapshot.best_ask is not None:
                    quotes = simulator.generate_quotes(row)
                    for quote in quotes:
                        append_jsonl(out_dir / "quotes.jsonl", quote)
        for market in markets:
            market_id = str(market.get("market_id"))
            scan = scan_market_from_books(market, books_by_market.get(market_id, {}))
            if scan and scan.get("is_alert"):
                scan["timestamp"] = iso_now()
                append_jsonl(out_dir / "arb_alerts.jsonl", scan)
        generate_report(out_dir)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_seconds, remaining))
    append_jsonl(
        out_dir / "risk_events.jsonl",
        {
            "type": "run_completed",
            "timestamp": iso_now(),
            "loops": loops,
            "mode": "polling",
            "observation_mode": observation_mode,
        },
    )
    return generate_report(out_dir)
