"""Tests for the headline-dedup logic in scripts/morning_briefing.py."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest import mock

# Stub required env vars before import (module reads them at module level)
os.environ.setdefault("NTFY_TOPIC", "test-topic")
os.environ.setdefault("GROQ_API_KEY", "test-key")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Avoid module-level env crash by mocking before import
with mock.patch.dict(os.environ, {"NTFY_TOPIC": "x", "GROQ_API_KEY": "y"}):
    from scripts.morning_briefing import dedupe_headlines, _normalize


class TestNormalize(unittest.TestCase):
    def test_lowercases_and_strips_punctuation(self):
        self.assertEqual(_normalize("Fed Cuts! 25bps."), "fed cuts 25bps")

    def test_collapses_whitespace(self):
        self.assertEqual(_normalize("a   b\t\nc"), "a b c")


class TestDedupe(unittest.TestCase):
    def test_drops_exact_duplicates_across_sources(self):
        headlines = [
            ("A", ["Fed cuts rates 25bps to support economy"]),
            ("B", ["Fed cuts rates 25bps to support economy"]),
        ]
        out = dedupe_headlines(headlines)
        self.assertEqual(len(out[0][1]), 1)
        self.assertEqual(len(out[1][1]), 0)

    def test_keeps_distinct_topics(self):
        headlines = [
            ("A", [
                "Fed cuts rates 25 basis points to support economy",
                "Trump signs new tariff bill on China",
                "Bitcoin hits new all-time high above 80k",
            ]),
        ]
        out = dedupe_headlines(headlines)
        self.assertEqual(len(out[0][1]), 3)

    def test_drops_minor_phrasing_variants(self):
        headlines = [
            ("A", ["Fed cuts rates 25 basis points to support economy"]),
            ("B", ["Federal Reserve cuts rates 25 basis points to support economy"]),
        ]
        out = dedupe_headlines(headlines)
        self.assertEqual(len(out[0][1]), 1)
        self.assertEqual(len(out[1][1]), 0)

    def test_preserves_source_order(self):
        headlines = [
            ("A", ["Apple reports record quarterly earnings beat"]),
            ("B", ["Apple reports record quarterly earnings beat"]),  # dup
            ("C", ["Bitcoin treasury company files for bankruptcy"]),
        ]
        out = dedupe_headlines(headlines)
        self.assertEqual(out[0][1], ["Apple reports record quarterly earnings beat"])
        self.assertEqual(out[1][1], [])
        self.assertEqual(out[2][1], ["Bitcoin treasury company files for bankruptcy"])

    def test_empty_input_returns_empty(self):
        self.assertEqual(dedupe_headlines([]), [])

    def test_filters_blank_normalized_strings(self):
        headlines = [("A", ["", "   ", "Real headline"])]
        out = dedupe_headlines(headlines)
        self.assertEqual(out[0][1], ["Real headline"])


if __name__ == "__main__":
    unittest.main()
