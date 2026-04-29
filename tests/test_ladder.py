"""Tests for the dip-ladder state machine in lib/ladder.py."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import ladder


class TestTierPrices(unittest.TestCase):
    def test_tier_prices_at_80k_ref(self):
        p = ladder.tier_prices(80000)
        self.assertEqual(p["WATCH"], 73600.0)  # -8%
        self.assertEqual(p["T1"], 72000.0)     # -10%
        self.assertEqual(p["T2"], 68000.0)     # -15%
        self.assertEqual(p["T3"], 62400.0)     # -22%
        self.assertEqual(p["T4"], 54400.0)     # -32%

    def test_tier_prices_scale_linearly_with_ref(self):
        p1 = ladder.tier_prices(50000)
        p2 = ladder.tier_prices(100000)
        for tier in ("T1", "T2", "T3", "T4", "WATCH"):
            self.assertAlmostEqual(p2[tier] / p1[tier], 2.0, places=2)


class TestClassifyState(unittest.TestCase):
    REF = 80000

    def test_above_ref_is_green(self):
        self.assertEqual(ladder.classify_state(85000, self.REF), "GREEN")
        self.assertEqual(ladder.classify_state(80000, self.REF), "GREEN")
        self.assertEqual(ladder.classify_state(73700, self.REF), "GREEN")

    def test_watch_zone(self):
        self.assertEqual(ladder.classify_state(73599, self.REF), "WATCH")
        self.assertEqual(ladder.classify_state(72500, self.REF), "WATCH")
        self.assertEqual(ladder.classify_state(72001, self.REF), "WATCH")

    def test_tier_boundaries(self):
        self.assertEqual(ladder.classify_state(72000 - 1, self.REF), "T1")
        self.assertEqual(ladder.classify_state(68000 - 1, self.REF), "T2")
        self.assertEqual(ladder.classify_state(62400 - 1, self.REF), "T3")
        self.assertEqual(ladder.classify_state(54400 - 1, self.REF), "T4")
        self.assertEqual(ladder.classify_state(20000, self.REF), "T4")


class TestUpdateArmed(unittest.TestCase):
    REF = 80000

    def test_disarmed_tier_rearms_after_5_percent_rebound(self):
        # T1 trigger = 72000, rearm threshold = 72000 * 1.05 = 75600
        armed = {"T1": False, "T2": True, "T3": True, "T4": True}
        # Below threshold — stays disarmed
        new = ladder.update_armed(armed, 75599, self.REF)
        self.assertFalse(new["T1"])
        # At threshold — re-arms
        new = ladder.update_armed(armed, 75600, self.REF)
        self.assertTrue(new["T1"])

    def test_armed_tier_unaffected(self):
        armed = ladder.default_armed()
        new = ladder.update_armed(armed, 60000, self.REF)
        self.assertEqual(new, armed)

    def test_multiple_tiers_rearm_independently(self):
        # Both T1 and T2 disarmed; price between T1 rearm (75600) and T2 rearm (71400)
        armed = {"T1": False, "T2": False, "T3": True, "T4": True}
        new = ladder.update_armed(armed, 72000, self.REF)
        self.assertFalse(new["T1"])  # 72000 < 75600
        self.assertTrue(new["T2"])   # 72000 >= 71400


class TestDecideNotification(unittest.TestCase):
    def test_green_to_watch_notifies(self):
        kind, _ = ladder.decide_notification("WATCH", "GREEN", ladder.default_armed())
        self.assertEqual(kind, "WATCH")

    def test_watch_to_t1_fires_and_disarms(self):
        kind, armed = ladder.decide_notification("T1", "WATCH", ladder.default_armed())
        self.assertEqual(kind, "T1")
        self.assertFalse(armed["T1"])
        self.assertTrue(armed["T2"])  # other tiers untouched

    def test_disarmed_tier_does_not_refire(self):
        armed = {"T1": False, "T2": True, "T3": True, "T4": True}
        kind, new_armed = ladder.decide_notification("T1", "GREEN", armed)
        self.assertIsNone(kind)
        self.assertEqual(new_armed, armed)

    def test_recovery_to_green_notifies(self):
        kind, _ = ladder.decide_notification("GREEN", "T2", ladder.default_armed())
        self.assertEqual(kind, "RECOVERED")

    def test_no_notify_when_state_unchanged(self):
        kind, _ = ladder.decide_notification("WATCH", "WATCH", ladder.default_armed())
        self.assertIsNone(kind)

    def test_skipping_tiers_in_one_check(self):
        # Price crashes from GREEN straight to T3 in one 2h window — should fire T3
        kind, armed = ladder.decide_notification("T3", "GREEN", ladder.default_armed())
        self.assertEqual(kind, "T3")
        self.assertFalse(armed["T3"])
        # T1 and T2 stay armed (they didn't fire)
        self.assertTrue(armed["T1"])
        self.assertTrue(armed["T2"])


if __name__ == "__main__":
    unittest.main()
