"""Read/write the BTC monitor state file with corruption recovery.

If state/btc_state.json is missing, malformed, or has wrong shape, returns
(default_state, recovery_reason). Caller can then push a recovery alert and
overwrite with the default. Never raises on read.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import ladder

REQUIRED_KEYS = {"tier", "armed"}
VALID_TIERS = {"GREEN", "WATCH", "T1", "T2", "T3", "T4"}


def default_state() -> dict[str, Any]:
    return {
        "tier": "GREEN",
        "armed": ladder.default_armed(),
        "last_price": None,
        "last_ref": None,
        "last_check_utc": None,
    }


def _validate(data: Any) -> str | None:
    """Return None if valid, else a short reason string."""
    if not isinstance(data, dict):
        return "not a JSON object"
    missing = REQUIRED_KEYS - data.keys()
    if missing:
        return f"missing keys: {sorted(missing)}"
    if data["tier"] not in VALID_TIERS:
        return f"invalid tier value: {data['tier']!r}"
    armed = data.get("armed")
    if not isinstance(armed, dict):
        return "armed is not a dict"
    expected_armed_keys = {name for name, _, _ in ladder.TIER_CONFIG}
    if set(armed.keys()) != expected_armed_keys:
        return f"armed keys mismatch: have {sorted(armed.keys())}, want {sorted(expected_armed_keys)}"
    for k, v in armed.items():
        if not isinstance(v, bool):
            return f"armed[{k!r}] is not a bool"
    return None


def load(path: Path) -> tuple[dict[str, Any], str | None]:
    """Load state. Returns (state, recovery_reason).

    recovery_reason is None on success, otherwise a short string explaining why
    the file was rejected and defaults were used.
    """
    if not path.exists():
        return default_state(), None  # missing is fine on first run
    try:
        raw = path.read_text()
    except OSError as e:
        return default_state(), f"could not read state file: {e}"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        return default_state(), f"corrupted JSON: {e.msg} at line {e.lineno}"
    reason = _validate(data)
    if reason:
        return default_state(), reason
    # Normalize: ensure armed has all expected tier keys (forward-compat for added tiers)
    full_armed = ladder.default_armed()
    full_armed.update(data["armed"])
    data["armed"] = full_armed
    return data, None


def save(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
