"""Model a GitHub release and fetch the latest one.

``parse_release`` is pure (JSON dict in, ``Release`` out) so it's fully testable
without a network. ``GithubReleaseProvider`` is the only thing that opens a
socket; it's behind the ``ReleaseProvider`` protocol so tests inject a fake.
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

# Public repo, anonymous read — no token, no account.
LATEST_URL = "https://api.github.com/repos/owenautosport/RSVP-Reader/releases/latest"
_TIMEOUT = 5.0  # seconds; a slow/absent network must never stall the app


@dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int = 0


@dataclass(frozen=True)
class Release:
    version: str                       # the git tag, e.g. "v1.1.0"
    notes: str = ""                    # the release body (markdown)
    prerelease: bool = False
    html_url: str = ""                 # release page, for the manual-download fallback
    assets: list[Asset] = field(default_factory=list)


def parse_release(data: dict) -> Release:
    """Turn the GitHub releases/latest JSON into a ``Release``.

    Tolerant of missing keys: assets without a download URL are dropped (e.g.
    GitHub's auto-generated source tarballs), never raising on a thin payload.
    """
    assets: list[Asset] = []
    for raw in data.get("assets") or []:
        url = raw.get("browser_download_url")
        if not url:
            continue
        assets.append(Asset(name=raw.get("name", ""), url=url, size=int(raw.get("size", 0) or 0)))
    return Release(
        version=str(data.get("tag_name") or ""),
        notes=str(data.get("body") or ""),
        prerelease=bool(data.get("prerelease", False)),
        html_url=str(data.get("html_url") or ""),
        assets=assets,
    )


class ReleaseProvider(Protocol):
    def latest(self) -> Release | None:
        """Return the latest release, or None if it can't be determined."""


class GithubReleaseProvider:
    """Reads the public releases/latest endpoint. Returns None on any network or
    parse error — being offline is normal, not exceptional."""

    def __init__(self, url: str = LATEST_URL, timeout: float = _TIMEOUT) -> None:
        self._url = url
        self._timeout = timeout

    def latest(self) -> Release | None:
        try:
            req = urllib.request.Request(
                self._url, headers={"Accept": "application/vnd.github+json",
                                    "User-Agent": "RSVP-Reader"}
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict) or not data.get("tag_name"):
            return None
        return parse_release(data)
