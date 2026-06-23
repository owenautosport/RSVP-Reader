"""Pick the installer asset that matches the running OS.

The release-CI publishes one asset per platform; we match on file extension,
which is stable across version-number changes in the filename.
"""

from __future__ import annotations

from .release import Asset, Release

# platform.system() -> the installer extension we want for that OS.
_EXT_BY_SYSTEM = {
    "Windows": ".exe",
    "Darwin": ".dmg",
    "Linux": ".appimage",
}


def choose_asset(release: Release, system: str) -> Asset | None:
    """Return the asset for ``system`` (a ``platform.system()`` value), or None
    when this release carries nothing installable for it."""
    ext = _EXT_BY_SYSTEM.get(system)
    if ext is None:
        return None
    for asset in release.assets:
        if asset.name.lower().endswith(ext):
            return asset
    return None
