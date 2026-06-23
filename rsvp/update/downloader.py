"""Stream a release asset to a local file, reporting progress.

Downloads to a temp file and only the caller decides what to do once it's
complete — an interrupted download leaves a temp file, never a half-applied
install.

Before opening any URL we enforce https + a GitHub host allowlist (release
assets only ever live on GitHub), so a tampered releases payload can't point us
at an arbitrary host or a non-TLS link. The download also streams the bytes
through SHA-256 so the caller can verify them against GitHub's asset digest.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

_CHUNK = 64 * 1024
_TIMEOUT = 60.0  # an installer is a few MB; allow a slow link without hanging forever

ProgressFn = Callable[[int, int], None]


class InsecureURLError(Exception):
    """The asset URL isn't an https GitHub URL; we refuse to download it."""


# Hosts GitHub serves release assets/redirects from. Exact match, or a suffix
# match for the wildcard entries (".github.com" matches "objects.github.com").
_ALLOWED_HOSTS = ("github.com",)
_ALLOWED_SUFFIXES = (".github.com", ".githubusercontent.com")


def _check_url(url: str) -> None:
    """Raise ``InsecureURLError`` unless ``url`` is https on an allowed host."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https":
        raise InsecureURLError(f"refusing non-https update URL: {url!r}")
    ok = host in _ALLOWED_HOSTS or any(host.endswith(s) for s in _ALLOWED_SUFFIXES)
    if not ok:
        raise InsecureURLError(f"refusing update URL from untrusted host {host!r}")


class _AllowlistRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-checks every redirect target against the allowlist. GitHub's asset URL
    302s to ``objects.githubusercontent.com`` (allowed); a redirect to anywhere
    else is refused, so a tampered payload can't bounce us off-host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class Downloader:
    def __init__(self, _allow_insecure: bool = False) -> None:
        # _allow_insecure is TEST-ONLY: it relaxes the https/host check so the
        # unit tests can serve bytes from a local file:// URL. Production always
        # constructs Downloader() with the check ON.
        self._allow_insecure = _allow_insecure
        self.last_sha256 = ""  # hexdigest of the most recent download

    def download(self, url: str, dest: Path | None = None, progress: ProgressFn | None = None) -> Path:
        """Fetch ``url`` into ``dest`` (a temp file if omitted) and return its
        path. ``progress(bytes_done, bytes_total)`` is called as data arrives;
        ``bytes_total`` is 0 when the server doesn't report a length. The SHA-256
        of the fetched bytes is stored on ``self.last_sha256``."""
        if not self._allow_insecure:
            _check_url(url)

        if dest is None:
            name = url.rsplit("/", 1)[-1] or "rsvp-update"
            fd, tmp = tempfile.mkstemp(prefix="rsvp-update-", suffix="-" + name)
            os.close(fd)
            dest = Path(tmp)

        digest = hashlib.sha256()
        req = urllib.request.Request(url, headers={"User-Agent": "RSVP-Reader"})
        # In production, follow redirects only to allowlisted hosts. The insecure
        # test path (file://) uses the default opener (no redirects involved).
        if self._allow_insecure:
            opener = urllib.request.urlopen
        else:
            opener = urllib.request.build_opener(_AllowlistRedirectHandler()).open
        with opener(req, timeout=_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            done = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    digest.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total or done)
        self.last_sha256 = digest.hexdigest()
        return dest
