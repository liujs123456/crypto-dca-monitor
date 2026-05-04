#!/usr/bin/env python3
"""Morning news briefing — fetch headlines, dedupe, summarize via Groq, push to ntfy."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import klinekit, ntfy

NTFY_TOPIC = os.environ["NTFY_TOPIC"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

RSS_FEEDS = [
    ("CNBC Markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
]

DEDUP_THRESHOLD = 0.65  # similarity ratio for same-story dedup. Conservative — Groq handles fuzzy cross-source merging.


def fetch_rss(name: str, url: str, max_items: int = 8) -> list[str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            xml_text = resp.read().decode("utf-8", errors="ignore")
        root = ET.fromstring(xml_text)
        items = []
        for item in root.iter("item"):
            title_el = item.find("title")
            if title_el is not None and title_el.text:
                items.append(title_el.text.strip())
            if len(items) >= max_items:
                break
        return items
    except Exception as e:
        print(f"[WARN] {name} failed: {e}", file=sys.stderr)
        return []


def _normalize(s: str) -> str:
    s = s.lower()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def dedupe_headlines(grouped: list[tuple[str, list[str]]]) -> list[tuple[str, list[str]]]:
    """Drop headlines too similar to one already kept (across all sources).

    Keeps first occurrence (preserves source-order priority). Returns the same
    structure with dropped items removed.
    """
    kept_norms: list[str] = []
    out = []
    dropped = 0
    for source, items in grouped:
        kept_for_source = []
        for h in items:
            n = _normalize(h)
            if not n:
                continue
            is_dup = any(
                SequenceMatcher(None, n, k).ratio() >= DEDUP_THRESHOLD
                for k in kept_norms
            )
            if is_dup:
                dropped += 1
                continue
            kept_norms.append(n)
            kept_for_source.append(h)
        out.append((source, kept_for_source))
    if dropped:
        print(f"Deduped {dropped} similar headlines.")
    return out


def call_groq(headlines: list[tuple[str, list[str]]]) -> str:
    payload_lines = []
    for source, items in headlines:
        if items:
            payload_lines.append(f"\n=== {source} ===")
            payload_lines.extend(f"- {h}" for h in items)
    headlines_block = "\n".join(payload_lines)

    prompt = f"""You are a financial news editor. Below are today's top headlines from multiple sources. Pick the 4-5 MOST IMPACTFUL items for a BTC/crypto investor and a US-equity-watcher to know about. Summarize each in CHINESE in this exact format (no extra text):

1. 事件: [一句话中文事件描述]
   → 影响: [对市场/BTC的潜在影响一句话]

2. ...

Prioritize: 美联储/Fed/利率/Powell/Warsh, ETF/BTC/SEC/加密监管, 地缘政治, 美股大动 (>2%), 宏观数据 (CPI/NFP), 大型科技股财报.

Skip: 名人八卦, 体育, 一般生活新闻.

Total output under 400 Chinese characters.

HEADLINES:
{headlines_block}
"""

    body = json.dumps({
        # llama-3.3-70b-versatile: Groq free tier, ~3s response, much better
        # Chinese summarization quality than 8b-instant.
        "model": "llama-3.3-70b-versatile",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 600,
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="ignore")
        print(f"[ERR] Groq HTTP {e.code}: {body_text[:500]}", file=sys.stderr)
        raise


def main() -> int:
    headlines = [(name, fetch_rss(name, url)) for name, url in RSS_FEEDS]
    raw_total = sum(len(items) for _, items in headlines)
    print(f"Fetched {raw_total} headlines across {len(RSS_FEEDS)} sources")

    headlines = dedupe_headlines(headlines)
    deduped_total = sum(len(items) for _, items in headlines)
    print(f"After dedup: {deduped_total} headlines")

    if deduped_total < 4:
        ntfy.push(
            f"📰 早报 {datetime.now().strftime('%m/%d')}",
            f"⚠️ 只抓到 {deduped_total} 条标题（{len([s for s,i in headlines if i])}/{len(RSS_FEEDS)} 个源工作），今日不发总结，避免低质量摘要。",
            priority="low",
            thread="morning-briefing",
        )
        return 1

    try:
        summary = call_groq(headlines)
    except Exception as e:
        print(f"[ERR] Groq: {e}", file=sys.stderr)
        ntfy.push(
            f"📰 早报 {datetime.now().strftime('%m/%d')} (raw)",
            "\n".join(
                f"【{src}】\n" + "\n".join(f"• {h}" for h in items[:3])
                for src, items in headlines
                if items
            )[:1500],
            priority="low",
            thread="morning-briefing",
        )
        return 1

    body = summary
    bt = klinekit.run_dip_ladder_backtest(days=30)
    if bt:
        body = body.rstrip() + f"\n\n📊 dip-ladder 30d: {bt['line']}"

    ok = ntfy.push(
        f"📰 早报 {datetime.now().strftime('%m/%d')}",
        body,
        priority="default",
        tags="newspaper",
        thread="morning-briefing",
    )
    print("Sent" if ok else "Failed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
