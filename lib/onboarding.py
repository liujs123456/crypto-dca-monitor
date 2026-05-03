"""Cold storage onboarding tracker.

Tracks the user's progress through the hardware-wallet learning curve so that
when total assets cross the migration threshold (e.g. $10K), the migration SOP
is already practiced — no first-time-mistakes at high stakes.

State lives in `state/cold_storage_onboarding.json`:

    {
      "device_purchased": false,
      "device_purchased_at": null,
      "device_model": null,
      "seed_engraved": false,
      "seed_engraved_at": null,
      "seed_backup_count": 0,           # how many physical metal backups exist
      "test_receive_done": false,
      "test_receive_done_at": null,
      "test_send_done": false,
      "test_send_done_at": null,
      "factory_reset_recovery_test_done": false,
      "factory_reset_recovery_test_done_at": null,
      "ready_for_migration": false,     # auto-derived when all above are true
      "migration_threshold_usd": 10000,
      "notes": ""
    }

The fields are designed to be edited manually (it's a small JSON; user can
scripts/onboarding_mark.py or just open the file). The summary script renders
a progress bar that shows up in the monthly health-check + weekly summary.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STEPS = [
    ("device_purchased", "购买 Ledger 硬件钱包（官网，非二手）"),
    ("seed_engraved", "24-word seed 抄到金属板（≥1 份；推荐 2 份）"),
    ("test_receive_done", "测试 receive：从 OKX 提 $20 BTC 到 Ledger"),
    ("test_send_done", "测试 send：从 Ledger 提 $20 BTC 回 OKX"),
    ("factory_reset_recovery_test_done", "Factory reset + 用金属板恢复，验证 seed 可用"),
]


def default_state() -> dict[str, Any]:
    state = {step: False for step, _ in STEPS}
    state.update({
        f"{step}_at": None for step, _ in STEPS
    })
    state.update({
        "device_model": None,
        "seed_backup_count": 0,
        "ready_for_migration": False,
        "migration_threshold_usd": 10000,
        "notes": "",
    })
    return state


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return default_state()
    try:
        data = json.loads(path.read_text())
    except Exception:
        return default_state()
    # Backfill any missing keys (forward-compat for new steps)
    base = default_state()
    base.update(data)
    return base


def save(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True, ensure_ascii=False) + "\n")


def is_ready(state: dict[str, Any]) -> bool:
    return all(state.get(step, False) for step, _ in STEPS) and state.get("seed_backup_count", 0) >= 1


def progress_summary(state: dict[str, Any]) -> dict[str, Any]:
    completed = sum(1 for step, _ in STEPS if state.get(step, False))
    total = len(STEPS)
    return {
        "completed": completed,
        "total": total,
        "ready": is_ready(state),
        "next_step": next(
            (label for step, label in STEPS if not state.get(step, False)),
            None,
        ),
    }


def render_progress_block(state: dict[str, Any]) -> str:
    """Multi-line block suitable for embedding in ntfy notifications."""
    summary = progress_summary(state)
    lines = []
    if summary["ready"]:
        lines.append("✅ 冷钱包准备 100% — 已具备 $10K 阈值迁移条件")
    else:
        bar = "█" * summary["completed"] + "░" * (summary["total"] - summary["completed"])
        lines.append(f"❄️ 冷钱包准备 [{bar}] {summary['completed']}/{summary['total']}")
        if summary["next_step"]:
            lines.append(f"   下一步: {summary['next_step']}")
    for step, label in STEPS:
        check = "✅" if state.get(step, False) else "⬜️"
        ts = state.get(f"{step}_at")
        ts_str = f" ({ts[:10]})" if ts else ""
        lines.append(f"   {check} {label}{ts_str}")
    return "\n".join(lines)


def mark_step(state: dict[str, Any], step: str, done: bool = True, **extra) -> dict[str, Any]:
    """Mark a step done/undone. extra fields like device_model can be passed for the device step."""
    if step not in {s for s, _ in STEPS}:
        raise ValueError(f"unknown step: {step!r}; valid: {[s for s, _ in STEPS]}")
    state = dict(state)
    state[step] = done
    state[f"{step}_at"] = datetime.now(timezone.utc).isoformat() if done else None
    for k, v in extra.items():
        state[k] = v
    state["ready_for_migration"] = is_ready(state)
    return state
