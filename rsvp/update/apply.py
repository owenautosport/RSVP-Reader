"""Apply a downloaded installer for the running OS, then relaunch.

This is the one genuinely side-effectful, hard-to-fully-unit-test corner of the
feature. Each applier's *dispatch and command construction* are tested with
injected runner/exiter fakes; the real install (running the NSIS installer,
swapping a mounted .app, replacing an AppImage) is verified manually against a
live release. Self-apply only makes sense for an installed/frozen build —
``can_self_apply`` is False when running from a source checkout, and the UI
falls back to opening the Releases page.

Code-signing note: installers aren't signed/notarized yet, so the OS may show one
Gatekeeper (macOS) / SmartScreen (Windows) prompt when the fresh installer runs —
the same prompt a manual download triggers. Built signing-ready.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable

Runner = Callable[[list], object]
Exiter = Callable[[], None]


def is_frozen() -> bool:
    """True when running as a packaged app (PyInstaller), where there's an
    installer/binary to replace."""
    return bool(getattr(sys, "frozen", False))


def can_self_apply() -> bool:
    return is_frozen()


def _default_exit() -> None:
    # Hand the install over and get out of the way so files unlock / the new
    # version can take over. The UI injects a version that tears down the window
    # first; this is the bare fallback.
    os._exit(0)


def _detached(cmd: list) -> object:
    """Start a process that outlives this one (so it can replace us)."""
    kwargs: dict = {}
    if os.name == "nt":
        # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen([str(c) for c in cmd], **kwargs)


class WindowsApplier:
    """Run the NSIS ``Setup.exe`` silently; it replaces the install and relaunches
    the app from its finish step."""

    def __init__(self, runner: Runner = _detached, exiter: Exiter = _default_exit) -> None:
        self._run = runner
        self._exit = exiter

    def apply(self, installer_path: Path) -> None:
        self._run([str(installer_path), "/S"])
        self._exit()


class LinuxApplier:
    """Swap the single AppImage file in place and re-exec it."""

    def __init__(self, appimage_path: str | None = None, execv=os.execv) -> None:
        self._target = appimage_path if appimage_path is not None else os.environ.get("APPIMAGE")
        self._execv = execv

    def apply(self, installer_path: Path) -> None:
        if not self._target:
            raise RuntimeError("APPIMAGE path unknown; cannot self-update")
        target = Path(self._target)
        os.replace(installer_path, target)  # atomic within the same filesystem
        target.chmod(target.stat().st_mode | 0o111)  # keep it executable
        self._execv(str(target), [str(target)])


class MacApplier:
    """Hand off to a detached shell that waits for us to quit, replaces the .app
    from the mounted DMG, strips quarantine, and relaunches."""

    def __init__(self, runner: Runner = _detached, exiter: Exiter = _default_exit,
                 app_path: str | None = None) -> None:
        self._run = runner
        self._exit = exiter
        self._app = app_path or _current_app_bundle()

    def apply(self, installer_path: Path) -> None:
        dmg = str(installer_path)
        app = self._app or "/Applications/RSVP Pocket E-Reader.app"
        pid = os.getpid()
        script = (
            f'while kill -0 {pid} 2>/dev/null; do sleep 0.3; done; '
            f'MNT=$(hdiutil attach -nobrowse "{dmg}" | grep -o "/Volumes/.*" | head -1); '
            f'SRC=$(find "$MNT" -maxdepth 1 -name "*.app" | head -1); '
            f'rm -rf "{app}"; cp -R "$SRC" "{app}"; '
            f'xattr -dr com.apple.quarantine "{app}" 2>/dev/null; '
            f'hdiutil detach "$MNT" 2>/dev/null; open "{app}"'
        )
        self._run(["/bin/sh", "-c", script])
        self._exit()


class _UnsupportedApplier:
    def apply(self, installer_path: Path) -> None:
        raise RuntimeError("Self-update is not supported on this platform")


def _current_app_bundle() -> str | None:
    """Best-effort path to the running ``.app`` bundle (…/Foo.app)."""
    exe = Path(sys.executable).resolve()
    for parent in exe.parents:
        if parent.suffix == ".app":
            return str(parent)
    return None


def get_applier(system: str):
    if system == "Windows":
        return WindowsApplier()
    if system == "Darwin":
        return MacApplier()
    if system == "Linux":
        return LinuxApplier()
    return _UnsupportedApplier()
