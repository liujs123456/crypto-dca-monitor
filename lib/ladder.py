"""Tier ladder math + state machine.

Tiers are percent-based offsets from a reference price (rolling 30d high):
    T1 = ref * 0.90  (-10%)
    T2 = ref * 0.85  (-15%)
    T3 = ref * 0.78  (-22%)
    T4 = ref * 0.68  (-32%)
    WATCH = ref * 0.92 (-8%, advance warning)

Rule: each tier fires ONCE. After firing it must rebound at least 5% above
its trigger price before it can re-arm.
"""
from __future__ import annotations

TIER_CONFIG = [
    ("T1", 0.90, 100),
    ("T2", 0.85, 200),
    ("T3", 0.78, 400),
    ("T4", 0.68, 800),
]
WATCH_FACTOR = 0.92
REARM_BUFFER = 0.05  # rebound 5% above trigger to re-arm


def tier_prices(ref: float) -> dict[str, float]:
    out = {name: round(ref * factor, 2) for name, factor, _ in TIER_CONFIG}
    out["WATCH"] = round(ref * WATCH_FACTOR, 2)
    return out


def classify_state(price: float, ref: float) -> str:
    prices = tier_prices(ref)
    if price < prices["T4"]:
        return "T4"
    if price < prices["T3"]:
        return "T3"
    if price < prices["T2"]:
        return "T2"
    if price < prices["T1"]:
        return "T1"
    if price < prices["WATCH"]:
        return "WATCH"
    return "GREEN"


def default_armed() -> dict[str, bool]:
    return {name: True for name, _, _ in TIER_CONFIG}


def update_armed(armed: dict[str, bool], price: float, ref: float) -> dict[str, bool]:
    """Re-arm any tier whose trigger price has rebounded by REARM_BUFFER."""
    new = dict(armed)
    prices = tier_prices(ref)
    for name, _, _ in TIER_CONFIG:
        if not new.get(name, True):
            rearm_threshold = prices[name] * (1 + REARM_BUFFER)
            if price >= rearm_threshold:
                new[name] = True
    return new


def decide_notification(
    state: str,
    prev_state: str,
    armed: dict[str, bool],
) -> tuple[str | None, dict[str, bool]]:
    """Return (notify_kind, new_armed).

    notify_kind is one of: "T1"/"T2"/"T3"/"T4"/"WATCH"/"RECOVERED" or None.
    Disarms the tier if it actually fires (so it can't fire again until re-armed).
    """
    rank = {"GREEN": 0, "WATCH": 1, "T1": 2, "T2": 3, "T3": 4, "T4": 5}
    cur, prev = rank.get(state, 0), rank.get(prev_state, 0)
    new_armed = dict(armed)

    if cur > prev:
        if state == "WATCH":
            return "WATCH", new_armed
        if state in armed and armed.get(state, True):
            new_armed[state] = False
            return state, new_armed
        return None, new_armed
    if cur < prev and state == "GREEN":
        return "RECOVERED", new_armed
    return None, new_armed


NOTIFICATION_TEMPLATES = {
    "WATCH":   ("🟡 WATCH: BTC 接近 Tier 1", "low",     "eyes",                          "BTC ${price} (ref ${ref}). 接近 Tier 1 (${t1})."),
    "T1":      ("🟠 T1 触发",                "high",    "chart_with_downwards_trend",    "BTC ${price}. Tier 1 触发. 加 $100. 开 Claude 确认."),
    "T2":      ("🟠 T2 触发",                "high",    "chart_with_downwards_trend",    "BTC ${price}. Tier 2 触发. 加 $200. 开 Claude 确认."),
    "T3":      ("🔴 T3: 深度修正",           "high",    "rotating_light",                "BTC ${price}. Tier 3 触发. 加 $400. 尽快开 Claude."),
    "T4":      ("🚨 T4: CAPITULATION",       "max",     "rotating_light,fire",           "🚨 BTC ${price}. Tier 4 触发. 加 $800."),
    "RECOVERED": ("✅ RECOVERED",            "low",     "white_check_mark",              "BTC 回到 ${price}. 已从触发恢复."),
}
