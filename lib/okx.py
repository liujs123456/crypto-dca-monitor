"""Lightweight OKX REST helper for read-only endpoints (HMAC-signed).

Built-in retry with exponential backoff on transient failures (5xx, timeouts,
network errors). 429 rate-limit responses are also retried. Auth/permission
errors (4xx other than 429) are surfaced immediately.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

OKX_BASE = "https://www.okx.com"

MAX_ATTEMPTS = 3
INITIAL_BACKOFF_S = 1.0
BACKOFF_MULTIPLIER = 3.0  # 1s, 3s, 9s
RETRYABLE_HTTP = {429, 500, 502, 503, 504}


def _ts() -> str:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _retryable_request(req: urllib.request.Request, what: str) -> dict:
    """Execute the request with exponential backoff on transient failures."""
    last_exc: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="ignore")
            if e.code in RETRYABLE_HTTP and attempt < MAX_ATTEMPTS:
                backoff = INITIAL_BACKOFF_S * (BACKOFF_MULTIPLIER ** (attempt - 1))
                print(f"[RETRY] OKX {what} HTTP {e.code} (attempt {attempt}/{MAX_ATTEMPTS}); waiting {backoff}s", file=sys.stderr)
                time.sleep(backoff)
                last_exc = e
                continue
            print(f"[ERR] OKX {what} HTTP {e.code}: {body[:300]}", file=sys.stderr)
            raise
        except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
            if attempt < MAX_ATTEMPTS:
                backoff = INITIAL_BACKOFF_S * (BACKOFF_MULTIPLIER ** (attempt - 1))
                print(f"[RETRY] OKX {what} {type(e).__name__}: {e} (attempt {attempt}/{MAX_ATTEMPTS}); waiting {backoff}s", file=sys.stderr)
                time.sleep(backoff)
                last_exc = e
                continue
            print(f"[ERR] OKX {what} network: {e}", file=sys.stderr)
            raise
    # Defensive: should be unreachable since the loop either returns or raises
    if last_exc:
        raise last_exc
    raise RuntimeError("OKX request exhausted retries with no exception")


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
            # Cloudflare in front of OKX returns 1010 on bare urllib UA — pass a
            # browser-like UA so the GH Actions runner IP isn't auto-banned.
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        },
        method="GET",
    )
    return _retryable_request(req, f"signed GET {path_and_query[:60]}")


def public_get(path_and_query: str) -> dict:
    req = urllib.request.Request(
        OKX_BASE + path_and_query,
        headers={"User-Agent": "Mozilla/5.0"},
    )
    return _retryable_request(req, f"public GET {path_and_query[:60]}")


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
