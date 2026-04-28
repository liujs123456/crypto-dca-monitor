"""Unit tests for fetch_position.py — stdlib only (unittest + unittest.mock).

Run:
    python3 -m unittest discover -s claude -p "test_*.py" -v
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import unittest
import urllib.error
from io import StringIO
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_position as fp


class PureFunctions(unittest.TestCase):
    def test_sign_deterministic(self):
        self.assertEqual(fp._sign("secret", "prehash"), fp._sign("secret", "prehash"))

    def test_sign_known_value(self):
        expected = base64.b64encode(
            hmac.new(b"abc", b"def", hashlib.sha256).digest()
        ).decode()
        self.assertEqual(fp._sign("abc", "def"), expected)

    def test_sign_changes_with_input(self):
        self.assertNotEqual(fp._sign("a", "x"), fp._sign("a", "y"))
        self.assertNotEqual(fp._sign("a", "x"), fp._sign("b", "x"))

    def test_ts_format(self):
        ts = fp._ts()
        self.assertEqual(len(ts), 24)
        self.assertTrue(ts.endswith("Z"))
        self.assertEqual(ts[10], "T")

    def test_coin_detail_found(self):
        bal = {"data": [{"details": [
            {"ccy": "BTC", "cashBal": "1.0"},
            {"ccy": "USDT", "cashBal": "100"},
        ]}]}
        self.assertEqual(fp._coin_detail(bal, "BTC")["cashBal"], "1.0")
        self.assertEqual(fp._coin_detail(bal, "USDT")["cashBal"], "100")

    def test_coin_detail_missing(self):
        self.assertEqual(
            fp._coin_detail({"data": [{"details": []}]}, "BTC"), {}
        )


class Ladder(unittest.TestCase):
    def setUp(self):
        os.environ["BTC_REF_PRICE"] = "100000"

    def tearDown(self):
        os.environ.pop("BTC_REF_PRICE", None)

    def test_tier_thresholds(self):
        result = fp.compute_ladder(100000)
        self.assertEqual(result["ref"], 100000)
        self.assertEqual(result["watch"], 92000)
        self.assertEqual(result["t1"], 90000)
        self.assertEqual(result["t2"], 85000)
        self.assertEqual(result["t3"], 78000)
        self.assertEqual(result["t4"], 68000)

    def test_state_green(self):
        self.assertEqual(fp.compute_ladder(95000)["current_state"], "GREEN")

    def test_state_watch_boundary(self):
        self.assertEqual(fp.compute_ladder(91999)["current_state"], "WATCH")
        self.assertEqual(fp.compute_ladder(92000)["current_state"], "GREEN")

    def test_state_t1(self):
        self.assertEqual(fp.compute_ladder(89999)["current_state"], "T1")

    def test_state_t2(self):
        self.assertEqual(fp.compute_ladder(84999)["current_state"], "T2")

    def test_state_t3(self):
        self.assertEqual(fp.compute_ladder(77999)["current_state"], "T3")

    def test_state_t4(self):
        self.assertEqual(fp.compute_ladder(50000)["current_state"], "T4")

    def test_default_ref(self):
        os.environ.pop("BTC_REF_PRICE", None)
        self.assertEqual(fp.compute_ladder(70000)["ref"], 79500)


class PnL(unittest.TestCase):
    def test_profit(self):
        pnl = fp.compute_pnl(
            {"last": 80000, "open24h": 78000, "change24h_pct": 2.56},
            {
                "btc": 1.0,
                "btc_avg_cost": 70000,
                "usdt_spot": 100,
                "usdt_earn_amt": 200,
                "usdt_earn_interest": 5,
            },
        )
        self.assertEqual(pnl["btc_value_usd"], 80000.0)
        self.assertEqual(pnl["total_usd"], 80300.0)
        self.assertEqual(pnl["unrealized_pl"], 10000.0)
        self.assertAlmostEqual(pnl["unrealized_pl_pct"], 14.29, places=2)

    def test_loss(self):
        pnl = fp.compute_pnl(
            {"last": 60000, "open24h": 65000, "change24h_pct": -7.69},
            {
                "btc": 0.5,
                "btc_avg_cost": 70000,
                "usdt_spot": 100,
                "usdt_earn_amt": 0,
                "usdt_earn_interest": 0,
            },
        )
        self.assertEqual(pnl["btc_value_usd"], 30000.0)
        self.assertEqual(pnl["total_usd"], 30100.0)
        self.assertEqual(pnl["unrealized_pl"], -5000.0)
        self.assertAlmostEqual(pnl["unrealized_pl_pct"], -14.29, places=2)

    def test_zero_btc_no_division_error(self):
        pnl = fp.compute_pnl(
            {"last": 80000, "open24h": 78000, "change24h_pct": 2.56},
            {
                "btc": 0,
                "btc_avg_cost": 0,
                "usdt_spot": 1000,
                "usdt_earn_amt": 500,
                "usdt_earn_interest": 0,
            },
        )
        self.assertEqual(pnl["unrealized_pl"], 0.0)
        self.assertEqual(pnl["unrealized_pl_pct"], 0.0)
        self.assertEqual(pnl["total_usd"], 1500.0)


class FetchPrice(unittest.TestCase):
    @patch.object(fp, "_http_get")
    def test_normal(self, mock_get):
        mock_get.return_value = {"data": [{"last": "71200", "open24h": "70100"}]}
        r = fp.fetch_price()
        self.assertEqual(r["last"], 71200.0)
        self.assertEqual(r["open24h"], 70100.0)
        self.assertAlmostEqual(r["change24h_pct"], 1.57, places=2)

    @patch.object(fp, "_http_get")
    def test_zero_open24h_does_not_divide(self, mock_get):
        mock_get.return_value = {"data": [{"last": "71200", "open24h": "0"}]}
        self.assertEqual(fp.fetch_price()["change24h_pct"], 0.0)


class FetchDcaToday(unittest.TestCase):
    @patch.object(fp, "okx_signed_get")
    def test_no_orders(self, mock_get):
        mock_get.return_value = {"data": []}
        self.assertEqual(
            fp.fetch_dca_today(),
            {"count": 0, "total_usd": 0.0, "avg_px": 0.0},
        )

    @patch.object(fp, "okx_signed_get")
    def test_filters_buy_filled(self, mock_get):
        mock_get.return_value = {"data": [
            {"side": "buy", "state": "filled", "accFillSz": "0.001", "avgPx": "70000"},
            {"side": "buy", "state": "canceled", "accFillSz": "0", "avgPx": "0"},
            {"side": "sell", "state": "filled", "accFillSz": "0.001", "avgPx": "70000"},
            {"side": "buy", "state": "filled", "accFillSz": "0.0005", "avgPx": "72000"},
        ]}
        r = fp.fetch_dca_today()
        self.assertEqual(r["count"], 2)
        self.assertAlmostEqual(r["total_usd"], 0.001 * 70000 + 0.0005 * 72000, places=2)
        self.assertEqual(r["avg_px"], round((70000 + 72000) / 2))


class OkxSignedGet(unittest.TestCase):
    @patch.dict(os.environ, {"OKX_API_KEY": "k", "OKX_SECRET": "s", "OKX_PASSPHRASE": "p"})
    @patch.object(fp, "_http_get")
    def test_includes_required_headers(self, mock_get):
        mock_get.return_value = {"data": []}
        fp.okx_signed_get("/api/v5/account/balance")
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://www.okx.com/api/v5/account/balance")
        h = kwargs["headers"]
        self.assertEqual(h["OK-ACCESS-KEY"], "k")
        self.assertEqual(h["OK-ACCESS-PASSPHRASE"], "p")
        self.assertEqual(h["Content-Type"], "application/json")
        self.assertIn("OK-ACCESS-SIGN", h)
        self.assertIn("OK-ACCESS-TIMESTAMP", h)
        # Sign should be valid base64
        base64.b64decode(h["OK-ACCESS-SIGN"])

    @patch.dict(os.environ, {}, clear=True)
    def test_missing_env_raises(self):
        with self.assertRaises(KeyError):
            fp.okx_signed_get("/api/v5/account/balance")


class MainExitCodes(unittest.TestCase):
    @patch.object(fp, "fetch_price", side_effect=KeyError("OKX_API_KEY"))
    def test_missing_env_returns_2(self, _):
        with patch("sys.stderr", new_callable=StringIO):
            self.assertEqual(fp.main(), 2)

    @patch.object(fp, "fetch_price", side_effect=urllib.error.HTTPError(
        "u", 401, "unauthorized", {}, None
    ))
    def test_http_error_returns_3(self, _):
        with patch("sys.stderr", new_callable=StringIO):
            self.assertEqual(fp.main(), 3)

    @patch.object(fp, "fetch_price")
    @patch.object(fp, "fetch_holdings")
    @patch.object(fp, "fetch_dca_today")
    def test_happy_path_emits_full_schema(self, mock_dca, mock_hold, mock_price):
        mock_price.return_value = {"last": 71000, "open24h": 70000, "change24h_pct": 1.43}
        mock_hold.return_value = {
            "btc": 0.01, "btc_avg_cost": 68000,
            "usdt_spot": 100, "usdt_earn_amt": 500, "usdt_earn_interest": 2,
        }
        mock_dca.return_value = {"count": 1, "total_usd": 20.0, "avg_px": 71000}
        os.environ["BTC_REF_PRICE"] = "79500"
        try:
            with patch("sys.stdout", new_callable=StringIO) as out:
                rc = fp.main()
            self.assertEqual(rc, 0)
            payload = json.loads(out.getvalue())
            for key in ("price", "holdings", "pnl", "dca_today", "ladder"):
                self.assertIn(key, payload)
            self.assertEqual(payload["ladder"]["current_state"], "T1")
            self.assertEqual(payload["pnl"]["btc_value_usd"], 710.0)
        finally:
            os.environ.pop("BTC_REF_PRICE", None)


if __name__ == "__main__":
    unittest.main()
