import unittest
from pathlib import Path

from rsvp.update.release import Asset, Release
from rsvp.update.updater import NoAssetError, Updater


class FakeProvider:
    def __init__(self, release):
        self.release = release
        self.calls = 0

    def latest(self):
        self.calls += 1
        return self.release


class FakeDownloader:
    def __init__(self):
        self.downloaded = None
        self.progress_seen = False

    def download(self, url, progress=None):
        self.downloaded = url
        if progress:
            progress(50, 100)
            self.progress_seen = True
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


if __name__ == "__main__":
    unittest.main()
