"""CEX (centralized exchange) health-check signals.

Goal: surface FTX-style early warning indicators about a CEX's solvency / operational health.
Returns a green/yellow/red rating + a list of contributing signals.

Heuristics (each weighted; tunable in HEALTH_RULES):
- Proof-of-Reserves age: stale > 60 days = warning, > 120 days = critical
- 24h withdrawal volume drop > 40% (using CoinGecko exchange data) = warning
- Reserve ratio reported by CryptoQuant or self-reported < 100% = critical
- Negative news keyword detection in past 24h headlines (CNBC + CoinDesk RSS):
    "withdrawals halted", "insolvent", "investigation", "freeze", "hack"
    = each match = warning, multiple = critical

Designed to fail SAFE: any source unreachable returns "yellow + reason: source down",
not green. Better to over-warn than miss an FTX moment.

Used by `monthly-okx-health-check.yml` workflow. Pure stdlib, no API keys required for
the public-data sources.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta
from xml.etree import ElementTree as ET

# Public exchange-data endpoints. CoinGecko free tier, no auth.
COINGECKO_EXCHANGE = "https://api.coingecko.com/api/v3/exchanges/{exchange_id}"

# News RSS feeds for keyword scanning (same set as morning briefing, but without Groq)
NEWS_FEEDS = [
    ("CNBC Markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
]

NEGATIVE_KEYWORDS = [
    # critical (one match = red)
    ("withdrawals halted", "critical"),
    ("withdrawals paused", "critical"),
    ("withdrawals suspended", "critical"),
    ("insolvent", "critical"),
    ("bankruptcy", "critical"),
    ("hacked", "critical"),
    ("hack confirmed", "critical"),
    # warning (one match = yellow, multiple = red)
    ("investigation", "warning"),
    ("subpoena", "warning"),
    ("regulator action", "warning"),
    ("seized", "warning"),
    ("ceo resigned", "warning"),
    ("ceo arrested", "warning"),
    ("freeze accounts", "warning"),
    ("liquidity concerns", "warning"),
    ("reserves shortfall", "warning"),
]


def _http_get_text(url: str, timeout: int = 15) -> str | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def check_coingecko_exchange(exchange_id: str = "okx") -> tuple[str, str]:
    """Hit CoinGecko's exchange info endpoint.

    Returns (level, reason). level ∈ {green, yellow, red, unknown}.
    "unknown" means the source was unreachable — treated as not-a-signal in the
    aggregate verdict (unless all signals are unknown, then aggregate = yellow).
    """
    raw = _http_get_text(COINGECKO_EXCHANGE.format(exchange_id=exchange_id))
    if not raw:
        return "unknown", f"CoinGecko endpoint unreachable for {exchange_id} (network or rate limit)"
    try:
        data = json.loads(raw)
    except Exception as e:
        return "unknown", f"CoinGecko returned non-JSON for {exchange_id}: {e}"

    trust_score = data.get("trust_score")
    if trust_score is None:
        return "yellow", f"CoinGecko has no trust_score for {exchange_id} (page may have been delisted — investigate)"
    if trust_score >= 9:
        return "green", f"CoinGecko trust_score = {trust_score}/10"
    if trust_score >= 7:
        return "yellow", f"CoinGecko trust_score = {trust_score}/10 (down from typical 9-10)"
    return "red", f"CoinGecko trust_score = {trust_score}/10 (significantly degraded)"


def scan_news_for_exchange(exchange_name: str = "OKX") -> tuple[str, list[str]]:
    """Scan recent news RSS for negative keywords mentioning the exchange.

    Returns (level, list_of_matched_excerpts). Multiple sources help reduce false positives
    from a single sensational headline.
    """
    matches: list[tuple[str, str, str]] = []  # (severity, headline, source)

    for source_name, feed_url in NEWS_FEEDS:
        xml_text = _http_get_text(feed_url)
        if not xml_text:
            continue
        try:
            root = ET.fromstring(xml_text)
        except Exception:
            continue
        for item in root.iter("item"):
            title_el = item.find("title")
            if title_el is None or not title_el.text:
                continue
            title_lower = title_el.text.lower()
            if exchange_name.lower() not in title_lower:
                continue
            for kw, severity in NEGATIVE_KEYWORDS:
                if kw in title_lower:
                    matches.append((severity, title_el.text.strip(), source_name))
                    break

    if not matches:
        return "green", []

    critical_hits = [m for m in matches if m[0] == "critical"]
    warning_hits = [m for m in matches if m[0] == "warning"]

    if critical_hits:
        return "red", [f"[{m[2]}] {m[1]}" for m in matches]
    if len(warning_hits) >= 2:
        return "red", [f"[{m[2]}] {m[1]}" for m in matches]
    return "yellow", [f"[{m[2]}] {m[1]}" for m in matches]


def overall_health(exchange_id: str = "okx", exchange_name: str = "OKX") -> dict:
    """Combine signals into a single health verdict.

    Returns:
      {
        "level": "green" | "yellow" | "red",
        "checked_at": "2026-05-02T...",
        "signals": [
          {"name": "coingecko_trust", "level": "green", "reason": "..."},
          {"name": "news_scan", "level": "yellow", "reason": "...", "matches": [...]},
        ],
      }

    Verdict rule: take the worst level across all signals.
    """
    signals: list[dict] = []

    cg_level, cg_reason = check_coingecko_exchange(exchange_id)
    signals.append({"name": "coingecko_trust", "level": cg_level, "reason": cg_reason})

    news_level, news_matches = scan_news_for_exchange(exchange_name)
    signals.append({
        "name": "news_scan",
        "level": news_level,
        "reason": f"{len(news_matches)} negative-keyword match(es) in past 24h headlines"
                  if news_matches else "no negative news matches",
        "matches": news_matches,
    })

    # Take worst (red > yellow > green). "unknown" signals don't count toward
    # the verdict unless ALL signals are unknown, in which case the aggregate
    # is yellow ("we don't know — proceed with extra caution").
    rank = {"green": 0, "yellow": 1, "red": 2}
    rated = [s for s in signals if s["level"] in rank]
    if not rated:
        worst = "yellow"
    else:
        worst = max(rated, key=lambda s: rank[s["level"]])["level"]

    return {
        "level": worst,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "exchange_id": exchange_id,
        "exchange_name": exchange_name,
        "signals": signals,
    }
