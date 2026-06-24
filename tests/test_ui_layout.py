import unittest

from rsvp.ui.layout import reading_font_size, word_font_size


class WordFontSizeTests(unittest.TestCase):
    def test_baseline_window_keeps_the_design_size(self):
        # The default 640x340 window must still render the word at 56pt.
        self.assertEqual(word_font_size(640, 340), 56)

    def test_scales_up_proportionally(self):
        self.assertEqual(word_font_size(1280, 680), 112)

    def test_grows_when_window_grows(self):
        self.assertGreater(word_font_size(900, 500), word_font_size(640, 340))

    def test_clamped_to_a_maximum(self):
        self.assertEqual(word_font_size(6000, 6000), 200)

    def test_clamped_to_a_minimum(self):
        self.assertEqual(word_font_size(80, 80), 24)

    def test_limited_by_width_on_a_tall_narrow_window(self):
        # A tall but narrow window must shrink the word so long words still fit.
        self.assertEqual(word_font_size(400, 1600), 35)

    def test_limited_by_height_on_a_wide_short_window(self):
        self.assertEqual(word_font_size(1600, 300), 49)


class ReadingFontSizeTests(unittest.TestCase):
    def test_baseline(self):
        self.assertEqual(reading_font_size(640, 340), 16)

    def test_scales_up(self):
        self.assertGreater(reading_font_size(1280, 680), 16)

    def test_clamped_min_and_max(self):
        self.assertEqual(reading_font_size(80, 80), 12)
        self.assertEqual(reading_font_size(6000, 6000), 40)

    def test_limited_by_the_tighter_dimension(self):
        # A tall narrow window scales by width, not the larger height.
        self.assertEqual(reading_font_size(400, 1600), reading_font_size(400, 400))


if __name__ == "__main__":
    unittest.main()
