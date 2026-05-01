from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .timeutils import iso, parse_millis, utc_now


GAMMA_MARKETS_URL = "https://gamma-api.polymarket.com/markets"
CLOB_BOOK_URL = "https://clob.polymarket.com/book"


class AdapterError(RuntimeError):
    pass


def _get_json(url: str, *, timeout: float = 10.0, retries: int = 2) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        request = Request(url, headers={"User-Agent": "polymarket-paper/0.1 read-only"})
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
            return json.loads(body)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(0.5 * (attempt + 1))
    raise AdapterError(f"read-only request failed: {url}: {last_error}")


def fetch_gamma_markets(limit: int) -> list[dict[str, Any]]:
    params = {
        "active": "true",
        "closed": "false",
        "order": "volume24hr",
        "ascending": "false",
        "limit": str(limit),
    }
    payload = _get_json(f"{GAMMA_MARKETS_URL}?{urlencode(params)}")
    if not isinstance(payload, list):
        raise AdapterError("Gamma markets response was not a list")
    return [item for item in payload if isinstance(item, dict)]


def _book_side(levels: object, *, side: str) -> tuple[float | None, float | None]:
    if not isinstance(levels, list):
        return None, None
    parsed: list[tuple[float, float]] = []
    for level in levels:
        if not isinstance(level, dict):
            continue
        try:
            parsed.append((float(level["price"]), float(level.get("size", 0))))
        except (KeyError, TypeError, ValueError):
            continue
    if not parsed:
        return None, None
    price, size = max(parsed, key=lambda item: item[0]) if side == "bid" else min(parsed, key=lambda item: item[0])
    return price, size


@dataclass(frozen=True)
class BookSnapshot:
    event_id: str
    timestamp: str
    market_id: str
    token_id: str
    outcome: str
    best_bid: float | None
    best_bid_size: float | None
    best_ask: float | None
    best_ask_size: float | None
    midpoint: float | None
    spread: float | None
    tick_size: float | None
    min_order_size: float | None
    source: str
    raw: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "type": "book_snapshot",
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "market_id": self.market_id,
            "token_id": self.token_id,
            "outcome": self.outcome,
            "best_bid": self.best_bid,
            "best_bid_size": self.best_bid_size,
            "best_ask": self.best_ask,
            "best_ask_size": self.best_ask_size,
            "midpoint": self.midpoint,
            "spread": self.spread,
            "tick_size": self.tick_size,
            "min_order_size": self.min_order_size,
            "source": self.source,
            "raw": self.raw,
        }


def fetch_book_snapshot(
    *,
    token_id: str,
    market_id: str,
    outcome: str,
    timeout: float = 10.0,
) -> BookSnapshot:
    payload = _get_json(f"{CLOB_BOOK_URL}?{urlencode({'token_id': token_id})}", timeout=timeout)
    if not isinstance(payload, dict):
        raise AdapterError("CLOB book response was not an object")
    best_bid, best_bid_size = _book_side(payload.get("bids"), side="bid")
    best_ask, best_ask_size = _book_side(payload.get("asks"), side="ask")
    midpoint = None
    spread = None
    if best_bid is not None and best_ask is not None:
        midpoint = round((best_bid + best_ask) / 2, 6)
        spread = round(best_ask - best_bid, 6)
    timestamp = iso(parse_millis(payload.get("timestamp"))) or utc_now().isoformat()
    event_id = f"book:{token_id}:{payload.get('timestamp') or int(time.time() * 1000)}:{payload.get('hash') or 'nohash'}"
    return BookSnapshot(
        event_id=event_id,
        timestamp=timestamp,
        market_id=market_id,
        token_id=token_id,
        outcome=outcome,
        best_bid=best_bid,
        best_bid_size=best_bid_size,
        best_ask=best_ask,
        best_ask_size=best_ask_size,
        midpoint=midpoint,
        spread=spread,
        tick_size=float(payload["tick_size"]) if payload.get("tick_size") is not None else None,
        min_order_size=float(payload["min_order_size"]) if payload.get("min_order_size") is not None else None,
        source="clob_polling",
        raw=payload,
    )
