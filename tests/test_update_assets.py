import unittest

from rsvp.update.assets import choose_asset
from rsvp.update.release import Asset, Release


def _release():
    return Release(
        version="v1.1.0",
        assets=[
            Asset("RSVP-Pocket-Reader-1.1.0-Setup.exe", "https://x/setup.exe"),
            Asset("RSVP-Pocket-Reader-1.1.0-macOS.dmg", "https://x/app.dmg"),
            Asset("RSVP-Pocket-Reader-1.1.0-x86_64.AppImage", "https://x/app.AppImage"),
        ],
    )


class ChooseAssetTests(unittest.TestCase):
    def test_windows_picks_exe(self):
        self.assertEqual(choose_asset(_release(), "Windows").url, "https://x/setup.exe")

    def test_macos_picks_dmg(self):
        self.assertEqual(choose_asset(_release(), "Darwin").url, "https://x/app.dmg")

    def test_linux_picks_appimage(self):
        self.assertEqual(choose_asset(_release(), "Linux").url, "https://x/app.AppImage")

    def test_extension_match_is_case_insensitive(self):
        rel = Release(version="v1", assets=[Asset("Foo.EXE", "https://x/e")])
        self.assertEqual(choose_asset(rel, "Windows").url, "https://x/e")

    def test_no_matching_asset_returns_none(self):
        rel = Release(version="v1", assets=[Asset("only.dmg", "https://x/d")])
        self.assertIsNone(choose_asset(rel, "Windows"))

    def test_unknown_system_returns_none(self):
        self.assertIsNone(choose_asset(_release(), "Plan9"))


if __name__ == "__main__":
    unittest.main()
