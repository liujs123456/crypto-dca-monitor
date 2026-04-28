#!/usr/bin/env python3
"""Fetch OKX spot account state + dip-ladder context, emit JSON to stdout.

Reads credentials from environment (OKX_API_KEY / OKX_SECRET / OKX_PASSPHRASE).
BTC_REF_PRICE is the rolling 30d high used as ladder reference (default 79500).

Output schema (single JSON object):
  price:      { last, open24h, change24h_pct }
  holdings:   { btc, btc_avg_cost, usdt_spot, usdt_earn_amt, usdt_earn_interest }
  pnl:        { btc_value_usd, total_usd, unrealized_pl, unrealized_pl_pct }
  dca_today:  { count, total_usd, avg_px }
  ladder:     { ref, watch, t1, t2, t3, t4, current_state }

Stdlib only — no third-party deps. Mirrors scripts/evening_summary.sh.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

OKX_HOST = "https://www.okx.com"
TIMEOUT = 15


def _ts() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _sign(secret: str, prehash: str) -> str:
    mac = hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()
    return base64.b64encode(mac).decode()


def _http_get(url: str, headers: dict | None = None) -> dict:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def okx_signed_get(path_and_query: str) -> dict:
    key = os.environ["OKX_API_KEY"]
    secret = os.environ["OKX_SECRET"]
    passphrase = os.environ["OKX_PASSPHRASE"]
    ts = _ts()
    sig = _sign(secret, f"{ts}GET{path_and_query}")
    return _http_get(
        f"{OKX_HOST}{path_and_query}",
        headers={
            "OK-ACCESS-KEY": key,
            "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": passphrase,
            "Content-Type": "application/json",
        },
    )


def fetch_price() -> dict:
    d = _http_get(f"{OKX_HOST}/api/v5/market/ticker?instId=BTC-USDT")["data"][0]
    last = float(d["last"])
    open24 = float(d["open24h"])
    change_pct = round((last / open24 - 1) * 100, 2) if open24 else 0.0
    return {"last": last, "open24h": open24, "change24h_pct": change_pct}


def _coin_detail(balance: dict, ccy: str) -> dict:
    for x in balance["data"][0]["details"]:
        if x["ccy"] == ccy:
            return x
    return {}


def fetch_holdings() -> dict:
    bal = okx_signed_get("/api/v5/account/balance")
    btc = _coin_detail(bal, "BTC")
    usdt = _coin_detail(bal, "USDT")
    earn = okx_signed_get("/api/v5/finance/savings/balance?ccy=USDT")
    earn_row = earn["data"][0] if earn.get("data") else {}
    return {
        "btc": float(btc.get("cashBal", 0) or 0),
        "btc_avg_cost": float(btc.get("accAvgPx", 0) or 0),
        "usdt_spot": float(usdt.get("cashBal", 0) or 0),
        "usdt_earn_amt": float(earn_row.get("amt", 0) or 0),
        "usdt_earn_interest": float(earn_row.get("earnings", 0) or 0),
    }


def fetch_dca_today() -> dict:
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    day_ago = now_ms - 86_400_000
    r = okx_signed_get(
        f"/api/v5/trade/orders-history?instType=SPOT&instId=BTC-USDT&begin={day_ago}&limit=20"
    )
    orders = [
        o for o in r.get("data", [])
        if o.get("side") == "buy" and o.get("state") == "filled"
    ]
    if not orders:
        return {"count": 0, "total_usd": 0.0, "avg_px": 0.0}
    total = sum(float(o["accFillSz"]) * float(o["avgPx"]) for o in orders)
    avg_px = sum(float(o["avgPx"]) for o in orders) / len(orders)
    return {"count": len(orders), "total_usd": round(total, 2), "avg_px": round(avg_px)}


def compute_ladder(price_last: float) -> dict:
    ref = float(os.environ.get("BTC_REF_PRICE", "79500"))
    tiers = {
        "ref": ref,
        "watch": round(ref * 0.92),
        "t1": round(ref * 0.90),
        "t2": round(ref * 0.85),
        "t3": round(ref * 0.78),
        "t4": round(ref * 0.68),
    }
    if price_last < tiers["t4"]:
        state = "T4"
    elif price_last < tiers["t3"]:
        state = "T3"
    elif price_last < tiers["t2"]:
        state = "T2"
    elif price_last < tiers["t1"]:
        state = "T1"
    elif price_last < tiers["watch"]:
        state = "WATCH"
    else:
        state = "GREEN"
    tiers["current_state"] = state
    return tiers


def compute_pnl(price: dict, holdings: dict) -> dict:
    btc_val = round(holdings["btc"] * price["last"], 2)
    total = round(
        holdings["usdt_spot"] + btc_val + holdings["usdt_earn_amt"], 2
    )
    avg = holdings["btc_avg_cost"]
    if avg and holdings["btc"]:
        upl = round(holdings["btc"] * (price["last"] - avg), 2)
        upl_pct = round((price["last"] / avg - 1) * 100, 2)
    else:
        upl = 0.0
        upl_pct = 0.0
    return {
        "btc_value_usd": btc_val,
        "total_usd": total,
        "unrealized_pl": upl,
        "unrealized_pl_pct": upl_pct,
    }


def main() -> int:
    try:
        price = fetch_price()
        holdings = fetch_holdings()
        dca_today = fetch_dca_today()
        pnl = compute_pnl(price, holdings)
        ladder = compute_ladder(price["last"])
    except KeyError as e:
        print(json.dumps({"error": f"missing env var: {e}"}), file=sys.stderr)
        return 2
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": f"OKX HTTP {e.code}: {e.reason}"}), file=sys.stderr)
        return 3

    out = {
        "price": price,
        "holdings": holdings,
        "pnl": pnl,
        "dca_today": dca_today,
        "ladder": ladder,
    }
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
