from __future__ import annotations

from typing import Any


def scan_binary(
    market_id: str,
    yes_ask: float | None,
    no_ask: float | None,
    *,
    min_edge: float = 0.002,
    fees_and_slippage: float = 0.0,
) -> dict[str, Any]:
    if yes_ask is None or no_ask is None:
        return {"type": "binary_no_arb_scan", "market_id": market_id, "status": "missing_ask"}
    basket_cost = yes_ask + no_ask + fees_and_slippage
    edge = 1.0 - basket_cost
    return {
        "type": "binary_arb_alert" if edge > min_edge else "binary_no_arb_scan",
        "market_id": market_id,
        "basket_cost": round(basket_cost, 6),
        "edge": round(edge, 6),
        "min_edge": min_edge,
        "is_alert": edge > min_edge,
    }


def scan_multi_outcome(
    market_id: str,
    asks: list[float | None],
    *,
    min_edge: float = 0.002,
    fees_and_slippage: float = 0.0,
) -> dict[str, Any]:
    if any(value is None for value in asks) or not asks:
        return {"type": "multi_no_arb_scan", "market_id": market_id, "status": "missing_ask"}
    basket_cost = sum(float(value) for value in asks if value is not None) + fees_and_slippage
    edge = 1.0 - basket_cost
    return {
        "type": "multi_arb_alert" if edge > min_edge else "multi_no_arb_scan",
        "market_id": market_id,
        "basket_cost": round(basket_cost, 6),
        "edge": round(edge, 6),
        "min_edge": min_edge,
        "is_alert": edge > min_edge,
    }


def scan_market_from_books(market: dict[str, Any], books_by_token: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    token_ids = list(market.get("token_ids") or [])
    outcomes = list(market.get("outcomes") or [])
    if len(token_ids) < 2:
        return None
    asks = [books_by_token.get(token_id, {}).get("best_ask") for token_id in token_ids]
    if len(token_ids) == 2 and {item.lower() for item in outcomes[:2]} == {"yes", "no"}:
        yes_index = 0 if outcomes[0].lower() == "yes" else 1
        no_index = 1 - yes_index
        return scan_binary(str(market.get("market_id")), asks[yes_index], asks[no_index])
    return scan_multi_outcome(str(market.get("market_id")), asks)
