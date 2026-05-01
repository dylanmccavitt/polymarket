from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from polymarket_paper.filters import journal_market


NOW = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)


def base_market(**overrides):
    raw = {
        "id": "m-good",
        "slug": "btc-above-150k",
        "question": "Will Bitcoin hit $150k by June 30, 2026?",
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "enableOrderBook": True,
        "endDate": (NOW + timedelta(days=60)).isoformat(),
        "updatedAt": (NOW - timedelta(minutes=10)).isoformat(),
        "volume24hr": 100000,
        "liquidityNum": 25000,
        "spread": 0.02,
        "orderPriceMinTickSize": 0.01,
        "orderMinSize": 5,
        "clobTokenIds": '["yes-token", "no-token"]',
        "outcomes": '["Yes", "No"]',
        "bestBid": 0.49,
        "bestAsk": 0.51,
        "negRisk": False,
        "negRiskOther": False,
        "resolutionSource": "https://www.binance.com/",
        "tags": [{"label": "Crypto"}],
        "feeSchedule": {"rate": 0.04},
    }
    raw.update(overrides)
    return raw


class MarketFilterTests(unittest.TestCase):
    def test_selected_tight_spread_market(self):
        row = journal_market(base_market(), now=NOW)
        self.assertTrue(row["selected"])
        self.assertEqual(row["decision_reason"], "selected")

    def test_skip_reasons_cover_trust_boundaries(self):
        cases = {
            "closed": base_market(id="closed", closed=True),
            "expired": base_market(id="expired", endDate=(NOW - timedelta(minutes=1)).isoformat()),
            "stale_metadata": base_market(id="stale", updatedAt=(NOW - timedelta(hours=12)).isoformat()),
            "non_orderbook": base_market(id="non-ob", enableOrderBook=False),
            "metadata_missing:clob_token_ids": base_market(id="missing-token", clobTokenIds='["only-one"]'),
            "metadata_missing:end_date": base_market(id="missing-end", endDate=None),
            "wide_spread": base_market(id="wide", spread=0.08),
            "negative_risk_skipped": base_market(id="neg", negRisk=True),
            "metadata_missing:best_bid_ask": base_market(id="missing-book", bestBid=None),
            "low_volume_24h": base_market(id="low-volume", volume24hr=10),
            "low_liquidity": base_market(id="low-liq", liquidityNum=10),
        }
        for expected, raw in cases.items():
            with self.subTest(expected=expected):
                row = journal_market(raw, now=NOW)
                self.assertFalse(row["selected"])
                self.assertEqual(row["skip_reason"], expected)


if __name__ == "__main__":
    unittest.main()
