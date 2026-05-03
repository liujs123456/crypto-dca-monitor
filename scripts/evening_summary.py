#!/usr/bin/env python3
"""Evening portfolio summary — OKX read-only API → ntfy push.

Runs daily at 20:17 PT. Includes ladder status (which tier is closest, distance
to each trigger, armed state) and day-over-day Earn interest delta.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import ladder, ntfy, okx, onboarding

DAILY_SNAP_PATH = ROOT / "state" / "daily_snapshots.json"
ONBOARDING_PATH = ROOT / "state" / "cold_storage_onboarding.json"
COLD_STORAGE_THRESHOLD_USD = 10000  # surface onboarding nudge once portfolio crosses this
KEEP_DAYS = 60  # rolling 2 months of daily snapshots


def fmt_money(x: float, decimals: int = 2) -> str:
    return f"${x:,.{decimals}f}"


def load_daily_snapshots() -> list[dict]:
    if not DAILY_SNAP_PATH.exists():
        return []
    try:
        return json.loads(DAILY_SNAP_PATH.read_text())
    except Exception:
        return []


def save_daily_snapshots(snaps: list[dict]) -> None:
    DAILY_SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    DAILY_SNAP_PATH.write_text(json.dumps(snaps[-KEEP_DAYS:], indent=2) + "\n")


def main() -> int:
    ref = float(os.environ.get("BTC_REF_PRICE", "79500"))

    btc_price, btc_open24 = okx.btc_ticker()
    bal = okx.account_balance()
    earn_amt, earn_int = okx.savings_balance("USDT")

    usdt = bal.get("USDT", {}).get("cashBal", 0)
    btc_held = bal.get("BTC", {}).get("cashBal", 0)
    btc_avg = bal.get("BTC", {}).get("accAvgPx", 0)

    day_ago_ms = int((time.time() - 86400) * 1000)
    orders = okx.filled_buys_since("BTC-USDT", day_ago_ms, limit=20)

    if orders:
        n = len(orders)
        total = sum(float(o["accFillSz"]) * float(o["avgPx"]) for o in orders)
        avg_px = sum(float(o["avgPx"]) for o in orders) / n
        dca_line = f"今日 DCA: {n} 单, ${total:.2f}, 均价 ${avg_px:,.0f}"
    else:
        dca_line = "今日 DCA: 0 单（请检查 OKX 自动 DCA 是否还在运行）"

    # Day-over-day Earn interest delta
    daily_snaps = load_daily_snapshots()
    interest_today = ""
    if daily_snaps:
        prev_int = daily_snaps[-1].get("earn_int", 0)
        delta = earn_int - prev_int
        if delta > 0:
            apr = (delta / earn_amt * 365 * 100) if earn_amt > 0 else 0
            interest_today = f"  今日新增利息: +{fmt_money(delta)} (年化 {apr:.1f}%)"

    btc_value = btc_held * btc_price
    total_assets = usdt + btc_value + earn_amt
    upl = btc_held * (btc_price - btc_avg) if btc_avg > 0 else 0
    upl_pct = (btc_price / btc_avg - 1) * 100 if btc_avg > 0 and btc_held > 0 else 0
    px_24h_pct = (btc_price / btc_open24 - 1) * 100 if btc_open24 > 0 else 0

    cur_state = ladder.classify_state(btc_price, ref)
    prices = ladder.tier_prices(ref)

    state_emoji = {
        "GREEN": "🟢", "WATCH": "🟡",
        "T1": "🟠", "T2": "🟠", "T3": "🔴", "T4": "🚨",
    }.get(cur_state, "🟢")

    distances = []
    for name, _, _ in ladder.TIER_CONFIG:
        tier_p = prices[name]
        dist_pct = (btc_price / tier_p - 1) * 100
        distances.append(f"{name}: ${tier_p:,.0f} ({dist_pct:+.1f}%)")

    earn_block = f"USDT Earn: {fmt_money(earn_amt)} (累计利息 +{fmt_money(earn_int)})"
    if interest_today:
        earn_block += f"\n{interest_today}"

    # Onboarding nudge: only show once total assets approach the cold-storage threshold
    # (within 30%) or already crossed it, to avoid noise in early phase.
    onboarding_block = ""
    if total_assets >= COLD_STORAGE_THRESHOLD_USD * 0.7:
        ob_state = onboarding.load(ONBOARDING_PATH)
        if not onboarding.is_ready(ob_state):
            ob_block = onboarding.render_progress_block(ob_state)
            onboarding_block = f"\n{ob_block}"

    body = f"""💰 总资产 {fmt_money(total_assets)}

BTC {fmt_money(btc_price, 0)} ({px_24h_pct:+.2f}%)
持仓 {btc_held:.5f} BTC ≈ {fmt_money(btc_value)}
均价 {fmt_money(btc_avg, 0)} | 浮盈 {fmt_money(upl)} ({upl_pct:+.2f}%)

USDT 现货: {fmt_money(usdt)}
{earn_block}

{dca_line}

{state_emoji} Ladder: {cur_state} (REF ${ref:,.0f})
{chr(10).join(distances)}{onboarding_block}"""

    ok = ntfy.push(
        f"📊 晚报 {datetime.now().strftime('%m/%d')}",
        body,
        priority="default",
        tags="bar_chart",
        thread="evening-summary",
    )

    # Append snapshot for tomorrow's delta calculation
    daily_snaps.append({
        "ts_utc": datetime.utcnow().isoformat(),
        "earn_amt": earn_amt,
        "earn_int": earn_int,
        "btc_price": btc_price,
        "btc_held": btc_held,
        "total_assets": total_assets,
    })
    save_daily_snapshots(daily_snaps)

    print(body)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
