from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .timeutils import parse_dt, utc_now


QUOTE_EXPIRY_SECONDS = 30
STALE_SECONDS = 20
MAX_CANCEL_SPREAD = 0.05
MAX_MIDPOINT_MOVE_TICKS = 2
SAME_RUN_GATE_MIN_QUOTES = 20
SAME_RUN_CONCENTRATION_SHARE = 0.35
SAME_RUN_ADVERSE_MARKOUT_SECONDS = (30, 60, 120)


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
    exit_counts_by_market: dict[str, int] = field(default_factory=dict)
    exit_counts_by_token: dict[str, int] = field(default_factory=dict)
    same_run_gate_entry_counts_by_market: dict[str, int] = field(default_factory=dict)
    same_run_gate_entry_counts_by_token: dict[str, int] = field(default_factory=dict)
    same_run_gate_quote_counts_by_market: dict[str, int] = field(default_factory=dict)
    same_run_gate_pending_entry_fills: list[dict[str, Any]] = field(default_factory=list)
    same_run_gate_adverse_fill_ids_by_market: dict[str, set[str]] = field(default_factory=dict)
    same_run_entry_gates: dict[str, dict[str, Any]] = field(default_factory=dict)
    _same_run_gate_events: list[dict[str, Any]] = field(default_factory=list)

    def token_key(self, market_id: str, token_id: str) -> str:
        return f"{market_id}:{token_id}"

    def market_exposure(self, market_id: str) -> float:
        prefix = f"{market_id}:"
        return sum(abs(value) for key, value in self.cash_by_token.items() if key.startswith(prefix))

    def total_exposure(self) -> float:
        return sum(abs(value) for value in self.cash_by_token.values())

    def shares(self, market_id: str, token_id: str) -> float:
        return self.positions.get(self.token_key(market_id, token_id), 0.0)

    def average_entry_price(self, market_id: str, token_id: str) -> float | None:
        key = self.token_key(market_id, token_id)
        shares = self.positions.get(key, 0.0)
        if shares <= 0:
            return None
        return round(self.cash_by_token.get(key, 0.0) / shares, 6)

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
        held = self.shares(market_id, token_id)
        if held < size:
            return RiskDecision(False, "insufficient_inventory_for_ask", {"held": held, "size": size})
        return RiskDecision(True, "allowed")

    def same_run_entry_gate_for_market(self, market_id: str) -> dict[str, Any] | None:
        return self.same_run_entry_gates.get(market_id)

    def record_entry_quote_for_same_run_gate(self, quote: dict[str, Any]) -> None:
        if quote.get("side") != "bid":
            return
        market_id = str(quote.get("market_id") or "")
        if not market_id:
            return
        self.same_run_gate_quote_counts_by_market[market_id] = self.same_run_gate_quote_counts_by_market.get(market_id, 0) + 1
        self._evaluate_same_run_concentration(
            market_id=market_id,
            token_id=str(quote.get("token_id") or ""),
            outcome=quote.get("outcome"),
            timestamp=quote.get("timestamp"),
            source_evidence_event_id=quote.get("source_event_id"),
            source_quote_id=quote.get("quote_id"),
        )

    def pop_same_run_entry_gate_events(self) -> list[dict[str, Any]]:
        events = list(self._same_run_gate_events)
        self._same_run_gate_events.clear()
        return events

    def observe_book_for_same_run_gate(self, snapshot: dict[str, Any], *, now: datetime | None = None) -> None:
        market_id = str(snapshot.get("market_id") or "")
        token_id = str(snapshot.get("token_id") or "")
        midpoint = snapshot.get("midpoint")
        if not market_id or not token_id or midpoint is None:
            return
        current = now or utc_now()
        snapshot_time = parse_dt(snapshot.get("timestamp")) or current
        midpoint_value = float(midpoint)
        for fill in self.same_run_gate_pending_entry_fills:
            if fill.get("market_id") != market_id or fill.get("token_id") != token_id:
                continue
            fill_time = parse_dt(fill.get("timestamp"))
            if fill_time is None:
                continue
            checked = fill.setdefault("checked_markout_seconds", set())
            if not isinstance(checked, set):
                checked = set(checked)
                fill["checked_markout_seconds"] = checked
            for seconds in SAME_RUN_ADVERSE_MARKOUT_SECONDS:
                if seconds in checked:
                    continue
                if snapshot_time < fill_time + timedelta(seconds=seconds):
                    continue
                checked.add(seconds)
                tick = float(fill.get("tick_size") or snapshot.get("tick_size") or 0.01)
                markout = midpoint_value - float(fill.get("price") or 0.0)
                if markout < -1 * tick:
                    self.same_run_gate_adverse_fill_ids_by_market.setdefault(market_id, set()).add(str(fill["fill_id"]))
                    self._evaluate_same_run_adverse(
                        market_id=market_id,
                        token_id=token_id,
                        outcome=snapshot.get("outcome") or fill.get("outcome"),
                        timestamp=current.isoformat(),
                        source_evidence_event_id=snapshot.get("event_id"),
                        source_quote_id=fill.get("quote_id"),
                    )
                    break

    def _activate_same_run_entry_gate(
        self,
        *,
        market_id: str,
        token_id: str | None,
        outcome: Any,
        classification: str,
        reason: str,
        threshold: str,
        timestamp: str | None,
        source_evidence_event_id: Any,
        source_quote_id: Any,
        details: dict[str, Any],
    ) -> None:
        if market_id in self.same_run_entry_gates:
            return
        gate = {
            "timestamp": timestamp or utc_now().isoformat(),
            "market_id": market_id,
            "token_id": token_id,
            "outcome": outcome,
            "classification": classification,
            "reason": reason,
            "threshold": threshold,
            "source_evidence_event_id": source_evidence_event_id,
            "source_quote_id": source_quote_id,
            "details": details,
        }
        self.same_run_entry_gates[market_id] = gate
        self._same_run_gate_events.append({"type": "same_run_entry_gate", **gate})

    def _evaluate_same_run_concentration(
        self,
        *,
        market_id: str,
        token_id: str | None,
        outcome: Any,
        timestamp: str | None,
        source_evidence_event_id: Any,
        source_quote_id: Any,
    ) -> None:
        if market_id in self.same_run_entry_gates:
            return
        market_count = self.same_run_gate_entry_counts_by_market.get(market_id, 0)
        token_count = self.same_run_gate_entry_counts_by_token.get(self.token_key(market_id, str(token_id or "")), 0)
        quote_count = self.same_run_gate_quote_counts_by_market.get(market_id, 0)
        total_entry_fills = sum(self.same_run_gate_entry_counts_by_market.values())
        if market_count >= self.max_market_fills:
            self._activate_same_run_entry_gate(
                market_id=market_id,
                token_id=token_id,
                outcome=outcome,
                classification="risky_concentrated",
                reason="entry_fill_count_reached_market_cap",
                threshold="entry_fill_count_at_market_cap",
                timestamp=timestamp,
                source_evidence_event_id=source_evidence_event_id,
                source_quote_id=source_quote_id,
                details={
                    "entry_fill_count": market_count,
                    "token_entry_fill_count": token_count,
                    "market_fill_cap": self.max_market_fills,
                    "entry_quote_count": quote_count,
                    "total_entry_fills": total_entry_fills,
                },
            )
            return
        fill_share = round(market_count / total_entry_fills, 6) if total_entry_fills else 0.0
        if quote_count >= SAME_RUN_GATE_MIN_QUOTES and fill_share > SAME_RUN_CONCENTRATION_SHARE:
            self._activate_same_run_entry_gate(
                market_id=market_id,
                token_id=token_id,
                outcome=outcome,
                classification="risky_concentrated",
                reason="entry_fill_share_above_35_percent",
                threshold="entry_fill_share_above_35_percent",
                timestamp=timestamp,
                source_evidence_event_id=source_evidence_event_id,
                source_quote_id=source_quote_id,
                details={
                    "entry_fill_count": market_count,
                    "entry_fill_share": fill_share,
                    "entry_quote_count": quote_count,
                    "min_entry_quotes": SAME_RUN_GATE_MIN_QUOTES,
                    "total_entry_fills": total_entry_fills,
                },
            )

    def _evaluate_same_run_adverse(
        self,
        *,
        market_id: str,
        token_id: str | None,
        outcome: Any,
        timestamp: str | None,
        source_evidence_event_id: Any,
        source_quote_id: Any,
    ) -> None:
        if market_id in self.same_run_entry_gates:
            return
        entry_count = self.same_run_gate_entry_counts_by_market.get(market_id, 0)
        quote_count = self.same_run_gate_quote_counts_by_market.get(market_id, 0)
        adverse_count = len(self.same_run_gate_adverse_fill_ids_by_market.get(market_id, set()))
        if entry_count <= 0:
            return
        if quote_count < SAME_RUN_GATE_MIN_QUOTES:
            return
        if adverse_count < entry_count / 2:
            return
        self._activate_same_run_entry_gate(
            market_id=market_id,
            token_id=token_id,
            outcome=outcome,
            classification="too_adverse",
            reason="adverse_selection_flags_at_least_half_of_entry_fills",
            threshold="adverse_selection_flags_at_least_half_of_entry_fills",
            timestamp=timestamp,
            source_evidence_event_id=source_evidence_event_id,
            source_quote_id=source_quote_id,
            details={
                "entry_fill_count": entry_count,
                "adverse_selection_flags": adverse_count,
                "entry_quote_count": quote_count,
                "min_entry_quotes": SAME_RUN_GATE_MIN_QUOTES,
            },
        )

    def _record_same_run_entry_fill(
        self,
        *,
        market_id: str,
        token_id: str,
        outcome: Any,
        price: float,
        timestamp: str | None,
        evidence_event_id: Any,
        quote_id: Any,
        tick_size: float | None,
    ) -> None:
        fill_id = str(quote_id or f"{market_id}:{token_id}:{timestamp}:{evidence_event_id}")
        key = self.token_key(market_id, token_id)
        self.same_run_gate_entry_counts_by_market[market_id] = self.same_run_gate_entry_counts_by_market.get(market_id, 0) + 1
        self.same_run_gate_entry_counts_by_token[key] = self.same_run_gate_entry_counts_by_token.get(key, 0) + 1
        self.same_run_gate_pending_entry_fills.append(
            {
                "fill_id": fill_id,
                "market_id": market_id,
                "token_id": token_id,
                "outcome": outcome,
                "price": price,
                "timestamp": timestamp,
                "evidence_event_id": evidence_event_id,
                "quote_id": quote_id,
                "tick_size": tick_size or 0.01,
                "checked_markout_seconds": set(),
            }
        )
        self._evaluate_same_run_concentration(
            market_id=market_id,
            token_id=token_id,
            outcome=outcome,
            timestamp=timestamp,
            source_evidence_event_id=evidence_event_id,
            source_quote_id=quote_id,
        )

    def record_fill(
        self,
        market_id: str,
        token_id: str,
        side: str,
        price: float,
        size: float,
        *,
        timestamp: str | None = None,
        evidence_event_id: Any = None,
        quote_id: Any = None,
        outcome: Any = None,
        tick_size: float | None = None,
    ) -> dict[str, Any]:
        key = self.token_key(market_id, token_id)
        if side == "bid":
            self.positions[key] = self.positions.get(key, 0.0) + size
            self.cash_by_token[key] = self.cash_by_token.get(key, 0.0) + price * size
            self.fill_counts_by_market[market_id] = self.fill_counts_by_market.get(market_id, 0) + 1
            self.fill_counts_by_token[key] = self.fill_counts_by_token.get(key, 0) + 1
            if timestamp is not None or evidence_event_id is not None or quote_id is not None:
                self._record_same_run_entry_fill(
                    market_id=market_id,
                    token_id=token_id,
                    outcome=outcome,
                    price=price,
                    timestamp=timestamp,
                    evidence_event_id=evidence_event_id,
                    quote_id=quote_id,
                    tick_size=tick_size,
                )
        elif side == "ask":
            average_entry = self.average_entry_price(market_id, token_id) or 0.0
            self.positions[key] = self.positions.get(key, 0.0) - size
            self.cash_by_token[key] = max(0.0, self.cash_by_token.get(key, 0.0) - average_entry * size)
            self.exit_counts_by_market[market_id] = self.exit_counts_by_market.get(market_id, 0) + 1
            self.exit_counts_by_token[key] = self.exit_counts_by_token.get(key, 0) + 1
        return {
            "shares": round(self.positions.get(key, 0.0), 6),
            "token_notional": round(self.cash_by_token.get(key, 0.0), 6),
            "market_exposure": round(self.market_exposure(market_id), 6),
            "total_exposure": round(self.total_exposure(), 6),
            "market_fill_count": self.fill_counts_by_market.get(market_id, 0),
            "token_fill_count": self.fill_counts_by_token.get(key, 0),
            "market_exit_count": self.exit_counts_by_market.get(market_id, 0),
            "token_exit_count": self.exit_counts_by_token.get(key, 0),
            "average_entry_price": self.average_entry_price(market_id, token_id),
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
