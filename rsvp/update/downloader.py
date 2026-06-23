"""Stream a release asset to a local file, reporting progress.

Downloads to a temp file and only the caller decides what to do once it's
complete — an interrupted download leaves a temp file, never a half-applied
install.
"""

from __future__ import annotations

import tempfile
import urllib.request
from pathlib import Path
from typing import Callable

_CHUNK = 64 * 1024
_TIMEOUT = 60.0  # an installer is a few MB; allow a slow link without hanging forever

ProgressFn = Callable[[int, int], None]


class Downloader:
    def download(self, url: str, dest: Path | None = None, progress: ProgressFn | None = None) -> Path:
        """Fetch ``url`` into ``dest`` (a temp file if omitted) and return its
        path. ``progress(bytes_done, bytes_total)`` is called as data arrives;
        ``bytes_total`` is 0 when the server doesn't report a length."""
        if dest is None:
            name = url.rsplit("/", 1)[-1] or "rsvp-update"
            fd, tmp = tempfile.mkstemp(prefix="rsvp-update-", suffix="-" + name)
            import os
            os.close(fd)
            dest = Path(tmp)

        req = urllib.request.Request(url, headers={"User-Agent": "RSVP-Reader"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            total = int(resp.headers.get("Content-Length", 0) or 0)
            done = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(_CHUNK)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total or done)
        return dest
