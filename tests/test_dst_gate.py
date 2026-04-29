"""Tests for the DST tolerance window in lib/dst_gate.py."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import dst_gate

PT = ZoneInfo("America/Los_Angeles")


def _patched_now(hour: int, minute: int):
    """Build a datetime in PT and return a context manager that patches dst_gate.datetime."""
    fake_now = datetime(2026, 5, 1, hour, minute, tzinfo=PT)
    return mock.patch.object(
        dst_gate, "datetime",
        wraps=datetime,
        **{"now.return_value": fake_now},
    )


class TestIsPtNow(unittest.TestCase):
    def test_exact_match(self):
        with _patched_now(7, 17):
            self.assertTrue(dst_gate.is_pt_now(7, 17))

    def test_within_tolerance_after(self):
        # 30 min tolerance — 7:46 is within of 7:17? 29 min apart → yes
        with _patched_now(7, 46):
            self.assertTrue(dst_gate.is_pt_now(7, 17))

    def test_within_tolerance_before(self):
        with _patched_now(6, 48):
            self.assertTrue(dst_gate.is_pt_now(7, 17))

    def test_outside_tolerance(self):
        with _patched_now(7, 50):
            self.assertFalse(dst_gate.is_pt_now(7, 17))
        with _patched_now(6, 30):
            self.assertFalse(dst_gate.is_pt_now(7, 17))

    def test_completely_different_hour(self):
        with _patched_now(15, 0):
            self.assertFalse(dst_gate.is_pt_now(7, 17))


class TestCli(unittest.TestCase):
    def test_skip_if_not_returns_skip_when_off(self):
        with _patched_now(15, 0), mock.patch.object(sys, "argv", ["dst_gate", "skip-if-not", "7", "17"]):
            self.assertEqual(dst_gate.main(), 0)  # exit 0 = skip

    def test_skip_if_not_returns_proceed_when_match(self):
        with _patched_now(7, 17), mock.patch.object(sys, "argv", ["dst_gate", "skip-if-not", "7", "17"]):
            self.assertEqual(dst_gate.main(), 1)  # exit 1 = proceed

    def test_bad_args_returns_2(self):
        with mock.patch.object(sys, "argv", ["dst_gate", "wrong"]):
            self.assertEqual(dst_gate.main(), 2)


if __name__ == "__main__":
    unittest.main()
