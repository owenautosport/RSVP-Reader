import unittest

from rsvp.update.version import is_newer, parse_version


class ParseVersionTests(unittest.TestCase):
    def test_strips_leading_v_tag_prefix(self):
        self.assertEqual(parse_version("v1.2.3"), ((1, 2, 3), ()))

    def test_plain_release(self):
        self.assertEqual(parse_version("1.0.0"), ((1, 0, 0), ()))

    def test_prerelease_suffix_split_off(self):
        self.assertEqual(parse_version("1.0.0-beta"), ((1, 0, 0), ("beta",)))


class IsNewerTests(unittest.TestCase):
    def test_higher_minor_is_newer(self):
        self.assertTrue(is_newer("1.0.0", "1.1.0"))

    def test_tag_prefix_on_candidate(self):
        self.assertTrue(is_newer("1.0.0", "v1.1.0"))

    def test_equal_is_not_newer(self):
        self.assertFalse(is_newer("1.0.0", "1.0.0"))

    def test_lower_is_not_newer(self):
        self.assertFalse(is_newer("1.2.0", "1.0.0"))

    def test_major_bump(self):
        self.assertTrue(is_newer("0.9.0", "1.0.0"))

    def test_differing_lengths(self):
        self.assertTrue(is_newer("1.0", "1.0.1"))
        self.assertFalse(is_newer("1.0.0", "1.0"))

    def test_final_release_beats_its_prerelease(self):
        self.assertTrue(is_newer("1.0.0-beta", "1.0.0"))

    def test_prerelease_is_not_newer_than_final(self):
        self.assertFalse(is_newer("1.0.0", "1.0.0-beta"))

    def test_unparseable_candidate_is_not_newer(self):
        self.assertFalse(is_newer("1.0.0", "garbage"))


if __name__ == "__main__":
    unittest.main()
