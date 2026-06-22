"""Read the system battery level.

Isolated so the hardware port only swaps this one file. On the Mac dev host the
source is the local ``pmset`` command (offline, no dependencies); the pocket
device will read its own battery gauge here instead.
"""

from __future__ import annotations

import re
import subprocess


def read_battery() -> tuple[int, bool] | None:
    """Return ``(percent, charging)`` or ``None`` if it can't be determined."""
    try:
        out = subprocess.run(
            ["pmset", "-g", "batt"],
            capture_output=True, text=True, timeout=2,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    m = re.search(r"(\d+)%", out)
    if not m:
        return None
    percent = max(0, min(100, int(m.group(1))))
    low = out.lower()
    charging = "discharging" not in low and (
        "ac power" in low or "charging" in low or "charged" in low
    )
    return percent, charging
