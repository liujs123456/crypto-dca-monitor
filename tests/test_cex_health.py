"""Tests for lib/cex_health.py — verdict aggregation logic.

Network-touching functions (check_coingecko_exchange, scan_news_for_exchange) are
tested via dependency injection — we replace them with stubs and verify the
overall_health aggregation behaves correctly across all combinations.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib import cex_health


class TestOverallHealthAggregation(unittest.TestCase):
    def _verdict(self, cg_result, news_result):
        with mock.patch.object(cex_health, "check_coingecko_exchange", return_value=cg_result), \
             mock.patch.object(cex_health, "scan_news_for_exchange", return_value=news_result):
            return cex_health.overall_health()["level"]

    def test_all_green(self):
        self.assertEqual(self._verdict(("green", "ok"), ("green", [])), "green")

    def test_one_yellow_drives_yellow(self):
        self.assertEqual(self._verdict(("yellow", "score 7"), ("green", [])), "yellow")

    def test_one_red_drives_red(self):
        self.assertEqual(self._verdict(("red", "score 4"), ("green", [])), "red")

    def test_red_beats_yellow(self):
        self.assertEqual(self._verdict(("red", "x"), ("yellow", ["news"])), "red")

    def test_unknown_does_not_count_when_other_signal_green(self):
        # CoinGecko unreachable but news clean → still green
        self.assertEqual(self._verdict(("unknown", "down"), ("green", [])), "green")

    def test_unknown_ignored_when_other_signal_yellow(self):
        self.assertEqual(self._verdict(("unknown", "down"), ("yellow", ["x"])), "yellow")

    def test_all_unknown_falls_back_to_yellow(self):
        # If we have no real info at all, conservatively warn (we don't know is not the
        # same as we know it's fine)
        self.assertEqual(self._verdict(("unknown", "down1"), ("unknown", ["down2"])), "yellow")


class TestNewsScanSeverityRules(unittest.TestCase):
    """The keyword-severity logic is the most error-prone — verify it directly."""

    def _make_xml(self, headlines: list[str]) -> str:
        items = "".join(f"<item><title>{h}</title></item>" for h in headlines)
        return f"<?xml version='1.0'?><rss><channel>{items}</channel></rss>"

    def test_no_mention_of_exchange_returns_green(self):
        xml = self._make_xml(["Apple reports earnings", "Fed holds rates"])
        with mock.patch.object(cex_health, "_http_get_text", return_value=xml):
            level, _ = cex_health.scan_news_for_exchange("OKX")
            self.assertEqual(level, "green")

    def test_mention_without_negative_keyword_returns_green(self):
        xml = self._make_xml(["OKX launches new product"])
        with mock.patch.object(cex_health, "_http_get_text", return_value=xml):
            level, _ = cex_health.scan_news_for_exchange("OKX")
            self.assertEqual(level, "green")

    def test_single_critical_keyword_returns_red(self):
        xml = self._make_xml(["OKX withdrawals halted reportedly"])
        with mock.patch.object(cex_health, "_http_get_text", return_value=xml):
            level, matches = cex_health.scan_news_for_exchange("OKX")
            self.assertEqual(level, "red")
            self.assertGreaterEqual(len(matches), 1)

    def test_single_warning_keyword_returns_yellow(self):
        # Only first feed has the headline; other feeds return None
        xml = self._make_xml(["OKX faces investigation by regulator"])
        side_effect = [xml, None, None]
        with mock.patch.object(cex_health, "_http_get_text", side_effect=side_effect):
            level, _ = cex_health.scan_news_for_exchange("OKX")
            self.assertEqual(level, "yellow")

    def test_same_warning_in_multiple_feeds_escalates_to_red(self):
        # If 2+ different sources independently report the same warning, treat as more credible
        xml = self._make_xml(["OKX faces investigation by regulator"])
        side_effect = [xml, xml, None]
        with mock.patch.object(cex_health, "_http_get_text", side_effect=side_effect):
            level, _ = cex_health.scan_news_for_exchange("OKX")
            self.assertEqual(level, "red")

    def test_multiple_warning_keywords_escalate_to_red(self):
        # 2 distinct warning matches across feeds → escalate to red
        xml = self._make_xml(["OKX investigation deepens", "OKX subpoena issued"])
        with mock.patch.object(cex_health, "_http_get_text", return_value=xml):
            level, _ = cex_health.scan_news_for_exchange("OKX")
            self.assertEqual(level, "red")

    def test_unreachable_feed_returns_green_for_news(self):
        # If RSS sources all down, we have no news signal — return green (the
        # CoinGecko side will independently flag "unknown" if relevant)
        with mock.patch.object(cex_health, "_http_get_text", return_value=None):
            level, matches = cex_health.scan_news_for_exchange("OKX")
            self.assertEqual(level, "green")
            self.assertEqual(matches, [])


if __name__ == "__main__":
    unittest.main()
