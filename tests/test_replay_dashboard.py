from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from polymarket_paper.journal import append_jsonl, ensure_run_dir
from polymarket_paper.report import build_run_state, generate_report


class ReplayDashboardParityTests(unittest.TestCase):
    def test_report_replays_jsonl_and_dashboard_state_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ensure_run_dir(Path(tmp))
            append_jsonl(
                run_dir / "markets.jsonl",
                {
                    "type": "market_filter",
                    "selected": True,
                    "normalized": {
                        "market_id": "m1",
                        "question": "Fixture market?",
                        "slug": "fixture-market",
                        "spread": 0.02,
                        "token_ids": ["yes", "no"],
                        "outcomes": ["Yes", "No"],
                    },
                },
            )
            append_jsonl(
                run_dir / "markets.jsonl",
                {"type": "market_filter", "selected": False, "skip_reason": "wide_spread", "normalized": {"market_id": "m2"}},
            )
            append_jsonl(
                run_dir / "books.jsonl",
                {
                    "type": "book_snapshot",
                    "event_id": "book-start",
                    "timestamp": "2026-05-01T12:00:00+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "outcome": "Yes",
                    "best_bid": 0.48,
                    "best_ask": 0.5,
                    "midpoint": 0.49,
                    "spread": 0.02,
                },
            )
            append_jsonl(
                run_dir / "books.jsonl",
                {
                    "type": "book_snapshot",
                    "event_id": "book-fill",
                    "timestamp": "2026-05-01T12:00:05+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "outcome": "Yes",
                    "best_bid": 0.47,
                    "best_ask": 0.49,
                    "midpoint": 0.48,
                    "spread": 0.02,
                },
            )
            append_jsonl(
                run_dir / "quotes.jsonl",
                {
                    "type": "virtual_quote",
                    "quote_id": "q1",
                    "market_id": "m1",
                    "token_id": "yes",
                    "side": "bid",
                    "price": 0.49,
                    "size": 5,
                    "evidence_event_id": "book-0",
                },
            )
            append_jsonl(
                run_dir / "fills.jsonl",
                {
                    "type": "simulated_fill",
                    "quote_id": "q1",
                    "market_id": "m1",
                    "token_id": "yes",
                    "side": "bid",
                    "price": 0.49,
                    "size": 5,
                    "evidence_event_id": "book-fill",
                },
            )
            append_jsonl(run_dir / "risk_events.jsonl", {"type": "fallback_mode", "mode": "polling"})
            append_jsonl(run_dir / "risk_events.jsonl", {"type": "run_completed"})
            append_jsonl(run_dir / "arb_alerts.jsonl", {"type": "binary_arb_alert", "market_id": "m1", "is_alert": True})

            state = generate_report(run_dir, date="2026-05-01", dashboard_url="http://127.0.0.1:8765")
            replayed = build_run_state(run_dir)

            self.assertTrue((run_dir / "summary.md").exists())
            self.assertTrue((run_dir / "dashboard_state.json").exists())
            self.assertEqual(state["counts"]["markets_watched"], replayed["counts"]["markets_watched"])
            self.assertEqual(state["counts"]["quotes"], replayed["counts"]["quotes"])
            self.assertEqual(state["counts"]["fills"], replayed["counts"]["fills"])
            self.assertEqual(state["counts"]["risk_events"], replayed["counts"]["risk_events"])
            self.assertEqual(state["counts"]["arb_alerts"], replayed["counts"]["arb_alerts"])
            self.assertEqual(state["pnl"], replayed["pnl"])
            self.assertEqual(state["market_summaries"][0]["question"], "Fixture market?")
            self.assertEqual(state["market_summaries"][0]["outcomes"][0]["outcome"], "Yes")
            self.assertEqual(len(state["market_summaries"][0]["outcomes"][0]["history"]), 2)
            self.assertEqual(state["latest_books"]["yes"]["display_name"], "Fixture market? - Yes")
            self.assertIn("Mark-to-mid PnL", (run_dir / "summary.md").read_text(encoding="utf-8"))

    def test_latest_run_start_keeps_dashboard_active_after_prior_completion(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ensure_run_dir(Path(tmp))
            append_jsonl(run_dir / "risk_events.jsonl", {"type": "run_started", "timestamp": "2026-05-01T12:00:00+00:00"})
            append_jsonl(run_dir / "risk_events.jsonl", {"type": "run_completed", "timestamp": "2026-05-01T12:10:00+00:00"})
            append_jsonl(run_dir / "risk_events.jsonl", {"type": "run_started", "timestamp": "2026-05-01T12:20:00+00:00"})

            state = build_run_state(run_dir)

            self.assertEqual(state["status"], "active_or_partial")


if __name__ == "__main__":
    unittest.main()
