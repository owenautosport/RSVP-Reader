"""Orchestrate the self-update: check -> compare -> download -> apply -> relaunch.

This is a thin coordinator over four collaborators (provider, version compare,
downloader, applier), all injectable, so the whole flow is testable with fakes
and the network/filesystem effects stay at the edges.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import platform
from pathlib import Path
from typing import Callable

from .assets import choose_asset
from .release import GithubReleaseProvider, Release, ReleaseProvider
from .version import is_newer

_log = logging.getLogger(__name__)

ProgressFn = Callable[[int, int], None]  # (bytes_done, bytes_total)


class NoAssetError(Exception):
    """This release has no installer for the running OS; caller should fall back
    to opening the release page for a manual download."""


class IntegrityError(Exception):
    """The downloaded installer's SHA-256 didn't match GitHub's published asset
    digest; the bytes are not what the release promised, so we refuse to apply."""


def _sha256_file(path: Path) -> str:
    """Hex SHA-256 of a file, read in chunks (installers are a few MB)."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
        # Stable channel: never offer prereleases as an update.
        if release.prerelease:
            return ("current", release)
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
        # Verify the bytes against GitHub's published per-asset digest. Older
        # releases may not carry one — then we can't verify, so we log a note and
        # proceed (the https/host allowlist still constrains where bytes came from).
        if asset.digest.startswith("sha256:"):
            expected = asset.digest.split(":", 1)[1].strip().lower()
            actual = _sha256_file(path)
            if not hmac.compare_digest(expected, actual):
                raise IntegrityError(
                    f"installer digest mismatch for {asset.name}: "
                    f"expected {expected}, got {actual}")
        else:
            # No digest published; integrity couldn't be verified (the https +
            # GitHub-host allowlist still constrains where the bytes came from).
            _log.warning("update: asset %r has no sha256 digest; skipping integrity check",
                         asset.name)
        self._applier.apply(path)
