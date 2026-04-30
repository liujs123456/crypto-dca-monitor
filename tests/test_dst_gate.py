"""Tests for the DST gate in lib/dst_gate.py."""
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import dst_gate

PT = ZoneInfo("America/Los_Angeles")


def _patched_now(hour: int, minute: int, *, month: int = 5):
    """Patch dst_gate.datetime so .now(PT) returns a fixed PT clock.

    Default month=5 (May) → DST active (PDT). Use month=12 to simulate PST.
    """
    fake_now = datetime(2026, month, 15, hour, minute, tzinfo=PT)
    return mock.patch.object(
        dst_gate, "datetime",
        wraps=datetime,
        **{"now.return_value": fake_now},
    )


class TestIsPtNow(unittest.TestCase):
    def test_exact_match(self):
        with _patched_now(7, 17):
            self.assertTrue(dst_gate.is_pt_now(7, 17))

    def test_within_tolerance(self):
        with _patched_now(7, 46):
            self.assertTrue(dst_gate.is_pt_now(7, 17))
        with _patched_now(6, 48):
            self.assertTrue(dst_gate.is_pt_now(7, 17))

    def test_outside_tolerance(self):
        with _patched_now(7, 50):
            self.assertFalse(dst_gate.is_pt_now(7, 17))
        with _patched_now(15, 0):
            self.assertFalse(dst_gate.is_pt_now(7, 17))


class TestIsCurrentlyPdt(unittest.TestCase):
    def test_may_is_pdt(self):
        with _patched_now(12, 0, month=5):
            self.assertTrue(dst_gate.is_currently_pdt())

    def test_december_is_pst(self):
        with _patched_now(12, 0, month=12):
            self.assertFalse(dst_gate.is_currently_pdt())


class TestSkipWrongSlot(unittest.TestCase):
    PDT_CRON = "17 14 * * *"
    PST_CRON = "17 15 * * *"

    def _argv(self, triggered: str):
        return ["dst_gate", "skip-wrong-slot", triggered, self.PDT_CRON, self.PST_CRON]

    def test_pdt_season_pdt_cron_proceeds(self):
        with _patched_now(7, 17, month=5), mock.patch.object(sys, "argv", self._argv(self.PDT_CRON)):
            self.assertEqual(dst_gate.main(), 1)

    def test_pdt_season_pst_cron_skips(self):
        with _patched_now(7, 17, month=5), mock.patch.object(sys, "argv", self._argv(self.PST_CRON)):
            self.assertEqual(dst_gate.main(), 0)

    def test_pst_season_pst_cron_proceeds(self):
        with _patched_now(7, 17, month=12), mock.patch.object(sys, "argv", self._argv(self.PST_CRON)):
            self.assertEqual(dst_gate.main(), 1)

    def test_pst_season_pdt_cron_skips(self):
        with _patched_now(7, 17, month=12), mock.patch.object(sys, "argv", self._argv(self.PDT_CRON)):
            self.assertEqual(dst_gate.main(), 0)

    def test_proceeds_even_when_clock_drifted_hours(self):
        """Critical: GH Actions cron can fire 2-3h late. The gate must NOT skip
        based on wall clock — only on whether the cron *string* matches the
        active DST half. This is the bug that caused silent skips."""
        # PDT season, PDT cron triggered, but actual fire time is 9:55 AM PT
        # (the cron said 7:17, GH delayed 2h38m). Old gate would skip; new gate
        # must proceed because the triggered cron matches the active slot.
        with _patched_now(9, 55, month=5), mock.patch.object(sys, "argv", self._argv(self.PDT_CRON)):
            self.assertEqual(dst_gate.main(), 1)

    def test_empty_triggered_cron_proceeds(self):
        # workflow_dispatch leaves github.event.schedule empty
        with mock.patch.object(sys, "argv", self._argv("")):
            self.assertEqual(dst_gate.main(), 1)

    def test_bad_args_returns_2(self):
        with mock.patch.object(sys, "argv", ["dst_gate", "skip-wrong-slot", "only-one"]):
            self.assertEqual(dst_gate.main(), 2)


class TestLegacyCli(unittest.TestCase):
    def test_skip_if_not_off_skips(self):
        with _patched_now(15, 0), mock.patch.object(sys, "argv", ["dst_gate", "skip-if-not", "7", "17"]):
            self.assertEqual(dst_gate.main(), 0)

    def test_skip_if_not_match_proceeds(self):
        with _patched_now(7, 17), mock.patch.object(sys, "argv", ["dst_gate", "skip-if-not", "7", "17"]):
            self.assertEqual(dst_gate.main(), 1)

    def test_unknown_mode_returns_2(self):
        with mock.patch.object(sys, "argv", ["dst_gate", "wrong-mode"]):
            self.assertEqual(dst_gate.main(), 2)


if __name__ == "__main__":
    unittest.main()
