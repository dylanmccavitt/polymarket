from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .timeutils import parse_dt, utc_now


QUOTE_EXPIRY_SECONDS = 30
STALE_SECONDS = 20
MAX_CANCEL_SPREAD = 0.05
MAX_MIDPOINT_MOVE_TICKS = 2


@dataclass(frozen=True)
class RiskDecision:
    allowed: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskState:
    max_total_exposure: float
    max_market_exposure: float = 25.0
    max_market_fills: int = 8
    max_token_fills: int = 4
    positions: dict[str, float] = field(default_factory=dict)
    cash_by_token: dict[str, float] = field(default_factory=dict)
    fill_counts_by_market: dict[str, int] = field(default_factory=dict)
    fill_counts_by_token: dict[str, int] = field(default_factory=dict)

    def token_key(self, market_id: str, token_id: str) -> str:
        return f"{market_id}:{token_id}"

    def market_exposure(self, market_id: str) -> float:
        prefix = f"{market_id}:"
        return sum(abs(value) for key, value in self.cash_by_token.items() if key.startswith(prefix))

    def total_exposure(self) -> float:
        return sum(abs(value) for value in self.cash_by_token.values())

    def shares(self, market_id: str, token_id: str) -> float:
        return self.positions.get(self.token_key(market_id, token_id), 0.0)

    def can_add_exposure(self, market_id: str, token_id: str, notional: float) -> RiskDecision:
        if notional < 0:
            return RiskDecision(False, "invalid_negative_notional")
        market_after = self.market_exposure(market_id) + notional
        total_after = self.total_exposure() + notional
        if market_after > self.max_market_exposure:
            return RiskDecision(
                False,
                "market_exposure_cap",
                {"market_after": round(market_after, 6), "cap": self.max_market_exposure},
            )
        if total_after > self.max_total_exposure:
            return RiskDecision(
                False,
                "total_exposure_cap",
                {"total_after": round(total_after, 6), "cap": self.max_total_exposure},
            )
        return RiskDecision(True, "allowed", {"market_after": market_after, "total_after": total_after})

    def can_add_fill_count(self, market_id: str, token_id: str) -> RiskDecision:
        market_count = self.fill_counts_by_market.get(market_id, 0)
        token_key = self.token_key(market_id, token_id)
        token_count = self.fill_counts_by_token.get(token_key, 0)
        if market_count >= self.max_market_fills:
            return RiskDecision(
                False,
                "market_fill_cap",
                {"market_count": market_count, "cap": self.max_market_fills},
            )
        if token_count >= self.max_token_fills:
            return RiskDecision(
                False,
                "token_fill_cap",
                {"token_count": token_count, "cap": self.max_token_fills},
            )
        return RiskDecision(
            True,
            "allowed",
            {"market_count_after": market_count + 1, "token_count_after": token_count + 1},
        )

    def can_quote(self, snapshot: dict[str, Any], *, price: float, size: float, now: datetime | None = None) -> RiskDecision:
        current = now or utc_now()
        event_time = parse_dt(snapshot.get("timestamp"))
        if event_time is None:
            return RiskDecision(False, "missing_book_timestamp")
        age = (current - event_time).total_seconds()
        if age > STALE_SECONDS:
            return RiskDecision(False, "stale_feed", {"age_seconds": round(age, 3), "cap_seconds": STALE_SECONDS})
        if snapshot.get("spread") is None:
            return RiskDecision(False, "missing_spread")
        if float(snapshot["spread"]) > MAX_CANCEL_SPREAD:
            return RiskDecision(False, "spread_too_wide", {"spread": snapshot["spread"]})
        return self.can_add_exposure(str(snapshot["market_id"]), str(snapshot["token_id"]), price * size)

    def can_fill_bid(self, market_id: str, token_id: str, price: float, size: float) -> RiskDecision:
        fill_count = self.can_add_fill_count(market_id, token_id)
        if not fill_count.allowed:
            return fill_count
        return self.can_add_exposure(market_id, token_id, price * size)

    def can_fill_ask(self, market_id: str, token_id: str, size: float) -> RiskDecision:
        fill_count = self.can_add_fill_count(market_id, token_id)
        if not fill_count.allowed:
            return fill_count
        held = self.shares(market_id, token_id)
        if held < size:
            return RiskDecision(False, "insufficient_inventory_for_ask", {"held": held, "size": size})
        return RiskDecision(True, "allowed")

    def record_fill(self, market_id: str, token_id: str, side: str, price: float, size: float) -> dict[str, float]:
        key = self.token_key(market_id, token_id)
        if side == "bid":
            self.positions[key] = self.positions.get(key, 0.0) + size
            self.cash_by_token[key] = self.cash_by_token.get(key, 0.0) + price * size
        elif side == "ask":
            self.positions[key] = self.positions.get(key, 0.0) - size
            self.cash_by_token[key] = max(0.0, self.cash_by_token.get(key, 0.0) - price * size)
        self.fill_counts_by_market[market_id] = self.fill_counts_by_market.get(market_id, 0) + 1
        self.fill_counts_by_token[key] = self.fill_counts_by_token.get(key, 0) + 1
        return {
            "shares": round(self.positions.get(key, 0.0), 6),
            "token_notional": round(self.cash_by_token.get(key, 0.0), 6),
            "market_exposure": round(self.market_exposure(market_id), 6),
            "total_exposure": round(self.total_exposure(), 6),
            "market_fill_count": self.fill_counts_by_market.get(market_id, 0),
            "token_fill_count": self.fill_counts_by_token.get(key, 0),
        }


def quote_should_cancel(quote: dict[str, Any], snapshot: dict[str, Any], *, now: datetime | None = None) -> RiskDecision:
    current = now or utc_now()
    expires_at = parse_dt(quote.get("expires_at"))
    if expires_at and current >= expires_at:
        return RiskDecision(True, "quote_expired")
    event_time = parse_dt(snapshot.get("timestamp"))
    if event_time is None:
        return RiskDecision(True, "missing_book_timestamp")
    age = (current - event_time).total_seconds()
    if age > STALE_SECONDS:
        return RiskDecision(True, "stale_feed", {"age_seconds": round(age, 3)})
    spread = snapshot.get("spread")
    if spread is not None and float(spread) > MAX_CANCEL_SPREAD:
        return RiskDecision(True, "spread_widened", {"spread": spread})
    old_mid = quote.get("midpoint")
    new_mid = snapshot.get("midpoint")
    tick = snapshot.get("tick_size") or quote.get("tick_size") or 0.01
    if old_mid is not None and new_mid is not None:
        if abs(float(new_mid) - float(old_mid)) > MAX_MIDPOINT_MOVE_TICKS * float(tick):
            return RiskDecision(
                True,
                "midpoint_moved",
                {"old_midpoint": old_mid, "new_midpoint": new_mid, "tick_size": tick},
            )
    return RiskDecision(False, "keep")
