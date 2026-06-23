import tempfile
import unittest
from pathlib import Path

from rsvp.update.downloader import Downloader


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.src = self.tmp / "source.bin"
        self.payload = b"RSVP-installer-bytes" * 5000  # ~100 KB, multi-chunk
        self.src.write_bytes(self.payload)
        self.url = self.src.as_uri()  # file:// URL — no network

    def test_writes_exact_bytes_to_dest(self):
        dest = self.tmp / "out.bin"
        result = Downloader().download(self.url, dest=dest)
        self.assertEqual(result, dest)
        self.assertEqual(dest.read_bytes(), self.payload)

    def test_reports_progress_reaching_total(self):
        seen = []
        Downloader().download(self.url, dest=self.tmp / "out2.bin",
                              progress=lambda d, t: seen.append((d, t)))
        self.assertTrue(seen)
        done, total = seen[-1]
        self.assertEqual(done, len(self.payload))
        self.assertEqual(total, len(self.payload))

    def test_default_dest_is_created_and_returned(self):
        result = Downloader().download(self.url)
        self.assertTrue(result.exists())
        self.assertEqual(result.read_bytes(), self.payload)


if __name__ == "__main__":
    unittest.main()
