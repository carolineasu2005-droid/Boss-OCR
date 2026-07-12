from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, call, patch

import calibration_template
from calibration_profiles import load_profile, profile_path
from calibration_steps import calibration_field_names
from ocr_calibration import CalibrationCancelled, ScreenRegion


def region(index):
    return ScreenRegion(left=index, top=index + 1, width=20 + index, height=30 + index)


def fixed_system_info():
    return {
        "os": "Windows",
        "screen_width": 1920,
        "screen_height": 1080,
        "dpi_scale": 1.25,
    }


class CalibrationTemplateTests(unittest.TestCase):
    def setUp(self):
        self.sleep = patch.object(calibration_template.time, "sleep").start()
        self.addCleanup(patch.stopall)

    def test_successful_generation_saves_all_registered_areas(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            selected_regions = [region(index) for index in range(11)]
            select_region = Mock(side_effect=selected_regions)
            output = StringIO()

            code = calibration_template.create_calibration_profile_interactive(
                base_dir=base_dir,
                input_func=Mock(return_value="main"),
                output=output,
                select_region=select_region,
                system_info_func=fixed_system_info,
            )

            self.assertEqual(code, calibration_template.EXIT_SUCCESS)
            self.assertEqual(select_region.call_count, 11)
            profile = load_profile("main", base_dir=base_dir)
            self.assertEqual(set(profile.areas), set(calibration_field_names()))
            self.assertEqual(profile.system_info, fixed_system_info())
            text = output.getvalue()
            self.assertIn(
                "调用校准模板前，请确保 Boss 页面窗口位置、大小、缩放状态与校准时基本一致",
                text,
            )
            self.assertIn("旧模板中的点击区域可能发生偏移", text)

    def test_cancelled_step_does_not_save_incomplete_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            select_region = Mock(side_effect=[region(0), CalibrationCancelled()])

            code = calibration_template.create_calibration_profile_interactive(
                base_dir=base_dir,
                input_func=Mock(return_value="main"),
                output=StringIO(),
                select_region=select_region,
                system_info_func=fixed_system_info,
            )

            self.assertEqual(code, calibration_template.EXIT_CANCELLED)
            self.assertFalse(profile_path("main", base_dir).exists())

    def test_existing_profile_requires_overwrite_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            base_dir.mkdir(exist_ok=True)
            profile_path("main", base_dir).write_text("old", encoding="utf-8")
            input_func = Mock(side_effect=["main", "n"])
            select_region = Mock()

            code = calibration_template.create_calibration_profile_interactive(
                base_dir=base_dir,
                input_func=input_func,
                output=StringIO(),
                select_region=select_region,
                system_info_func=fixed_system_info,
            )

            self.assertEqual(code, calibration_template.EXIT_NOT_OVERWRITTEN)
            select_region.assert_not_called()
            self.assertEqual(profile_path("main", base_dir).read_text(encoding="utf-8"), "old")

    def test_existing_profile_can_be_overwritten_after_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            base_dir.mkdir(exist_ok=True)
            profile_path("main", base_dir).write_text("old", encoding="utf-8")
            input_func = Mock(side_effect=["main", "y"])
            select_region = Mock(side_effect=[region(index) for index in range(11)])

            code = calibration_template.create_calibration_profile_interactive(
                base_dir=base_dir,
                input_func=input_func,
                output=StringIO(),
                select_region=select_region,
                system_info_func=fixed_system_info,
            )

            self.assertEqual(code, calibration_template.EXIT_SUCCESS)
            profile = load_profile("main", base_dir=base_dir)
            self.assertEqual(set(profile.areas), set(calibration_field_names()))

    def test_collect_calibration_areas_passes_min_size_and_prompt_to_selector(self):
        selected_regions = [region(index) for index in range(11)]
        select_region = Mock(side_effect=selected_regions)

        areas = calibration_template.collect_calibration_areas(
            select_region=select_region,
            output=StringIO(),
        )

        self.assertEqual(tuple(areas), calibration_field_names())
        for call_args in select_region.call_args_list:
            kwargs = call_args.kwargs
            self.assertIn("min_size", kwargs)
            self.assertIn("instruction", kwargs)
            self.assertIn("subtitle", kwargs)

    def test_each_step_waits_three_seconds_before_region_selection(self):
        selected_regions = [region(index) for index in range(11)]
        calls = []

        def wait_before_selection(seconds, *, output):
            calls.append(("wait", seconds, output))

        def select_region(**_kwargs):
            calls.append(("select",))
            return selected_regions.pop(0)

        output = StringIO()
        calibration_template.collect_calibration_areas(
            select_region=select_region,
            wait_before_selection=wait_before_selection,
            output=output,
        )

        self.assertEqual(
            [item[0] for item in calls],
            [item for _ in calibration_field_names() for item in ("wait", "select")],
        )
        self.assertEqual(
            [item[1] for item in calls if item[0] == "wait"],
            [calibration_template.CALIBRATION_STEP_WAIT_SECONDS]
            * len(calibration_field_names()),
        )

    def test_wait_before_region_selection_counts_down_with_mocked_sleep(self):
        output = StringIO()

        calibration_template.wait_before_region_selection(output=output)

        self.sleep.assert_has_calls([call(1), call(1), call(1)])
        self.assertEqual(self.sleep.call_count, 3)
        self.assertIn("3 秒后开始框选", output.getvalue())


if __name__ == "__main__":
    unittest.main()
