from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .journal import read_jsonl
from .timeutils import iso_now, parse_dt


def _latest_books(books: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for book in books:
        token_id = str(book.get("token_id") or "")
        if token_id:
            latest[token_id] = book
    return latest


def _token_lookup(markets: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    lookup: dict[str, dict[str, str]] = {}
    for market in markets:
        if not isinstance(market, dict):
            continue
        token_ids = list(market.get("token_ids") or [])
        outcomes = list(market.get("outcomes") or [])
        for index, token_id in enumerate(token_ids):
            outcome = str(outcomes[index]) if index < len(outcomes) else f"Outcome {index + 1}"
            lookup[str(token_id)] = {
                "market_id": str(market.get("market_id") or ""),
                "question": str(market.get("question") or market.get("slug") or "Unknown market"),
                "slug": str(market.get("slug") or ""),
                "outcome": outcome,
            }
    return lookup


def _book_history(books: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    history: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for book in books:
        token_id = str(book.get("token_id") or "")
        if not token_id:
            continue
        history[token_id].append(
            {
                "timestamp": book.get("timestamp"),
                "best_bid": book.get("best_bid"),
                "best_ask": book.get("best_ask"),
                "midpoint": book.get("midpoint"),
                "spread": book.get("spread"),
            }
        )
    return {token_id: points[-80:] for token_id, points in history.items()}


def _market_summaries(
    watched_markets: list[dict[str, Any]],
    latest_books: dict[str, dict[str, Any]],
    histories: dict[str, list[dict[str, Any]]],
    quotes: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    quote_counts = Counter(str(row.get("market_id")) for row in quotes if row.get("market_id"))
    fill_counts = Counter(str(row.get("market_id")) for row in fills if row.get("market_id"))
    risk_counts = Counter(str(row.get("market_id")) for row in risk_events if row.get("market_id"))
    summaries: list[dict[str, Any]] = []
    for market in watched_markets:
        if not isinstance(market, dict):
            continue
        token_ids = list(market.get("token_ids") or [])
        outcomes = list(market.get("outcomes") or [])
        outcome_rows: list[dict[str, Any]] = []
        for index, token_id in enumerate(token_ids):
            token = str(token_id)
            book = latest_books.get(token, {})
            outcome_rows.append(
                {
                    "token_id": token,
                    "outcome": str(outcomes[index]) if index < len(outcomes) else f"Outcome {index + 1}",
                    "best_bid": book.get("best_bid"),
                    "best_ask": book.get("best_ask"),
                    "midpoint": book.get("midpoint"),
                    "spread": book.get("spread"),
                    "state": "missing" if book.get("best_bid") is None or book.get("best_ask") is None else "live/polled",
                    "history": histories.get(token, []),
                }
            )
        summaries.append(
            {
                "market_id": market.get("market_id"),
                "question": market.get("question") or market.get("slug"),
                "slug": market.get("slug"),
                "spread": market.get("spread"),
                "volume_24h": market.get("volume_24h"),
                "liquidity": market.get("liquidity"),
                "quote_count": quote_counts[str(market.get("market_id"))],
                "fill_count": fill_counts[str(market.get("market_id"))],
                "risk_event_count": risk_counts[str(market.get("market_id"))],
                "outcomes": outcome_rows,
            }
        )
    return summaries


def _compute_pnl(fills: list[dict[str, Any]], books: list[dict[str, Any]]) -> dict[str, Any]:
    latest = _latest_books(books)
    positions: dict[str, float] = defaultdict(float)
    cash: dict[str, float] = defaultdict(float)
    avg_cost: dict[str, float] = defaultdict(float)
    realized = 0.0
    for fill in fills:
        if fill.get("type") != "simulated_fill":
            continue
        token_id = str(fill.get("token_id"))
        price = float(fill.get("price") or 0.0)
        size = float(fill.get("size") or 0.0)
        if fill.get("side") == "bid":
            old_pos = positions[token_id]
            old_cost = avg_cost[token_id] * old_pos
            positions[token_id] += size
            avg_cost[token_id] = (old_cost + price * size) / positions[token_id] if positions[token_id] else 0.0
            cash[token_id] -= price * size
        elif fill.get("side") == "ask":
            sell_size = min(size, positions[token_id])
            realized += (price - avg_cost[token_id]) * sell_size
            positions[token_id] -= sell_size
            cash[token_id] += price * sell_size
    mark_value = 0.0
    missing_marks: list[str] = []
    for token_id, shares in positions.items():
        if shares == 0:
            continue
        book = latest.get(token_id)
        midpoint = book.get("midpoint") if book else None
        if midpoint is None:
            missing_marks.append(token_id)
            midpoint = avg_cost[token_id]
        mark_value += shares * float(midpoint)
    total_cash = sum(cash.values())
    mark_to_mid = total_cash + mark_value
    return {
        "mark_to_mid_pnl": round(mark_to_mid, 6),
        "spread_capture_pnl": round(realized, 6),
        "inventory_mark_pnl": round(mark_to_mid - realized, 6),
        "fees_estimated": "unknown",
        "rebates_estimated": "unknown",
        "rewards_estimated": "unknown",
        "open_positions": {token: round(shares, 6) for token, shares in positions.items() if shares},
        "missing_marks": missing_marks,
    }


def build_run_state(data_dir: Path) -> dict[str, Any]:
    markets = read_jsonl(data_dir / "markets.jsonl")
    books = read_jsonl(data_dir / "books.jsonl")
    quotes = read_jsonl(data_dir / "quotes.jsonl")
    fills = read_jsonl(data_dir / "fills.jsonl")
    risk_events = read_jsonl(data_dir / "risk_events.jsonl")
    arb_alerts = read_jsonl(data_dir / "arb_alerts.jsonl")
    selected = [row for row in markets if row.get("selected")]
    skipped = [row for row in markets if row.get("selected") is False]
    watched_markets = [row.get("normalized") for row in selected if isinstance(row.get("normalized"), dict)]
    skipped_counts = Counter(str(row.get("skip_reason") or row.get("decision_reason")) for row in skipped)
    fill_rows = [row for row in fills if row.get("type") == "simulated_fill"]
    denied_fill_rows = [row for row in fills if row.get("type") == "fill_denied"]
    risk_counts = Counter(str(row.get("type")) for row in risk_events)
    latest_books = _latest_books(books)
    histories = _book_history(books)
    labels_by_token = _token_lookup(watched_markets)
    for token_id, book in latest_books.items():
        label = labels_by_token.get(token_id)
        if label:
            book["market_question"] = label["question"]
            book["market_slug"] = label["slug"]
            book["outcome"] = label["outcome"]
            book["display_name"] = f"{label['question']} - {label['outcome']}"
    stale_books = [row for row in latest_books.values() if row.get("best_bid") is None or row.get("best_ask") is None]
    exposures: dict[str, float] = defaultdict(float)
    for fill in fill_rows:
        market_id = str(fill.get("market_id"))
        notional = float(fill.get("price") or 0.0) * float(fill.get("size") or 0.0)
        exposures[market_id] += notional if fill.get("side") == "bid" else -notional
    pnl = _compute_pnl(fill_rows, books)
    run_started_times = [
        parsed
        for parsed in (parse_dt(row.get("timestamp")) for row in risk_events if row.get("type") == "run_started")
        if parsed is not None
    ]
    run_completed_times = [
        parsed
        for parsed in (parse_dt(row.get("timestamp")) for row in risk_events if row.get("type") == "run_completed")
        if parsed is not None
    ]
    if run_started_times:
        completed = bool(run_completed_times and max(run_completed_times) >= max(run_started_times))
    else:
        completed = any(row.get("type") == "run_completed" for row in risk_events)
    observation_mode = any(row.get("type") == "observation_mode" for row in risk_events)
    fallback_mode = next(
        (row.get("mode") for row in risk_events if row.get("type") == "fallback_mode"),
        None,
    )
    return {
        "generated_at": iso_now(),
        "data_dir": str(data_dir),
        "status": "completed" if completed else "active_or_partial",
        "observation_mode": observation_mode,
        "fallback_mode": fallback_mode,
        "counts": {
            "markets_total": len(markets),
            "markets_watched": len(selected),
            "markets_skipped": len(skipped),
            "books": len(books),
            "quotes": len(quotes),
            "fills": len(fill_rows),
            "fills_denied": len(denied_fill_rows),
            "risk_events": len(risk_events),
            "arb_alerts": len([row for row in arb_alerts if row.get("is_alert")]),
        },
        "skipped_counts": dict(skipped_counts),
        "risk_counts": dict(risk_counts),
        "watched_markets": watched_markets,
        "market_summaries": _market_summaries(watched_markets, latest_books, histories, quotes, fill_rows, risk_events),
        "labels_by_token": labels_by_token,
        "book_history": histories,
        "latest_books": latest_books,
        "stale_or_missing_books": stale_books,
        "recent_quotes": quotes[-50:],
        "recent_fills": fill_rows[-50:],
        "recent_risk_events": risk_events[-50:],
        "arb_alerts": [row for row in arb_alerts if row.get("is_alert")],
        "exposures_by_market": {market: round(value, 6) for market, value in exposures.items()},
        "pnl": pnl,
    }


def write_dashboard_state(data_dir: Path, state: dict[str, Any]) -> None:
    with (data_dir / "dashboard_state.json").open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)


def render_summary(state: dict[str, Any], *, date: str | None = None, dashboard_url: str | None = None) -> str:
    counts = state["counts"]
    pnl = state["pnl"]
    skipped_counts = state["skipped_counts"]
    risk_counts = state["risk_counts"]
    lines = [
        f"# Polymarket Paper Run Summary{f' - {date}' if date else ''}",
        "",
        f"- Status: {state['status']}",
        f"- Observation mode: {state['observation_mode']}",
        f"- Data mode: {state['fallback_mode'] or 'unknown'}",
        f"- Markets watched: {counts['markets_watched']}",
        f"- Markets skipped: {counts['markets_skipped']}",
        f"- Virtual quotes: {counts['quotes']}",
        f"- Simulated fills: {counts['fills']}",
        f"- Denied fills: {counts['fills_denied']}",
        f"- Book events: {counts['books']}",
        f"- Risk events: {counts['risk_events']}",
        f"- Arbitrage alerts: {counts['arb_alerts']}",
        "",
        "## PnL Components",
        "",
        f"- Mark-to-mid PnL: {pnl['mark_to_mid_pnl']}",
        f"- Spread-capture PnL: {pnl['spread_capture_pnl']}",
        f"- Inventory mark PnL: {pnl['inventory_mark_pnl']}",
        f"- Fees: {pnl['fees_estimated']}",
        f"- Rebates: {pnl['rebates_estimated']}",
        f"- Rewards: {pnl['rewards_estimated']}",
        "",
        "## Exposure",
        "",
    ]
    if state["exposures_by_market"]:
        for market_id, exposure in sorted(state["exposures_by_market"].items()):
            lines.append(f"- {market_id}: {exposure}")
    else:
        lines.append("- No simulated fill exposure.")
    lines.extend(["", "## Skipped Markets", ""])
    if skipped_counts:
        for reason, count in sorted(skipped_counts.items()):
            lines.append(f"- {reason}: {count}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Risk Events", ""])
    if risk_counts:
        for event_type, count in sorted(risk_counts.items()):
            lines.append(f"- {event_type}: {count}")
    else:
        lines.append("- None.")
    lines.extend(["", "## Checks Run", ""])
    checks = [row for row in state["recent_risk_events"] if row.get("type") == "checks_run"]
    if checks:
        for check in checks:
            lines.append(f"- {check.get('command')}: {check.get('status')}")
    else:
        lines.append("- Not recorded in this run directory.")
    lines.extend(["", "## Dashboard", ""])
    lines.append(f"- URL: {dashboard_url or 'not started by report command'}")
    lines.extend(["", "## Next Experiment", ""])
    if state["observation_mode"]:
        lines.append("- Review filter bottlenecks before relaxing any constraints; keep the next run paper-only.")
    elif counts["fills"] == 0:
        lines.append("- Compare quote placement against subsequent book moves to decide whether bid-only maker simulation is too conservative.")
    else:
        lines.append("- Replay fills against longer book history and tighten adverse-selection accounting before adding any strategy complexity.")
    return "\n".join(lines) + "\n"


def generate_report(data_dir: Path, *, date: str | None = None, dashboard_url: str | None = None) -> dict[str, Any]:
    state = build_run_state(data_dir)
    write_dashboard_state(data_dir, state)
    summary = render_summary(state, date=date, dashboard_url=dashboard_url)
    (data_dir / "summary.md").write_text(summary, encoding="utf-8")
    return state
