"""ntfy push helper."""
from __future__ import annotations

import json
import os
import sys
import urllib.request


def push(
    title: str,
    body: str,
    *,
    priority: str | int = "default",
    tags: str = "",
    click: str | None = None,
) -> bool:
    topic = os.environ["NTFY_TOPIC"]
    headers = {
        "Title": title,
        "Priority": str(priority),
    }
    if tags:
        headers["Tags"] = tags
    if click:
        headers["Click"] = click

    req = urllib.request.Request(
        f"https://ntfy.sh/{topic}",
        data=body.encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"[ERR] ntfy push: {e}", file=sys.stderr)
        return False
