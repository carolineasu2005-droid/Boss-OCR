import inspect
import unittest

from ocr_calibration import (
    ScreenRegion,
    physical_point_from_overlay,
    region_from_points,
    select_screen_region,
)


class CalibrationTests(unittest.TestCase):
    def test_region_supports_reverse_drag(self):
        self.assertEqual(
            region_from_points((500, 400), (100, 150)),
            ScreenRegion(left=100, top=150, width=400, height=250),
        )

    def test_small_region_is_rejected(self):
        with self.assertRaises(ValueError):
            region_from_points((0, 0), (10, 10), min_size=80)

    def test_smaller_focus_region_can_use_a_custom_minimum(self):
        self.assertEqual(
            region_from_points((400, 350), (501, 401), min_size=20),
            ScreenRegion(left=400, top=350, width=101, height=51),
        )

    def test_screen_region_selector_keeps_ocr_prompt_defaults(self):
        parameters = inspect.signature(select_screen_region).parameters
        self.assertEqual(parameters["min_size"].default, 80)
        self.assertEqual(
            parameters["instruction"].default,
            "拖动框选候选人详情区域 · Esc 取消",
        )
        self.assertEqual(parameters["subtitle"].default, "第一版仅支持主显示器")

    def test_overlay_points_scale_to_physical_pixels_at_150_percent(self):
        monitor = ScreenRegion(left=0, top=0, width=1920, height=1080)
        self.assertEqual(
            physical_point_from_overlay((640, 360), (1280, 720), monitor),
            (960, 540),
        )

    def test_overlay_points_include_primary_monitor_offset(self):
        monitor = ScreenRegion(left=100, top=50, width=1600, height=900)
        self.assertEqual(
            physical_point_from_overlay((800, 450), (1600, 900), monitor),
            (900, 500),
        )


if __name__ == "__main__":
    unittest.main()
