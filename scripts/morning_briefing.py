#!/usr/bin/env python3
"""Morning news briefing — fetch headlines, summarize via Groq, push to ntfy."""

import json
import os
import sys
import urllib.request
import urllib.parse
from datetime import datetime
from xml.etree import ElementTree as ET

NTFY_TOPIC = os.environ["NTFY_TOPIC"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]

NTFY_URL = f"https://ntfy.sh/{NTFY_TOPIC}"

RSS_FEEDS = [
    ("CNBC Markets", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=10001147"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ("Cointelegraph", "https://cointelegraph.com/rss"),
]


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
        "model": "llama-3.1-8b-instant",
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


def push_ntfy(title: str, body: str, priority: int = 3, tags: str = "newspaper") -> bool:
    payload = json.dumps({
        "topic": NTFY_TOPIC,
        "title": title,
        "message": body,
        "priority": priority,
        "tags": [tags],
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://ntfy.sh/",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="ignore")
        print(f"[ERR] ntfy HTTP {e.code}: {body_text[:300]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERR] ntfy: {e}", file=sys.stderr)
        return False


def main() -> int:
    headlines = [(name, fetch_rss(name, url)) for name, url in RSS_FEEDS]
    total = sum(len(items) for _, items in headlines)
    print(f"Fetched {total} headlines across {len(RSS_FEEDS)} sources")

    if total == 0:
        push_ntfy(
            f"📰 早报 {datetime.now().strftime('%m/%d')}",
            "今日所有新闻源都获取失败。",
            priority=2,
        )
        return 1

    try:
        summary = call_groq(headlines)
    except Exception as e:
        print(f"[ERR] Groq: {e}", file=sys.stderr)
        push_ntfy(
            f"📰 早报 {datetime.now().strftime('%m/%d')} (raw)",
            "\n".join(
                f"【{src}】\n" + "\n".join(f"• {h}" for h in items[:3])
                for src, items in headlines
                if items
            )[:1500],
            priority=2,
        )
        return 1

    ok = push_ntfy(
        f"📰 早报 {datetime.now().strftime('%m/%d')}",
        summary,
        priority=3,
    )
    print("Sent" if ok else "Failed")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
