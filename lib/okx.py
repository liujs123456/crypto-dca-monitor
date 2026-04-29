"""Lightweight OKX REST helper for read-only endpoints (HMAC-signed)."""
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

OKX_BASE = "https://www.okx.com"


def _ts() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def signed_get(path_and_query: str) -> dict:
    api_key = os.environ["OKX_API_KEY"]
    secret = os.environ["OKX_SECRET"]
    passphrase = os.environ["OKX_PASSPHRASE"]

    ts = _ts()
    prehash = f"{ts}GET{path_and_query}"
    sig = base64.b64encode(
        hmac.new(secret.encode(), prehash.encode(), hashlib.sha256).digest()
    ).decode()

    req = urllib.request.Request(
        OKX_BASE + path_and_query,
        headers={
            "OK-ACCESS-KEY": api_key,
            "OK-ACCESS-SIGN": sig,
            "OK-ACCESS-TIMESTAMP": ts,
            "OK-ACCESS-PASSPHRASE": passphrase,
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"[ERR] OKX HTTP {e.code}: {body[:300]}", file=sys.stderr)
        raise


def public_get(path_and_query: str) -> dict:
    req = urllib.request.Request(
        OKX_BASE + path_and_query,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def account_balance() -> dict[str, dict]:
    """Return {ccy: {cashBal, accAvgPx?}} for all coins in trading account."""
    data = signed_get("/api/v5/account/balance")
    if not data.get("data"):
        return {}
    out = {}
    for x in data["data"][0].get("details", []):
        out[x["ccy"]] = {
            "cashBal": float(x.get("cashBal", 0) or 0),
            "accAvgPx": float(x.get("accAvgPx", 0) or 0),
        }
    return out


def savings_balance(ccy: str) -> tuple[float, float]:
    """Return (amount, accumulated_earnings) for given ccy."""
    data = signed_get(f"/api/v5/finance/savings/balance?ccy={ccy}")
    if not data.get("data"):
        return 0.0, 0.0
    row = data["data"][0]
    return float(row.get("amt", 0) or 0), float(row.get("earnings", 0) or 0)


def filled_buys_since(inst_id: str, since_ms: int, limit: int = 100) -> list[dict]:
    """Return filled BUY orders for given instId since unix-ms."""
    data = signed_get(
        f"/api/v5/trade/orders-history?instType=SPOT&instId={inst_id}"
        f"&begin={since_ms}&limit={limit}"
    )
    return [
        o for o in data.get("data", [])
        if o.get("side") == "buy" and o.get("state") == "filled"
    ]


def btc_ticker() -> tuple[float, float]:
    """Return (last_price, open_24h) from public ticker."""
    data = public_get("/api/v5/market/ticker?instId=BTC-USDT")
    row = data["data"][0]
    return float(row["last"]), float(row["open24h"])
