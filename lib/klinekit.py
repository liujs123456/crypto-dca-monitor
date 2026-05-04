"""Optional integration with the klinekit Java backtester.

Hits klinekit's /api/v1/backtest with source=okx so we don't need to ship
candle history with the request. Returns a dict suitable for a one-line
summary, or None if the API is unreachable / disabled.

Usage in a script:
    from lib import klinekit
    summary = klinekit.run_dip_ladder_backtest(days=365)
    if summary:
        body += f"\\n📊 dip-ladder YTD: {summary['line']}"

Configure via env:
    KLINEKIT_API   base URL of klinekit api (e.g. http://localhost:8080/api/v1)
                   if unset, this module is a no-op.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request


DEFAULT_TIMEOUT = 30  # backtest fetch from OKX + run takes a few seconds


def run_dip_ladder_backtest(
    days: int = 365,
    bar: str = "1D",
    symbol: str = "BTC-USDT",
    initial_cash: str = "10000",
    api_url: str | None = None,
) -> dict | None:
    """Trigger a dip-ladder backtest and return a parsed summary.

    Returns:
        {
          "id": str,
          "totalReturnPct": float,
          "maxDrawdownPct": float,
          "tradeCount": int,
          "finalEquity": float,
          "line": "+1.87% / -1.65% DD / 5 trades over 365d",
        }
        or None if the API is not configured or unreachable.
    """
    base = api_url or os.environ.get("KLINEKIT_API")
    if not base:
        return None

    payload = {
        "strategy": "dip-ladder",
        "symbol": symbol,
        "initialCash": initial_cash,
        "feeBps": "10",
        "slippageBps": "5",
        "params": {"refLookbackDays": "30"},
        "source": {"provider": "okx", "symbol": symbol, "bar": bar, "count": days},
    }
    req = urllib.request.Request(
        f"{base.rstrip('/')}/backtest",
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError):
        return None
    except Exception:
        return None

    metrics = data.get("metrics") or {}
    ret = float(metrics.get("totalReturnPct", 0))
    dd = float(metrics.get("maxDrawdownPct", 0))
    trades = int(float(metrics.get("tradeCount", 0)))
    final_equity = float(data.get("finalEquity", 0))

    return {
        "id": data.get("id"),
        "totalReturnPct": ret,
        "maxDrawdownPct": dd,
        "tradeCount": trades,
        "finalEquity": final_equity,
        "line": f"{ret:+.2f}% / {dd:.2f}% DD / {trades} trades over {days}d",
    }
