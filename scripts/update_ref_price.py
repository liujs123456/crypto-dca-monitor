#!/usr/bin/env python3
"""Auto-update BTC_REF_PRICE GH variable with rolling 30d high.

Rounds up to the nearest $500 to avoid trivial daily rewrites. Only updates
if the new value differs from the current one (also avoids polluting Audit Log).
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import btc_price, ntfy

ROUND_TO = 500


def current_ref() -> int:
    raw = os.environ.get("BTC_REF_PRICE")
    if raw:
        try:
            return int(float(raw))
        except ValueError:
            pass
    return 79500


def gh_set_variable(name: str, value: str) -> bool:
    try:
        subprocess.run(
            ["gh", "variable", "set", name, "-b", value],
            check=True,
            capture_output=True,
            text=True,
        )
        return True
    except subprocess.CalledProcessError as e:
        print(f"[ERR] gh variable set: {e.stderr}", file=sys.stderr)
        return False


def main() -> int:
    high = btc_price.fetch_30d_high()
    if high is None:
        print("[WARN] could not fetch 30d high — skipping update")
        return 0

    new_ref = int(math.ceil(high / ROUND_TO) * ROUND_TO)
    cur = current_ref()
    print(f"30d high: ${high:,.2f} | rounded REF: ${new_ref:,} | current: ${cur:,}")

    if new_ref == cur:
        print("No change.")
        return 0

    if not gh_set_variable("BTC_REF_PRICE", str(new_ref)):
        return 1

    delta_pct = round((new_ref / cur - 1) * 100, 1) if cur else 0
    ntfy.push(
        "🔧 REF 价格更新",
        f"BTC 30d 滚动高点: ${high:,.0f}\n"
        f"REF: ${cur:,} → ${new_ref:,} ({delta_pct:+.1f}%)\n"
        f"Tier 触发价随之调整。",
        priority="low",
        tags="gear",
        thread="ref-update",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
