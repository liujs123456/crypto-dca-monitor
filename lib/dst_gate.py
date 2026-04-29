"""DST gate: skip a workflow run if the current UTC time isn't the intended PT time.

GH Actions cron only supports UTC. To run a workflow at a fixed PT time across
DST changes, we schedule it at BOTH possible UTC times (PDT and PST shifts) and
let this gate filter which one actually runs.

Usage in a workflow step:
    if python3 -m lib.dst_gate skip-if-not 7 17; then exit 0; fi

That command exits 0 (= skip) when current PT time is NOT 7:17.
"""
from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
TOLERANCE_MIN = 30


def is_pt_now(target_h: int, target_m: int) -> bool:
    now = datetime.now(PT)
    target_minutes = target_h * 60 + target_m
    now_minutes = now.hour * 60 + now.minute
    return abs(now_minutes - target_minutes) <= TOLERANCE_MIN


def main() -> int:
    if len(sys.argv) != 4 or sys.argv[1] != "skip-if-not":
        print("usage: python3 -m lib.dst_gate skip-if-not <PT_hour> <PT_minute>", file=sys.stderr)
        return 2
    h, m = int(sys.argv[2]), int(sys.argv[3])
    if is_pt_now(h, m):
        print(f"PT time matches {h:02d}:{m:02d} — proceed.")
        return 1  # caller's `if` is false → don't skip
    pt_now = datetime.now(PT).strftime("%H:%M %Z")
    print(f"PT now is {pt_now}, target {h:02d}:{m:02d} — skip.")
    return 0  # caller's `if` is true → skip


if __name__ == "__main__":
    sys.exit(main())
