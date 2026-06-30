import unittest

from ocr_calibration import ScreenRegion, region_from_points


class CalibrationTests(unittest.TestCase):
    def test_region_supports_reverse_drag(self):
        self.assertEqual(
            region_from_points((500, 400), (100, 150)),
            ScreenRegion(left=100, top=150, width=400, height=250),
        )

    def test_small_region_is_rejected(self):
        with self.assertRaises(ValueError):
            region_from_points((0, 0), (10, 10), min_size=80)


if __name__ == "__main__":
    unittest.main()
