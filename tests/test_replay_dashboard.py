from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from polymarket_paper.dashboard import INDEX_HTML
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
            self.assertIn("fill_opportunity", state)
            self.assertIn("policy_comparison", state)
            self.assertIn("Fill Opportunity Analysis", (run_dir / "summary.md").read_text(encoding="utf-8"))
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

    def test_round_trip_replay_reports_realized_exit_pnl(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ensure_run_dir(Path(tmp))
            append_jsonl(run_dir / "risk_events.jsonl", {"type": "run_started", "timestamp": "2026-05-01T12:00:00+00:00"})
            append_jsonl(
                run_dir / "markets.jsonl",
                {
                    "type": "market_filter",
                    "selected": True,
                    "normalized": {
                        "market_id": "m1",
                        "question": "Round trip fixture?",
                        "slug": "round-trip-fixture",
                        "token_ids": ["yes"],
                        "outcomes": ["Yes"],
                    },
                },
            )
            append_jsonl(
                run_dir / "fills.jsonl",
                {
                    "type": "simulated_fill",
                    "quote_id": "entry-q",
                    "timestamp": "2026-05-01T12:00:00+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "side": "bid",
                    "price": 0.50,
                    "size": 5,
                    "evidence_event_id": "book-entry",
                },
            )
            append_jsonl(
                run_dir / "fills.jsonl",
                {
                    "type": "simulated_fill",
                    "quote_id": "exit-q",
                    "timestamp": "2026-05-01T12:03:00+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "side": "ask",
                    "price": 0.53,
                    "size": 5,
                    "evidence_event_id": "book-exit",
                },
            )

            state = build_run_state(run_dir)
            round_trip = state["round_trip_pnl"]

            self.assertEqual(round_trip["entry_fill_count"], 1)
            self.assertEqual(round_trip["exit_fill_count"], 1)
            self.assertEqual(round_trip["round_trip_count"], 1)
            self.assertEqual(round_trip["realized_pnl"], 0.15)
            self.assertEqual(round_trip["average_profit_per_share"], 0.03)
            self.assertEqual(round_trip["average_hold_seconds"], 180.0)
            self.assertEqual(round_trip["fill_to_flip_rate"], 1.0)
            self.assertEqual(round_trip["open_inventory_size"], 0.0)
            self.assertEqual(state["round_trips"][0]["entry_evidence_event_id"], "book-entry")
            self.assertEqual(state["round_trips"][0]["exit_evidence_event_id"], "book-exit")
            reported = generate_report(run_dir)
            summary = (run_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("## Round Trip PnL", summary)
            self.assertIn("Realized round-trip PnL", summary)
            self.assertEqual(reported["round_trip_pnl"], build_run_state(run_dir)["round_trip_pnl"])

    def test_round_trip_replay_reports_stuck_open_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ensure_run_dir(Path(tmp))
            append_jsonl(
                run_dir / "risk_events.jsonl",
                {
                    "type": "run_started",
                    "timestamp": "2026-05-01T12:00:00+00:00",
                    "stuck_inventory_minutes": 20,
                },
            )
            append_jsonl(run_dir / "risk_events.jsonl", {"type": "run_completed", "timestamp": "2026-05-01T12:45:00+00:00"})
            append_jsonl(
                run_dir / "markets.jsonl",
                {
                    "type": "market_filter",
                    "selected": True,
                    "normalized": {
                        "market_id": "m1",
                        "question": "Stuck fixture?",
                        "slug": "stuck-fixture",
                        "token_ids": ["yes"],
                        "outcomes": ["Yes"],
                    },
                },
            )
            append_jsonl(
                run_dir / "fills.jsonl",
                {
                    "type": "simulated_fill",
                    "quote_id": "entry-q",
                    "timestamp": "2026-05-01T12:00:00+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "side": "bid",
                    "price": 0.50,
                    "size": 5,
                    "evidence_event_id": "book-entry",
                },
            )

            state = build_run_state(run_dir)
            round_trip = state["round_trip_pnl"]

            self.assertEqual(round_trip["entry_fill_count"], 1)
            self.assertEqual(round_trip["exit_fill_count"], 0)
            self.assertEqual(round_trip["open_inventory_size"], 5.0)
            self.assertEqual(round_trip["open_inventory_lots"], 1)
            self.assertEqual(round_trip["stuck_inventory_lots"], 1)
            self.assertEqual(round_trip["oldest_open_seconds"], 2700.0)
            self.assertEqual(state["open_inventory_lots"][0]["status"], "stuck")

    def test_quote_lifecycle_replays_missed_tick_and_longer_expiry_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ensure_run_dir(Path(tmp))
            append_jsonl(
                run_dir / "markets.jsonl",
                {
                    "type": "market_filter",
                    "selected": True,
                    "normalized": {
                        "market_id": "m1",
                        "question": "Will the fixture move?",
                        "slug": "fixture-move",
                        "token_ids": ["yes"],
                        "outcomes": ["Yes"],
                    },
                },
            )
            append_jsonl(
                run_dir / "books.jsonl",
                {
                    "type": "book_snapshot",
                    "event_id": "book-place",
                    "timestamp": "2026-05-01T12:00:00+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "outcome": "Yes",
                    "best_bid": 0.49,
                    "best_ask": 0.53,
                    "midpoint": 0.51,
                    "spread": 0.04,
                    "tick_size": 0.01,
                },
            )
            append_jsonl(
                run_dir / "quotes.jsonl",
                {
                    "type": "virtual_quote",
                    "quote_id": "q-expired",
                    "timestamp": "2026-05-01T12:00:00+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "outcome": "Yes",
                    "side": "bid",
                    "price": 0.5,
                    "size": 5,
                    "midpoint": 0.51,
                    "spread": 0.04,
                    "tick_size": 0.01,
                    "quote_mode": "one_tick_inside",
                    "quote_expiry_seconds": 30,
                    "expires_at": "2026-05-01T12:00:30+00:00",
                    "source_event_id": "book-place",
                },
            )
            append_jsonl(
                run_dir / "books.jsonl",
                {
                    "type": "book_snapshot",
                    "event_id": "book-one-tick-away",
                    "timestamp": "2026-05-01T12:00:25+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "outcome": "Yes",
                    "best_bid": 0.49,
                    "best_ask": 0.51,
                    "midpoint": 0.5,
                    "spread": 0.02,
                    "tick_size": 0.01,
                },
            )
            append_jsonl(
                run_dir / "risk_events.jsonl",
                {
                    "type": "quote_cancelled",
                    "timestamp": "2026-05-01T12:00:31+00:00",
                    "quote_id": "q-expired",
                    "market_id": "m1",
                    "token_id": "yes",
                    "reason": "quote_expired",
                    "evidence_event_id": "book-one-tick-away",
                },
            )
            append_jsonl(
                run_dir / "books.jsonl",
                {
                    "type": "book_snapshot",
                    "event_id": "book-after-expiry-fillable",
                    "timestamp": "2026-05-01T12:00:45+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "outcome": "Yes",
                    "best_bid": 0.48,
                    "best_ask": 0.5,
                    "midpoint": 0.49,
                    "spread": 0.02,
                    "tick_size": 0.01,
                },
            )
            append_jsonl(run_dir / "risk_events.jsonl", {"type": "run_completed", "timestamp": "2026-05-01T12:01:00+00:00"})

            state = generate_report(run_dir, date="2026-05-01")
            lifecycle = state["quote_lifecycle"][0]

            self.assertEqual(lifecycle["quote_id"], "q-expired")
            self.assertEqual(lifecycle["outcome"], "cancelled")
            self.assertEqual(lifecycle["cancel_reason"], "quote_expired")
            self.assertEqual(lifecycle["ticks_missed"], 1)
            self.assertEqual(lifecycle["closest_during_lifetime"]["event_id"], "book-one-tick-away")
            self.assertEqual(lifecycle["closest_subsequent"]["event_id"], "book-after-expiry-fillable")
            self.assertTrue(lifecycle["would_have_filled_under_longer_expiry"])
            self.assertEqual(state["fill_opportunity"]["expired_quotes"], 1)
            self.assertEqual(state["fill_opportunity"]["missed_ticks"]["1_tick"], 1)
            self.assertIn("m1", state["fill_opportunity"]["markets_with_useful_book_movement"])
            self.assertIn("midpoint_when_spread_allows", state["policy_comparison"]["modes"])
            self.assertEqual(state["policy_comparison"]["modes"]["best_bid"]["avg_ticks_missed"], 2.0)
            self.assertEqual(state["policy_comparison"]["modes"]["one_tick_inside"]["avg_ticks_missed"], 1.0)
            self.assertEqual(state["policy_comparison"]["modes"]["one_tick_inside"]["post_expiry_fill_count"], 1)
            self.assertEqual(state["policy_comparison"]["modes"]["midpoint_when_spread_allows"]["plausible_fill_count"], 1)
            summary = (run_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("## Fill Opportunity Analysis", summary)
            self.assertIn("## Policy Comparison", summary)

    def test_fill_quality_reports_post_fill_markout(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ensure_run_dir(Path(tmp))
            append_jsonl(
                run_dir / "markets.jsonl",
                {
                    "type": "market_filter",
                    "selected": True,
                    "normalized": {
                        "market_id": "m1",
                        "question": "Will markout move?",
                        "slug": "markout-move",
                        "token_ids": ["yes"],
                        "outcomes": ["Yes"],
                    },
                },
            )
            for event_id, seconds, midpoint in (
                ("book-fill", 0, 0.5),
                ("book-30", 30, 0.48),
                ("book-60", 60, 0.47),
                ("book-120", 120, 0.46),
            ):
                append_jsonl(
                    run_dir / "books.jsonl",
                    {
                        "type": "book_snapshot",
                        "event_id": event_id,
                        "timestamp": f"2026-05-01T12:{seconds // 60:02d}:{seconds % 60:02d}+00:00",
                        "market_id": "m1",
                        "token_id": "yes",
                        "outcome": "Yes",
                        "best_bid": round(midpoint - 0.01, 2),
                        "best_ask": round(midpoint + 0.01, 2),
                        "midpoint": midpoint,
                        "spread": 0.02,
                        "tick_size": 0.01,
                    },
                )
            append_jsonl(
                run_dir / "fills.jsonl",
                {
                    "type": "simulated_fill",
                    "quote_id": "q1",
                    "timestamp": "2026-05-01T12:00:00+00:00",
                    "market_id": "m1",
                    "token_id": "yes",
                    "side": "bid",
                    "price": 0.5,
                    "size": 5,
                    "evidence_event_id": "book-fill",
                },
            )

            state = build_run_state(run_dir)
            quality = state["fill_quality"]

            self.assertEqual(quality["fills_analyzed"], 1)
            self.assertEqual(quality["adverse_selection_flags"], 1)
            self.assertEqual(quality["horizons"]["30s"]["average_markout"], -0.02)
            self.assertEqual(quality["horizons"]["60s"]["average_markout"], -0.03)
            self.assertEqual(quality["horizons"]["120s"]["average_markout"], -0.04)

    def test_static_market_is_reported_from_quote_diagnostics(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ensure_run_dir(Path(tmp))
            append_jsonl(
                run_dir / "markets.jsonl",
                {
                    "type": "market_filter",
                    "selected": True,
                    "normalized": {
                        "market_id": "m-static",
                        "question": "Static fixture?",
                        "slug": "static-fixture",
                        "token_ids": ["yes"],
                        "outcomes": ["Yes"],
                    },
                },
            )
            for index in range(3):
                append_jsonl(
                    run_dir / "books.jsonl",
                    {
                        "type": "book_snapshot",
                        "event_id": f"book-static-{index}",
                        "timestamp": f"2026-05-01T12:00:{index * 10:02d}+00:00",
                        "market_id": "m-static",
                        "token_id": "yes",
                        "outcome": "Yes",
                        "best_bid": 0.4,
                        "best_ask": 0.46,
                        "midpoint": 0.43,
                        "spread": 0.06,
                        "tick_size": 0.01,
                    },
                )
            append_jsonl(
                run_dir / "quotes.jsonl",
                {
                    "type": "virtual_quote",
                    "quote_id": "q-static",
                    "timestamp": "2026-05-01T12:00:00+00:00",
                    "market_id": "m-static",
                    "token_id": "yes",
                    "side": "bid",
                    "price": 0.41,
                    "size": 5,
                    "tick_size": 0.01,
                    "quote_mode": "one_tick_inside",
                    "expires_at": "2026-05-01T12:00:30+00:00",
                    "source_event_id": "book-static-0",
                },
            )
            append_jsonl(
                run_dir / "risk_events.jsonl",
                {
                    "type": "quote_cancelled",
                    "timestamp": "2026-05-01T12:00:31+00:00",
                    "quote_id": "q-static",
                    "market_id": "m-static",
                    "token_id": "yes",
                    "reason": "quote_expired",
                    "evidence_event_id": "book-static-2",
                },
            )

            state = build_run_state(run_dir)

            self.assertIn("m-static", state["fill_opportunity"]["markets_too_static"])
            self.assertEqual(state["fill_opportunity"]["missed_ticks"]["more"], 1)

    def test_market_suitability_classifies_concentration(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ensure_run_dir(Path(tmp))
            append_jsonl(
                run_dir / "risk_events.jsonl",
                {
                    "type": "run_started",
                    "timestamp": "2026-05-01T12:00:00+00:00",
                    "max_fills_per_market": 8,
                },
            )
            for market_id, token_id in (("m-concentrated", "yes-c"), ("m-balanced", "yes-b")):
                append_jsonl(
                    run_dir / "markets.jsonl",
                    {
                        "type": "market_filter",
                        "selected": True,
                        "normalized": {
                            "market_id": market_id,
                            "question": f"{market_id} fixture?",
                            "slug": market_id,
                            "token_ids": [token_id],
                            "outcomes": ["Yes"],
                        },
                    },
                )
                for index in range(24):
                    append_jsonl(
                        run_dir / "quotes.jsonl",
                        {
                            "type": "virtual_quote",
                            "quote_id": f"{market_id}-q-{index}",
                            "timestamp": f"2026-05-01T12:{index:02d}:00+00:00",
                            "market_id": market_id,
                            "token_id": token_id,
                            "side": "bid",
                            "price": 0.5,
                            "size": 5,
                            "tick_size": 0.01,
                        },
                    )

            def append_fill_with_markouts(market_id: str, token_id: str, index: int, *, adverse: bool) -> None:
                timestamp = datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc) + timedelta(minutes=index * 10)
                midpoint = 0.48 if adverse else 0.51
                append_jsonl(
                    run_dir / "fills.jsonl",
                    {
                        "type": "simulated_fill",
                        "quote_id": f"{market_id}-fill-{index}",
                        "timestamp": timestamp.isoformat(),
                        "market_id": market_id,
                        "token_id": token_id,
                        "side": "bid",
                        "price": 0.5,
                        "size": 5,
                        "evidence_event_id": f"{market_id}-book-fill-{index}",
                    },
                )
                for seconds in (0, 30, 60, 120):
                    append_jsonl(
                        run_dir / "books.jsonl",
                        {
                            "type": "book_snapshot",
                            "event_id": f"{market_id}-book-{index}-{seconds}",
                            "timestamp": (timestamp + timedelta(seconds=seconds)).isoformat(),
                            "market_id": market_id,
                            "token_id": token_id,
                            "outcome": "Yes",
                            "best_bid": round(midpoint - 0.01, 2),
                            "best_ask": round(midpoint + 0.01, 2),
                            "midpoint": midpoint,
                            "spread": 0.02,
                            "tick_size": 0.01,
                        },
                    )

            for index in range(9):
                append_fill_with_markouts("m-concentrated", "yes-c", index, adverse=index < 6)
            for index in range(2):
                append_fill_with_markouts("m-balanced", "yes-b", index, adverse=False)

            state = build_run_state(run_dir)
            suitability = {row["market_id"]: row for row in state["market_suitability"]}

            self.assertEqual(suitability["m-concentrated"]["classification"], "risky_concentrated")
            self.assertEqual(suitability["m-balanced"]["classification"], "candidate")

    def test_same_run_gate_state_replays_into_report_and_dashboard(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = ensure_run_dir(Path(tmp))
            append_jsonl(
                run_dir / "risk_events.jsonl",
                {
                    "type": "same_run_entry_gate",
                    "timestamp": "2026-05-01T12:05:00+00:00",
                    "market_id": "m-gated",
                    "token_id": "yes",
                    "outcome": "Yes",
                    "classification": "risky_concentrated",
                    "reason": "entry_fill_count_reached_market_cap",
                    "threshold": "entry_fill_count_at_market_cap",
                    "source_evidence_event_id": "book-fill-1",
                    "details": {"entry_fill_count": 8, "market_fill_cap": 8},
                },
            )

            state = generate_report(run_dir, dashboard_url="http://127.0.0.1:8771")

            self.assertEqual(
                state["same_run_entry_gates"],
                [
                    {
                        "timestamp": "2026-05-01T12:05:00+00:00",
                        "market_id": "m-gated",
                        "token_id": "yes",
                        "outcome": "Yes",
                        "classification": "risky_concentrated",
                        "reason": "entry_fill_count_reached_market_cap",
                        "threshold": "entry_fill_count_at_market_cap",
                        "source_evidence_event_id": "book-fill-1",
                        "details": {"entry_fill_count": 8, "market_fill_cap": 8},
                    }
                ],
            )
            summary = (run_dir / "summary.md").read_text(encoding="utf-8")
            self.assertIn("## Same-Run Entry Gates", summary)
            self.assertIn("m-gated: classification=risky_concentrated", summary)
            self.assertIn("source_evidence=book-fill-1", summary)
            self.assertIn("Same-Run Entry Gates", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
