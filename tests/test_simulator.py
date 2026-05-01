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


if __name__ == "__main__":
    unittest.main()
