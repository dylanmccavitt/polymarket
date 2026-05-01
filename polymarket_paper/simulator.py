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


QUOTE_MODES = ("best_bid", "one_tick_inside", "midpoint_when_spread_allows")


def quote_price_for_policy(snapshot: dict[str, Any], *, side: str, mode: str) -> float | None:
    if mode not in QUOTE_MODES:
        raise ValueError(f"unknown quote mode: {mode}")
    bid = snapshot.get("best_bid")
    ask = snapshot.get("best_ask")
    midpoint = snapshot.get("midpoint")
    tick = float(snapshot.get("tick_size") or 0.01)
    if bid is None or ask is None or midpoint is None:
        return None
    best_bid = float(bid)
    best_ask = float(ask)
    mid = float(midpoint)
    if side == "bid":
        if mode == "best_bid":
            return best_bid
        if mode == "midpoint_when_spread_allows":
            candidate = _round_tick(mid, tick)
            if best_bid < candidate < best_ask:
                return candidate
        candidate = _round_tick(min(best_ask - tick, best_bid + tick), tick)
        return candidate if best_bid < candidate < best_ask else best_bid
    if side == "ask":
        if mode == "best_bid":
            return best_ask
        if mode == "midpoint_when_spread_allows":
            candidate = _round_tick(mid, tick)
            if best_bid < candidate < best_ask:
                return candidate
        candidate = _round_tick(max(best_bid + tick, best_ask - tick), tick)
        return candidate if best_bid < candidate < best_ask else best_ask
    raise ValueError(f"unknown quote side: {side}")


def _placement_context(snapshot: dict[str, Any], *, side: str, price: float, mode: str) -> dict[str, Any]:
    tick = float(snapshot.get("tick_size") or 0.01)
    bid = snapshot.get("best_bid")
    ask = snapshot.get("best_ask")
    spread = snapshot.get("spread")
    context: dict[str, Any] = {
        "quote_mode": mode,
        "best_bid": bid,
        "best_ask": ask,
        "best_bid_size": snapshot.get("best_bid_size"),
        "best_ask_size": snapshot.get("best_ask_size"),
        "midpoint": snapshot.get("midpoint"),
        "spread": spread,
        "tick_size": tick,
        "source_event_id": snapshot.get("event_id"),
    }
    if spread is not None:
        context["spread_ticks"] = round(float(spread) / tick, 6) if tick else None
    if side == "bid" and bid is not None:
        context["placement_distance_from_bid_ticks"] = round((price - float(bid)) / tick, 6) if tick else None
    if side == "ask" and ask is not None:
        context["placement_distance_from_ask_ticks"] = round((float(ask) - price) / tick, 6) if tick else None
    return context


@dataclass
class PaperSimulator:
    risk: RiskState
    quote_size: float
    quote_mode: str = "one_tick_inside"
    quote_expiry_seconds: int = QUOTE_EXPIRY_SECONDS
    min_exit_profit_ticks: int = 1
    active_quotes: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.quote_mode not in QUOTE_MODES:
            raise ValueError(f"unknown quote mode: {self.quote_mode}")
        if self.quote_expiry_seconds <= 0:
            raise ValueError("quote_expiry_seconds must be positive")
        if self.min_exit_profit_ticks < 0:
            raise ValueError("min_exit_profit_ticks must be nonnegative")

    def _exit_context(self, snapshot: dict[str, Any], *, ask_price: float, held: float) -> dict[str, Any] | None:
        market_id = str(snapshot["market_id"])
        token_id = str(snapshot["token_id"])
        tick = float(snapshot.get("tick_size") or 0.01)
        average_entry = self.risk.average_entry_price(market_id, token_id)
        if average_entry is None:
            return None
        min_exit_price = round(average_entry + self.min_exit_profit_ticks * tick, 6)
        if ask_price < min_exit_price:
            return None
        return {
            "average_entry_price": average_entry,
            "min_exit_price": min_exit_price,
            "min_exit_profit_ticks": self.min_exit_profit_ticks,
            "available_inventory": round(held, 6),
            "expected_profit_per_share": round(ask_price - average_entry, 6),
        }

    def _can_place_exit_quote(self, snapshot: dict[str, Any], *, now) -> bool:
        decision = self.risk.can_quote(snapshot, price=0.0, size=0.0, now=now)
        return decision.allowed or decision.reason in {"market_exposure_cap", "total_exposure_cap"}

    def generate_quotes(self, snapshot: dict[str, Any], *, now=None) -> list[dict[str, Any]]:
        current = now or utc_now()
        bid = snapshot.get("best_bid")
        ask = snapshot.get("best_ask")
        midpoint = snapshot.get("midpoint")
        spread = snapshot.get("spread")
        tick = float(snapshot.get("tick_size") or 0.01)
        if bid is None or ask is None or midpoint is None or spread is None:
            return []
        quotes: list[dict[str, Any]] = []
        price = quote_price_for_policy(snapshot, side="bid", mode=self.quote_mode)
        size = max(self.quote_size, float(snapshot.get("min_order_size") or self.quote_size))
        if price is not None and price > 0 and price < float(ask):
            decision = self.risk.can_quote(snapshot, price=price, size=size, now=current)
            if decision.allowed:
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
                    "quote_mode": self.quote_mode,
                    "quote_expiry_seconds": self.quote_expiry_seconds,
                    "reason": f"paper_maker_bid_{self.quote_mode}",
                    "expires_at": (current + timedelta(seconds=self.quote_expiry_seconds)).isoformat(),
                    "placement_context": _placement_context(snapshot, side="bid", price=price, mode=self.quote_mode),
                    "risk": decision.details,
                    "source_event_id": snapshot["event_id"],
                }
                self.active_quotes[quote_id] = quote
                quotes.append(quote)
        held = self.risk.shares(str(snapshot["market_id"]), str(snapshot["token_id"]))
        if held > 0 and self._can_place_exit_quote(snapshot, now=current):
            ask_price = quote_price_for_policy(snapshot, side="ask", mode=self.quote_mode)
            if ask_price is None or ask_price <= float(bid):
                ask_price = float(ask)
            ask_size = min(size, held)
            exit_context = self._exit_context(snapshot, ask_price=ask_price, held=held)
            if exit_context is not None:
                ask_id = f"quote:{snapshot['event_id']}:ask"
                ask_quote = {
                    "type": "virtual_quote",
                    "quote_id": ask_id,
                    "timestamp": current.isoformat(),
                    "market_id": snapshot["market_id"],
                    "token_id": snapshot["token_id"],
                    "outcome": snapshot.get("outcome"),
                    "side": "ask",
                    "price": ask_price,
                    "size": ask_size,
                    "midpoint": midpoint,
                    "spread": spread,
                    "tick_size": tick,
                    "quote_mode": self.quote_mode,
                    "quote_expiry_seconds": self.quote_expiry_seconds,
                    "reason": f"paper_maker_inventory_exit_{self.quote_mode}",
                    "expires_at": (current + timedelta(seconds=self.quote_expiry_seconds)).isoformat(),
                    "placement_context": _placement_context(snapshot, side="ask", price=ask_price, mode=self.quote_mode),
                    "exit_context": exit_context,
                    "source_event_id": snapshot["event_id"],
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
                        "quote_mode": quote.get("quote_mode"),
                        "expires_at": quote.get("expires_at"),
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
                "exit_context": quote.get("exit_context"),
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
            "exit_context": quote.get("exit_context"),
            "exposure_after": exposure,
        }


def is_quote_expired(quote: dict[str, Any], *, now=None) -> bool:
    current = now or utc_now()
    expires_at = parse_dt(quote.get("expires_at"))
    return bool(expires_at and current >= expires_at)
