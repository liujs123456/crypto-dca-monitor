#!/usr/bin/env python3
"""Monthly OKX health check.

Aggregates green/yellow/red signals about OKX's operational health (trust score,
negative news scan) and pushes a ntfy notification with the verdict + reasoning.

Designed for users on the path to a $10K cold-storage migration threshold:
ANY non-green verdict is a strong nudge to migrate funds to hardware wallet sooner
rather than waiting for the threshold. Better paranoid than FTX'd.

Pure stdlib. No OKX API key needed (uses public CoinGecko + RSS).
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import cex_health, ntfy, onboarding

ONBOARDING_PATH = ROOT / "state" / "cold_storage_onboarding.json"

EMOJI = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unknown": "⚪️"}
PRIORITY = {"green": "low", "yellow": "high", "red": "max", "unknown": "low"}
TAGS = {"green": "white_check_mark", "yellow": "warning", "red": "rotating_light", "unknown": "grey_question"}


def main() -> int:
    verdict = cex_health.overall_health(exchange_id="okx", exchange_name="OKX")
    level = verdict["level"]

    lines = [f"{EMOJI[level]} OKX 健康度: {level.upper()}", ""]

    for sig in verdict["signals"]:
        lines.append(f"{EMOJI[sig['level']]} {sig['name']}: {sig['reason']}")
        for match in sig.get("matches", [])[:3]:
            lines.append(f"  • {match}")

    lines.append("")
    if level == "green":
        lines.append("OKX 当前无显著负面信号。继续按 $10K 阈值计划迁移到冷钱包。")
    elif level == "yellow":
        lines.append("⚠️ 出现轻度警告信号。建议加快冷钱包准备进度，未达 $10K 也可考虑提前迁移 50%。")
    else:  # red
        lines.append("🚨 严重警告信号。**立即**评估是否提前执行 cold storage 迁移，不要等 $10K 阈值。")
        lines.append("查看上面的具体信号，并搜索最新新闻交叉验证。")

    # Cold-storage onboarding progress (urgency depends on health level)
    onboarding_state = onboarding.load(ONBOARDING_PATH)
    lines.append("")
    lines.append(onboarding.render_progress_block(onboarding_state))

    body = "\n".join(lines)

    ok = ntfy.push(
        f"📋 OKX 月度健康检查 {datetime.now().strftime('%m/%d')}",
        body,
        priority=PRIORITY[level],
        tags=TAGS[level],
        thread="okx-health-check",
    )
    print(body)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
