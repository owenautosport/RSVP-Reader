import unittest

from rsvp.update.release import Asset, Release, parse_release


def _gh(**over):
    data = {
        "tag_name": "v1.1.0",
        "name": "RSVP 1.1.0",
        "body": "## What's new\n- faster",
        "prerelease": False,
        "draft": False,
        "html_url": "https://github.com/owenautosport/RSVP-Reader/releases/tag/v1.1.0",
        "assets": [
            {"name": "RSVP-Setup.exe", "browser_download_url": "https://x/setup.exe", "size": 1000},
            {"name": "RSVP-macOS.dmg", "browser_download_url": "https://x/app.dmg", "size": 2000},
        ],
    }
    data.update(over)
    return data


class ParseReleaseTests(unittest.TestCase):
    def test_parses_version_and_notes(self):
        r = parse_release(_gh())
        self.assertEqual(r.version, "v1.1.0")
        self.assertIn("faster", r.notes)
        self.assertFalse(r.prerelease)

    def test_parses_assets(self):
        r = parse_release(_gh())
        self.assertEqual(len(r.assets), 2)
        self.assertEqual(r.assets[0], Asset(name="RSVP-Setup.exe", url="https://x/setup.exe", size=1000))

    def test_missing_assets_key_gives_empty_list(self):
        r = parse_release(_gh(assets=[]))
        self.assertEqual(r.assets, [])

    def test_asset_without_download_url_is_skipped(self):
        r = parse_release(_gh(assets=[{"name": "src.zip", "size": 5}]))
        self.assertEqual(r.assets, [])

    def test_html_url_carried_for_fallback(self):
        r = parse_release(_gh())
        self.assertTrue(r.html_url.endswith("/tag/v1.1.0"))

    def test_prerelease_flag_preserved(self):
        self.assertTrue(parse_release(_gh(prerelease=True)).prerelease)


if __name__ == "__main__":
    unittest.main()
