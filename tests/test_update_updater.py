import hashlib
import logging
import tempfile
import unittest
from pathlib import Path

from rsvp.update.release import Asset, Release
from rsvp.update.updater import IntegrityError, NoAssetError, Updater


def setUpModule():
    # The no-digest path logs a warning by design; silence it so test output
    # stays clean (real errors still surface).
    logging.getLogger("rsvp.update.updater").setLevel(logging.ERROR)


class FakeProvider:
    def __init__(self, release):
        self.release = release
        self.calls = 0

    def latest(self):
        self.calls += 1
        return self.release


class FakeDownloader:
    def __init__(self, content=None):
        self.downloaded = None
        self.progress_seen = False
        self._content = content  # if set, writes real bytes so a digest can be checked

    def download(self, url, progress=None):
        self.downloaded = url
        if progress:
            progress(50, 100)
            self.progress_seen = True
        if self._content is not None:
            fd, tmp = tempfile.mkstemp(prefix="rsvp-test-")
            Path(tmp).write_bytes(self._content)
            return Path(tmp)
        return Path("/tmp/downloaded-installer")


class FakeApplier:
    def __init__(self):
        self.applied = None

    def apply(self, path):
        self.applied = path


def _release(version="v1.1.0", assets=None):
    if assets is None:
        assets = [Asset("RSVP-Setup.exe", "https://x/setup.exe")]
    return Release(version=version, notes="notes", html_url="https://x/rel", assets=assets)


def _updater(release, system="Windows"):
    prov, dl, ap = FakeProvider(release), FakeDownloader(), FakeApplier()
    up = Updater(current_version="1.0.0", provider=prov,
                 downloader=dl, applier=ap, system=system)
    return up, prov, dl, ap


class CheckTests(unittest.TestCase):
    def test_returns_release_when_newer(self):
        up, prov, _, _ = _updater(_release("v1.1.0"))
        self.assertEqual(up.check().version, "v1.1.0")
        self.assertEqual(prov.calls, 1)

    def test_returns_none_when_same_version(self):
        up, _, _, _ = _updater(_release("v1.0.0"))
        self.assertIsNone(up.check())

    def test_returns_none_when_offline(self):
        up, _, _, _ = _updater(None)
        self.assertIsNone(up.check())


class StatusTests(unittest.TestCase):
    def test_update_when_newer(self):
        up, _, _, _ = _updater(_release("v1.1.0"))
        state, rel = up.status()
        self.assertEqual(state, "update")
        self.assertEqual(rel.version, "v1.1.0")

    def test_current_when_same(self):
        up, _, _, _ = _updater(_release("v1.0.0"))
        state, rel = up.status()
        self.assertEqual(state, "current")
        self.assertIsNotNone(rel)

    def test_offline_when_provider_returns_none(self):
        up, _, _, _ = _updater(None)
        self.assertEqual(up.status(), ("offline", None))


class DownloadAndApplyTests(unittest.TestCase):
    def test_downloads_then_applies_chosen_asset(self):
        up, _, dl, ap = _updater(_release())
        up.download_and_apply(_release())
        self.assertEqual(dl.downloaded, "https://x/setup.exe")
        self.assertEqual(ap.applied, Path("/tmp/downloaded-installer"))

    def test_forwards_progress_callback(self):
        up, _, dl, _ = _updater(_release())
        seen = []
        up.download_and_apply(_release(), progress=lambda d, t: seen.append((d, t)))
        self.assertTrue(dl.progress_seen)
        self.assertEqual(seen, [(50, 100)])

    def test_raises_when_no_asset_for_this_os(self):
        rel = _release(assets=[Asset("only.dmg", "https://x/d")])
        up, _, _, ap = _updater(rel, system="Windows")
        with self.assertRaises(NoAssetError):
            up.download_and_apply(rel)
        self.assertIsNone(ap.applied)


class IntegrityTests(unittest.TestCase):
    def _setup(self, content, digest):
        asset = Asset("RSVP-Setup.exe", "https://x/setup.exe", digest=digest)
        rel = _release(assets=[asset])
        prov = FakeProvider(rel)
        dl = FakeDownloader(content=content)
        ap = FakeApplier()
        up = Updater(current_version="1.0.0", provider=prov,
                     downloader=dl, applier=ap, system="Windows")
        return up, rel, ap

    def test_matching_digest_applies(self):
        payload = b"installer-bytes"
        digest = "sha256:" + hashlib.sha256(payload).hexdigest()
        up, rel, ap = self._setup(payload, digest)
        up.download_and_apply(rel)
        self.assertIsNotNone(ap.applied)

    def test_mismatched_digest_raises_and_does_not_apply(self):
        up, rel, ap = self._setup(b"installer-bytes", "sha256:" + "0" * 64)
        with self.assertRaises(IntegrityError):
            up.download_and_apply(rel)
        self.assertIsNone(ap.applied)

    def test_missing_digest_still_applies(self):
        up, rel, ap = self._setup(b"installer-bytes", "")
        up.download_and_apply(rel)
        self.assertIsNotNone(ap.applied)


class PrereleaseTests(unittest.TestCase):
    def test_prerelease_is_not_offered_as_update(self):
        rel = Release(version="v2.0.0", prerelease=True,
                      assets=[Asset("RSVP-Setup.exe", "https://x/setup.exe")])
        up, _, _, _ = _updater(rel)
        state, returned = up.status()
        self.assertEqual(state, "current")  # newer, but prerelease → not offered
        self.assertIs(returned, rel)
        self.assertIsNone(up.check())


if __name__ == "__main__":
    unittest.main()
