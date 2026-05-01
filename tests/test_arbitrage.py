from __future__ import annotations

import unittest

from polymarket_paper.arbitrage import scan_binary, scan_multi_outcome


class ArbitrageMathTests(unittest.TestCase):
    def test_binary_no_arb(self):
        result = scan_binary("m1", 0.51, 0.50)
        self.assertFalse(result["is_alert"])
        self.assertEqual(result["type"], "binary_no_arb_scan")

    def test_binary_arb(self):
        result = scan_binary("m1", 0.49, 0.49)
        self.assertTrue(result["is_alert"])
        self.assertEqual(result["type"], "binary_arb_alert")

    def test_multi_outcome_no_arb(self):
        result = scan_multi_outcome("m2", [0.25, 0.3, 0.46])
        self.assertFalse(result["is_alert"])

    def test_multi_outcome_arb(self):
        result = scan_multi_outcome("m2", [0.2, 0.25, 0.5])
        self.assertTrue(result["is_alert"])
        self.assertEqual(result["type"], "multi_arb_alert")


if __name__ == "__main__":
    unittest.main()
