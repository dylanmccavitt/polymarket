from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from polymarket_paper.risk import RiskState, quote_should_cancel
from polymarket_paper.simulator import PaperSimulator


NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)


def snapshot(**overrides):
    row = {
        "type": "book_snapshot",
        "event_id": "book-1",
        "timestamp": NOW.isoformat(),
        "market_id": "m1",
        "token_id": "yes",
        "outcome": "Yes",
        "best_bid": 0.49,
        "best_ask": 0.51,
        "midpoint": 0.5,
        "spread": 0.02,
        "tick_size": 0.01,
        "min_order_size": 5,
    }
    row.update(overrides)
    return row


class SimulatorTrustTests(unittest.TestCase):
    def test_quote_expiry_cancels(self):
        risk = RiskState(max_total_exposure=100)
        sim = PaperSimulator(risk=risk, quote_size=5)
        quote = sim.generate_quotes(snapshot(), now=NOW)[0]
        decision = quote_should_cancel(quote, snapshot(timestamp=(NOW + timedelta(seconds=31)).isoformat()), now=NOW + timedelta(seconds=31))
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "quote_expired")

    def test_stale_feed_stops_quoting(self):
        risk = RiskState(max_total_exposure=100)
        stale = snapshot(timestamp=(NOW - timedelta(seconds=25)).isoformat())
        decision = risk.can_quote(stale, price=0.5, size=5, now=NOW)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "stale_feed")

    def test_spread_widening_cancels_quote(self):
        risk = RiskState(max_total_exposure=100)
        sim = PaperSimulator(risk=risk, quote_size=5)
        quote = sim.generate_quotes(snapshot(), now=NOW)[0]
        decision = quote_should_cancel(quote, snapshot(event_id="book-2", spread=0.09, best_bid=0.45, best_ask=0.54), now=NOW)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "spread_widened")

    def test_midpoint_move_cancels_quote(self):
        risk = RiskState(max_total_exposure=100)
        sim = PaperSimulator(risk=risk, quote_size=5)
        quote = sim.generate_quotes(snapshot(), now=NOW)[0]
        decision = quote_should_cancel(quote, snapshot(event_id="book-2", midpoint=0.54, best_bid=0.53, best_ask=0.55), now=NOW)
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "midpoint_moved")

    def test_exposure_cap_denies_fill(self):
        risk = RiskState(max_total_exposure=2)
        decision = risk.can_fill_bid("m1", "yes", price=0.6, size=5)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "total_exposure_cap")

    def test_ambiguous_fill_evidence_stays_unfilled(self):
        risk = RiskState(max_total_exposure=100)
        sim = PaperSimulator(risk=risk, quote_size=5)
        sim.generate_quotes(snapshot(), now=NOW)
        fills, risk_events = sim.process_snapshot(snapshot(event_id="book-2", best_bid=0.49, best_ask=0.51), now=NOW + timedelta(seconds=5))
        self.assertEqual(fills, [])
        self.assertEqual(risk_events, [])

    def test_conservative_fill_requires_cited_book_event(self):
        risk = RiskState(max_total_exposure=100)
        sim = PaperSimulator(risk=risk, quote_size=5)
        sim.generate_quotes(snapshot(), now=NOW)
        fills, _ = sim.process_snapshot(
            snapshot(event_id="book-fill", best_bid=0.49, best_ask=0.5, midpoint=0.495, spread=0.01),
            now=NOW + timedelta(seconds=5),
        )
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0]["type"], "simulated_fill")
        self.assertEqual(fills[0]["evidence_event_id"], "book-fill")
        self.assertEqual(fills[0]["reason"], "book_ask_traded_through_bid")

    def test_market_fill_cap_denies_additional_bid_fills(self):
        risk = RiskState(max_total_exposure=100, max_market_fills=1, max_token_fills=10)
        sim = PaperSimulator(risk=risk, quote_size=5, quote_expiry_seconds=60)

        sim.generate_quotes(snapshot(event_id="book-1"), now=NOW)
        fills, _ = sim.process_snapshot(
            snapshot(event_id="book-fill-1", best_bid=0.49, best_ask=0.5, midpoint=0.495, spread=0.01),
            now=NOW + timedelta(seconds=5),
        )
        self.assertEqual(fills[0]["type"], "simulated_fill")

        sim.generate_quotes(snapshot(event_id="book-2"), now=NOW + timedelta(seconds=6))
        denied, _ = sim.process_snapshot(
            snapshot(event_id="book-fill-2", best_bid=0.49, best_ask=0.5, midpoint=0.495, spread=0.01),
            now=NOW + timedelta(seconds=10),
        )

        self.assertEqual(denied[0]["type"], "fill_denied")
        self.assertEqual(denied[0]["reason"], "market_fill_cap")
        self.assertEqual(denied[0]["evidence_event_id"], "book-fill-2")

    def test_token_fill_cap_denies_additional_outcome_fills(self):
        risk = RiskState(max_total_exposure=100, max_market_fills=10, max_token_fills=1)
        sim = PaperSimulator(risk=risk, quote_size=5, quote_expiry_seconds=60)

        sim.generate_quotes(snapshot(event_id="book-1"), now=NOW)
        fills, _ = sim.process_snapshot(
            snapshot(event_id="book-fill-1", best_bid=0.49, best_ask=0.5, midpoint=0.495, spread=0.01),
            now=NOW + timedelta(seconds=5),
        )
        self.assertEqual(fills[0]["type"], "simulated_fill")

        sim.generate_quotes(snapshot(event_id="book-2"), now=NOW + timedelta(seconds=6))
        denied, _ = sim.process_snapshot(
            snapshot(event_id="book-fill-2", best_bid=0.49, best_ask=0.5, midpoint=0.495, spread=0.01),
            now=NOW + timedelta(seconds=10),
        )

        self.assertEqual(denied[0]["type"], "fill_denied")
        self.assertEqual(denied[0]["reason"], "token_fill_cap")
        self.assertEqual(denied[0]["evidence_event_id"], "book-fill-2")

    def test_inventory_exit_quote_requires_min_profit_target(self):
        risk = RiskState(max_total_exposure=100)
        risk.record_fill("m1", "yes", "bid", price=0.5, size=5)
        sim = PaperSimulator(
            risk=risk,
            quote_size=5,
            quote_expiry_seconds=60,
            min_exit_profit_ticks=2,
        )

        too_cheap = sim.generate_quotes(
            snapshot(best_bid=0.49, best_ask=0.51, midpoint=0.5, spread=0.02),
            now=NOW,
        )
        self.assertEqual([quote for quote in too_cheap if quote["side"] == "ask"], [])

        profitable = sim.generate_quotes(
            snapshot(event_id="book-profitable", best_bid=0.51, best_ask=0.54, midpoint=0.525, spread=0.03),
            now=NOW + timedelta(seconds=1),
        )
        asks = [quote for quote in profitable if quote["side"] == "ask"]

        self.assertEqual(len(asks), 1)
        self.assertEqual(asks[0]["side"], "ask")
        self.assertGreaterEqual(asks[0]["price"], 0.52)
        self.assertEqual(asks[0]["exit_context"]["average_entry_price"], 0.5)
        self.assertEqual(asks[0]["exit_context"]["min_exit_price"], 0.52)
        self.assertEqual(asks[0]["exit_context"]["min_exit_profit_ticks"], 2)

    def test_inventory_exit_fill_is_not_blocked_by_entry_fill_cap(self):
        risk = RiskState(max_total_exposure=100, max_market_fills=1, max_token_fills=1)
        risk.record_fill("m1", "yes", "bid", price=0.5, size=5)
        sim = PaperSimulator(
            risk=risk,
            quote_size=5,
            quote_expiry_seconds=60,
            min_exit_profit_ticks=1,
        )

        sim.generate_quotes(
            snapshot(event_id="book-exit-quote", best_bid=0.51, best_ask=0.54, midpoint=0.525, spread=0.03),
            now=NOW,
        )
        fills, risk_events = sim.process_snapshot(
            snapshot(event_id="book-exit-fill", best_bid=0.53, best_ask=0.55, midpoint=0.54, spread=0.02),
            now=NOW + timedelta(seconds=5),
        )

        exit_fills = [fill for fill in fills if fill["side"] == "ask"]
        self.assertEqual(risk_events, [])
        self.assertEqual(len(exit_fills), 1)
        self.assertEqual(exit_fills[0]["type"], "simulated_fill")
        self.assertEqual(exit_fills[0]["reason"], "book_bid_traded_through_ask")
        self.assertEqual(exit_fills[0]["evidence_event_id"], "book-exit-fill")

    def test_prior_replay_entry_gate_blocks_bid_but_allows_inventory_exit(self):
        risk = RiskState(max_total_exposure=100)
        risk.record_fill("m1", "yes", "bid", price=0.5, size=5)
        sim = PaperSimulator(
            risk=risk,
            quote_size=5,
            quote_expiry_seconds=60,
            min_exit_profit_ticks=1,
            entry_blocked_markets={"m1": "risky_concentrated"},
        )

        quotes = sim.generate_quotes(
            snapshot(event_id="book-gated", best_bid=0.51, best_ask=0.54, midpoint=0.525, spread=0.03),
            now=NOW,
        )

        self.assertEqual([quote for quote in quotes if quote["side"] == "bid"], [])
        asks = [quote for quote in quotes if quote["side"] == "ask"]
        self.assertEqual(len(asks), 1)
        self.assertEqual(asks[0]["reason"], "paper_maker_inventory_exit_one_tick_inside")
        self.assertEqual(asks[0]["exit_context"]["min_exit_price"], 0.51)

    def test_prior_replay_entry_gate_blocks_empty_inventory_market(self):
        sim = PaperSimulator(
            risk=RiskState(max_total_exposure=100),
            quote_size=5,
            entry_blocked_markets={"m1": "too_adverse"},
        )

        quotes = sim.generate_quotes(snapshot(event_id="book-gated"), now=NOW)

        self.assertEqual(quotes, [])

    def test_quote_policy_variants_choose_distinct_maker_prices(self):
        wide = snapshot(best_bid=0.49, best_ask=0.53, midpoint=0.51, spread=0.04)

        best_bid = PaperSimulator(risk=RiskState(max_total_exposure=100), quote_size=5, quote_mode="best_bid")
        one_tick = PaperSimulator(risk=RiskState(max_total_exposure=100), quote_size=5, quote_mode="one_tick_inside")
        midpoint = PaperSimulator(
            risk=RiskState(max_total_exposure=100),
            quote_size=5,
            quote_mode="midpoint_when_spread_allows",
        )

        self.assertEqual(best_bid.generate_quotes(wide, now=NOW)[0]["price"], 0.49)
        self.assertEqual(one_tick.generate_quotes(wide, now=NOW)[0]["price"], 0.5)
        self.assertEqual(midpoint.generate_quotes(wide, now=NOW)[0]["price"], 0.51)
        self.assertEqual(midpoint.generate_quotes(wide, now=NOW)[0]["quote_mode"], "midpoint_when_spread_allows")

    def test_quote_expiry_seconds_are_configurable(self):
        sim = PaperSimulator(risk=RiskState(max_total_exposure=100), quote_size=5, quote_expiry_seconds=12)

        quote = sim.generate_quotes(snapshot(), now=NOW)[0]

        self.assertEqual(quote["expires_at"], (NOW + timedelta(seconds=12)).isoformat())
        self.assertEqual(quote["quote_expiry_seconds"], 12)

    def test_policy_variants_do_not_create_optimistic_fills_without_trade_through(self):
        sim = PaperSimulator(
            risk=RiskState(max_total_exposure=100),
            quote_size=5,
            quote_mode="midpoint_when_spread_allows",
        )
        sim.generate_quotes(snapshot(best_bid=0.49, best_ask=0.53, midpoint=0.51, spread=0.04), now=NOW)

        fills, risk_events = sim.process_snapshot(
            snapshot(event_id="book-2", best_bid=0.5, best_ask=0.52, midpoint=0.51, spread=0.02),
            now=NOW + timedelta(seconds=5),
        )

        self.assertEqual(fills, [])
        self.assertEqual(risk_events, [])


if __name__ == "__main__":
    unittest.main()
