from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path
from typing import Any

from .journal import read_jsonl
from .simulator import QUOTE_MODES, quote_price_for_policy
from .timeutils import iso_now, parse_dt


FILL_MARKOUT_SECONDS = (30, 60, 120)


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


def _books_by_token(books: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for book in books:
        token_id = str(book.get("token_id") or "")
        if token_id:
            grouped[token_id].append(book)
    for rows in grouped.values():
        rows.sort(key=lambda row: parse_dt(row.get("timestamp")) or parse_dt("1970-01-01T00:00:00+00:00"))
    return grouped


def _books_by_event_id(books: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(book.get("event_id")): book for book in books if book.get("event_id")}


def _event_by_quote_id(rows: list[dict[str, Any]], row_type: str | None = None) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row_type and row.get("type") != row_type:
            continue
        quote_id = str(row.get("quote_id") or "")
        if quote_id and quote_id not in events:
            events[quote_id] = row
    return events


def _ticks_for_distance(distance: float | None, tick: float) -> int | None:
    if distance is None:
        return None
    if distance <= 0:
        return 0
    if tick <= 0:
        return None
    return max(0, int(math.ceil((distance - 1e-9) / tick)))


def _quote_distance(quote: dict[str, Any], book: dict[str, Any]) -> float | None:
    side = quote.get("side")
    price = quote.get("price")
    if price is None:
        return None
    if side == "bid":
        best_ask = book.get("best_ask")
        return None if best_ask is None else round(float(best_ask) - float(price), 6)
    if side == "ask":
        best_bid = book.get("best_bid")
        return None if best_bid is None else round(float(price) - float(best_bid), 6)
    return None


def _book_digest(book: dict[str, Any] | None, quote: dict[str, Any]) -> dict[str, Any] | None:
    if not book:
        return None
    tick = float(quote.get("tick_size") or book.get("tick_size") or 0.01)
    distance = _quote_distance(quote, book)
    return {
        "event_id": book.get("event_id"),
        "timestamp": book.get("timestamp"),
        "best_bid": book.get("best_bid"),
        "best_ask": book.get("best_ask"),
        "midpoint": book.get("midpoint"),
        "spread": book.get("spread"),
        "distance_to_fill": distance,
        "ticks_missed": _ticks_for_distance(distance, tick),
    }


def _closest_book(quote: dict[str, Any], books: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[tuple[float, dict[str, Any]]] = []
    for book in books:
        distance = _quote_distance(quote, book)
        if distance is None:
            continue
        candidates.append((distance, book))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _books_after_quote(
    quote: dict[str, Any],
    books: list[dict[str, Any]],
    source_book: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    quote_time = parse_dt(quote.get("timestamp"))
    if quote_time is None and source_book is not None:
        quote_time = parse_dt(source_book.get("timestamp"))
    source_event_id = quote.get("source_event_id")
    rows: list[dict[str, Any]] = []
    for book in books:
        if source_event_id and book.get("event_id") == source_event_id:
            continue
        book_time = parse_dt(book.get("timestamp"))
        if quote_time is not None and book_time is not None and book_time < quote_time:
            continue
        rows.append(book)
    return rows


def _quote_close_event(
    quote: dict[str, Any],
    fills_by_quote: dict[str, dict[str, Any]],
    cancels_by_quote: dict[str, dict[str, Any]],
) -> tuple[str, str | None, dict[str, Any] | None]:
    quote_id = str(quote.get("quote_id") or "")
    fill = fills_by_quote.get(quote_id)
    if fill:
        return "filled", fill.get("reason") or "simulated_fill", fill
    cancel = cancels_by_quote.get(quote_id)
    if cancel:
        return "cancelled", str(cancel.get("reason") or "cancelled"), cancel
    return "open", "open_at_replay_end", None


def _quote_lifecycle_row(
    quote: dict[str, Any],
    token_books: list[dict[str, Any]],
    source_book: dict[str, Any] | None,
    fills_by_quote: dict[str, dict[str, Any]],
    cancels_by_quote: dict[str, dict[str, Any]],
    *,
    assume_expiry_cancel: bool = False,
) -> dict[str, Any]:
    outcome, cancel_reason, close_event = _quote_close_event(quote, fills_by_quote, cancels_by_quote)
    quote_time = parse_dt(quote.get("timestamp"))
    if quote_time is None and source_book is not None:
        quote_time = parse_dt(source_book.get("timestamp"))
    expires_at = parse_dt(quote.get("expires_at"))
    close_time = parse_dt(close_event.get("timestamp")) if close_event else None
    if assume_expiry_cancel and outcome == "open" and expires_at is not None:
        outcome = "cancelled"
        cancel_reason = "quote_expired"
        close_time = expires_at
    lifetime_end = close_time or expires_at
    subsequent = _books_after_quote(quote, token_books, source_book)
    during_lifetime: list[dict[str, Any]] = []
    after_lifetime: list[dict[str, Any]] = []
    for book in subsequent:
        book_time = parse_dt(book.get("timestamp"))
        if lifetime_end is not None and book_time is not None and book_time <= lifetime_end:
            during_lifetime.append(book)
        elif lifetime_end is not None and book_time is not None and book_time > lifetime_end:
            after_lifetime.append(book)
        elif lifetime_end is None:
            during_lifetime.append(book)
    closest_during = _closest_book(quote, during_lifetime)
    closest_subsequent = _closest_book(quote, subsequent)
    closest_after = _closest_book(quote, after_lifetime)
    tick = float(quote.get("tick_size") or (source_book or {}).get("tick_size") or 0.01)
    during_distance = _quote_distance(quote, closest_during) if closest_during else None
    subsequent_distance = _quote_distance(quote, closest_subsequent) if closest_subsequent else None
    after_distance = _quote_distance(quote, closest_after) if closest_after else None
    would_fill_during = during_distance is not None and during_distance <= 0
    would_fill_after = after_distance is not None and after_distance <= 0
    placement_context = quote.get("placement_context")
    if not isinstance(placement_context, dict):
        placement_context = _book_digest(source_book, quote) or {
            "midpoint": quote.get("midpoint"),
            "spread": quote.get("spread"),
            "tick_size": tick,
            "source_event_id": quote.get("source_event_id"),
        }
    lifetime_seconds = None
    if quote_time and lifetime_end:
        lifetime_seconds = round((lifetime_end - quote_time).total_seconds(), 3)
    return {
        "quote_id": quote.get("quote_id"),
        "market_id": quote.get("market_id"),
        "token_id": quote.get("token_id"),
        "outcome": outcome,
        "side": quote.get("side"),
        "price": quote.get("price"),
        "size": quote.get("size"),
        "quote_mode": quote.get("quote_mode") or "unknown",
        "quote_expiry_seconds": quote.get("quote_expiry_seconds"),
        "placed_at": quote.get("timestamp") or (source_book or {}).get("timestamp"),
        "expires_at": quote.get("expires_at"),
        "closed_at": close_event.get("timestamp") if close_event else (expires_at.isoformat() if assume_expiry_cancel and expires_at else None),
        "cancel_reason": None if outcome == "filled" else cancel_reason,
        "fill_reason": cancel_reason if outcome == "filled" else None,
        "source_event_id": quote.get("source_event_id"),
        "close_event_id": close_event.get("evidence_event_id") if close_event else None,
        "placement_context": placement_context,
        "closest_during_lifetime": _book_digest(closest_during, quote),
        "closest_subsequent": _book_digest(closest_subsequent, quote),
        "ticks_missed": _ticks_for_distance(during_distance, tick),
        "best_subsequent_ticks_missed": _ticks_for_distance(subsequent_distance, tick),
        "would_fill_during_lifetime": would_fill_during,
        "would_have_filled_under_longer_expiry": bool(
            outcome != "filled" and cancel_reason == "quote_expired" and not would_fill_during and would_fill_after
        ),
        "quote_lifetime_seconds": lifetime_seconds,
    }


def _quote_lifecycle(
    quotes: list[dict[str, Any]],
    books: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped_books = _books_by_token(books)
    by_event = _books_by_event_id(books)
    fills_by_quote = _event_by_quote_id([row for row in fills if row.get("type") == "simulated_fill"])
    cancels_by_quote = _event_by_quote_id(risk_events, "quote_cancelled")
    rows: list[dict[str, Any]] = []
    for quote in quotes:
        if quote.get("type") != "virtual_quote":
            continue
        token_id = str(quote.get("token_id") or "")
        source_book = by_event.get(str(quote.get("source_event_id") or ""))
        rows.append(_quote_lifecycle_row(quote, grouped_books.get(token_id, []), source_book, fills_by_quote, cancels_by_quote))
    return rows


def _midpoint_range_ticks(books: list[dict[str, Any]], tick: float) -> float:
    mids = [float(book["midpoint"]) for book in books if book.get("midpoint") is not None]
    if len(mids) < 2 or tick <= 0:
        return 0.0
    return round((max(mids) - min(mids)) / tick, 6)


def _fill_opportunity_analysis(
    lifecycles: list[dict[str, Any]],
    books: list[dict[str, Any]],
    risk_events: list[dict[str, Any]],
    policy_comparison: dict[str, Any],
) -> dict[str, Any]:
    missed = {"1_tick": 0, "2_ticks": 0, "more": 0, "unknown": 0}
    by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for lifecycle in lifecycles:
        market_id = str(lifecycle.get("market_id") or "")
        if market_id:
            by_market[market_id].append(lifecycle)
        if lifecycle.get("outcome") == "filled":
            continue
        ticks = lifecycle.get("ticks_missed")
        if ticks is None:
            missed["unknown"] += 1
        elif ticks == 1:
            missed["1_tick"] += 1
        elif ticks == 2:
            missed["2_ticks"] += 1
        elif ticks > 2:
            missed["more"] += 1
    books_by_market_token: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for book in books:
        market_id = str(book.get("market_id") or "")
        token_id = str(book.get("token_id") or "")
        if market_id and token_id:
            books_by_market_token[market_id][token_id].append(book)
    useful: list[str] = []
    static: list[str] = []
    for market_id, rows in sorted(by_market.items()):
        token_books = books_by_market_token.get(market_id, {})
        movement_ticks = 0.0
        for token_rows in token_books.values():
            tick = float(next((row.get("tick_size") for row in token_rows if row.get("tick_size")), 0.01))
            movement_ticks = max(movement_ticks, _midpoint_range_ticks(token_rows, tick))
        best_ticks = [row.get("ticks_missed") for row in rows if row.get("ticks_missed") is not None]
        min_missed = min(best_ticks) if best_ticks else None
        closed_rows = [row for row in rows if row.get("outcome") != "open"]
        has_useful = any(row.get("outcome") == "filled" or row.get("would_have_filled_under_longer_expiry") for row in rows)
        if has_useful or (min_missed is not None and min_missed <= 2) or movement_ticks >= 2:
            useful.append(market_id)
        elif closed_rows and movement_ticks < 1:
            static.append(market_id)
    trade_evidence = next(
        (row for row in reversed(risk_events) if row.get("type") == "public_trade_evidence_status"),
        None,
    )
    return {
        "expired_quotes": sum(1 for row in lifecycles if row.get("cancel_reason") == "quote_expired"),
        "filled_quotes": sum(1 for row in lifecycles if row.get("outcome") == "filled"),
        "cancelled_quotes": sum(1 for row in lifecycles if row.get("outcome") == "cancelled"),
        "open_quotes": sum(1 for row in lifecycles if row.get("outcome") == "open"),
        "missed_ticks": missed,
        "would_have_filled_under_longer_expiry": sum(1 for row in lifecycles if row.get("would_have_filled_under_longer_expiry")),
        "markets_with_useful_book_movement": useful,
        "markets_too_static": static,
        "quote_policy_assessments": {
            mode: values.get("assessment") for mode, values in policy_comparison.get("modes", {}).items()
        },
        "evidence_model": trade_evidence
        or {
            "type": "public_trade_evidence_status",
            "status": "book_move_only",
            "reason": "public_trade_tape_not_recorded_in_this_run",
        },
    }


def _synthetic_quote_for_mode(quote: dict[str, Any], source_book: dict[str, Any], mode: str) -> dict[str, Any] | None:
    side = str(quote.get("side") or "bid")
    price = quote_price_for_policy(source_book, side=side, mode=mode)
    if price is None:
        return None
    synthetic = dict(quote)
    synthetic["quote_id"] = f"{quote.get('quote_id')}:{mode}:replay"
    synthetic["price"] = price
    synthetic["quote_mode"] = mode
    synthetic["timestamp"] = quote.get("timestamp") or source_book.get("timestamp")
    if not synthetic.get("expires_at"):
        placed = parse_dt(synthetic.get("timestamp"))
        expiry = float(synthetic.get("quote_expiry_seconds") or 30)
        if placed:
            synthetic["expires_at"] = (placed + timedelta(seconds=expiry)).isoformat()
    return synthetic


def _policy_assessment(quote_count: int, plausible: int, adverse: int, avg_ticks: float | None) -> str:
    if quote_count == 0:
        return "no comparable quote evidence"
    if plausible == 0 and avg_ticks is not None and avg_ticks > 2:
        return "looked too passive on this evidence"
    if plausible > 0 and adverse / plausible >= 0.5:
        return "looked more aggressive; inspect adverse-selection evidence"
    return "inconclusive or balanced on this evidence"


def _policy_comparison(quotes: list[dict[str, Any]], books: list[dict[str, Any]]) -> dict[str, Any]:
    grouped_books = _books_by_token(books)
    by_event = _books_by_event_id(books)
    modes: dict[str, dict[str, Any]] = {}
    for mode in QUOTE_MODES:
        lifecycles: list[dict[str, Any]] = []
        for quote in quotes:
            if quote.get("type") != "virtual_quote":
                continue
            source_book = by_event.get(str(quote.get("source_event_id") or ""))
            if not source_book:
                continue
            synthetic = _synthetic_quote_for_mode(quote, source_book, mode)
            if synthetic is None:
                continue
            token_id = str(synthetic.get("token_id") or "")
            lifecycles.append(
                _quote_lifecycle_row(
                    synthetic,
                    grouped_books.get(token_id, []),
                    source_book,
                    {},
                    {},
                    assume_expiry_cancel=True,
                )
            )
        tick_values = [row.get("ticks_missed") for row in lifecycles if row.get("ticks_missed") is not None]
        lifetimes = [
            float(row["quote_lifetime_seconds"])
            for row in lifecycles
            if row.get("quote_lifetime_seconds") is not None
        ]
        plausible = sum(1 for row in lifecycles if row.get("would_fill_during_lifetime"))
        adverse = 0
        for row in lifecycles:
            closest = row.get("closest_during_lifetime")
            if not isinstance(closest, dict) or closest.get("ticks_missed") != 0:
                continue
            price = float(row.get("price") or 0.0)
            tick = float((row.get("placement_context") or {}).get("tick_size") or 0.01)
            midpoint = closest.get("midpoint")
            if midpoint is None:
                continue
            if row.get("side") == "bid" and float(midpoint) <= price - tick:
                adverse += 1
            if row.get("side") == "ask" and float(midpoint) >= price + tick:
                adverse += 1
        avg_ticks = round(sum(float(value) for value in tick_values) / len(tick_values), 3) if tick_values else None
        modes[mode] = {
            "quote_count": len(lifecycles),
            "plausible_fill_count": plausible,
            "post_expiry_fill_count": sum(1 for row in lifecycles if row.get("would_have_filled_under_longer_expiry")),
            "avg_ticks_missed": avg_ticks,
            "avg_lifetime_seconds": round(sum(lifetimes) / len(lifetimes), 3) if lifetimes else None,
            "adverse_selection_risk_count": adverse,
            "assessment": _policy_assessment(len(lifecycles), plausible, adverse, avg_ticks),
        }
    return {
        "basis": "replayed from actual quote placement book events; no profitability claim",
        "modes": modes,
    }


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_book_at_or_after(books: list[dict[str, Any]], target) -> dict[str, Any] | None:
    for book in books:
        timestamp = parse_dt(book.get("timestamp"))
        if timestamp is not None and timestamp >= target and book.get("midpoint") is not None:
            return book
    return None


def _tick_size_for_fill(
    fill: dict[str, Any],
    by_event: dict[str, dict[str, Any]],
    token_books: list[dict[str, Any]],
) -> float:
    evidence = by_event.get(str(fill.get("evidence_event_id") or ""))
    tick = _float_or_none(fill.get("tick_size"))
    if tick is None and evidence is not None:
        tick = _float_or_none(evidence.get("tick_size"))
    if tick is None:
        tick = next((_float_or_none(book.get("tick_size")) for book in token_books if _float_or_none(book.get("tick_size"))), None)
    return tick or 0.01


def _fill_markout_rows(fills: list[dict[str, Any]], books: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped_books = _books_by_token(books)
    by_event = _books_by_event_id(books)
    rows: list[dict[str, Any]] = []
    for fill in fills:
        if fill.get("type") != "simulated_fill":
            continue
        token_id = str(fill.get("token_id") or "")
        token_books = grouped_books.get(token_id, [])
        fill_time = parse_dt(fill.get("timestamp"))
        price = _float_or_none(fill.get("price"))
        tick = _tick_size_for_fill(fill, by_event, token_books)
        horizons: dict[str, dict[str, Any]] = {}
        for seconds in FILL_MARKOUT_SECONDS:
            key = f"{seconds}s"
            mark_book = _first_book_at_or_after(token_books, fill_time + timedelta(seconds=seconds)) if fill_time else None
            midpoint = _float_or_none(mark_book.get("midpoint")) if mark_book else None
            markout = None
            if midpoint is not None and price is not None:
                if fill.get("side") == "ask":
                    markout = round(price - midpoint, 6)
                else:
                    markout = round(midpoint - price, 6)
            horizons[key] = {
                "markout": markout,
                "event_id": mark_book.get("event_id") if mark_book else None,
                "timestamp": mark_book.get("timestamp") if mark_book else None,
                "midpoint": midpoint,
            }
        rows.append(
            {
                "quote_id": fill.get("quote_id"),
                "market_id": fill.get("market_id"),
                "token_id": fill.get("token_id"),
                "side": fill.get("side"),
                "price": fill.get("price"),
                "size": fill.get("size"),
                "timestamp": fill.get("timestamp"),
                "tick_size": tick,
                "horizons": horizons,
                "adverse_selection_flag": any(
                    values.get("markout") is not None and float(values["markout"]) < -1 * tick
                    for values in horizons.values()
                ),
            }
        )
    return rows


def _fill_quality_from_markouts(markouts: list[dict[str, Any]]) -> dict[str, Any]:
    horizon_stats: dict[str, dict[str, Any]] = {}
    missing = 0
    for seconds in FILL_MARKOUT_SECONDS:
        key = f"{seconds}s"
        samples: list[float] = []
        adverse = 0
        for row in markouts:
            values = (row.get("horizons") or {}).get(key) or {}
            markout = values.get("markout")
            if markout is None:
                missing += 1
                continue
            markout_value = float(markout)
            samples.append(markout_value)
            if markout_value < -1 * float(row.get("tick_size") or 0.01):
                adverse += 1
        horizon_stats[key] = {
            "average_markout": round(sum(samples) / len(samples), 6) if samples else 0.0,
            "adverse_count": adverse,
            "sample_count": len(samples),
        }
    return {
        "fills_analyzed": len(markouts),
        "adverse_selection_flags": sum(1 for row in markouts if row.get("adverse_selection_flag")),
        "missing_markouts": missing,
        "horizons": horizon_stats,
    }


def _configured_market_fill_cap(risk_events: list[dict[str, Any]]) -> int:
    for event in reversed(risk_events):
        if event.get("type") != "run_started":
            continue
        cap = event.get("max_fills_per_market")
        if isinstance(cap, int):
            return cap
        try:
            return int(cap)
        except (TypeError, ValueError):
            return 8
    return 8


def _average_missed_ticks(markouts: list[dict[str, Any]]) -> float | None:
    missed_ticks: list[float] = []
    for row in markouts:
        tick = float(row.get("tick_size") or 0.01)
        if tick <= 0:
            continue
        for values in (row.get("horizons") or {}).values():
            markout = values.get("markout") if isinstance(values, dict) else None
            if markout is None:
                continue
            missed_ticks.append(max(0.0, -1 * float(markout) / tick))
    if not missed_ticks:
        return None
    return round(sum(missed_ticks) / len(missed_ticks), 3)


def _market_suitability(
    watched_markets: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    fills: list[dict[str, Any]],
    fill_markouts: list[dict[str, Any]],
    quote_lifecycle: list[dict[str, Any]],
    fill_opportunity: dict[str, Any],
    risk_events: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    quote_counts = Counter(str(row.get("market_id")) for row in quotes if row.get("market_id"))
    fill_counts = Counter(str(row.get("market_id")) for row in fills if row.get("market_id"))
    expired_counts = Counter(
        str(row.get("market_id"))
        for row in quote_lifecycle
        if row.get("market_id") and row.get("cancel_reason") == "quote_expired"
    )
    markouts_by_market: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fill_markouts:
        market_id = str(row.get("market_id") or "")
        if market_id:
            markouts_by_market[market_id].append(row)
    total_fills = sum(fill_counts.values())
    static_markets = set(fill_opportunity.get("markets_too_static") or [])
    market_cap = _configured_market_fill_cap(risk_events)
    rows: list[dict[str, Any]] = []
    for market in watched_markets:
        market_id = str(market.get("market_id") or "")
        quote_count = quote_counts[market_id]
        fill_count = fill_counts[market_id]
        fill_share = round(fill_count / total_fills, 6) if total_fills else 0.0
        market_markouts = markouts_by_market.get(market_id, [])
        adverse_flags = sum(1 for row in market_markouts if row.get("adverse_selection_flag"))
        if quote_count < 20:
            classification = "insufficient_evidence"
            reason = "fewer_than_20_quotes"
        elif fill_share > 0.35:
            classification = "risky_concentrated"
            reason = "fill_share_above_35_percent"
        elif fill_count > market_cap:
            classification = "risky_concentrated"
            reason = "fill_count_above_market_cap"
        elif fill_count > 0 and adverse_flags >= fill_count / 2:
            classification = "too_adverse"
            reason = "adverse_selection_flags_at_least_half_of_fills"
        elif market_id in static_markets:
            classification = "too_static"
            reason = "static_book_movement"
        else:
            classification = "candidate"
            reason = "balanced_fill_activity"
        rows.append(
            {
                "market_id": market_id,
                "quote_count": quote_count,
                "fill_count": fill_count,
                "fill_share": fill_share,
                "adverse_selection_flags": adverse_flags,
                "avg_ticks_missed": _average_missed_ticks(market_markouts),
                "expired_quotes": expired_counts[market_id],
                "classification": classification,
                "reason": reason,
            }
        )
    return rows


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
    quote_lifecycle = _quote_lifecycle(quotes, books, fills, risk_events)
    policy_comparison = _policy_comparison(quotes, books)
    fill_opportunity = _fill_opportunity_analysis(quote_lifecycle, books, risk_events, policy_comparison)
    fill_markouts = _fill_markout_rows(fill_rows, books)
    fill_quality = _fill_quality_from_markouts(fill_markouts)
    market_suitability = _market_suitability(
        watched_markets,
        quotes,
        fill_rows,
        fill_markouts,
        quote_lifecycle,
        fill_opportunity,
        risk_events,
    )
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
        "quote_lifecycle": quote_lifecycle,
        "fill_opportunity": fill_opportunity,
        "fill_quality": fill_quality,
        "market_suitability": market_suitability,
        "policy_comparison": policy_comparison,
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
    opportunity = state.get("fill_opportunity", {})
    quality = state.get("fill_quality", {})
    comparison = state.get("policy_comparison", {})
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
    lines.extend(["", "## Fill Opportunity Analysis", ""])
    missed = opportunity.get("missed_ticks") or {}
    lines.append(f"- Expired quotes: {opportunity.get('expired_quotes', 0)}")
    lines.append(f"- Filled quotes: {opportunity.get('filled_quotes', 0)}")
    lines.append(f"- Cancelled quotes: {opportunity.get('cancelled_quotes', 0)}")
    lines.append(f"- Missed by 1 tick: {missed.get('1_tick', 0)}")
    lines.append(f"- Missed by 2 ticks: {missed.get('2_ticks', 0)}")
    lines.append(f"- Missed by more: {missed.get('more', 0)}")
    lines.append(f"- Would have filled under longer expiry: {opportunity.get('would_have_filled_under_longer_expiry', 0)}")
    useful = opportunity.get("markets_with_useful_book_movement") or []
    static = opportunity.get("markets_too_static") or []
    lines.append(f"- Markets with useful book movement: {', '.join(useful) if useful else 'none'}")
    lines.append(f"- Markets too static: {', '.join(static) if static else 'none'}")
    evidence_model = opportunity.get("evidence_model") or {}
    lines.append(
        "- Fill evidence model: "
        f"{evidence_model.get('status', 'unknown')} ({evidence_model.get('reason', 'no reason recorded')})"
    )
    horizons = quality.get("horizons") or {}
    lines.extend(["", "## Fill Quality", ""])
    lines.append(f"- Fills analyzed: `{quality.get('fills_analyzed', 0)}`")
    lines.append(f"- Adverse-selection flags: `{quality.get('adverse_selection_flags', 0)}`")
    lines.append(f"- Missing markouts: `{quality.get('missing_markouts', 0)}`")
    lines.append(f"- 30s average markout: `{(horizons.get('30s') or {}).get('average_markout', 0.0)}`")
    lines.append(f"- 60s average markout: `{(horizons.get('60s') or {}).get('average_markout', 0.0)}`")
    lines.append(f"- 120s average markout: `{(horizons.get('120s') or {}).get('average_markout', 0.0)}`")
    lines.extend(["", "## Market Suitability", ""])
    suitability = state.get("market_suitability") or []
    if suitability:
        for row in suitability:
            lines.append(
                "- "
                f"{row.get('market_id')}: classification={row.get('classification')}, "
                f"fills={row.get('fill_count')}, "
                f"fill_share={row.get('fill_share')}, "
                f"adverse_flags={row.get('adverse_selection_flags')}, "
                f"reason={row.get('reason')}"
            )
    else:
        lines.append("- No watched markets.")
    lines.extend(["", "## Policy Comparison", ""])
    lines.append(f"- Basis: {comparison.get('basis', 'not enough quote placement evidence')}")
    modes = comparison.get("modes") or {}
    if modes:
        for mode, values in sorted(modes.items()):
            lines.append(
                "- "
                f"{mode}: plausible_fills={values.get('plausible_fill_count', 0)}, "
                f"longer_expiry_fills={values.get('post_expiry_fill_count', 0)}, "
                f"avg_ticks_missed={values.get('avg_ticks_missed')}, "
                f"avg_lifetime_seconds={values.get('avg_lifetime_seconds')}, "
                f"adverse_selection_flags={values.get('adverse_selection_risk_count', 0)}, "
                f"assessment={values.get('assessment')}"
            )
    else:
        lines.append("- No comparable quote policies.")
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
