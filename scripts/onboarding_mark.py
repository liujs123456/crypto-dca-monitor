#!/usr/bin/env python3
"""CLI to update cold-storage onboarding state.

Usage:
    python3 scripts/onboarding_mark.py status
    python3 scripts/onboarding_mark.py mark device_purchased --device-model "Ledger Nano X"
    python3 scripts/onboarding_mark.py mark seed_engraved --backup-count 2
    python3 scripts/onboarding_mark.py mark test_receive_done
    python3 scripts/onboarding_mark.py mark test_send_done
    python3 scripts/onboarding_mark.py mark factory_reset_recovery_test_done
    python3 scripts/onboarding_mark.py unmark <step>
    python3 scripts/onboarding_mark.py note "any free-form note"

Edits state/cold_storage_onboarding.json (committed back by the workflow that
calls this; or just run locally and commit by hand).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib import onboarding

STATE_PATH = ROOT / "state" / "cold_storage_onboarding.json"


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="print current onboarding state")

    p_mark = sub.add_parser("mark", help="mark a step as completed")
    p_mark.add_argument("step", choices=[s for s, _ in onboarding.STEPS])
    p_mark.add_argument("--device-model", default=None)
    p_mark.add_argument("--backup-count", type=int, default=None,
                        help="number of physical metal backups (only for seed_engraved)")

    p_unmark = sub.add_parser("unmark", help="unmark a step")
    p_unmark.add_argument("step", choices=[s for s, _ in onboarding.STEPS])

    p_note = sub.add_parser("note", help="set free-form note")
    p_note.add_argument("text")

    args = parser.parse_args()
    state = onboarding.load(STATE_PATH)

    if args.cmd == "status":
        print(onboarding.render_progress_block(state))
        if state.get("device_model"):
            print(f"\nDevice: {state['device_model']}")
        if state.get("notes"):
            print(f"Notes: {state['notes']}")
        return 0

    if args.cmd == "mark":
        extra = {}
        if args.device_model:
            extra["device_model"] = args.device_model
        if args.backup_count is not None:
            extra["seed_backup_count"] = args.backup_count
        state = onboarding.mark_step(state, args.step, done=True, **extra)
        onboarding.save(STATE_PATH, state)
        print(f"✅ Marked {args.step} as done.")
        print(onboarding.render_progress_block(state))
        return 0

    if args.cmd == "unmark":
        state = onboarding.mark_step(state, args.step, done=False)
        onboarding.save(STATE_PATH, state)
        print(f"⬜️ Unmarked {args.step}.")
        return 0

    if args.cmd == "note":
        state["notes"] = args.text
        onboarding.save(STATE_PATH, state)
        print(f"📝 Note saved: {args.text}")
        return 0

    return 2


if __name__ == "__main__":
    sys.exit(main())
