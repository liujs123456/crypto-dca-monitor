"""ntfy push helper.

Uses ntfy's JSON publishing API (POST to https://ntfy.sh/ with a JSON body),
not the header-based API. Reason: HTTP headers are restricted to latin-1, so
emoji in titles (🟠 🚨 🔧 etc.) will raise UnicodeEncodeError if passed via
a Title header. The JSON body accepts UTF-8 cleanly.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _to_int_priority(p: str | int) -> int:
    if isinstance(p, int):
        return p
    return {
        "min": 1, "low": 2, "default": 3, "high": 4, "max": 5, "urgent": 5,
    }.get(p.lower(), 3)


def push(
    title: str,
    body: str,
    *,
    priority: str | int = "default",
    tags: str = "",
    click: str | None = None,
) -> bool:
    topic = os.environ["NTFY_TOPIC"]
    payload: dict = {
        "topic": topic,
        "title": title,
        "message": body,
        "priority": _to_int_priority(priority),
    }
    if tags:
        payload["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
    if click:
        payload["click"] = click

    req = urllib.request.Request(
        "https://ntfy.sh/",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        body_text = e.read().decode("utf-8", errors="ignore")
        print(f"[ERR] ntfy HTTP {e.code}: {body_text[:300]}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERR] ntfy push: {e}", file=sys.stderr)
        return False
