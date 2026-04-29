#!/usr/bin/env python3
"""BTC dip ladder monitor — runs every 2h via GitHub Actions.

Tier state is persisted in ../state/btc_state.json (committed back to repo
by the workflow). lib/state_store.py validates the file on read and recovers
gracefully (with a notification) if it's corrupted.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import btc_price, ladder, ntfy, state_store

STATE_PATH = ROOT / "state" / "btc_state.json"
THREAD_TAG = "btc-monitor"  # ntfy iOS grouping


def main() -> int:
    ref = float(os.environ.get("BTC_REF_PRICE", "79500"))
    price, change_24h = btc_price.fetch_btc_price()

    if price is None:
        ntfy.push(
            "⚠️ Monitor 失败",
            "BTC 价格源全部不可达，跳过本次。",
            priority="low",
            thread=THREAD_TAG,
        )
        return 1

    state, recovery_reason = state_store.load(STATE_PATH)
    if recovery_reason:
        ntfy.push(
            "⚠️ State 文件已重置",
            f"btc_state.json 损坏（{recovery_reason}），已重置为默认。"
            f"\n注意：所有 tier 重新 armed，可能重新触发。",
            priority="high",
            tags="warning",
            thread=THREAD_TAG,
        )

    prev_tier = state.get("tier", "GREEN")
    armed = ladder.update_armed(state["armed"], price, ref)
    cur_tier = ladder.classify_state(price, ref)

    notify_kind, armed = ladder.decide_notification(cur_tier, prev_tier, armed)

    prices = ladder.tier_prices(ref)
    if notify_kind:
        title, prio, tags, body_tpl = ladder.NOTIFICATION_TEMPLATES[notify_kind]
        body = Template(body_tpl).substitute(
            price=f"{price:,.0f}",
            ref=f"{ref:,.0f}",
            t1=f"{prices['T1']:,.0f}",
        )
        ntfy.push(title, body, priority=prio, tags=tags, thread=THREAD_TAG)

    if change_24h is not None and abs(change_24h) > 8:
        last_flash = state.get("last_flash_utc")
        now_utc = datetime.now(timezone.utc)
        if not last_flash or (
            now_utc - datetime.fromisoformat(last_flash)
        ).total_seconds() > 6 * 3600:
            ntfy.push(
                "⚡ FLASH: 异常波动",
                f"BTC 24h {change_24h}%. 现价 ${price:,.0f}.",
                priority="default",
                tags="zap",
                thread=THREAD_TAG,
            )
            state["last_flash_utc"] = now_utc.isoformat()

    state["tier"] = cur_tier
    state["armed"] = armed
    state["last_price"] = price
    state["last_ref"] = ref
    state["last_check_utc"] = datetime.now(timezone.utc).isoformat()
    state_store.save(STATE_PATH, state)

    print(
        f"BTC: ${price:,.0f} | 24h: {change_24h}% | REF: ${ref:,.0f} | "
        f"State: {cur_tier} | Prev: {prev_tier} | Armed: {armed} | "
        f"Notify: {notify_kind or 'none'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
