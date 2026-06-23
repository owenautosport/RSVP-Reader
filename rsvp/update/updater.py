"""Orchestrate the self-update: check -> compare -> download -> apply -> relaunch.

This is a thin coordinator over four collaborators (provider, version compare,
downloader, applier), all injectable, so the whole flow is testable with fakes
and the network/filesystem effects stay at the edges.
"""

from __future__ import annotations

import platform
from pathlib import Path
from typing import Callable

from .assets import choose_asset
from .release import GithubReleaseProvider, Release, ReleaseProvider
from .version import is_newer

ProgressFn = Callable[[int, int], None]  # (bytes_done, bytes_total)


class NoAssetError(Exception):
    """This release has no installer for the running OS; caller should fall back
    to opening the release page for a manual download."""


class Updater:
    def __init__(
        self,
        current_version: str,
        provider: ReleaseProvider | None = None,
        downloader=None,
        applier=None,
        system: str | None = None,
    ) -> None:
        self._current = current_version
        self._provider = provider or GithubReleaseProvider()
        self._system = system or platform.system()
        if downloader is None:
            from .downloader import Downloader  # lazy: only the real path needs it
            downloader = Downloader()
        if applier is None:
            from .apply import get_applier
            applier = get_applier(self._system)
        self._downloader = downloader
        self._applier = applier

    def status(self) -> tuple[str, Release | None]:
        """Distinguish the three outcomes a manual check cares about:
        ``("update", release)``, ``("current", release)``, or
        ``("offline", None)`` when the latest release can't be reached."""
        release = self._provider.latest()
        if release is None:
            return ("offline", None)
        if is_newer(self._current, release.version):
            return ("update", release)
        return ("current", release)

    def check(self) -> Release | None:
        """Return the latest release if it's newer than what's running, else None
        (also None when offline or no release exists)."""
        state, release = self.status()
        return release if state == "update" else None

    def download_and_apply(self, release: Release, progress: ProgressFn | None = None) -> None:
        """Download the installer for this OS and apply it (which relaunches the
        app). Raises ``NoAssetError`` when nothing installable is available."""
        asset = choose_asset(release, self._system)
        if asset is None:
            raise NoAssetError(release.version)
        path: Path = self._downloader.download(asset.url, progress=progress)
        self._applier.apply(path)
