"""Tests for lib/state_store.py — corruption recovery + schema validation."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import state_store


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        self.path = Path(self.tmp.name)
        self.tmp.close()

    def tearDown(self):
        if self.path.exists():
            self.path.unlink()

    def test_missing_file_returns_default_no_recovery(self):
        self.path.unlink()
        state, reason = state_store.load(self.path)
        self.assertIsNone(reason)
        self.assertEqual(state["tier"], "GREEN")
        self.assertTrue(all(state["armed"].values()))

    def test_valid_file_loads_unchanged(self):
        valid = {
            "tier": "T2",
            "armed": {"T1": False, "T2": False, "T3": True, "T4": True},
            "last_price": 70000.0,
            "last_ref": 80000.0,
            "last_check_utc": "2026-04-28T10:00:00+00:00",
        }
        self.path.write_text(json.dumps(valid))
        state, reason = state_store.load(self.path)
        self.assertIsNone(reason)
        self.assertEqual(state["tier"], "T2")
        self.assertFalse(state["armed"]["T1"])

    def test_malformed_json_returns_default_with_reason(self):
        self.path.write_text("{not valid json")
        state, reason = state_store.load(self.path)
        self.assertIsNotNone(reason)
        self.assertIn("corrupted JSON", reason)
        self.assertEqual(state["tier"], "GREEN")
        self.assertTrue(all(state["armed"].values()))

    def test_missing_required_keys(self):
        self.path.write_text(json.dumps({"tier": "GREEN"}))
        state, reason = state_store.load(self.path)
        self.assertIn("missing keys", reason)
        self.assertEqual(state["tier"], "GREEN")

    def test_invalid_tier_value(self):
        self.path.write_text(json.dumps({
            "tier": "T99",
            "armed": {"T1": True, "T2": True, "T3": True, "T4": True},
        }))
        _, reason = state_store.load(self.path)
        self.assertIn("invalid tier", reason)

    def test_armed_not_dict(self):
        self.path.write_text(json.dumps({"tier": "GREEN", "armed": [True, True]}))
        _, reason = state_store.load(self.path)
        self.assertIn("not a dict", reason)

    def test_armed_keys_mismatch(self):
        self.path.write_text(json.dumps({
            "tier": "GREEN",
            "armed": {"T1": True, "T2": True},
        }))
        _, reason = state_store.load(self.path)
        self.assertIn("armed keys mismatch", reason)

    def test_armed_value_not_bool(self):
        self.path.write_text(json.dumps({
            "tier": "GREEN",
            "armed": {"T1": True, "T2": True, "T3": "yes", "T4": True},
        }))
        _, reason = state_store.load(self.path)
        self.assertIn("not a bool", reason)

    def test_root_not_object(self):
        self.path.write_text(json.dumps([1, 2, 3]))
        _, reason = state_store.load(self.path)
        self.assertIn("not a JSON object", reason)


class TestSave(unittest.TestCase):
    def test_roundtrip_with_nested_dir_creation(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "state.json"
            original = state_store.default_state()
            state_store.save(path, original)
            loaded, reason = state_store.load(path)
            self.assertIsNone(reason)
            self.assertEqual(loaded["tier"], original["tier"])
            self.assertEqual(loaded["armed"], original["armed"])

    def test_save_is_deterministic_sorted(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "state.json"
            state_store.save(path, {
                "z_last": "x",
                "tier": "GREEN",
                "armed": {"T1": True, "T2": True, "T3": True, "T4": True},
            })
            content = path.read_text()
            self.assertLess(content.index('"armed"'), content.index('"tier"'))


if __name__ == "__main__":
    unittest.main()
