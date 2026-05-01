from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from .risk import QUOTE_EXPIRY_SECONDS, RiskState, quote_should_cancel
from .timeutils import parse_dt, utc_now


def _round_tick(value: float, tick: float) -> float:
    if tick <= 0:
        return round(value, 6)
    ticks = round(value / tick)
    return round(ticks * tick, 6)


@dataclass
class PaperSimulator:
    risk: RiskState
    quote_size: float
    active_quotes: dict[str, dict[str, Any]] = field(default_factory=dict)

    def generate_quotes(self, snapshot: dict[str, Any], *, now=None) -> list[dict[str, Any]]:
        current = now or utc_now()
        bid = snapshot.get("best_bid")
        ask = snapshot.get("best_ask")
        midpoint = snapshot.get("midpoint")
        spread = snapshot.get("spread")
        tick = float(snapshot.get("tick_size") or 0.01)
        if bid is None or ask is None or midpoint is None or spread is None:
            return []
        price = _round_tick(min(float(ask) - tick, float(bid) + tick), tick)
        if price <= 0 or price >= float(ask):
            price = float(bid)
        size = max(self.quote_size, float(snapshot.get("min_order_size") or self.quote_size))
        decision = self.risk.can_quote(snapshot, price=price, size=size, now=current)
        if not decision.allowed:
            return []
        quote_id = f"quote:{snapshot['event_id']}:bid"
        quote = {
            "type": "virtual_quote",
            "quote_id": quote_id,
            "timestamp": current.isoformat(),
            "market_id": snapshot["market_id"],
            "token_id": snapshot["token_id"],
            "outcome": snapshot.get("outcome"),
            "side": "bid",
            "price": price,
            "size": size,
            "midpoint": midpoint,
            "spread": spread,
            "tick_size": tick,
            "reason": "paper_maker_bid_inside_or_at_touch",
            "expires_at": (current + timedelta(seconds=QUOTE_EXPIRY_SECONDS)).isoformat(),
            "risk": decision.details,
            "source_event_id": snapshot["event_id"],
        }
        self.active_quotes[quote_id] = quote
        quotes = [quote]
        held = self.risk.shares(str(snapshot["market_id"]), str(snapshot["token_id"]))
        if held > 0:
            ask_price = _round_tick(max(float(bid) + tick, float(ask) - tick), tick)
            if ask_price <= float(bid):
                ask_price = float(ask)
            ask_size = min(size, held)
            ask_id = f"quote:{snapshot['event_id']}:ask"
            ask_quote = {
                **quote,
                "quote_id": ask_id,
                "side": "ask",
                "price": ask_price,
                "size": ask_size,
                "reason": "paper_maker_inventory_ask_inside_or_at_touch",
            }
            self.active_quotes[ask_id] = ask_quote
            quotes.append(ask_quote)
        return quotes

    def process_snapshot(self, snapshot: dict[str, Any], *, now=None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        current = now or utc_now()
        fills: list[dict[str, Any]] = []
        risk_events: list[dict[str, Any]] = []
        for quote_id, quote in list(self.active_quotes.items()):
            if quote.get("market_id") != snapshot.get("market_id") or quote.get("token_id") != snapshot.get("token_id"):
                continue
            cancel = quote_should_cancel(quote, snapshot, now=current)
            if cancel.allowed:
                risk_events.append(
                    {
                        "type": "quote_cancelled",
                        "timestamp": current.isoformat(),
                        "quote_id": quote_id,
                        "market_id": quote["market_id"],
                        "token_id": quote["token_id"],
                        "reason": cancel.reason,
                        "details": cancel.details,
                        "evidence_event_id": snapshot.get("event_id"),
                    }
                )
                self.active_quotes.pop(quote_id, None)
                continue
            fill = self._try_fill(quote, snapshot, now=current)
            if fill is None:
                continue
            fills.append(fill)
            self.active_quotes.pop(quote_id, None)
        return fills, risk_events

    def _try_fill(self, quote: dict[str, Any], snapshot: dict[str, Any], *, now) -> dict[str, Any] | None:
        side = quote["side"]
        evidence_reason: str | None = None
        if side == "bid":
            best_ask = snapshot.get("best_ask")
            if best_ask is not None and float(best_ask) <= float(quote["price"]):
                evidence_reason = "book_ask_traded_through_bid"
            else:
                return None
            decision = self.risk.can_fill_bid(
                str(quote["market_id"]),
                str(quote["token_id"]),
                float(quote["price"]),
                float(quote["size"]),
            )
        else:
            best_bid = snapshot.get("best_bid")
            if best_bid is not None and float(best_bid) >= float(quote["price"]):
                evidence_reason = "book_bid_traded_through_ask"
            else:
                return None
            decision = self.risk.can_fill_ask(str(quote["market_id"]), str(quote["token_id"]), float(quote["size"]))
        if not decision.allowed:
            return {
                "type": "fill_denied",
                "timestamp": now.isoformat(),
                "quote_id": quote["quote_id"],
                "market_id": quote["market_id"],
                "token_id": quote["token_id"],
                "side": side,
                "price": quote["price"],
                "size": quote["size"],
                "reason": decision.reason,
                "details": decision.details,
                "evidence_event_id": snapshot.get("event_id"),
            }
        exposure = self.risk.record_fill(
            str(quote["market_id"]),
            str(quote["token_id"]),
            side,
            float(quote["price"]),
            float(quote["size"]),
        )
        return {
            "type": "simulated_fill",
            "timestamp": now.isoformat(),
            "quote_id": quote["quote_id"],
            "market_id": quote["market_id"],
            "token_id": quote["token_id"],
            "outcome": quote.get("outcome"),
            "side": side,
            "price": quote["price"],
            "size": quote["size"],
            "reason": evidence_reason,
            "evidence_event_id": snapshot.get("event_id"),
            "source_quote_event_id": quote.get("source_event_id"),
            "exposure_after": exposure,
        }


def is_quote_expired(quote: dict[str, Any], *, now=None) -> bool:
    current = now or utc_now()
    expires_at = parse_dt(quote.get("expires_at"))
    return bool(expires_at and current >= expires_at)
