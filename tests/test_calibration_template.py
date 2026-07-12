from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

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
    def test_successful_generation_saves_all_registered_areas(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            selected_regions = [region(index) for index in range(11)]
            select_region = Mock(side_effect=selected_regions)
            sleep_fn = Mock()
            output = StringIO()

            code = calibration_template.create_calibration_profile_interactive(
                base_dir=base_dir,
                input_func=Mock(return_value="main"),
                output=output,
                select_region=select_region,
                sleep_fn=sleep_fn,
                system_info_func=fixed_system_info,
            )

            self.assertEqual(code, calibration_template.EXIT_SUCCESS)
            self.assertEqual(select_region.call_count, 11)
            self.assertEqual(sleep_fn.call_count, 11)
            sleep_fn.assert_called_with(
                calibration_template.CALIBRATION_STEP_DELAY_SECONDS
            )
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
            sleep_fn = Mock()

            code = calibration_template.create_calibration_profile_interactive(
                base_dir=base_dir,
                input_func=Mock(return_value="main"),
                output=StringIO(),
                select_region=select_region,
                sleep_fn=sleep_fn,
                system_info_func=fixed_system_info,
            )

            self.assertEqual(code, calibration_template.EXIT_CANCELLED)
            self.assertEqual(sleep_fn.call_count, 2)
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
                sleep_fn=Mock(),
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
                sleep_fn=Mock(),
                system_info_func=fixed_system_info,
            )

            self.assertEqual(code, calibration_template.EXIT_SUCCESS)
            profile = load_profile("main", base_dir=base_dir)
            self.assertEqual(set(profile.areas), set(calibration_field_names()))

    def test_collect_calibration_areas_passes_min_size_and_prompt_to_selector(self):
        selected_regions = [region(index) for index in range(11)]
        select_region = Mock(side_effect=selected_regions)
        sleep_fn = Mock()

        areas = calibration_template.collect_calibration_areas(
            select_region=select_region,
            sleep_fn=sleep_fn,
            output=StringIO(),
        )

        self.assertEqual(tuple(areas), calibration_field_names())
        self.assertEqual(sleep_fn.call_count, 11)
        for call_args in select_region.call_args_list:
            kwargs = call_args.kwargs
            self.assertIn("min_size", kwargs)
            self.assertIn("instruction", kwargs)
            self.assertIn("subtitle", kwargs)

    def test_each_step_prints_prompt_then_waits_before_selection(self):
        events = []
        output = StringIO()
        prompt_snapshots = []

        def sleep_fn(seconds):
            prompt_snapshots.append(output.getvalue())
            events.append(("sleep", seconds))

        def select_region(**_kwargs):
            events.append(("select", None))
            return region(len(events))

        calibration_template.collect_calibration_areas(
            select_region=select_region,
            sleep_fn=sleep_fn,
            output=output,
        )

        self.assertEqual(len(events), 22)
        self.assertEqual(
            events,
            [
                event
                for _ in range(11)
                for event in (
                    ("sleep", calibration_template.CALIBRATION_STEP_DELAY_SECONDS),
                    ("select", None),
                )
            ],
        )
        text = output.getvalue()
        self.assertEqual(text.count("当前步骤："), 11)
        self.assertEqual(text.count("3 秒后开始框选……"), 11)
        for index, snapshot in enumerate(prompt_snapshots, start=1):
            self.assertEqual(snapshot.count("当前步骤："), index)
            self.assertEqual(snapshot.count("3 秒后开始框选……"), index)

    def test_selection_exception_does_not_wait_for_later_steps(self):
        sleep_fn = Mock()
        select_region = Mock(side_effect=[region(0), RuntimeError("selector failed")])

        with self.assertRaisesRegex(RuntimeError, "selector failed"):
            calibration_template.collect_calibration_areas(
                select_region=select_region,
                sleep_fn=sleep_fn,
                output=StringIO(),
            )

        self.assertEqual(select_region.call_count, 2)
        self.assertEqual(sleep_fn.call_count, 2)


if __name__ == "__main__":
    unittest.main()
