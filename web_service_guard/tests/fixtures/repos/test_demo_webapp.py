"""Tests for the buggy demo web app."""

from __future__ import annotations

__test__ = False

import sys
from pathlib import Path
import unittest

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from demo_webapp import calculate_total_from_query


class CalculateTotalTests(unittest.TestCase):
    def test_total_with_discount(self) -> None:
        self.assertEqual(calculate_total_from_query("subtotal=100&discount=15"), 85)

    def test_total_without_discount_defaults_to_zero(self) -> None:
        self.assertEqual(calculate_total_from_query("subtotal=100"), 100)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
