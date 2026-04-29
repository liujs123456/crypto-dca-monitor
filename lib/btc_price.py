"""BTC price + 24h change fetcher with provider failover."""
from __future__ import annotations

import json
import urllib.request


def _http_get(url: str, timeout: int = 10) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def fetch_btc_price() -> tuple[float | None, float | None]:
    """Return (last_price_usd, change_24h_pct). Either may be None on total failure.

    Tries Coinbase for spot, CoinGecko for 24h change. Falls back to CoinGecko
    if Coinbase fails.
    """
    last = None
    change_24h = None

    cb_raw = _http_get("https://api.coinbase.com/v2/prices/BTC-USD/spot")
    if cb_raw:
        try:
            last = float(json.loads(cb_raw)["data"]["amount"])
        except Exception:
            pass

    cg_raw = _http_get(
        "https://api.coingecko.com/api/v3/simple/price"
        "?ids=bitcoin&vs_currencies=usd&include_24hr_change=true"
    )
    if cg_raw:
        try:
            data = json.loads(cg_raw)["bitcoin"]
            if last is None:
                last = float(data["usd"])
            change_24h = round(float(data.get("usd_24h_change", 0)), 2)
        except Exception:
            pass

    return last, change_24h


def fetch_30d_high() -> float | None:
    """Return BTC's highest daily close over the past 30 days."""
    raw = _http_get(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart"
        "?vs_currency=usd&days=30&interval=daily",
        timeout=15,
    )
    if not raw:
        return None
    try:
        prices = json.loads(raw)["prices"]
        return round(max(p[1] for p in prices), 2)
    except Exception:
        return None
