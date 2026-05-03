"""Tests for lib/onboarding.py — cold-storage onboarding tracker."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import onboarding


class TestDefaultState(unittest.TestCase):
    def test_default_all_steps_false(self):
        state = onboarding.default_state()
        for step, _ in onboarding.STEPS:
            self.assertFalse(state[step])
            self.assertIsNone(state[f"{step}_at"])

    def test_default_not_ready(self):
        self.assertFalse(onboarding.is_ready(onboarding.default_state()))


class TestProgress(unittest.TestCase):
    def test_zero_completed(self):
        s = onboarding.default_state()
        p = onboarding.progress_summary(s)
        self.assertEqual(p["completed"], 0)
        self.assertEqual(p["total"], 5)
        self.assertFalse(p["ready"])
        self.assertEqual(p["next_step"], onboarding.STEPS[0][1])

    def test_partial_completion(self):
        s = onboarding.default_state()
        s = onboarding.mark_step(s, "device_purchased", device_model="Ledger Nano X")
        p = onboarding.progress_summary(s)
        self.assertEqual(p["completed"], 1)
        self.assertFalse(p["ready"])
        self.assertEqual(p["next_step"], onboarding.STEPS[1][1])

    def test_all_steps_ready_only_with_backup_count(self):
        s = onboarding.default_state()
        for step, _ in onboarding.STEPS:
            s = onboarding.mark_step(s, step)
        # Even with all steps marked, ready requires backup_count >= 1
        self.assertEqual(s["seed_backup_count"], 0)
        self.assertFalse(onboarding.is_ready(s))

    def test_all_steps_plus_backup_is_ready(self):
        s = onboarding.default_state()
        for step, _ in onboarding.STEPS:
            s = onboarding.mark_step(s, step)
        s["seed_backup_count"] = 2
        self.assertTrue(onboarding.is_ready(s))


class TestMarkStep(unittest.TestCase):
    def test_mark_sets_timestamp(self):
        s = onboarding.default_state()
        s = onboarding.mark_step(s, "device_purchased")
        self.assertTrue(s["device_purchased"])
        self.assertIsNotNone(s["device_purchased_at"])
        # Timestamp is iso format
        self.assertIn("T", s["device_purchased_at"])

    def test_mark_with_extra_fields(self):
        s = onboarding.default_state()
        s = onboarding.mark_step(s, "device_purchased", device_model="Ledger Nano X")
        self.assertEqual(s["device_model"], "Ledger Nano X")

    def test_unmark_clears_timestamp(self):
        s = onboarding.default_state()
        s = onboarding.mark_step(s, "device_purchased")
        s = onboarding.mark_step(s, "device_purchased", done=False)
        self.assertFalse(s["device_purchased"])
        self.assertIsNone(s["device_purchased_at"])

    def test_mark_unknown_step_raises(self):
        with self.assertRaises(ValueError):
            onboarding.mark_step(onboarding.default_state(), "not_a_real_step")

    def test_ready_flag_auto_updates(self):
        s = onboarding.default_state()
        s["seed_backup_count"] = 1
        for step, _ in onboarding.STEPS:
            s = onboarding.mark_step(s, step)
        self.assertTrue(s["ready_for_migration"])


class TestPersistence(unittest.TestCase):
    def test_load_missing_returns_default(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            s = onboarding.load(p)
            self.assertEqual(s, onboarding.default_state())

    def test_load_corrupted_returns_default(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            p.write_text("{not valid")
            s = onboarding.load(p)
            self.assertEqual(s["device_purchased"], False)

    def test_load_backfills_missing_keys(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            # Old version without seed_backup_count
            p.write_text(json.dumps({"device_purchased": True}))
            s = onboarding.load(p)
            self.assertTrue(s["device_purchased"])
            self.assertEqual(s["seed_backup_count"], 0)
            self.assertIn("notes", s)

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.json"
            s = onboarding.default_state()
            s = onboarding.mark_step(s, "device_purchased", device_model="Ledger Nano X")
            onboarding.save(p, s)
            loaded = onboarding.load(p)
            self.assertEqual(loaded["device_model"], "Ledger Nano X")
            self.assertTrue(loaded["device_purchased"])


class TestRenderProgressBlock(unittest.TestCase):
    def test_renders_progress_bar(self):
        s = onboarding.default_state()
        block = onboarding.render_progress_block(s)
        self.assertIn("[░░░░░]", block)
        self.assertIn("0/5", block)

    def test_renders_ready_state(self):
        s = onboarding.default_state()
        for step, _ in onboarding.STEPS:
            s = onboarding.mark_step(s, step)
        s["seed_backup_count"] = 2
        block = onboarding.render_progress_block(s)
        self.assertIn("✅", block)
        self.assertIn("100%", block)


if __name__ == "__main__":
    unittest.main()
