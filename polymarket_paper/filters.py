from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from .timeutils import parse_dt, utc_now


MIN_VOLUME_24H = 50_000.0
MIN_LIQUIDITY = 10_000.0
MAX_SPREAD = 0.03
MAX_ORDER_MIN_SIZE = 20.0
MIN_END_BUFFER = timedelta(hours=6)
MAX_METADATA_AGE = timedelta(hours=6)


@dataclass(frozen=True)
class NormalizedMarket:
    market_id: str
    slug: str
    question: str
    active: bool
    closed: bool
    accepting_orders: bool
    enable_order_book: bool
    end_date: str | None
    updated_at: str | None
    volume_24h: float | None
    liquidity: float | None
    spread: float | None
    tick_size: float | None
    order_min_size: float | None
    token_ids: tuple[str, ...]
    outcomes: tuple[str, ...]
    best_bid: float | None
    best_ask: float | None
    neg_risk: bool
    neg_risk_other: bool
    resolution_source: str | None
    tags: tuple[str, ...]
    fee_rate: float | None
    rewards_min_size: float | None
    rewards_max_spread: float | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "slug": self.slug,
            "question": self.question,
            "active": self.active,
            "closed": self.closed,
            "accepting_orders": self.accepting_orders,
            "enable_order_book": self.enable_order_book,
            "end_date": self.end_date,
            "updated_at": self.updated_at,
            "volume_24h": self.volume_24h,
            "liquidity": self.liquidity,
            "spread": self.spread,
            "tick_size": self.tick_size,
            "order_min_size": self.order_min_size,
            "token_ids": list(self.token_ids),
            "outcomes": list(self.outcomes),
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "neg_risk": self.neg_risk,
            "neg_risk_other": self.neg_risk_other,
            "resolution_source": self.resolution_source,
            "tags": list(self.tags),
            "fee_rate": self.fee_rate,
            "rewards_min_size": self.rewards_min_size,
            "rewards_max_spread": self.rewards_max_spread,
        }


def _float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes"}
    return bool(value)


def _json_list(value: object) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _field(raw: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in raw:
            return raw[name]
    return None


def normalize_market(raw: dict[str, Any]) -> NormalizedMarket:
    tokens_from_clob = [str(item) for item in _json_list(_field(raw, "clobTokenIds", "clob_token_ids")) if item]
    tokens_from_sampling = [
        str(token.get("token_id"))
        for token in _json_list(raw.get("tokens"))
        if isinstance(token, dict) and token.get("token_id")
    ]
    outcomes = [str(item) for item in _json_list(_field(raw, "outcomes")) if item]
    if not outcomes and isinstance(raw.get("tokens"), list):
        outcomes = [
            str(token.get("outcome"))
            for token in raw["tokens"]
            if isinstance(token, dict) and token.get("outcome")
        ]
    fee_schedule = raw.get("feeSchedule") if isinstance(raw.get("feeSchedule"), dict) else {}
    if not fee_schedule:
        fee_schedule = raw.get("fee_schedule") if isinstance(raw.get("fee_schedule"), dict) else {}
    tags = raw.get("tags")
    tag_names: list[str] = []
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict) and tag.get("label"):
                tag_names.append(str(tag["label"]))
            elif isinstance(tag, str):
                tag_names.append(tag)
    return NormalizedMarket(
        market_id=str(_field(raw, "id", "conditionId", "condition_id") or ""),
        slug=str(_field(raw, "slug", "market_slug") or ""),
        question=str(_field(raw, "question", "title") or ""),
        active=_bool(_field(raw, "active")),
        closed=_bool(_field(raw, "closed")),
        accepting_orders=_bool(_field(raw, "acceptingOrders", "accepting_orders")),
        enable_order_book=_bool(_field(raw, "enableOrderBook", "enable_order_book")),
        end_date=_field(raw, "endDate", "endDateIso", "end_date_iso"),
        updated_at=_field(raw, "updatedAt", "updated_at"),
        volume_24h=_float(_field(raw, "volume24hr", "volume24hrClob", "volume_24h")),
        liquidity=_float(_field(raw, "liquidityNum", "liquidityClob", "liquidity", "liquidity_num")),
        spread=_float(_field(raw, "spread")),
        tick_size=_float(_field(raw, "orderPriceMinTickSize", "minimum_tick_size", "tick_size")),
        order_min_size=_float(_field(raw, "orderMinSize", "minimum_order_size", "order_min_size")),
        token_ids=tuple(tokens_from_clob or tokens_from_sampling),
        outcomes=tuple(outcomes),
        best_bid=_float(_field(raw, "bestBid", "best_bid")),
        best_ask=_float(_field(raw, "bestAsk", "best_ask")),
        neg_risk=_bool(_field(raw, "negRisk", "neg_risk")),
        neg_risk_other=_bool(_field(raw, "negRiskOther", "neg_risk_other")),
        resolution_source=(
            str(_field(raw, "resolutionSource", "resolution_source")).strip()
            if _field(raw, "resolutionSource", "resolution_source")
            else None
        ),
        tags=tuple(tag_names),
        fee_rate=_float(fee_schedule.get("rate")),
        rewards_min_size=_float(_field(raw, "rewardsMinSize", "rewards_min_size")),
        rewards_max_spread=_float(_field(raw, "rewardsMaxSpread", "rewards_max_spread")),
    )


def _monitorable_resolution(market: NormalizedMarket) -> bool:
    if market.resolution_source:
        return True
    tags = {tag.lower() for tag in market.tags}
    monitorable_tags = {
        "crypto",
        "sports",
        "nba",
        "nfl",
        "nhl",
        "mlb",
        "finance",
        "economy",
        "fed",
        "commodities",
    }
    return bool(tags & monitorable_tags)


def evaluate_market(market: NormalizedMarket, *, now=None) -> tuple[bool, str]:
    current = now or utc_now()
    if not market.market_id:
        return False, "metadata_missing:market_id"
    if not market.active:
        return False, "inactive"
    if market.closed:
        return False, "closed"
    if not market.accepting_orders:
        return False, "not_accepting_orders"
    if not market.enable_order_book:
        return False, "non_orderbook"
    if market.neg_risk or market.neg_risk_other:
        return False, "negative_risk_skipped"
    if market.end_date is None:
        return False, "metadata_missing:end_date"
    end_date = parse_dt(market.end_date)
    if end_date is None:
        return False, "metadata_invalid:end_date"
    if end_date <= current:
        return False, "expired"
    if end_date - current < MIN_END_BUFFER:
        return False, "near_resolution"
    updated_at = parse_dt(market.updated_at)
    if updated_at and current - updated_at > MAX_METADATA_AGE:
        return False, "stale_metadata"
    if market.volume_24h is None:
        return False, "metadata_missing:volume_24h"
    if market.volume_24h < MIN_VOLUME_24H:
        return False, "low_volume_24h"
    if market.liquidity is None:
        return False, "metadata_missing:liquidity"
    if market.liquidity < MIN_LIQUIDITY:
        return False, "low_liquidity"
    if market.tick_size is None:
        return False, "metadata_missing:tick_size"
    if market.spread is None:
        return False, "metadata_missing:spread"
    if not (market.spread <= MAX_SPREAD or market.spread <= 3 * market.tick_size):
        return False, "wide_spread"
    if market.order_min_size is None:
        return False, "metadata_missing:order_min_size"
    if market.order_min_size > MAX_ORDER_MIN_SIZE:
        return False, "order_min_size_too_large"
    if len(market.token_ids) < 2:
        return False, "metadata_missing:clob_token_ids"
    if market.best_bid is None or market.best_ask is None:
        return False, "metadata_missing:best_bid_ask"
    if market.best_bid <= 0 or market.best_ask >= 1 or market.best_bid >= market.best_ask:
        return False, "invalid_best_bid_ask"
    if not _monitorable_resolution(market):
        return False, "resolution_source_unmonitorable"
    return True, "selected"


def journal_market(raw: dict[str, Any], *, now=None) -> dict[str, Any]:
    normalized = normalize_market(raw)
    selected, reason = evaluate_market(normalized, now=now)
    return {
        "type": "market_filter",
        "raw": raw,
        "normalized": normalized.as_dict(),
        "selected": selected,
        "skip_reason": None if selected else reason,
        "decision_reason": reason,
    }


def selected_market_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if row.get("selected") and isinstance(row.get("normalized"), dict)]


def observation_candidates(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for row in rows:
        normalized = row.get("normalized")
        if not isinstance(normalized, dict):
            continue
        if len(normalized.get("token_ids") or []) >= 2 and normalized.get("enable_order_book"):
            candidates.append(row)
    return candidates
