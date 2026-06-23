import hashlib
import tempfile
import unittest
import urllib.request
from pathlib import Path

from rsvp.update.downloader import (
    Downloader,
    InsecureURLError,
    _AllowlistRedirectHandler,
)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "source.bin"
        self.payload = b"RSVP-installer-bytes" * 5000  # ~100 KB, multi-chunk
        self.src.write_bytes(self.payload)
        self.url = self.src.as_uri()  # file:// URL — no network

    def _dl(self):
        # file:// URLs need the test-only insecure override (production enforces
        # https + a GitHub host allowlist).
        return Downloader(_allow_insecure=True)

    def test_writes_exact_bytes_to_dest(self):
        dest = self.tmp / "out.bin"
        result = self._dl().download(self.url, dest=dest)
        self.assertEqual(result, dest)
        self.assertEqual(dest.read_bytes(), self.payload)

    def test_reports_progress_reaching_total(self):
        seen = []
        self._dl().download(self.url, dest=self.tmp / "out2.bin",
                            progress=lambda d, t: seen.append((d, t)))
        self.assertTrue(seen)
        done, total = seen[-1]
        self.assertEqual(done, len(self.payload))
        self.assertEqual(total, len(self.payload))

    def test_default_dest_is_created_and_returned(self):
        result = self._dl().download(self.url)
        self.assertTrue(result.exists())
        self.assertEqual(result.read_bytes(), self.payload)

    def test_computes_sha256_of_downloaded_bytes(self):
        dl = self._dl()
        dl.download(self.url, dest=self.tmp / "out3.bin")
        self.assertEqual(dl.last_sha256, hashlib.sha256(self.payload).hexdigest())


class URLAllowlistTests(unittest.TestCase):
    def test_rejects_http_scheme_by_default(self):
        with self.assertRaises(InsecureURLError):
            Downloader().download("http://github.com/owen/x.exe")

    def test_rejects_non_github_https_host(self):
        with self.assertRaises(InsecureURLError):
            Downloader().download("https://evil.example.com/x.exe")

    def test_accepts_github_https_host(self):
        # Should pass the allowlist check (it then fails opening the URL, which
        # is a different/expected error — not InsecureURLError).
        with self.assertRaises(Exception) as ctx:
            Downloader().download("https://objects.githubusercontent.com/no-such")
        self.assertNotIsInstance(ctx.exception, InsecureURLError)


class RedirectAllowlistTests(unittest.TestCase):
    def test_redirect_to_untrusted_host_is_refused(self):
        h = _AllowlistRedirectHandler()
        with self.assertRaises(InsecureURLError):
            h.redirect_request(None, None, 302, "Found", {}, "https://evil.example.com/x")

    def test_redirect_to_github_host_is_allowed(self):
        h = _AllowlistRedirectHandler()
        req = urllib.request.Request("https://github.com/owenautosport/RSVP-Reader/x")
        out = h.redirect_request(req, None, 302, "Found", {},
                                 "https://objects.githubusercontent.com/y")
        self.assertIsNotNone(out)


if __name__ == "__main__":
    unittest.main()
