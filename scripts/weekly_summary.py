#!/usr/bin/env python3
"""Weekly summary — runs every Sunday 21:30 PT.

Aggregates the past 7 days: DCA total, avg fill price, BTC price change,
PnL change vs last Sunday's snapshot (stored in state/weekly_snapshots.json).
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

from lib import ladder, ntfy, okx

SNAP_PATH = ROOT / "state" / "weekly_snapshots.json"


def load_snapshots() -> list[dict]:
    if not SNAP_PATH.exists():
        return []
    return json.loads(SNAP_PATH.read_text())


def save_snapshots(snaps: list[dict]) -> None:
    SNAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    SNAP_PATH.write_text(json.dumps(snaps[-26:], indent=2) + "\n")  # keep ~6 months


def fmt_money(x: float, decimals: int = 2) -> str:
    return f"${x:,.{decimals}f}"


def main() -> int:
    ref = float(os.environ.get("BTC_REF_PRICE", "79500"))

    btc_price, _ = okx.btc_ticker()
    bal = okx.account_balance()
    earn_amt, earn_int = okx.savings_balance("USDT")

    usdt = bal.get("USDT", {}).get("cashBal", 0)
    btc_held = bal.get("BTC", {}).get("cashBal", 0)
    btc_avg = bal.get("BTC", {}).get("accAvgPx", 0)

    week_ago_ms = int((time.time() - 7 * 86400) * 1000)
    week_orders = okx.filled_buys_since("BTC-USDT", week_ago_ms, limit=100)

    if week_orders:
        n = len(week_orders)
        total = sum(float(o["accFillSz"]) * float(o["avgPx"]) for o in week_orders)
        avg_px = sum(float(o["avgPx"]) for o in week_orders) / n
        sz_total = sum(float(o["accFillSz"]) for o in week_orders)
        dca_block = (
            f"本周 DCA: {n} 单, {fmt_money(total)}\n"
            f"  累计 BTC: {sz_total:.6f}\n"
            f"  本周均价: ${avg_px:,.0f}"
        )
    else:
        dca_block = "本周 DCA: 0 单 ⚠️"

    btc_value = btc_held * btc_price
    total_assets = usdt + btc_value + earn_amt
    upl = btc_held * (btc_price - btc_avg) if btc_avg > 0 else 0
    upl_pct = (btc_price / btc_avg - 1) * 100 if btc_avg > 0 and btc_held > 0 else 0

    snaps = load_snapshots()
    delta_block = ""
    if snaps:
        prev = snaps[-1]
        d_assets = total_assets - prev.get("total_assets", total_assets)
        d_btc_held = btc_held - prev.get("btc_held", btc_held)
        d_btc_price = btc_price - prev.get("btc_price", btc_price)
        d_btc_pct = (
            (btc_price / prev["btc_price"] - 1) * 100 if prev.get("btc_price") else 0
        )
        delta_block = (
            f"\n📈 周环比\n"
            f"  总资产: {d_assets:+.2f}\n"
            f"  BTC 持仓: {d_btc_held:+.6f}\n"
            f"  BTC 价格: ${d_btc_price:+,.0f} ({d_btc_pct:+.2f}%)"
        )

    snaps.append({
        "ts_utc": datetime.utcnow().isoformat(),
        "btc_price": btc_price,
        "btc_held": btc_held,
        "btc_avg": btc_avg,
        "total_assets": total_assets,
        "usdt": usdt,
        "earn_amt": earn_amt,
        "earn_int": earn_int,
    })
    save_snapshots(snaps)

    cur_state = ladder.classify_state(btc_price, ref)
    state_emoji = {
        "GREEN": "🟢", "WATCH": "🟡",
        "T1": "🟠", "T2": "🟠", "T3": "🔴", "T4": "🚨",
    }.get(cur_state, "🟢")

    body = f"""💼 总资产 {fmt_money(total_assets)}
BTC ${btc_price:,.0f} | 持仓 {btc_held:.5f} ≈ {fmt_money(btc_value)}
均价 ${btc_avg:,.0f} | 浮盈 {fmt_money(upl)} ({upl_pct:+.2f}%)
USDT 现货 {fmt_money(usdt)} | Earn {fmt_money(earn_amt)} (+{fmt_money(earn_int)})

{dca_block}
{delta_block}

{state_emoji} Ladder: {cur_state} (REF ${ref:,.0f})"""

    ok = ntfy.push(
        f"📅 周报 {datetime.now().strftime('%m/%d')}",
        body,
        priority="default",
        tags="calendar",
    )
    print(body)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
