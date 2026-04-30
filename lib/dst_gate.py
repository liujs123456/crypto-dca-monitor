"""DST gate: skip a workflow run when the *triggering cron slot* is for the
opposite DST half of the year.

Each daily/weekly workflow has two cron entries (one PDT slot, one PST slot).
GitHub Actions cron firings are often delayed by 1-3 hours, so a clock-based
gate is unreliable — instead we read `github.event.schedule` (the literal cron
string that fired this run) and compare it against the currently-active DST
state of America/Los_Angeles. If the firing cron is for the wrong half, skip.

CLI:
    python3 -m lib.dst_gate skip-wrong-slot <triggered_cron> <pdt_cron> <pst_cron>
        exit 0  → caller should skip this run
        exit 1  → caller should proceed
        exit 2  → bad arguments

(Old `skip-if-not <PT_hour> <PT_minute>` mode is preserved for tests but no
longer used by the workflows.)
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
TOLERANCE_MIN = 30


def is_pt_now(target_h: int, target_m: int) -> bool:
    now = datetime.now(PT)
    target_minutes = target_h * 60 + target_m
    now_minutes = now.hour * 60 + now.minute
    return abs(now_minutes - target_minutes) <= TOLERANCE_MIN


def is_currently_pdt() -> bool:
    """True if America/Los_Angeles is currently observing DST (PDT, UTC-7)."""
    return datetime.now(PT).dst() != timedelta(0)


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: see module docstring", file=sys.stderr)
        return 2

    mode = sys.argv[1]

    if mode == "skip-if-not":
        if len(sys.argv) != 4:
            print("usage: skip-if-not <PT_hour> <PT_minute>", file=sys.stderr)
            return 2
        h, m = int(sys.argv[2]), int(sys.argv[3])
        if is_pt_now(h, m):
            print(f"PT time matches {h:02d}:{m:02d} — proceed.")
            return 1
        pt_now = datetime.now(PT).strftime("%H:%M %Z")
        print(f"PT now is {pt_now}, target {h:02d}:{m:02d} — skip.")
        return 0

    if mode == "skip-wrong-slot":
        if len(sys.argv) != 5:
            print("usage: skip-wrong-slot <triggered_cron> <pdt_cron> <pst_cron>", file=sys.stderr)
            return 2
        triggered = sys.argv[2].strip()
        pdt_cron = sys.argv[3].strip()
        pst_cron = sys.argv[4].strip()

        if not triggered:
            # Manual workflow_dispatch leaves github.event.schedule empty — proceed.
            print("No triggered cron (manual dispatch) — proceed.")
            return 1

        in_pdt = is_currently_pdt()
        active_label = "PDT" if in_pdt else "PST"
        active_cron = pdt_cron if in_pdt else pst_cron

        if triggered == active_cron:
            print(f"Currently {active_label}; triggered cron {triggered!r} matches active slot — proceed.")
            return 1

        print(
            f"Currently {active_label}; triggered cron {triggered!r} is the wrong slot "
            f"(active {active_label} slot is {active_cron!r}) — skip."
        )
        return 0

    print(f"unknown mode: {mode}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
