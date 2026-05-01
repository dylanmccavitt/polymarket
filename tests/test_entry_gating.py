from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from polymarket_paper.runner import load_entry_blocked_markets


class EntryGatingTests(unittest.TestCase):
    def test_loads_blocked_markets_from_prior_dashboard_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "dashboard_state.json").write_text(
                json.dumps(
                    {
                        "market_suitability": [
                            {"market_id": "m-risky", "classification": "risky_concentrated"},
                            {"market_id": "m-adverse", "classification": "too_adverse"},
                            {"market_id": "m-candidate", "classification": "candidate"},
                            {"market_id": "m-thin", "classification": "insufficient_evidence"},
                        ]
                    }
                ),
                encoding="utf-8",
            )

            blocked = load_entry_blocked_markets(run_dir)

            self.assertEqual(
                blocked,
                {
                    "m-risky": "risky_concentrated",
                    "m-adverse": "too_adverse",
                },
            )


if __name__ == "__main__":
    unittest.main()
