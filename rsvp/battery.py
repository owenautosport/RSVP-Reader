"""Read the system battery level — cross-platform.

Isolated so the hardware port (and each desktop OS) only swaps this one file.

  * macOS   : the ``pmset`` command
  * Windows : GetSystemPowerStatus via ctypes
  * Linux   : /sys/class/power_supply

Each returns ``(percent, charging)`` or ``None`` when it can't be determined
(e.g. a desktop with no battery). No third-party dependencies.
"""

from __future__ import annotations

import sys


def read_battery() -> tuple[int, bool] | None:
    try:
        if sys.platform == "darwin":
            return _macos()
        if sys.platform.startswith("win"):
            return _windows()
        return _linux()
    except Exception:
        return None


def _macos() -> tuple[int, bool] | None:
    import re
    import subprocess

    out = subprocess.run(
        ["pmset", "-g", "batt"], capture_output=True, text=True, timeout=2
    ).stdout
    m = re.search(r"(\d+)%", out)
    if not m:
        return None
    percent = max(0, min(100, int(m.group(1))))
    low = out.lower()
    charging = "discharging" not in low and (
        "ac power" in low or "charging" in low or "charged" in low
    )
    return percent, charging


def _windows() -> tuple[int, bool] | None:
    import ctypes

    class _Status(ctypes.Structure):
        _fields_ = [
            ("ACLineStatus", ctypes.c_byte),
            ("BatteryFlag", ctypes.c_byte),
            ("BatteryLifePercent", ctypes.c_byte),
            ("SystemStatusFlag", ctypes.c_byte),
            ("BatteryLifeTime", ctypes.c_ulong),
            ("BatteryFullLifeTime", ctypes.c_ulong),
        ]

    status = _Status()
    if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status)):
        return None
    percent = status.BatteryLifePercent
    if percent == 255:  # unknown / no battery
        return None
    charging = status.ACLineStatus == 1
    return max(0, min(100, percent)), charging


def _linux() -> tuple[int, bool] | None:
    from pathlib import Path

    base = Path("/sys/class/power_supply")
    for bat in sorted(base.glob("BAT*")):
        try:
            percent = int((bat / "capacity").read_text().strip())
        except (OSError, ValueError):
            continue
        try:
            charging = (bat / "status").read_text().strip().lower() != "discharging"
        except OSError:
            charging = False
        return max(0, min(100, percent)), charging
    return None
