from contextlib import ExitStack
from dataclasses import replace
import sys
import tempfile
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
import ocr_calibration
import simple_brush


class BrowserPrepareTests(unittest.TestCase):
    def assert_preflight_exits_without_business_actions(self, result, extra_args=()):
        argv = ["simple_brush.py", "--preflight-only", *extra_args]
        module_actions = (
            "get_user_input",
            "initialize_ocr",
            "click_first_candidate",
            "apply_batch_filter_and_open_first_candidate",
            "ensure_batch_filter_regions_calibrated",
            "ensure_focus_restore_region_calibrated",
            "ensure_forward_click_regions_calibrated",
            "ensure_ocr_region_calibrated",
            "view_candidate",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
            "select_screen_region",
            "save_region_preview",
            "MSSScreenCapture",
            "OCRKeywordDetector",
            "capture_screen_coordinate_diagnostics",
            "run_coordinate_diagnostics_only",
        )
        pyautogui_actions = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "argv", argv))
            prepare = stack.enter_context(
                patch.object(simple_brush, "prepare_browser", return_value=result)
            )
            blocked_actions = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in module_actions
            }
            blocked_actions["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked_actions.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_actions
                }
            )
            print_output = stack.enter_context(patch("builtins.print"))
            self.assertEqual(simple_brush.run(), 0)

        prepare.assert_called_once_with()
        for name, mock in blocked_actions.items():
            with self.subTest(blocked_action=name):
                mock.assert_not_called()
        return print_output

    def test_parse_args_recognizes_preflight_only_and_defaults_off(self):
        with patch.object(simple_brush.sys, "argv", ["simple_brush.py"]):
            default_args = simple_brush.parse_args()
        with patch.object(
            simple_brush.sys,
            "argv",
            [
                "simple_brush.py",
                "--preflight-only",
                "--auto",
                "--no-forward",
                "--no-batch-filter",
                "--simple-mouse",
            ],
        ):
            combined_args = simple_brush.parse_args()

        self.assertFalse(default_args["preflight_only"])
        self.assertTrue(combined_args["preflight_only"])
        self.assertTrue(combined_args["auto"])
        self.assertTrue(combined_args["no_forward"])
        self.assertTrue(combined_args["no_batch_filter"])
        self.assertTrue(combined_args["simple_mouse"])

    def test_parse_args_recognizes_coordinate_diagnostics_only_and_conflict(self):
        with patch.object(simple_brush.sys, "argv", ["simple_brush.py"]):
            default_args = simple_brush.parse_args()

        with patch.object(
            simple_brush.sys,
            "argv",
            [
                "simple_brush.py",
                "--coordinate-diagnostics-only",
            ],
        ):
            coordinate_args = simple_brush.parse_args()

        with patch.object(
            simple_brush.sys,
            "argv",
            [
                "simple_brush.py",
                "--coordinate-diagnostics-only",
                "--preflight-only",
            ],
        ):
            with self.assertRaisesRegex(ValueError, "不能与 --preflight-only 同时使用"):
                simple_brush.parse_args()

        self.assertFalse(default_args["coordinate_diagnostics_only"])
        self.assertTrue(coordinate_args["coordinate_diagnostics_only"])
        self.assertFalse(coordinate_args["preflight_only"])

    def test_preflight_only_combined_flags_still_only_run_preflight(self):
        result = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            message="permissions unknown",
            error_code="MACOS_PERMISSIONS_NOT_READY",
        )
        output = self.assert_preflight_exits_without_business_actions(
            result,
            (
                "--keywords",
                '"Python"',
                "--auto",
                "--no-forward",
                "--no-batch-filter",
                "--simple-mouse",
            ),
        )
        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in output.call_args_list
        )
        self.assertIn("platform: macos", rendered)
        self.assertIn("browser: chrome", rendered)
        self.assertIn("launched: True", rendered)
        self.assertIn("ready: False", rendered)
        self.assertIn("MACOS_PERMISSIONS_NOT_READY", rendered)
        self.assertIn("focus_frontmost: None", rendered)
        self.assertIn("page_url: none", rendered)
        self.assertIn("page_title: none", rendered)
        self.assertIn("page_allowed: None", rendered)
        self.assertIn("page_error_code: none", rendered)
        self.assertIn("diagnoses window focus and page identity", rendered)
        self.assertIn("does not validate Retina coordinates", rendered)

    def test_preflight_only_does_not_query_chrome_tab_identity(self):
        result = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            error_code="MACOS_PERMISSIONS_NOT_READY",
        )
        with (
            patch.object(
                simple_brush, "get_chrome_active_tab_identity"
            ) as tab_identity,
            patch.object(simple_brush, "is_allowed_boss_page") as page_allowed,
        ):
            self.assert_preflight_exits_without_business_actions(result)

        tab_identity.assert_not_called()
        page_allowed.assert_not_called()

    def test_preflight_only_does_not_touch_coordinate_diagnostics(self):
        result = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            error_code="MACOS_PERMISSIONS_NOT_READY",
        )
        with patch.object(
            simple_brush, "capture_screen_coordinate_diagnostics"
        ) as coordinate:
            self.assert_preflight_exits_without_business_actions(result)

        coordinate.assert_not_called()

    def test_preflight_only_prints_page_diagnostics_and_still_exits(self):
        result = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            focus_frontmost=True,
            page_url="https://www.zhipin.com/",
            page_title="BOSS直聘",
            page_allowed=True,
            page_error_code="MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY",
            error_code="MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY",
        )

        output = self.assert_preflight_exits_without_business_actions(result)
        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in output.call_args_list
        )

        self.assertIn("focus_frontmost: True", rendered)
        self.assertIn("page_url: https://www.zhipin.com/", rendered)
        self.assertIn("page_title: BOSS直聘", rendered)
        self.assertIn("page_allowed: True", rendered)
        self.assertIn(
            "page_error_code: MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY", rendered
        )

    def _coordinate_diagnostics_output(self, result):
        argv = ["simple_brush.py", "--coordinate-diagnostics-only"]
        module_actions = (
            "prepare_browser",
            "run_preflight_only",
            "get_user_input",
            "initialize_ocr",
            "click_first_candidate",
            "apply_batch_filter_and_open_first_candidate",
            "ensure_batch_filter_regions_calibrated",
            "ensure_focus_restore_region_calibrated",
            "ensure_forward_click_regions_calibrated",
            "ensure_ocr_region_calibrated",
            "view_candidate",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
            "select_screen_region",
            "save_region_preview",
            "MSSScreenCapture",
            "OCRKeywordDetector",
        )
        pyautogui_actions = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "argv", argv))
            coordinate = stack.enter_context(
                patch.object(
                    simple_brush,
                    "capture_screen_coordinate_diagnostics",
                    return_value=result,
                )
            )
            blocked_actions = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in module_actions
            }
            blocked_actions["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked_actions.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_actions
                }
            )
            print_output = stack.enter_context(patch("builtins.print"))
            self.assertEqual(simple_brush.run(), 0)

        coordinate.assert_called_once_with()
        for name, mock in blocked_actions.items():
            with self.subTest(blocked_action=name):
                mock.assert_not_called()
        return print_output

    def test_coordinate_diagnostics_only_runs_helper_and_exits(self):
        result = simple_brush.ScreenCoordinateDiagnostics(
            platform="darwin",
            pyautogui_size=(1512, 982),
            pyautogui_position=(12, 34),
            mss_monitors=(
                {
                    "left": 0,
                    "top": 0,
                    "width": 1512,
                    "height": 982,
                    "is_primary": True,
                },
                {
                    "left": 0,
                    "top": 0,
                    "width": 1512,
                    "height": 982,
                    "is_primary": True,
                },
            ),
            primary_monitor={
                "left": 0,
                "top": 0,
                "width": 1512,
                "height": 982,
                "is_primary": True,
            },
            tk_version="8.6",
            tcl_version="8.6",
            display_fingerprint="fingerprint",
            passed=True,
            message="ok",
        )
        output = self._coordinate_diagnostics_output(result)
        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in output.call_args_list
        )
        self.assertIn("Coordinate diagnostics only (no business actions):", rendered)
        self.assertIn("platform: darwin", rendered)
        self.assertIn("pyautogui_size: (1512, 982)", rendered)
        self.assertIn("pyautogui_position: (12, 34)", rendered)
        self.assertIn("display_fingerprint: fingerprint", rendered)
        self.assertIn("passed: True", rendered)
        self.assertIn("message: ok", rendered)

    def test_coordinate_diagnostics_only_does_not_save_crop_preview(self):
        result = simple_brush.ScreenCoordinateDiagnostics(
            platform="darwin",
            pyautogui_size=(1512, 982),
            pyautogui_position=(12, 34),
            mss_monitors=(),
            primary_monitor=None,
            tk_version="8.6",
            tcl_version="8.6",
            display_fingerprint="fingerprint",
            passed=True,
            message="ok",
        )
        with patch.object(
            simple_brush, "save_crop_preview_for_manual_check"
        ) as save_preview:
            self._coordinate_diagnostics_output(result)

        save_preview.assert_not_called()

    def test_capture_screen_coordinate_diagnostics_collects_macos_metadata(self):
        class FakeCapture:
            def __init__(self):
                self.grab = Mock()
                self.monitors = [
                    {
                        "left": 0,
                        "top": 0,
                        "width": 1512,
                        "height": 982,
                        "is_primary": False,
                    },
                    {
                        "left": 0,
                        "top": 0,
                        "width": 1512,
                        "height": 982,
                        "is_primary": True,
                    },
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_capture = FakeCapture()
        fake_mss = SimpleNamespace(MSS=Mock(return_value=fake_capture))
        fake_tk = SimpleNamespace(TkVersion=8.6, TclVersion=8.6)
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(simple_brush.pyautogui, "size", return_value=(1512, 982)),
            patch.object(simple_brush.pyautogui, "position", return_value=(12, 34)),
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "mouseDown") as mouse_down,
            patch.object(simple_brush.pyautogui, "mouseUp") as mouse_up,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
            patch.object(simple_brush.pyautogui, "typewrite") as typewrite,
            patch.object(simple_brush.listener, "start") as listener_start,
            patch.object(simple_brush, "initialize_ocr") as initialize_ocr,
            patch.object(simple_brush, "select_screen_region") as select_region,
            patch.dict(
                "sys.modules",
                {"mss": fake_mss, "tkinter": fake_tk},
            ),
        ):
            result = simple_brush.capture_screen_coordinate_diagnostics()

        self.assertTrue(result.passed)
        self.assertEqual(result.platform, "darwin")
        self.assertEqual(result.pyautogui_size, (1512, 982))
        self.assertEqual(result.pyautogui_position, (12, 34))
        self.assertEqual(len(result.mss_monitors), 2)
        self.assertEqual(result.primary_monitor["is_primary"], True)
        self.assertEqual(result.tk_version, "8.6")
        self.assertEqual(result.tcl_version, "8.6")
        self.assertTrue(result.display_fingerprint)
        fake_mss.MSS.assert_called_once_with()
        fake_capture.grab.assert_not_called()
        for mock in (
            move,
            click,
            mouse_down,
            mouse_up,
            press,
            hotkey,
            scroll,
            typewrite,
        ):
            mock.assert_not_called()
        listener_start.assert_not_called()
        initialize_ocr.assert_not_called()
        select_region.assert_not_called()

    def test_display_fingerprint_is_stable_for_same_monitor_snapshot(self):
        monitors = (
            {"left": 0, "top": 0, "width": 100, "height": 200, "is_primary": True},
            {"left": 100, "top": 0, "width": 100, "height": 200, "is_primary": False},
        )
        first = simple_brush._build_display_fingerprint(monitors)
        second = simple_brush._build_display_fingerprint(monitors)
        self.assertEqual(first, second)

    def test_display_fingerprint_changes_when_geometry_changes(self):
        base = (
            {"left": 0, "top": 0, "width": 100, "height": 200, "is_primary": True},
        )
        changed = (
            {"left": 0, "top": 0, "width": 120, "height": 200, "is_primary": True},
        )
        self.assertNotEqual(
            simple_brush._build_display_fingerprint(base),
            simple_brush._build_display_fingerprint(changed),
        )

    def test_infer_retina_scale_accepts_one_two_and_non_integer_scales(self):
        cases = (
            ((1000, 800), (1000, 800), 1.0),
            ((1000, 800), (2000, 1600), 2.0),
            ((1000, 800), (1500, 1200), 1.5),
        )

        for request_size, image_size, expected_scale in cases:
            with self.subTest(expected_scale=expected_scale):
                result = simple_brush.infer_retina_scale(request_size, image_size)

            self.assertTrue(result.passed)
            self.assertEqual(result.request_size, request_size)
            self.assertEqual(result.image_size, image_size)
            self.assertEqual(result.scale_x, expected_scale)
            self.assertEqual(result.scale_y, expected_scale)
            self.assertIsNone(result.error_code)

    def test_infer_retina_scale_rejects_invalid_request_dimensions(self):
        for request_size in ((0, 800), (1000, 0), (-1, 800), (1000, -1)):
            with self.subTest(request_size=request_size):
                result = simple_brush.infer_retina_scale(
                    request_size, (1000, 800)
                )

            self.assertFalse(result.passed)
            self.assertEqual(
                result.error_code, "RETINA_SCALE_REQUEST_SIZE_INVALID"
            )

    def test_infer_retina_scale_rejects_invalid_image_dimensions(self):
        for image_size in ((0, 800), (1000, 0), (-1, 800), (1000, -1)):
            with self.subTest(image_size=image_size):
                result = simple_brush.infer_retina_scale(
                    (1000, 800), image_size
                )

            self.assertFalse(result.passed)
            self.assertEqual(result.error_code, "RETINA_SCALE_IMAGE_SIZE_INVALID")

    def test_infer_retina_scale_rejects_non_integer_sizes(self):
        invalid_sizes = ((1000.0, 800), (True, 800), ("1000", 800))
        for invalid_size in invalid_sizes:
            with self.subTest(invalid_size=invalid_size):
                request_result = simple_brush.infer_retina_scale(
                    invalid_size, (1000, 800)
                )
                image_result = simple_brush.infer_retina_scale(
                    (1000, 800), invalid_size
                )

            self.assertEqual(
                request_result.error_code, "RETINA_SCALE_REQUEST_SIZE_INVALID"
            )
            self.assertEqual(
                image_result.error_code, "RETINA_SCALE_IMAGE_SIZE_INVALID"
            )

    def test_infer_retina_scale_rejects_axis_mismatch(self):
        result = simple_brush.infer_retina_scale((1000, 1000), (2000, 2200))

        self.assertFalse(result.passed)
        self.assertEqual(result.scale_x, 2.0)
        self.assertEqual(result.scale_y, 2.2)
        self.assertEqual(result.error_code, "RETINA_SCALE_AXIS_MISMATCH")

    def test_infer_retina_scale_rejects_scales_outside_inclusive_range(self):
        for image_size in ((400, 400), (5000, 5000)):
            with self.subTest(image_size=image_size):
                result = simple_brush.infer_retina_scale(
                    (1000, 1000), image_size
                )

            self.assertFalse(result.passed)
            self.assertEqual(result.error_code, "RETINA_SCALE_OUT_OF_RANGE")

    def test_infer_retina_scale_rejects_non_finite_overflow(self):
        result = simple_brush.infer_retina_scale(
            (1, 1), (10 ** 400, 10 ** 400)
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.error_code, "RETINA_SCALE_NON_FINITE")

    def test_infer_retina_scale_honors_tolerance_boundary(self):
        within = simple_brush.infer_retina_scale(
            (1000, 1000), (2000, 2020), tolerance=0.02
        )
        outside = simple_brush.infer_retina_scale(
            (1000, 1000), (2000, 2021), tolerance=0.02
        )

        self.assertTrue(within.passed)
        self.assertFalse(outside.passed)
        self.assertEqual(outside.error_code, "RETINA_SCALE_AXIS_MISMATCH")

    def test_infer_retina_scale_rejects_invalid_tolerance(self):
        for tolerance in (-0.01, float("inf"), float("nan"), True):
            with self.subTest(tolerance=tolerance):
                result = simple_brush.infer_retina_scale(
                    (1000, 800), (2000, 1600), tolerance=tolerance
                )

            self.assertFalse(result.passed)
            self.assertEqual(
                result.error_code, "RETINA_SCALE_TOLERANCE_INVALID"
            )

    def test_infer_monitor_capture_scale_uses_monitor_request_size(self):
        monitor = {"left": 0, "top": 0, "width": 1000, "height": 800}

        result = simple_brush.infer_monitor_capture_scale(
            monitor, (1500, 1200)
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.request_size, (1000, 800))
        self.assertEqual(result.scale_x, 1.5)
        self.assertEqual(result.scale_y, 1.5)

    def test_infer_monitor_capture_scale_rejects_invalid_monitor_metadata(self):
        invalid_monitors = (
            {},
            {"height": 800},
            {"width": 1000},
            {"width": 1000.0, "height": 800},
            {"width": 1000, "height": 800.0},
            {"width": True, "height": 800},
            {"width": 0, "height": 800},
            {"width": 1000, "height": 0},
            {"width": -1, "height": 800},
            {"width": 1000, "height": -1},
            None,
        )

        for monitor in invalid_monitors:
            with self.subTest(monitor=monitor):
                result = simple_brush.infer_monitor_capture_scale(
                    monitor, (1000, 800)
                )

            self.assertFalse(result.passed)
            self.assertEqual(result.error_code, "RETINA_SCALE_MONITOR_INVALID")

    def test_scale_inference_helpers_have_no_screen_input_or_ocr_side_effects(self):
        fake_mss = SimpleNamespace(MSS=Mock())
        monitor = {"width": 1000, "height": 800}
        with (
            patch.dict("sys.modules", {"mss": fake_mss}),
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.pyautogui, "mouseDown") as mouse_down,
            patch.object(simple_brush.pyautogui, "mouseUp") as mouse_up,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
            patch.object(simple_brush.pyautogui, "typewrite") as typewrite,
            patch.object(simple_brush.listener, "start") as listener_start,
            patch.object(simple_brush, "initialize_ocr") as initialize_ocr,
        ):
            direct = simple_brush.infer_retina_scale(
                (1000, 800), (2000, 1600)
            )
            from_monitor = simple_brush.infer_monitor_capture_scale(
                monitor, (2000, 1600)
            )

        self.assertTrue(direct.passed)
        self.assertTrue(from_monitor.passed)
        fake_mss.MSS.assert_not_called()
        for mock in (
            click,
            move,
            mouse_down,
            mouse_up,
            press,
            hotkey,
            scroll,
            typewrite,
            listener_start,
            initialize_ocr,
        ):
            mock.assert_not_called()

    def test_normalize_drag_selection_supports_all_four_drag_directions(self):
        drags = (
            ((10, 20), (40, 60)),
            ((40, 60), (10, 20)),
            ((40, 20), (10, 60)),
            ((10, 60), (40, 20)),
        )
        expected = simple_brush.TkSelectionRegion(10.0, 20.0, 30.0, 40.0)

        for start, end in drags:
            with self.subTest(start=start, end=end):
                result = simple_brush.normalize_drag_selection(start, end)

            self.assertTrue(result.passed)
            self.assertEqual(result.tk_selection, expected)
            self.assertIsNone(result.crop_region)
            self.assertIsNone(result.error_code)

    def test_normalize_drag_selection_rejects_too_small_region(self):
        result = simple_brush.normalize_drag_selection(
            (10, 20), (10.5, 22), min_size=1.0
        )

        self.assertFalse(result.passed)
        self.assertEqual(result.error_code, "TK_SELECTION_TOO_SMALL")

    def test_normalize_drag_selection_rejects_nan_and_infinite_points(self):
        invalid_points = (
            ((float("nan"), 0), (10, 10)),
            ((0, float("inf")), (10, 10)),
            ((0, 0), (float("-inf"), 10)),
        )

        for start, end in invalid_points:
            with self.subTest(start=start, end=end):
                result = simple_brush.normalize_drag_selection(start, end)

            self.assertFalse(result.passed)
            self.assertEqual(result.error_code, "TK_SELECTION_POINTS_INVALID")

    def test_map_tk_selection_rejects_invalid_overlay_size(self):
        selection = simple_brush.TkSelectionRegion(0, 0, 10, 10)
        for overlay_size in ((0, 800), (1000, 0)):
            with self.subTest(overlay_size=overlay_size):
                result = simple_brush.map_tk_selection_to_screenshot_crop(
                    selection, overlay_size, (1000, 800)
                )

            self.assertFalse(result.passed)
            self.assertEqual(result.error_code, "TK_OVERLAY_SIZE_INVALID")

    def test_map_tk_selection_rejects_invalid_screenshot_size(self):
        selection = simple_brush.TkSelectionRegion(0, 0, 10, 10)
        for screenshot_size in ((0, 800), (1000, 0)):
            with self.subTest(screenshot_size=screenshot_size):
                result = simple_brush.map_tk_selection_to_screenshot_crop(
                    selection, (1000, 800), screenshot_size
                )

            self.assertFalse(result.passed)
            self.assertEqual(result.error_code, "SCREENSHOT_SIZE_INVALID")

    def test_map_tk_selection_accepts_exact_overlay_bounds(self):
        selection = simple_brush.TkSelectionRegion(0, 0, 1000, 800)

        result = simple_brush.map_tk_selection_to_screenshot_crop(
            selection, (1000, 800), (2000, 1600)
        )

        self.assertTrue(result.passed)
        self.assertEqual(
            result.crop_region,
            simple_brush.ScreenshotCropRegion(0, 0, 2000, 1600),
        )

    def test_map_tk_selection_rejects_negative_and_overflowing_bounds(self):
        selections = (
            simple_brush.TkSelectionRegion(-1, 0, 10, 10),
            simple_brush.TkSelectionRegion(0, -1, 10, 10),
            simple_brush.TkSelectionRegion(991, 0, 10, 10),
            simple_brush.TkSelectionRegion(0, 791, 10, 10),
        )

        for selection in selections:
            with self.subTest(selection=selection):
                result = simple_brush.map_tk_selection_to_screenshot_crop(
                    selection, (1000, 800), (2000, 1600)
                )

            self.assertFalse(result.passed)
            self.assertEqual(result.error_code, "TK_SELECTION_OUT_OF_BOUNDS")

    def test_map_tk_selection_accepts_right_and_bottom_edges(self):
        selection = simple_brush.TkSelectionRegion(900, 700, 100, 100)

        result = simple_brush.map_tk_selection_to_screenshot_crop(
            selection, (1000, 800), (2000, 1600)
        )

        self.assertTrue(result.passed)
        self.assertEqual(
            result.crop_region,
            simple_brush.ScreenshotCropRegion(1800, 1400, 200, 200),
        )

    def test_map_tk_selection_maps_one_to_one_and_two_x(self):
        selection = simple_brush.TkSelectionRegion(10, 20, 100, 50)
        cases = (
            ((1000, 800), simple_brush.ScreenshotCropRegion(10, 20, 100, 50)),
            ((2000, 1600), simple_brush.ScreenshotCropRegion(20, 40, 200, 100)),
        )

        for screenshot_size, expected_crop in cases:
            with self.subTest(screenshot_size=screenshot_size):
                result = simple_brush.map_tk_selection_to_screenshot_crop(
                    selection, (1000, 800), screenshot_size
                )

            self.assertTrue(result.passed)
            self.assertEqual(result.crop_region, expected_crop)

    def test_map_tk_selection_uses_floor_ceil_for_fractional_1_5_scale(self):
        selection = simple_brush.TkSelectionRegion(10.2, 20.4, 100.1, 50.2)

        result = simple_brush.map_tk_selection_to_screenshot_crop(
            selection, (1000, 800), (1500, 1200)
        )

        self.assertTrue(result.passed)
        self.assertEqual(
            result.crop_region,
            simple_brush.ScreenshotCropRegion(15, 30, 151, 76),
        )
        self.assertGreater(result.crop_region.width, 0)
        self.assertGreater(result.crop_region.height, 0)

    def test_validate_screenshot_crop_rejects_empty_and_out_of_bounds(self):
        empty = simple_brush.validate_screenshot_crop(
            simple_brush.ScreenshotCropRegion(10, 10, 0, 20),
            (100, 100),
        )
        overflow = simple_brush.validate_screenshot_crop(
            simple_brush.ScreenshotCropRegion(90, 90, 11, 10),
            (100, 100),
        )

        self.assertFalse(empty.passed)
        self.assertEqual(empty.error_code, "SCREENSHOT_CROP_EMPTY")
        self.assertFalse(overflow.passed)
        self.assertEqual(overflow.error_code, "SCREENSHOT_CROP_OUT_OF_BOUNDS")
        self.assertEqual(overflow.crop_region.left, 90)
        self.assertEqual(overflow.crop_region.width, 11)

    def test_tk_crop_mapping_helpers_have_no_gui_capture_or_ocr_side_effects(self):
        fake_mss = SimpleNamespace(MSS=Mock())
        fake_tk = SimpleNamespace(Tk=Mock())
        selection = simple_brush.TkSelectionRegion(10, 20, 100, 50)
        with (
            patch.dict("sys.modules", {"mss": fake_mss, "tkinter": fake_tk}),
            patch.object(simple_brush, "select_screen_region") as select_region,
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.pyautogui, "mouseDown") as mouse_down,
            patch.object(simple_brush.pyautogui, "mouseUp") as mouse_up,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
            patch.object(simple_brush.pyautogui, "typewrite") as typewrite,
            patch.object(simple_brush.listener, "start") as listener_start,
            patch.object(simple_brush, "initialize_ocr") as initialize_ocr,
        ):
            normalized = simple_brush.normalize_drag_selection((10, 20), (110, 70))
            mapped = simple_brush.map_tk_selection_to_screenshot_crop(
                selection, (1000, 800), (2000, 1600)
            )

        self.assertTrue(normalized.passed)
        self.assertTrue(mapped.passed)
        fake_mss.MSS.assert_not_called()
        fake_tk.Tk.assert_not_called()
        for mock in (
            select_region,
            click,
            move,
            mouse_down,
            mouse_up,
            press,
            hotkey,
            scroll,
            typewrite,
            listener_start,
            initialize_ocr,
        ):
            mock.assert_not_called()

    def test_crop_image_for_preview_extracts_correct_region_from_2d_image(self):
        image = np.arange(25, dtype=np.uint8).reshape(5, 5)
        crop = simple_brush.ScreenshotCropRegion(1, 2, 3, 2)

        ok, cropped, error_code = simple_brush.crop_image_for_preview(image, crop)

        self.assertTrue(ok)
        self.assertIsNone(error_code)
        self.assertTrue(
            np.array_equal(cropped, np.array([[11, 12, 13], [16, 17, 18]], dtype=np.uint8))
        )

    def test_crop_image_for_preview_extracts_correct_region_from_3d_image(self):
        image = np.arange(4 * 5 * 3, dtype=np.uint8).reshape(4, 5, 3)
        crop = simple_brush.ScreenshotCropRegion(2, 1, 2, 2)

        ok, cropped, error_code = simple_brush.crop_image_for_preview(image, crop)

        self.assertTrue(ok)
        self.assertIsNone(error_code)
        self.assertEqual(cropped.shape, (2, 2, 3))
        self.assertTrue(np.array_equal(cropped, image[1:3, 2:4, :]))

    def test_crop_image_for_preview_does_not_modify_original_image(self):
        image = np.arange(16, dtype=np.uint8).reshape(4, 4)
        original = image.copy()
        crop = simple_brush.ScreenshotCropRegion(1, 1, 2, 2)

        ok, cropped, error_code = simple_brush.crop_image_for_preview(image, crop)

        self.assertTrue(ok)
        self.assertIsNone(error_code)
        cropped[0, 0] = 255
        self.assertTrue(np.array_equal(image, original))

    def test_crop_image_for_preview_rejects_negative_origin(self):
        image = np.zeros((4, 4), dtype=np.uint8)
        for crop in (
            simple_brush.ScreenshotCropRegion(-1, 0, 1, 1),
            simple_brush.ScreenshotCropRegion(0, -1, 1, 1),
        ):
            with self.subTest(crop=crop):
                ok, cropped, error_code = simple_brush.crop_image_for_preview(
                    image, crop
                )

            self.assertFalse(ok)
            self.assertIsNone(cropped)
            self.assertEqual(error_code, "CROP_PREVIEW_REGION_INVALID")

    def test_crop_image_for_preview_rejects_right_and_bottom_overflow(self):
        image = np.zeros((4, 4), dtype=np.uint8)
        for crop in (
            simple_brush.ScreenshotCropRegion(3, 0, 2, 1),
            simple_brush.ScreenshotCropRegion(0, 3, 1, 2),
        ):
            with self.subTest(crop=crop):
                ok, cropped, error_code = simple_brush.crop_image_for_preview(
                    image, crop
                )

            self.assertFalse(ok)
            self.assertIsNone(cropped)
            self.assertEqual(error_code, "CROP_PREVIEW_REGION_OUT_OF_BOUNDS")

    def test_crop_image_for_preview_rejects_empty_region(self):
        image = np.zeros((4, 4), dtype=np.uint8)
        for crop in (
            simple_brush.ScreenshotCropRegion(0, 0, 0, 1),
            simple_brush.ScreenshotCropRegion(0, 0, 1, 0),
        ):
            with self.subTest(crop=crop):
                ok, cropped, error_code = simple_brush.crop_image_for_preview(
                    image, crop
                )

            self.assertFalse(ok)
            self.assertIsNone(cropped)
            self.assertEqual(error_code, "CROP_PREVIEW_REGION_INVALID")

    def test_crop_image_for_preview_rejects_non_numpy_and_invalid_dimensions(self):
        invalid_images = (
            [[1, 2], [3, 4]],
            np.zeros((4,), dtype=np.uint8),
            np.zeros((1, 2, 3, 4), dtype=np.uint8),
        )

        for image in invalid_images:
            with self.subTest(image_type=type(image), shape=getattr(image, "shape", None)):
                ok, cropped, error_code = simple_brush.crop_image_for_preview(
                    image,
                    simple_brush.ScreenshotCropRegion(0, 0, 1, 1),
                )

            self.assertFalse(ok)
            self.assertIsNone(cropped)
            self.assertEqual(error_code, "CROP_PREVIEW_IMAGE_INVALID")

    def test_build_coordinate_diagnostics_dir_returns_timestamp_child(self):
        base_dir = "logs/macos-coordinate-diagnostics"

        result = simple_brush.build_coordinate_diagnostics_dir(base_dir)

        self.assertEqual(result.parent.as_posix(), base_dir)
        self.assertTrue(result.name)

    def test_save_crop_preview_for_manual_check_saves_only_crop(self):
        image = np.arange(6 * 7 * 3, dtype=np.uint8).reshape(6, 7, 3)
        crop = simple_brush.ScreenshotCropRegion(2, 1, 3, 2)
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = simple_brush.Path(tmpdir) / "nested" / "preview"

            result = simple_brush.save_crop_preview_for_manual_check(
                image,
                crop,
                output_dir=output_dir,
            )

            from PIL import Image

            saved_image = np.asarray(Image.open(result.preview_path))
            self.assertTrue(output_dir.exists())
            self.assertTrue(result.preview_path.endswith("crop_preview.png"))
            self.assertEqual(saved_image.shape[:2], (2, 3))

        self.assertTrue(result.saved)
        self.assertEqual(result.crop_size, (3, 2))
        self.assertFalse(np.array_equal(saved_image, image))

    def test_gitignore_already_covers_macos_coordinate_diagnostics_logs(self):
        result = subprocess.run(
            ["git", "check-ignore", "logs/macos-coordinate-diagnostics/example.png"],
            capture_output=True,
            text=True,
            check=False,
            cwd=simple_brush.Path(__file__).resolve().parents[1],
        )

        self.assertEqual(result.returncode, 0)

    def test_save_crop_preview_for_manual_check_rejects_path_traversal(self):
        image = np.zeros((4, 4), dtype=np.uint8)
        crop = simple_brush.ScreenshotCropRegion(0, 0, 2, 2)
        with tempfile.TemporaryDirectory() as tmpdir:
            result = simple_brush.save_crop_preview_for_manual_check(
                image,
                crop,
                output_dir=tmpdir,
                filename="../escape.png",
            )

        self.assertFalse(result.saved)
        self.assertEqual(result.error_code, "CROP_PREVIEW_PATH_INVALID")
        self.assertIsNone(result.preview_path)

    def test_save_crop_preview_for_manual_check_fail_closed_when_save_fails(self):
        image = np.zeros((4, 4), dtype=np.uint8)
        crop = simple_brush.ScreenshotCropRegion(0, 0, 2, 2)
        with (
            tempfile.TemporaryDirectory() as tmpdir,
            patch("PIL.Image.Image.save", side_effect=OSError("disk full")),
        ):
            result = simple_brush.save_crop_preview_for_manual_check(
                image,
                crop,
                output_dir=tmpdir,
            )

        self.assertFalse(result.saved)
        self.assertEqual(result.error_code, "CROP_PREVIEW_SAVE_FAILED")
        self.assertIn("disk full", result.message)

    def test_crop_preview_helpers_have_no_capture_gui_or_ocr_side_effects(self):
        image = np.arange(25, dtype=np.uint8).reshape(5, 5)
        crop = simple_brush.ScreenshotCropRegion(1, 1, 2, 2)
        fake_mss = SimpleNamespace(MSS=Mock())
        fake_tk = SimpleNamespace(Tk=Mock())
        with (
            patch.dict("sys.modules", {"mss": fake_mss, "tkinter": fake_tk}),
            patch.object(simple_brush, "select_screen_region") as select_region,
            patch.object(simple_brush, "initialize_ocr") as initialize_ocr,
            patch.object(simple_brush.listener, "start") as listener_start,
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.pyautogui, "mouseDown") as mouse_down,
            patch.object(simple_brush.pyautogui, "mouseUp") as mouse_up,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
            patch.object(simple_brush.pyautogui, "typewrite") as typewrite,
            patch.object(simple_brush, "MSSScreenCapture") as screen_capture,
            patch.object(simple_brush, "OCRKeywordDetector") as detector,
        ):
            ok, cropped, error_code = simple_brush.crop_image_for_preview(image, crop)
            built_dir = simple_brush.build_coordinate_diagnostics_dir()
            with tempfile.TemporaryDirectory() as tmpdir:
                saved = simple_brush.save_crop_preview_for_manual_check(
                    image,
                    crop,
                    output_dir=tmpdir,
                )

        self.assertTrue(ok)
        self.assertIsNone(error_code)
        self.assertEqual(cropped.shape, (2, 2))
        self.assertTrue(built_dir.parent.as_posix().endswith("logs/macos-coordinate-diagnostics"))
        self.assertTrue(saved.saved)
        fake_mss.MSS.assert_not_called()
        fake_tk.Tk.assert_not_called()
        for mock in (
            select_region,
            initialize_ocr,
            listener_start,
            click,
            move,
            mouse_down,
            mouse_up,
            press,
            hotkey,
            scroll,
            typewrite,
            screen_capture,
            detector,
        ):
            mock.assert_not_called()

    def test_capture_screen_coordinate_diagnostics_fails_closed_when_pyautogui_size_fails(self):
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(
                simple_brush.pyautogui,
                "size",
                side_effect=RuntimeError("size failed"),
            ),
            patch.object(simple_brush.pyautogui, "position") as position,
        ):
            result = simple_brush.capture_screen_coordinate_diagnostics()

        position.assert_not_called()
        self.assertFalse(result.passed)
        self.assertEqual(result.error_code, "COORDINATE_DIAGNOSTICS_PYAUTOGUI_FAILED")
        self.assertIn("size failed", result.message)

    def test_capture_screen_coordinate_diagnostics_fails_closed_when_pyautogui_position_fails(self):
        fake_capture = SimpleNamespace(monitors=[])
        fake_mss = SimpleNamespace(MSS=Mock(return_value=fake_capture))
        fake_tk = SimpleNamespace(TkVersion=8.6, TclVersion=8.6)
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(simple_brush.pyautogui, "size", return_value=(1512, 982)),
            patch.object(
                simple_brush.pyautogui,
                "position",
                side_effect=RuntimeError("position failed"),
            ),
            patch.dict(
                "sys.modules",
                {"mss": fake_mss, "tkinter": fake_tk},
            ),
        ):
            result = simple_brush.capture_screen_coordinate_diagnostics()

        self.assertFalse(result.passed)
        self.assertEqual(result.error_code, "COORDINATE_DIAGNOSTICS_PYAUTOGUI_FAILED")
        self.assertIn("position failed", result.message)

    def test_capture_screen_coordinate_diagnostics_fails_closed_when_mss_init_fails(self):
        class BrokenMSS:
            def __call__(self):
                raise RuntimeError("mss init failed")

        fake_tk = SimpleNamespace(TkVersion=8.6, TclVersion=8.6)
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(simple_brush.pyautogui, "size", return_value=(1512, 982)),
            patch.object(simple_brush.pyautogui, "position", return_value=(12, 34)),
            patch.dict("sys.modules", {"mss": SimpleNamespace(MSS=BrokenMSS()), "tkinter": fake_tk}),
        ):
            result = simple_brush.capture_screen_coordinate_diagnostics()

        self.assertFalse(result.passed)
        self.assertEqual(result.error_code, "COORDINATE_DIAGNOSTICS_MSS_FAILED")
        self.assertIn("mss 监视器读取失败", result.message)

    def test_capture_screen_coordinate_diagnostics_fails_closed_when_mss_monitor_read_fails(self):
        class FailingCapture:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            @property
            def monitors(self):
                raise RuntimeError("monitor failed")

        fake_mss = SimpleNamespace(MSS=Mock(return_value=FailingCapture()))
        fake_tk = SimpleNamespace(TkVersion=8.6, TclVersion=8.6)
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(simple_brush.pyautogui, "size", return_value=(1512, 982)),
            patch.object(simple_brush.pyautogui, "position", return_value=(12, 34)),
            patch.dict(
                "sys.modules",
                {"mss": fake_mss, "tkinter": fake_tk},
            ),
        ):
            result = simple_brush.capture_screen_coordinate_diagnostics()

        self.assertFalse(result.passed)
        self.assertEqual(result.error_code, "COORDINATE_DIAGNOSTICS_MSS_FAILED")
        self.assertIn("mss 监视器读取失败", result.message)

    def test_capture_screen_coordinate_diagnostics_fails_closed_when_tk_read_fails(self):
        class FakeCapture:
            def __init__(self):
                self.monitors = [
                    {
                        "left": 0,
                        "top": 0,
                        "width": 1512,
                        "height": 982,
                        "is_primary": True,
                    }
                ]

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        fake_capture = FakeCapture()
        fake_mss = SimpleNamespace(MSS=Mock(return_value=fake_capture))
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(simple_brush.pyautogui, "size", return_value=(1512, 982)),
            patch.object(simple_brush.pyautogui, "position", return_value=(12, 34)),
            patch.dict("sys.modules", {"mss": fake_mss, "tkinter": None}),
        ):
            result = simple_brush.capture_screen_coordinate_diagnostics()

        self.assertFalse(result.passed)
        self.assertEqual(result.error_code, "COORDINATE_DIAGNOSTICS_TK_FAILED")
        self.assertIn("Tk/Tcl 版本读取失败", result.message)

    def test_allowed_boss_page_accepts_only_explicit_https_paths(self):
        allowed_urls = (
            "https://www.zhipin.com/",
            "https://www.zhipin.com/web/geek/job-recommend",
            "https://www.zhipin.com/geek/jobs",
            "https://www.zhipin.com/job_detail/abc.html",
            "https://www.zhipin.com/chat/index",
            "https://www.zhipin.com/boss/home",
        )

        for url in allowed_urls:
            with self.subTest(url=url):
                self.assertTrue(simple_brush.is_allowed_boss_page(url, "BOSS直聘"))

    def test_allowed_boss_page_denies_missing_internal_and_untrusted_urls(self):
        denied_urls = (
            None,
            "",
            "about:blank",
            "chrome://settings",
            "file:///tmp/a.html",
            "http://www.zhipin.com/web/jobs",
            "https://zhipin.com/web/jobs",
            "https://evilzhipin.com/web/jobs",
            "https://www.zhipin.com.evil.com/web/jobs",
            "https://zhipin.com.evil.com/web/jobs",
            "https://www.zhipin.com/unsupported/path",
            "https://www.zhipin.com:bad/web/jobs",
            "not a valid URL",
        )

        for url in denied_urls:
            with self.subTest(url=url):
                self.assertFalse(simple_brush.is_allowed_boss_page(url, "BOSS直聘"))

    def test_allowed_boss_page_title_cannot_allow_untrusted_url(self):
        self.assertFalse(
            simple_brush.is_allowed_boss_page(
                "https://example.com/boss/zhipin", "BOSS直聘招聘页面"
            )
        )

    def test_allowed_boss_page_allows_empty_title_when_url_strictly_matches(self):
        self.assertTrue(
            simple_brush.is_allowed_boss_page("https://www.zhipin.com/", "")
        )
        self.assertTrue(
            simple_brush.is_allowed_boss_page("https://www.zhipin.com/web/jobs", None)
        )

    def test_allowed_boss_page_is_pure_and_does_not_query_or_focus_chrome(self):
        with (
            patch.object(simple_brush, "run_osascript") as run_osascript,
            patch.object(simple_brush, "focus_chrome_window") as focus,
            patch.object(
                simple_brush, "get_chrome_active_tab_identity"
            ) as tab_identity,
        ):
            result = simple_brush.is_allowed_boss_page(
                "https://www.zhipin.com/chat/index", "BOSS直聘"
            )

        self.assertTrue(result)
        run_osascript.assert_not_called()
        focus.assert_not_called()
        tab_identity.assert_not_called()

    def test_preflight_only_exits_on_windows_macos_and_unknown_platforms(self):
        results = (
            simple_brush.BrowserPrepareResult(
                ready=True,
                platform="windows",
                browser="edge",
            ),
            simple_brush.BrowserPrepareResult(
                ready=False,
                platform="macos",
                browser="chrome",
                launched=True,
                error_code="MACOS_PERMISSIONS_NOT_READY",
            ),
            simple_brush.BrowserPrepareResult(
                ready=False,
                platform="linux",
                browser="",
                error_code="UNSUPPORTED_PLATFORM",
            ),
        )
        for result in results:
            with self.subTest(platform=result.platform):
                self.assert_preflight_exits_without_business_actions(result)

    def test_macos_default_chrome_path_is_exact(self):
        self.assertEqual(
            str(simple_brush.MACOS_CHROME_EXECUTABLE),
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        )

    def test_windows_success_reuses_edge_foreground(self):
        with patch.object(
            simple_brush, "bring_edge_foreground", return_value=True
        ) as bring_edge:
            result = simple_brush.prepare_browser("win32")

        bring_edge.assert_called_once_with()
        self.assertEqual(
            result,
            simple_brush.BrowserPrepareResult(
                ready=True,
                platform="windows",
                browser="edge",
            ),
        )

    def test_windows_failure_is_structured_and_fail_closed(self):
        with patch.object(
            simple_brush, "bring_edge_foreground", return_value=False
        ) as bring_edge:
            result = simple_brush.prepare_browser("win32")

        bring_edge.assert_called_once_with()
        self.assertFalse(result.ready)
        self.assertEqual(result.platform, "windows")
        self.assertEqual(result.browser, "edge")
        self.assertFalse(result.launched)
        self.assertEqual(result.executable_path, "")
        self.assertEqual(result.error_code, "EDGE_PREPARE_FAILED")
        self.assertTrue(result.message)

    def test_macos_missing_chrome_is_fail_closed(self):
        missing = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
            message="missing",
            error_code="CHROME_NOT_FOUND",
        )
        with (
            patch.object(simple_brush, "bring_edge_foreground") as bring_edge,
            patch.object(
                simple_brush, "resolve_chrome_executable", return_value=missing
            ) as resolve,
            patch.object(simple_brush, "launch_chrome_safe_target") as launch,
            patch.object(simple_brush, "focus_chrome_window") as focus,
            patch.object(
                simple_brush, "get_chrome_active_tab_identity"
            ) as tab_identity,
            patch.object(simple_brush, "is_allowed_boss_page") as page_allowed,
        ):
            result = simple_brush.prepare_browser("darwin")

        bring_edge.assert_not_called()
        resolve.assert_called_once_with()
        launch.assert_not_called()
        focus.assert_not_called()
        tab_identity.assert_not_called()
        page_allowed.assert_not_called()
        self.assertFalse(result.ready)
        self.assertEqual(result.platform, "macos")
        self.assertEqual(result.browser, "chrome")
        self.assertFalse(result.launched)
        self.assertEqual(result.error_code, "CHROME_NOT_FOUND")
        self.assertTrue(result.message)

    def test_macos_launch_failure_stops_before_focus_tab_and_allowlist(self):
        resolved = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        launch_failed = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
            error_code="CHROME_LAUNCH_FAILED",
        )
        with (
            patch.object(
                simple_brush, "resolve_chrome_executable", return_value=resolved
            ),
            patch.object(
                simple_brush,
                "launch_chrome_safe_target",
                return_value=launch_failed,
            ),
            patch.object(simple_brush, "check_macos_permissions") as permissions,
            patch.object(simple_brush, "focus_chrome_window") as focus,
            patch.object(
                simple_brush, "get_chrome_active_tab_identity"
            ) as tab_identity,
            patch.object(simple_brush, "is_allowed_boss_page") as page_allowed,
        ):
            result = simple_brush.prepare_browser("darwin")

        self.assertEqual(result.error_code, "CHROME_LAUNCH_FAILED")
        self.assertFalse(result.ready)
        permissions.assert_not_called()
        focus.assert_not_called()
        tab_identity.assert_not_called()
        page_allowed.assert_not_called()

    def test_resolve_missing_path_does_not_launch(self):
        path = simple_brush.Path("/missing/Google Chrome")
        with (
            patch.object(simple_brush.Path, "exists", return_value=False),
            patch.object(simple_brush.subprocess, "Popen") as popen,
        ):
            result = simple_brush.resolve_chrome_executable(path)

        popen.assert_not_called()
        self.assertFalse(result.ready)
        self.assertEqual(result.error_code, "CHROME_NOT_FOUND")

    def test_resolve_directory_is_fail_closed(self):
        path = simple_brush.Path("/Applications/Fake Chrome")
        with (
            patch.object(simple_brush.Path, "exists", return_value=True),
            patch.object(simple_brush.Path, "is_file", return_value=False),
            patch.object(simple_brush.os, "access") as access,
            patch.object(simple_brush.subprocess, "Popen") as popen,
        ):
            result = simple_brush.resolve_chrome_executable(path)

        access.assert_not_called()
        popen.assert_not_called()
        self.assertFalse(result.ready)
        self.assertEqual(result.error_code, "CHROME_NOT_EXECUTABLE")

    def test_resolve_non_executable_file_is_fail_closed(self):
        path = simple_brush.Path("/Applications/Fake Chrome")
        with (
            patch.object(simple_brush.Path, "exists", return_value=True),
            patch.object(simple_brush.Path, "is_file", return_value=True),
            patch.object(simple_brush.os, "access", return_value=False) as access,
            patch.object(simple_brush.subprocess, "Popen") as popen,
        ):
            result = simple_brush.resolve_chrome_executable(path)

        access.assert_called_once_with(path, simple_brush.os.X_OK)
        popen.assert_not_called()
        self.assertFalse(result.ready)
        self.assertEqual(result.error_code, "CHROME_NOT_EXECUTABLE")

    def test_launch_uses_argument_list_with_only_about_blank(self):
        path = simple_brush.Path(
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        )
        with patch.object(simple_brush.subprocess, "Popen") as popen:
            result = simple_brush.launch_chrome_safe_target(path)

        popen.assert_called_once_with([str(path), "about:blank"])
        args, kwargs = popen.call_args
        self.assertEqual(kwargs, {})
        command = " ".join(args[0]).lower()
        self.assertNotIn("boss", command)
        self.assertNotIn("zhipin", command)
        self.assertFalse(result.ready)
        self.assertTrue(result.launched)
        self.assertEqual(result.browser, "chrome")
        self.assertEqual(result.error_code, "MACOS_BROWSER_STARTED_NOT_READY")

    def test_launch_exception_is_fail_closed(self):
        path = simple_brush.Path("/Applications/Fake Chrome")
        with patch.object(
            simple_brush.subprocess,
            "Popen",
            side_effect=OSError("launch denied"),
        ) as popen:
            result = simple_brush.launch_chrome_safe_target(path)

        popen.assert_called_once_with([str(path), "about:blank"])
        self.assertFalse(result.ready)
        self.assertFalse(result.launched)
        self.assertEqual(result.error_code, "CHROME_LAUNCH_FAILED")
        self.assertIn("launch denied", result.message)

    def test_run_osascript_uses_argument_list_without_shell(self):
        with patch.object(simple_brush.subprocess, "run") as run:
            simple_brush.run_osascript('return "ok"', timeout=1.5)

        run.assert_called_once_with(
            ["osascript", "-e", 'return "ok"'],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )

    def test_focus_chrome_window_successfully_activates_and_confirms_frontmost(self):
        events = []
        activate = subprocess.CompletedProcess(
            args=["osascript", "-e", 'tell application "Google Chrome" to activate'],
            returncode=0,
            stdout="",
            stderr="",
        )
        frontmost = subprocess.CompletedProcess(
            args=["osascript", "-e", "frontmost query"],
            returncode=0,
            stdout="Google Chrome\n",
            stderr="",
        )

        def fake_run(script, timeout=3.0):
            events.append((script, timeout))
            if "activate" in script:
                return activate
            if "frontmost" in script:
                return frontmost
            self.fail(f"unexpected script: {script}")

        with (
            patch.object(simple_brush, "run_osascript", side_effect=fake_run),
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
            patch.object(simple_brush.listener, "start") as listener_start,
        ):
            result = simple_brush.focus_chrome_window()

        self.assertEqual(
            events,
            [
                ('tell application "Google Chrome" to activate', 3.0),
                (
                    'tell application "System Events" '
                    'to get name of first application process whose frontmost is true',
                    3.0,
                ),
            ],
        )
        self.assertEqual(result.platform, "macos")
        self.assertEqual(result.browser, "chrome")
        self.assertTrue(result.activated)
        self.assertTrue(result.frontmost)
        self.assertEqual(result.error_code, "")
        self.assertIn("已激活并确认位于前台", result.message)
        click.assert_not_called()
        move.assert_not_called()
        press.assert_not_called()
        scroll.assert_not_called()
        hotkey.assert_not_called()
        listener_start.assert_not_called()

    def test_focus_chrome_window_activate_failure_is_fail_closed(self):
        activate = subprocess.CompletedProcess(
            args=["osascript", "-e", 'tell application "Google Chrome" to activate'],
            returncode=1,
            stdout="",
            stderr="permission denied",
        )
        with patch.object(simple_brush, "run_osascript", return_value=activate) as run:
            result = simple_brush.focus_chrome_window()

        run.assert_called_once_with('tell application "Google Chrome" to activate')
        self.assertFalse(result.activated)
        self.assertFalse(result.frontmost)
        self.assertEqual(result.error_code, "MACOS_CHROME_ACTIVATE_FAILED")
        self.assertIn("permission denied", result.message)

    def test_focus_chrome_window_frontmost_query_failure_is_fail_closed(self):
        activate = subprocess.CompletedProcess(
            args=["osascript", "-e", 'tell application "Google Chrome" to activate'],
            returncode=0,
            stdout="",
            stderr="",
        )
        frontmost = subprocess.CompletedProcess(
            args=["osascript", "-e", "frontmost query"],
            returncode=1,
            stdout="",
            stderr="system events denied",
        )
        with patch.object(
            simple_brush, "run_osascript", side_effect=[activate, frontmost]
        ):
            result = simple_brush.focus_chrome_window()

        self.assertTrue(result.activated)
        self.assertFalse(result.frontmost)
        self.assertEqual(
            result.error_code, "MACOS_CHROME_FRONTMOST_QUERY_FAILED"
        )
        self.assertIn("system events denied", result.message)

    def test_focus_chrome_window_non_chrome_frontmost_is_fail_closed(self):
        activate = subprocess.CompletedProcess(
            args=["osascript", "-e", 'tell application "Google Chrome" to activate'],
            returncode=0,
            stdout="",
            stderr="",
        )
        frontmost = subprocess.CompletedProcess(
            args=["osascript", "-e", "frontmost query"],
            returncode=0,
            stdout="Finder\n",
            stderr="",
        )
        with patch.object(
            simple_brush, "run_osascript", side_effect=[activate, frontmost]
        ):
            result = simple_brush.focus_chrome_window()

        self.assertTrue(result.activated)
        self.assertFalse(result.frontmost)
        self.assertEqual(result.error_code, "MACOS_CHROME_NOT_FRONTMOST")
        self.assertIn("Finder", result.message)

    def test_focus_chrome_window_timeout_is_fail_closed(self):
        with patch.object(
            simple_brush,
            "run_osascript",
            side_effect=subprocess.TimeoutExpired(cmd=["osascript"], timeout=3.0),
        ):
            result = simple_brush.focus_chrome_window()

        self.assertFalse(result.activated)
        self.assertFalse(result.frontmost)
        self.assertEqual(result.error_code, "MACOS_OSASCRIPT_TIMEOUT")

    def test_focus_chrome_window_missing_osascript_is_fail_closed(self):
        with patch.object(
            simple_brush,
            "run_osascript",
            side_effect=FileNotFoundError("osascript not found"),
        ):
            result = simple_brush.focus_chrome_window()

        self.assertFalse(result.activated)
        self.assertFalse(result.frontmost)
        self.assertEqual(result.error_code, "MACOS_OSASCRIPT_UNAVAILABLE")
        self.assertIn("osascript not found", result.message)

    def test_focus_chrome_window_osascript_oserror_is_fail_closed(self):
        with patch.object(
            simple_brush,
            "run_osascript",
            side_effect=OSError("apple events unavailable"),
        ):
            result = simple_brush.focus_chrome_window()

        self.assertFalse(result.activated)
        self.assertFalse(result.frontmost)
        self.assertEqual(result.error_code, "MACOS_OSASCRIPT_ERROR")
        self.assertIn("apple events unavailable", result.message)

    def test_focus_chrome_window_only_runs_activate_and_frontmost_scripts(self):
        seen_scripts = []
        activate = subprocess.CompletedProcess(
            args=["osascript", "-e", "activate"],
            returncode=0,
            stdout="",
            stderr="",
        )
        frontmost = subprocess.CompletedProcess(
            args=["osascript", "-e", "frontmost"],
            returncode=0,
            stdout="Google Chrome\n",
            stderr="",
        )

        def fake_run(script, timeout=3.0):
            seen_scripts.append(script)
            if script == 'tell application "Google Chrome" to activate':
                return activate
            if (
                script
                == 'tell application "System Events" '
                'to get name of first application process whose frontmost is true'
            ):
                return frontmost
            self.fail(f"unexpected script: {script}")

        with patch.object(simple_brush, "run_osascript", side_effect=fake_run):
            result = simple_brush.focus_chrome_window()

        self.assertTrue(result.frontmost)
        self.assertEqual(len(seen_scripts), 2)
        self.assertTrue(any("Google Chrome" in script for script in seen_scripts))
        self.assertFalse(any("active tab" in script.lower() for script in seen_scripts))
        self.assertFalse(any("url" in script.lower() for script in seen_scripts))
        self.assertFalse(any("title" in script.lower() for script in seen_scripts))

    def test_get_chrome_active_tab_identity_successfully_reads_url_and_title(self):
        script_result = subprocess.CompletedProcess(
            args=["osascript", "-e", "tab query"],
            returncode=0,
            stdout="https://www.zhipin.com/web/geek/job-recommend\nBOSS Page\n",
            stderr="",
        )
        with (
            patch.object(simple_brush, "run_osascript", return_value=script_result) as run,
            patch.object(simple_brush, "focus_chrome_window") as focus,
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
            patch.object(simple_brush.listener, "start") as listener_start,
            patch.object(simple_brush, "initialize_ocr") as initialize_ocr,
        ):
            result = simple_brush.get_chrome_active_tab_identity()

        run.assert_called_once()
        script_text = run.call_args.args[0]
        self.assertIn('tell application "Google Chrome"', script_text)
        self.assertIn('active tab of frontWindow', script_text)
        self.assertNotIn('activate', script_text.lower())
        self.assertEqual(result.platform, "macos")
        self.assertEqual(result.browser, "chrome")
        self.assertEqual(result.url, "https://www.zhipin.com/web/geek/job-recommend")
        self.assertEqual(result.title, "BOSS Page")
        self.assertEqual(result.error_code, "")
        focus.assert_not_called()
        click.assert_not_called()
        move.assert_not_called()
        press.assert_not_called()
        scroll.assert_not_called()
        hotkey.assert_not_called()
        listener_start.assert_not_called()
        initialize_ocr.assert_not_called()

    def test_get_chrome_active_tab_identity_preserves_title_newlines(self):
        script_result = subprocess.CompletedProcess(
            args=["osascript", "-e", "tab query"],
            returncode=0,
            stdout="https://example.com\nLine 1\nLine 2\nLine 3\n",
            stderr="",
        )
        with patch.object(simple_brush, "run_osascript", return_value=script_result):
            result = simple_brush.get_chrome_active_tab_identity()

        self.assertEqual(result.url, "https://example.com")
        self.assertEqual(result.title, "Line 1\nLine 2\nLine 3")
        self.assertEqual(result.error_code, "")

    def test_get_chrome_active_tab_identity_missing_url_is_fail_closed(self):
        script_result = subprocess.CompletedProcess(
            args=["osascript", "-e", "tab query"],
            returncode=0,
            stdout="\nTitle Only\n",
            stderr="",
        )
        with patch.object(simple_brush, "run_osascript", return_value=script_result):
            result = simple_brush.get_chrome_active_tab_identity()

        self.assertEqual(result.url, "")
        self.assertEqual(result.title, "Title Only")
        self.assertEqual(result.error_code, "MACOS_CHROME_ACTIVE_TAB_URL_MISSING")

    def test_get_chrome_active_tab_identity_query_failure_is_fail_closed(self):
        script_result = subprocess.CompletedProcess(
            args=["osascript", "-e", "tab query"],
            returncode=1,
            stdout="",
            stderr="apple event failed",
        )
        with patch.object(simple_brush, "run_osascript", return_value=script_result):
            result = simple_brush.get_chrome_active_tab_identity()

        self.assertEqual(result.error_code, "MACOS_CHROME_TAB_QUERY_FAILED")
        self.assertIn("apple event failed", result.message)

    def test_get_chrome_active_tab_identity_maps_no_front_window(self):
        script_result = subprocess.CompletedProcess(
            args=["osascript", "-e", "tab query"],
            returncode=1,
            stdout="",
            stderr="NO_FRONT_WINDOW",
        )
        with patch.object(simple_brush, "run_osascript", return_value=script_result):
            result = simple_brush.get_chrome_active_tab_identity()

        self.assertEqual(result.error_code, "MACOS_CHROME_NO_FRONT_WINDOW")
        self.assertIn("front window", result.message)

    def test_get_chrome_active_tab_identity_maps_no_active_tab(self):
        script_result = subprocess.CompletedProcess(
            args=["osascript", "-e", "tab query"],
            returncode=1,
            stdout="",
            stderr="NO_ACTIVE_TAB",
        )
        with patch.object(simple_brush, "run_osascript", return_value=script_result):
            result = simple_brush.get_chrome_active_tab_identity()

        self.assertEqual(result.error_code, "MACOS_CHROME_NO_ACTIVE_TAB")
        self.assertIn("active tab", result.message)

    def test_get_chrome_active_tab_identity_timeout_is_fail_closed(self):
        with patch.object(
            simple_brush,
            "run_osascript",
            side_effect=subprocess.TimeoutExpired(cmd=["osascript"], timeout=3.0),
        ):
            result = simple_brush.get_chrome_active_tab_identity()

        self.assertEqual(result.error_code, "MACOS_OSASCRIPT_TIMEOUT")
        self.assertEqual(result.url, "")
        self.assertEqual(result.title, "")

    def test_get_chrome_active_tab_identity_missing_osascript_is_fail_closed(self):
        with patch.object(
            simple_brush,
            "run_osascript",
            side_effect=FileNotFoundError("osascript not found"),
        ):
            result = simple_brush.get_chrome_active_tab_identity()

        self.assertEqual(result.error_code, "MACOS_OSASCRIPT_UNAVAILABLE")
        self.assertIn("osascript not found", result.message)

    def test_get_chrome_active_tab_identity_osascript_oserror_is_fail_closed(self):
        with patch.object(
            simple_brush,
            "run_osascript",
            side_effect=OSError("apple events unavailable"),
        ):
            result = simple_brush.get_chrome_active_tab_identity()

        self.assertEqual(result.error_code, "MACOS_OSASCRIPT_ERROR")
        self.assertIn("apple events unavailable", result.message)

    def test_macos_focus_failure_stops_before_tab_and_allowlist(self):
        resolved = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        launched = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        focus_failed = simple_brush.MacOSChromeFocusResult(
            platform="macos",
            browser="chrome",
            activated=False,
            frontmost=False,
            message="activate failed",
            error_code="MACOS_CHROME_ACTIVATE_FAILED",
        )
        with (
            patch.object(
                simple_brush, "resolve_chrome_executable", return_value=resolved
            ) as resolve,
            patch.object(
                simple_brush, "launch_chrome_safe_target", return_value=launched
            ) as launch,
            patch.object(
                simple_brush, "focus_chrome_window", return_value=focus_failed
            ) as focus,
            patch.object(
                simple_brush, "get_chrome_active_tab_identity"
            ) as tab_identity,
            patch.object(simple_brush, "is_allowed_boss_page") as page_allowed,
        ):
            result = simple_brush.prepare_browser("darwin")

        resolve.assert_called_once_with()
        launch.assert_called_once_with(simple_brush.MACOS_CHROME_EXECUTABLE)
        focus.assert_called_once_with()
        tab_identity.assert_not_called()
        page_allowed.assert_not_called()
        self.assertFalse(result.ready)
        self.assertTrue(result.launched)
        self.assertFalse(result.focus_frontmost)
        self.assertEqual(result.error_code, "MACOS_CHROME_ACTIVATE_FAILED")
        self.assertIn("accessibility=unknown", result.message)

    def test_macos_tab_failure_stops_before_allowlist(self):
        resolved = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        launched = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        focus = simple_brush.MacOSChromeFocusResult(
            platform="macos",
            browser="chrome",
            activated=True,
            frontmost=True,
        )
        tab_failed = simple_brush.MacOSChromeTabIdentity(
            platform="macos",
            browser="chrome",
            message="tab query failed",
            error_code="MACOS_CHROME_TAB_QUERY_FAILED",
        )
        with (
            patch.object(
                simple_brush, "resolve_chrome_executable", return_value=resolved
            ),
            patch.object(
                simple_brush, "launch_chrome_safe_target", return_value=launched
            ),
            patch.object(simple_brush, "focus_chrome_window", return_value=focus),
            patch.object(
                simple_brush,
                "get_chrome_active_tab_identity",
                return_value=tab_failed,
            ) as tab_identity,
            patch.object(simple_brush, "is_allowed_boss_page") as page_allowed,
        ):
            result = simple_brush.prepare_browser("darwin")

        tab_identity.assert_called_once_with()
        page_allowed.assert_not_called()
        self.assertFalse(result.ready)
        self.assertTrue(result.focus_frontmost)
        self.assertEqual(result.error_code, "MACOS_CHROME_TAB_QUERY_FAILED")
        self.assertEqual(result.page_error_code, "MACOS_CHROME_TAB_QUERY_FAILED")

    def test_macos_about_blank_and_non_boss_pages_are_not_allowed(self):
        for url in ("about:blank", "https://example.com/jobs"):
            with self.subTest(url=url):
                resolved = simple_brush.BrowserPrepareResult(
                    ready=False,
                    platform="macos",
                    browser="chrome",
                    executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
                )
                launched = simple_brush.BrowserPrepareResult(
                    ready=False,
                    platform="macos",
                    browser="chrome",
                    launched=True,
                    executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
                )
                focus = simple_brush.MacOSChromeFocusResult(
                    platform="macos",
                    browser="chrome",
                    activated=True,
                    frontmost=True,
                )
                tab = simple_brush.MacOSChromeTabIdentity(
                    platform="macos",
                    browser="chrome",
                    url=url,
                    title="Page",
                )
                with (
                    patch.object(
                        simple_brush,
                        "resolve_chrome_executable",
                        return_value=resolved,
                    ),
                    patch.object(
                        simple_brush,
                        "launch_chrome_safe_target",
                        return_value=launched,
                    ),
                    patch.object(
                        simple_brush, "focus_chrome_window", return_value=focus
                    ),
                    patch.object(
                        simple_brush,
                        "get_chrome_active_tab_identity",
                        return_value=tab,
                    ),
                    patch.object(
                        simple_brush,
                        "is_allowed_boss_page",
                        wraps=simple_brush.is_allowed_boss_page,
                    ) as page_allowed,
                ):
                    result = simple_brush.prepare_browser("darwin")

                page_allowed.assert_called_once_with(url, "Page")
                self.assertFalse(result.ready)
                self.assertFalse(result.page_allowed)
                self.assertEqual(result.page_url, url)
                self.assertEqual(result.error_code, "MACOS_PAGE_NOT_ALLOWED")
                self.assertEqual(result.page_error_code, "MACOS_PAGE_NOT_ALLOWED")

    def test_macos_allowed_page_is_still_not_business_ready(self):
        resolved = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        launched = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        permissions = simple_brush.MacOSPermissionStatus(
            accessibility="unknown",
            screen_recording="unknown",
            keyboard_listener="unknown",
            ready=False,
            message="permissions unknown.",
        )
        focus = simple_brush.MacOSChromeFocusResult(
            platform="macos",
            browser="chrome",
            activated=True,
            frontmost=True,
            message="frontmost",
        )
        tab = simple_brush.MacOSChromeTabIdentity(
            platform="macos",
            browser="chrome",
            url="https://www.zhipin.com/web/geek/job-recommend",
            title="BOSS Page",
        )
        with (
            patch.object(
                simple_brush, "resolve_chrome_executable", return_value=resolved
            ),
            patch.object(
                simple_brush, "launch_chrome_safe_target", return_value=launched
            ),
            patch.object(
                simple_brush, "check_macos_permissions", return_value=permissions
            ),
            patch.object(simple_brush, "focus_chrome_window", return_value=focus),
            patch.object(
                simple_brush, "get_chrome_active_tab_identity", return_value=tab
            ),
            patch.object(
                simple_brush, "is_allowed_boss_page", return_value=True
            ) as page_allowed,
        ):
            result = simple_brush.prepare_browser("darwin")

        page_allowed.assert_called_once_with(tab.url, tab.title)
        self.assertFalse(result.ready)
        self.assertTrue(result.focus_frontmost)
        self.assertTrue(result.page_allowed)
        self.assertEqual(result.page_url, tab.url)
        self.assertEqual(result.page_title, tab.title)
        self.assertEqual(
            result.error_code, "MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY"
        )
        self.assertIn("Retina", result.message)
        self.assertIn("OCR", result.message)
        self.assertIn("不放行业务动作", result.message)

    def test_permission_diagnostics_default_to_unknown(self):
        status = simple_brush.check_macos_permissions()

        self.assertEqual(status.accessibility, "unknown")
        self.assertEqual(status.screen_recording, "unknown")
        self.assertEqual(status.keyboard_listener, "unknown")
        self.assertFalse(status.ready)
        self.assertIn("Terminal / iTerm / VS Code / Python", status.message)
        self.assertIn("系统设置 → 隐私与安全性 → 辅助功能", status.message)
        self.assertIn("系统设置 → 隐私与安全性 → 屏幕录制", status.message)
        self.assertIn("输入监控或辅助功能", status.message)

    def test_each_failed_permission_is_fail_closed(self):
        checks = {
            "accessibility": "check_macos_accessibility_capability",
            "screen_recording": "check_macos_screen_recording_capability",
            "keyboard_listener": "check_macos_keyboard_listener_capability",
        }
        for field, function_name in checks.items():
            with (
                self.subTest(field=field),
                patch.object(
                    simple_brush,
                    "check_macos_accessibility_capability",
                    return_value="ok",
                ),
                patch.object(
                    simple_brush,
                    "check_macos_screen_recording_capability",
                    return_value="ok",
                ),
                patch.object(
                    simple_brush,
                    "check_macos_keyboard_listener_capability",
                    return_value="ok",
                ),
                patch.object(simple_brush, function_name, return_value="failed"),
            ):
                status = simple_brush.check_macos_permissions()

            self.assertFalse(status.ready)
            self.assertEqual(getattr(status, field), "failed")

    def test_permission_check_exception_after_launch_is_fail_closed(self):
        resolved = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        launched = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        with (
            patch.object(
                simple_brush, "resolve_chrome_executable", return_value=resolved
            ),
            patch.object(
                simple_brush, "launch_chrome_safe_target", return_value=launched
            ),
            patch.object(
                simple_brush,
                "check_macos_permissions",
                side_effect=RuntimeError("diagnostic failed"),
            ),
            patch.object(simple_brush, "focus_chrome_window") as focus,
        ):
            result = simple_brush.prepare_browser("darwin")

        self.assertFalse(result.ready)
        self.assertTrue(result.launched)
        self.assertEqual(result.error_code, "MACOS_PERMISSION_CHECK_FAILED")
        self.assertIn("diagnostic failed", result.message)
        self.assertIn("完全退出并重启宿主进程", result.message)
        focus.assert_not_called()

    def test_all_ok_permissions_still_do_not_make_browser_ready(self):
        resolved = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        launched = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
        )
        permissions = simple_brush.MacOSPermissionStatus(
            accessibility="ok",
            screen_recording="ok",
            keyboard_listener="ok",
            ready=True,
            message="permissions ok.",
        )
        focus = simple_brush.MacOSChromeFocusResult(
            platform="macos",
            browser="chrome",
            activated=True,
            frontmost=True,
        )
        tab = simple_brush.MacOSChromeTabIdentity(
            platform="macos",
            browser="chrome",
            url="https://www.zhipin.com/",
            title="",
        )
        with (
            patch.object(
                simple_brush, "resolve_chrome_executable", return_value=resolved
            ),
            patch.object(
                simple_brush, "launch_chrome_safe_target", return_value=launched
            ),
            patch.object(
                simple_brush, "check_macos_permissions", return_value=permissions
            ),
            patch.object(simple_brush, "focus_chrome_window", return_value=focus),
            patch.object(
                simple_brush, "get_chrome_active_tab_identity", return_value=tab
            ),
            patch.object(simple_brush, "is_allowed_boss_page", return_value=True),
        ):
            result = simple_brush.prepare_browser("darwin")

        self.assertFalse(result.ready)
        self.assertTrue(result.launched)
        self.assertTrue(result.page_allowed)
        self.assertEqual(
            result.error_code, "MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY"
        )
        self.assertIn("不放行业务动作", result.message)

    def test_permission_diagnostics_have_no_gui_capture_or_ocr_side_effects(self):
        with (
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
            patch.object(simple_brush, "save_region_preview") as save_preview,
            patch.object(simple_brush, "MSSScreenCapture") as screen_capture,
            patch.object(simple_brush, "OCRKeywordDetector") as detector,
            patch.object(simple_brush.listener, "start") as listener_start,
        ):
            status = simple_brush.check_macos_permissions()

        self.assertFalse(status.ready)
        click.assert_not_called()
        move.assert_not_called()
        press.assert_not_called()
        hotkey.assert_not_called()
        scroll.assert_not_called()
        save_preview.assert_not_called()
        screen_capture.assert_not_called()
        detector.assert_not_called()
        listener_start.assert_not_called()

    def test_unknown_platform_is_fail_closed(self):
        with (
            patch.object(simple_brush, "bring_edge_foreground") as bring_edge,
            patch.object(simple_brush, "check_macos_permissions") as permissions,
            patch.object(simple_brush, "focus_chrome_window") as focus,
            patch.object(
                simple_brush, "get_chrome_active_tab_identity"
            ) as tab_identity,
            patch.object(simple_brush, "is_allowed_boss_page") as page_allowed,
        ):
            result = simple_brush.prepare_browser("linux")

        bring_edge.assert_not_called()
        permissions.assert_not_called()
        focus.assert_not_called()
        tab_identity.assert_not_called()
        page_allowed.assert_not_called()
        self.assertFalse(result.ready)
        self.assertEqual(result.platform, "linux")
        self.assertEqual(result.browser, "")
        self.assertEqual(result.error_code, "UNSUPPORTED_PLATFORM")
        self.assertIn("linux", result.message)

    def test_default_dispatch_uses_sys_platform(self):
        with (
            patch.object(simple_brush.sys, "platform", "win32"),
            patch.object(
                simple_brush, "bring_edge_foreground", return_value=True
            ) as bring_edge,
        ):
            result = simple_brush.prepare_browser()

        bring_edge.assert_called_once_with()
        self.assertTrue(result.ready)
        self.assertEqual(result.platform, "windows")

    def test_windows_does_not_call_chrome_resolution_or_popen(self):
        with (
            patch.object(
                simple_brush, "bring_edge_foreground", return_value=True
            ) as bring_edge,
            patch.object(simple_brush, "resolve_chrome_executable") as resolve,
            patch.object(simple_brush.subprocess, "Popen") as popen,
            patch.object(simple_brush, "check_macos_permissions") as permissions,
            patch.object(simple_brush, "focus_chrome_window") as focus,
            patch.object(
                simple_brush, "get_chrome_active_tab_identity"
            ) as tab_identity,
            patch.object(simple_brush, "is_allowed_boss_page") as page_allowed,
        ):
            result = simple_brush.prepare_browser("win32")

        bring_edge.assert_called_once_with()
        resolve.assert_not_called()
        popen.assert_not_called()
        permissions.assert_not_called()
        focus.assert_not_called()
        tab_identity.assert_not_called()
        page_allowed.assert_not_called()
        self.assertTrue(result.ready)
        self.assertIsNone(result.focus_frontmost)
        self.assertIsNone(result.page_allowed)

    def test_windows_ready_preserves_run_preparation_order(self):
        events = []
        ready = simple_brush.BrowserPrepareResult(
            ready=True,
            platform="windows",
            browser="edge",
        )

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = True
            simple_brush.forward_keywords = simple_brush.parse_keyword_rules('"Python"')
            simple_brush.batch_filter_enabled = True

        with (
            patch.object(simple_brush, "forward_enabled", False),
            patch.object(simple_brush, "forward_keywords", []),
            patch.object(simple_brush, "batch_filter_enabled", False),
            patch.object(
                simple_brush,
                "parse_args",
                return_value={
                    "keywords": "",
                    "email": "",
                    "duration_seconds": "",
                    "no_forward": True,
                    "no_batch_filter": False,
                    "simple_mouse": False,
                    "auto": False,
                },
            ),
            patch.object(
                simple_brush, "get_user_input", side_effect=configure_input
            ),
            patch.object(
                simple_brush,
                "initialize_ocr",
                side_effect=lambda: events.append("initialize_ocr"),
            ),
            patch.object(
                simple_brush.listener,
                "start",
                side_effect=lambda: events.append("listener_start"),
            ),
            patch.object(
                simple_brush,
                "prepare_browser",
                side_effect=lambda: events.append("prepare_browser") or ready,
            ),
            patch.object(
                simple_brush,
                "open_first_candidate_for_batch",
                side_effect=lambda: events.append("open_first_candidate") or False,
            ),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            events,
            [
                "initialize_ocr",
                "listener_start",
                "prepare_browser",
                "open_first_candidate",
            ],
        )

    def test_run_stops_before_business_actions_when_not_ready(self):
        not_ready = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            launched=True,
            executable_path=str(simple_brush.MACOS_CHROME_EXECUTABLE),
            message="allowed but not business ready",
            error_code="MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY",
            focus_frontmost=True,
            page_url="https://www.zhipin.com/",
            page_title="BOSS直聘",
            page_allowed=True,
            page_error_code="MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY",
        )
        with (
            patch.object(
                simple_brush.sys,
                "argv",
                [
                    "simple_brush.py",
                    "--keywords",
                    '"Python"',
                    "--no-forward",
                    "--auto",
                ],
            ),
            patch.object(simple_brush.listener, "start"),
            patch.object(simple_brush, "prepare_browser", return_value=not_ready),
            patch.object(simple_brush, "initialize_ocr") as initialize_ocr,
            patch.object(simple_brush, "ensure_ocr_region_calibrated") as calibrate_ocr,
            patch.object(simple_brush, "detect_keywords") as detect_keywords,
            patch.object(
                simple_brush, "ensure_batch_filter_regions_calibrated"
            ) as calibrate_filter,
            patch.object(
                simple_brush, "open_first_candidate_for_batch"
            ) as open_first,
            patch.object(simple_brush, "view_candidate") as view_candidate,
            patch.object(simple_brush, "next_candidate") as next_candidate,
            patch.object(simple_brush, "refresh_page") as refresh_page,
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush.pyautogui, "position") as position,
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
        ):
            self.assertEqual(simple_brush.run(), 0)

        initialize_ocr.assert_called_once_with()
        calibrate_ocr.assert_not_called()
        detect_keywords.assert_not_called()
        calibrate_filter.assert_not_called()
        open_first.assert_not_called()
        view_candidate.assert_not_called()
        next_candidate.assert_not_called()
        refresh_page.assert_not_called()
        forward.assert_not_called()
        position.assert_not_called()
        click.assert_not_called()
        press.assert_not_called()
        scroll.assert_not_called()
        hotkey.assert_not_called()


class MacSafeBrowseGuardTests(unittest.TestCase):
    def make_config(self, **overrides):
        values = {
            "enabled": True,
            "no_forward_required": True,
            "max_candidates": 1,
            "max_runtime_minutes": 5,
            "require_page_allowed": True,
            "require_coordinate_validated": True,
            "require_manual_confirmation": True,
        }
        values.update(overrides)
        return simple_brush.MacSafeBrowseConfig(**values)

    def make_evidence(self, **overrides):
        values = {
            "platform": "darwin",
            "no_forward_enabled": True,
            "forwarding_email_present": False,
            "page_allowed": True,
            "page_stage_allowed": True,
            "chrome_frontmost": True,
            "coordinate_validated": True,
            "manual_confirmed": True,
            "listener_available": True,
            "profile_unique": True,
            "display_fingerprint_matches": True,
        }
        values.update(overrides)
        return simple_brush.MacSafeBrowseEvidence(**values)

    def assert_guard_failure(
        self,
        error_code,
        *,
        config_overrides=None,
        evidence_overrides=None,
    ):
        result = simple_brush.validate_mac_safe_browse_guard(
            self.make_config(**(config_overrides or {})),
            self.make_evidence(**(evidence_overrides or {})),
        )
        self.assertFalse(result.passed)
        self.assertFalse(result.ready_for_browse)
        self.assertEqual(result.error_code, error_code)

    def test_guard_rejects_disabled_or_unsupported_platform(self):
        cases = (
            (
                {"enabled": False},
                {},
                "MAC_SAFE_BROWSE_DISABLED",
            ),
            (
                {},
                {"platform": "win32"},
                "MAC_SAFE_BROWSE_UNSUPPORTED_PLATFORM",
            ),
        )
        for config, evidence, error_code in cases:
            with self.subTest(error_code=error_code):
                self.assert_guard_failure(
                    error_code,
                    config_overrides=config,
                    evidence_overrides=evidence,
                )

    def test_guard_requires_no_forward_and_no_email(self):
        cases = (
            (
                {"no_forward_required": False},
                {},
                "MAC_SAFE_BROWSE_NO_FORWARD_REQUIRED",
            ),
            (
                {},
                {"no_forward_enabled": False},
                "MAC_SAFE_BROWSE_NO_FORWARD_REQUIRED",
            ),
            (
                {},
                {"forwarding_email_present": True},
                "MAC_SAFE_BROWSE_FORWARDING_EMAIL_PRESENT",
            ),
        )
        for config, evidence, error_code in cases:
            with self.subTest(config=config, evidence=evidence):
                self.assert_guard_failure(
                    error_code,
                    config_overrides=config,
                    evidence_overrides=evidence,
                )

    def test_guard_rejects_invalid_candidate_limits(self):
        for value in (None, 0, 6):
            with self.subTest(max_candidates=value):
                self.assert_guard_failure(
                    "MAC_SAFE_BROWSE_LIMIT_INVALID",
                    config_overrides={"max_candidates": value},
                )

    def test_guard_rejects_invalid_runtime_limits(self):
        for value in (None, 0, 16):
            with self.subTest(max_runtime_minutes=value):
                self.assert_guard_failure(
                    "MAC_SAFE_BROWSE_LIMIT_INVALID",
                    config_overrides={"max_runtime_minutes": value},
                )

    def test_guard_rejects_page_focus_coordinate_and_confirmation_failures(self):
        cases = (
            ("page_allowed", False, "MAC_SAFE_BROWSE_PAGE_NOT_ALLOWED"),
            (
                "page_stage_allowed",
                False,
                "MAC_SAFE_BROWSE_PAGE_STATE_AMBIGUOUS",
            ),
            (
                "chrome_frontmost",
                False,
                "MAC_SAFE_BROWSE_CHROME_NOT_FRONTMOST",
            ),
            (
                "coordinate_validated",
                False,
                "MAC_SAFE_BROWSE_COORDINATE_NOT_VALIDATED",
            ),
            (
                "manual_confirmed",
                False,
                "MAC_SAFE_BROWSE_PREVIEW_NOT_CONFIRMED",
            ),
            (
                "listener_available",
                False,
                "MAC_SAFE_BROWSE_LISTENER_UNAVAILABLE",
            ),
        )
        for field_name, value, error_code in cases:
            with self.subTest(field_name=field_name):
                self.assert_guard_failure(
                    error_code,
                    evidence_overrides={field_name: value},
                )

    def test_guard_rejects_ambiguous_profile(self):
        for value in (False, None):
            with self.subTest(profile_unique=value):
                self.assert_guard_failure(
                    "MAC_SAFE_BROWSE_PROFILE_AMBIGUOUS",
                    evidence_overrides={"profile_unique": value},
                )

    def test_guard_rejects_missing_or_mismatched_display_fingerprint(self):
        for value in (False, None):
            with self.subTest(display_fingerprint_matches=value):
                self.assert_guard_failure(
                    "MAC_SAFE_BROWSE_DISPLAY_FINGERPRINT_MISMATCH",
                    evidence_overrides={"display_fingerprint_matches": value},
                )

    def test_guard_passes_with_all_required_evidence(self):
        result = simple_brush.validate_mac_safe_browse_guard(
            self.make_config(),
            self.make_evidence(),
        )

        self.assertTrue(result.passed)
        self.assertTrue(result.ready_for_browse)
        self.assertTrue(result.no_forward_enforced)
        self.assertTrue(result.page_allowed)
        self.assertTrue(result.coordinate_validated)
        self.assertTrue(result.manual_confirmed)
        self.assertIsNone(result.error_code)
        self.assertIn("不代表业务 ready", result.message)
        self.assertIn("禁止转发", result.message)

    def test_guard_success_does_not_change_existing_readiness_objects(self):
        browser_result = simple_brush.BrowserPrepareResult(
            ready=False,
            platform="macos",
            browser="chrome",
            page_allowed=True,
        )
        coordinate_metadata = simple_brush.CoordinateCalibrationMetadata(
            display_fingerprint="display-fingerprint",
            scale_inference=None,
            tk_to_screenshot_mapping=None,
            crop_preview=None,
            validated=True,
            manually_confirmed=True,
            message="validated for test",
        )

        result = simple_brush.validate_mac_safe_browse_guard(
            self.make_config(),
            self.make_evidence(),
        )

        self.assertTrue(result.ready_for_browse)
        self.assertFalse(browser_result.ready)
        self.assertFalse(coordinate_metadata.business_ready)

    def test_guard_is_pure_and_does_not_call_runtime_helpers(self):
        blocked_names = (
            "prepare_browser",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
            "initialize_ocr",
            "select_screen_region",
            "save_region_preview",
            "MSSScreenCapture",
            "OCRKeywordDetector",
            "forward_one_candidate",
        )
        pyautogui_names = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        with ExitStack() as stack:
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            result = simple_brush.validate_mac_safe_browse_guard(
                self.make_config(),
                self.make_evidence(),
            )

        self.assertTrue(result.passed)
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()


class MacSafeBrowseCLITests(unittest.TestCase):
    def parse(self, *args):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", *args],
        ):
            return simple_brush.parse_args()

    def valid_args(self, **overrides):
        values = self.parse(
            "--mac-safe-browse-only",
            "--no-forward",
            "--max-candidates",
            "1",
            "--max-runtime-minutes",
            "5",
        )
        values.update(overrides)
        return values

    def assert_argument_error(self, error_code, args, *, platform="darwin"):
        with self.assertRaises(simple_brush.MacSafeBrowseArgumentError) as caught:
            simple_brush.build_mac_safe_browse_config(
                args,
                platform_name=platform,
            )
        self.assertEqual(caught.exception.error_code, error_code)

    def test_parse_args_recognizes_safe_browse_and_limits(self):
        defaults = self.parse()
        parsed = self.valid_args()

        self.assertFalse(defaults["mac_safe_browse_only"])
        self.assertIsNone(defaults["max_candidates"])
        self.assertIsNone(defaults["max_runtime_minutes"])
        self.assertTrue(parsed["mac_safe_browse_only"])
        self.assertEqual(parsed["max_candidates"], 1)
        self.assertEqual(parsed["max_runtime_minutes"], 5)

    def test_parse_args_rejects_safe_browse_mode_conflicts(self):
        for conflicting_flag in (
            "--auto",
            "--preflight-only",
            "--coordinate-diagnostics-only",
        ):
            with self.subTest(conflicting_flag=conflicting_flag):
                with self.assertRaises(
                    simple_brush.MacSafeBrowseArgumentError
                ) as caught:
                    self.parse(
                        "--mac-safe-browse-only",
                        "--no-forward",
                        "--max-candidates",
                        "1",
                        "--max-runtime-minutes",
                        "5",
                        conflicting_flag,
                    )
                self.assertEqual(
                    caught.exception.error_code,
                    "MAC_SAFE_BROWSE_CONFLICTING_MODE",
                )

    def test_build_safe_browse_config_rejects_non_macos_and_missing_no_forward(self):
        self.assert_argument_error(
            "MAC_SAFE_BROWSE_UNSUPPORTED_PLATFORM",
            self.valid_args(),
            platform="win32",
        )
        self.assert_argument_error(
            "MAC_SAFE_BROWSE_NO_FORWARD_REQUIRED",
            self.valid_args(no_forward=False),
        )

    def test_build_safe_browse_config_rejects_missing_and_invalid_limits(self):
        cases = (
            ("max_candidates", None),
            ("max_candidates", 0),
            ("max_candidates", 6),
            ("max_runtime_minutes", None),
            ("max_runtime_minutes", 0),
            ("max_runtime_minutes", 16),
        )
        for field_name, value in cases:
            with self.subTest(field_name=field_name, value=value):
                self.assert_argument_error(
                    "MAC_SAFE_BROWSE_LIMIT_INVALID",
                    self.valid_args(**{field_name: value}),
                )

    def test_build_safe_browse_config_rejects_email(self):
        self.assert_argument_error(
            "MAC_SAFE_BROWSE_FORWARDING_EMAIL_PRESENT",
            self.valid_args(email="forward@example.com"),
        )


class TkOverlayLifecycleTests(unittest.TestCase):
    class FakeCanvas:
        def __init__(self):
            self.bindings = {}

        def pack(self, **_kwargs):
            return None

        def create_text(self, *_args, **_kwargs):
            return 1

        def create_rectangle(self, *_args, **_kwargs):
            return 2

        def delete(self, *_args):
            return None

        def coords(self, *_args):
            return None

        def itemconfigure(self, *_args, **_kwargs):
            return None

        def winfo_width(self):
            return 1000

        def winfo_height(self):
            return 800

        def bind(self, event_name, callback):
            self.bindings[event_name] = callback

    class FakeRoot:
        def __init__(self, mainloop_mode):
            self.mainloop_mode = mainloop_mode
            self.bindings = {}
            self.canvas = None

        def overrideredirect(self, *_args):
            return None

        def geometry(self, *_args):
            return None

        def attributes(self, *_args):
            return None

        def configure(self, **_kwargs):
            return None

        def bind(self, event_name, callback):
            self.bindings[event_name] = callback

        def lift(self):
            return None

        def focus_force(self):
            return None

        def quit(self):
            return None

        def mainloop(self):
            if self.mainloop_mode == "success":
                self.canvas.bindings["<ButtonPress-1>"](
                    SimpleNamespace(x=10, y=20)
                )
                self.canvas.bindings["<ButtonRelease-1>"](
                    SimpleNamespace(x=210, y=220)
                )
                return
            if self.mainloop_mode == "cancel":
                self.bindings["<Escape>"](SimpleNamespace())
                return
            raise RuntimeError("mainloop failed")

    def fake_tk_module(self, root):
        def canvas_factory(_root, **_kwargs):
            canvas = self.FakeCanvas()
            root.canvas = canvas
            return canvas

        return SimpleNamespace(
            Tk=Mock(return_value=root),
            Canvas=canvas_factory,
            BOTH="both",
            TclError=RuntimeError,
        )

    def run_selection(self, mainloop_mode, cleanup_fn):
        root = self.FakeRoot(mainloop_mode)
        with (
            patch.dict(sys.modules, {"tkinter": self.fake_tk_module(root)}),
            patch.object(
                ocr_calibration,
                "primary_monitor_region",
                return_value=ocr_calibration.ScreenRegion(0, 0, 1000, 800),
            ),
        ):
            result = ocr_calibration.select_screen_region(
                overlay_cleanup_fn=cleanup_fn,
                cleanup_sleep_fn=Mock(),
                cleanup_settle_seconds=0.2,
            )
        return root, result

    def test_successful_selection_always_runs_overlay_cleanup(self):
        cleanup = Mock()

        root, region = self.run_selection("success", cleanup)

        self.assertEqual(region, ocr_calibration.ScreenRegion(10, 20, 200, 200))
        cleanup.assert_called_once()
        self.assertIs(cleanup.call_args.args[0], root)

    def test_cancelled_selection_always_runs_overlay_cleanup(self):
        cleanup = Mock()
        root = self.FakeRoot("cancel")
        with (
            patch.dict(sys.modules, {"tkinter": self.fake_tk_module(root)}),
            patch.object(
                ocr_calibration,
                "primary_monitor_region",
                return_value=ocr_calibration.ScreenRegion(0, 0, 1000, 800),
            ),
            self.assertRaises(ocr_calibration.CalibrationCancelled),
        ):
            ocr_calibration.select_screen_region(overlay_cleanup_fn=cleanup)

        cleanup.assert_called_once()
        self.assertIs(cleanup.call_args.args[0], root)

    def test_selection_exception_always_runs_overlay_cleanup(self):
        cleanup = Mock()
        root = self.FakeRoot("exception")
        with (
            patch.dict(sys.modules, {"tkinter": self.fake_tk_module(root)}),
            patch.object(
                ocr_calibration,
                "primary_monitor_region",
                return_value=ocr_calibration.ScreenRegion(0, 0, 1000, 800),
            ),
            self.assertRaisesRegex(RuntimeError, "mainloop failed"),
        ):
            ocr_calibration.select_screen_region(overlay_cleanup_fn=cleanup)

        cleanup.assert_called_once()
        self.assertIs(cleanup.call_args.args[0], root)

    def test_cleanup_failure_replaces_selection_success_with_fail_closed_error(self):
        cleanup = Mock(side_effect=RuntimeError("destroy failed"))

        with self.assertRaises(
            ocr_calibration.CalibrationCleanupFailed
        ) as caught:
            self.run_selection("success", cleanup)

        self.assertIn("destroy failed", str(caught.exception))

    def test_cleanup_hides_flushes_destroys_and_waits_for_window_server(self):
        root = SimpleNamespace(
            quit=Mock(),
            attributes=Mock(),
            withdraw=Mock(),
            update_idletasks=Mock(),
            update=Mock(),
            destroy=Mock(),
        )
        sleep_fn = Mock()

        ocr_calibration.cleanup_tk_overlay(root, sleep_fn=sleep_fn)

        root.quit.assert_called_once_with()
        root.attributes.assert_called_once_with("-topmost", False)
        root.withdraw.assert_called_once_with()
        root.update_idletasks.assert_called_once_with()
        root.update.assert_called_once_with()
        root.destroy.assert_called_once_with()
        sleep_fn.assert_called_once_with(0.2)
        self.assertTrue(ocr_calibration.is_tk_overlay_cleanup_complete())

    def test_destroy_failure_leaves_cleanup_incomplete(self):
        root = SimpleNamespace(
            quit=Mock(),
            attributes=Mock(),
            withdraw=Mock(),
            update_idletasks=Mock(),
            update=Mock(),
            destroy=Mock(side_effect=RuntimeError("destroy failed")),
        )
        with self.assertRaises(ocr_calibration.CalibrationCleanupFailed):
            ocr_calibration.cleanup_tk_overlay(root, sleep_fn=Mock())

        self.assertFalse(ocr_calibration.is_tk_overlay_cleanup_complete())


class MacSafeBrowseCalibrateAndDryRunTests(unittest.TestCase):
    def parse(self, *args):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", *args],
        ):
            return simple_brush.parse_args()

    def valid_args(self, **overrides):
        values = self.parse(
            "--mac-safe-browse-calibrate-and-dry-run",
            "--no-forward",
            "--max-candidates",
            "1",
            "--max-runtime-minutes",
            "5",
        )
        values.update(overrides)
        return values

    def diagnostics(self, **overrides):
        values = {
            "platform": "darwin",
            "pyautogui_size": (1440, 900),
            "pyautogui_position": (100, 120),
            "mss_monitors": (
                {"left": 0, "top": 0, "width": 2880, "height": 1800},
            ),
            "primary_monitor": {
                "left": 0,
                "top": 0,
                "width": 2880,
                "height": 1800,
            },
            "tk_version": "8.6",
            "tcl_version": "8.6",
            "display_fingerprint": "display-fingerprint",
            "passed": True,
            "message": "diagnostics ok",
            "error_code": None,
        }
        values.update(overrides)
        return simple_brush.ScreenCoordinateDiagnostics(**values)

    def capture_image(self, width=600, height=400, channels=3):
        return np.zeros((height, width, channels), dtype=np.uint8)

    def calibrated_region(self):
        metadata = simple_brush.CoordinateCalibrationMetadata(
            display_fingerprint="display-fingerprint",
            scale_inference=None,
            tk_to_screenshot_mapping=None,
            crop_preview=None,
            validated=True,
            manually_confirmed=True,
            message="validated for test",
        )
        return simple_brush.CalibratedScreenRegion(
            region=simple_brush.ScreenRegion(10, 20, 300, 200),
            coordinate_metadata=metadata,
        )

    def assert_argument_error(self, error_code, args, *, platform="darwin"):
        with self.assertRaises(simple_brush.MacSafeBrowseArgumentError) as caught:
            simple_brush.build_mac_safe_browse_calibrate_and_dry_run_config(
                args,
                platform_name=platform,
            )
        self.assertEqual(caught.exception.error_code, error_code)

    def test_parse_args_recognizes_calibrate_and_dry_run(self):
        defaults = self.parse()
        parsed = self.valid_args()

        self.assertFalse(defaults["mac_safe_browse_calibrate_and_dry_run"])
        self.assertFalse(defaults["mac_safe_browse_real_capture_once"])
        self.assertTrue(parsed["mac_safe_browse_calibrate_and_dry_run"])
        self.assertEqual(parsed["max_candidates"], 1)
        self.assertEqual(parsed["max_runtime_minutes"], 5)

    def test_parse_args_recognizes_real_capture_once(self):
        parsed = self.parse(
            "--mac-safe-browse-calibrate-and-dry-run",
            "--mac-safe-browse-real-capture-once",
            "--no-forward",
            "--max-candidates",
            "1",
            "--max-runtime-minutes",
            "5",
        )

        self.assertTrue(parsed["mac_safe_browse_calibrate_and_dry_run"])
        self.assertTrue(parsed["mac_safe_browse_real_capture_once"])

    def test_parse_args_recognizes_open_candidate_once(self):
        parsed = self.parse(
            "--mac-safe-browse-calibrate-and-dry-run",
            "--mac-safe-browse-open-candidate-once",
            "--no-forward",
            "--max-candidates",
            "1",
            "--max-runtime-minutes",
            "5",
        )

        self.assertTrue(parsed["mac_safe_browse_calibrate_and_dry_run"])
        self.assertTrue(parsed["mac_safe_browse_open_candidate_once"])

    def test_parse_args_rejects_calibrate_and_dry_run_conflicts(self):
        for conflicting_flag in (
            "--mac-safe-browse-only",
            "--mac-safe-browse-calibrate-only",
            "--preflight-only",
            "--coordinate-diagnostics-only",
            "--auto",
        ):
            with self.subTest(conflicting_flag=conflicting_flag):
                with self.assertRaises(
                    simple_brush.MacSafeBrowseArgumentError
                ) as caught:
                    self.parse(
                        "--mac-safe-browse-calibrate-and-dry-run",
                        "--no-forward",
                        "--max-candidates",
                        "1",
                        "--max-runtime-minutes",
                        "5",
                        conflicting_flag,
                    )
                self.assertEqual(
                    caught.exception.error_code,
                    "MAC_SAFE_BROWSE_CALIBRATE_AND_DRY_RUN_CONFLICTING_MODE",
                )

    def test_parse_args_rejects_real_capture_once_without_combo_mode(self):
        with self.assertRaises(simple_brush.MacSafeBrowseArgumentError) as caught:
            self.parse("--mac-safe-browse-real-capture-once")
        self.assertEqual(
            caught.exception.error_code,
            "MAC_SAFE_BROWSE_REAL_CAPTURE_CONFLICTING_MODE",
        )

    def test_parse_args_rejects_open_candidate_once_without_combo_mode(self):
        with self.assertRaises(simple_brush.MacSafeBrowseArgumentError) as caught:
            self.parse("--mac-safe-browse-open-candidate-once")
        self.assertEqual(
            caught.exception.error_code,
            "MAC_SAFE_BROWSE_OPEN_CANDIDATE_CONFLICTING_MODE",
        )

    def test_candidate_open_point_requires_explicit_yes(self):
        with self.assertRaises(simple_brush.MacSafeBrowseRuntimeError) as caught:
            simple_brush.get_mac_safe_browse_candidate_open_point(
                confirm_fn=Mock(return_value="NO"),
                position_fn=Mock(return_value=(10, 20)),
            )
        self.assertEqual(
            caught.exception.error_code,
            "MAC_SAFE_BROWSE_CANDIDATE_OPEN_CONFIRMATION_REQUIRED",
        )

    def test_candidate_open_point_returns_current_mouse_coordinates(self):
        point = simple_brush.get_mac_safe_browse_candidate_open_point(
            confirm_fn=Mock(return_value="YES"),
            position_fn=Mock(return_value=SimpleNamespace(x=123, y=456)),
            sleep_fn=Mock(),
        )

        self.assertEqual(point, (123, 456))

    def test_candidate_open_point_waits_before_reading_position(self):
        order = []

        def sleep_fn(seconds):
            order.append(("sleep", seconds))

        def position_fn():
            order.append(("position", None))
            return SimpleNamespace(x=123, y=456)

        point = simple_brush.get_mac_safe_browse_candidate_open_point(
            confirm_fn=Mock(return_value="YES"),
            position_fn=position_fn,
            sleep_fn=sleep_fn,
            countdown_seconds=5,
        )

        self.assertEqual(point, (123, 456))
        self.assertEqual(order, [("sleep", 5), ("position", None)])

    def test_candidate_open_point_position_failure_is_fail_closed(self):
        with self.assertRaises(simple_brush.MacSafeBrowseRuntimeError) as caught:
            simple_brush.get_mac_safe_browse_candidate_open_point(
                confirm_fn=Mock(return_value="YES"),
                position_fn=Mock(side_effect=RuntimeError("pos boom")),
                sleep_fn=Mock(),
            )
        self.assertEqual(
            caught.exception.error_code,
            "MAC_SAFE_BROWSE_CANDIDATE_OPEN_POINT_UNAVAILABLE",
        )

    def test_config_rejects_platform_no_forward_email_and_missing_limits(self):
        self.assert_argument_error(
            "MAC_SAFE_BROWSE_UNSUPPORTED_PLATFORM",
            self.valid_args(),
            platform="win32",
        )
        self.assert_argument_error(
            "MAC_SAFE_BROWSE_NO_FORWARD_REQUIRED",
            self.valid_args(no_forward=False),
        )
        self.assert_argument_error(
            "MAC_SAFE_BROWSE_FORWARDING_EMAIL_PRESENT",
            self.valid_args(email="forward@example.com"),
        )
        for field_name, value in (
            ("max_candidates", None),
            ("max_runtime_minutes", None),
        ):
            with self.subTest(field_name=field_name):
                self.assert_argument_error(
                    "MAC_SAFE_BROWSE_LIMIT_INVALID",
                    self.valid_args(**{field_name: value}),
                )

    def test_config_rejects_open_candidate_once_limit_constraints(self):
        self.assert_argument_error(
            "MAC_SAFE_BROWSE_OPEN_CANDIDATE_LIMIT_INVALID",
            self.valid_args(mac_safe_browse_open_candidate_once=True, max_candidates=2),
        )
        self.assert_argument_error(
            "MAC_SAFE_BROWSE_OPEN_CANDIDATE_LIMIT_INVALID",
            self.valid_args(
                mac_safe_browse_open_candidate_once=True,
                max_runtime_minutes=6,
            ),
        )

    def test_calibration_failure_stops_before_dry_pipeline(self):
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch("builtins.print") as print_output,
            patch.object(
                simple_brush,
                "run_mac_safe_browse_dry_pipeline",
            ) as dry_pipeline,
        ):
            result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                self.valid_args(),
                diagnostics_fn=Mock(
                    return_value=self.diagnostics(passed=False, message="diag fail")
                ),
            )

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIn("calibration_published: False", rendered)
        self.assertIn("MAC_SAFE_BROWSE_CALIBRATION_DIAGNOSTICS_FAILED", rendered)
        dry_pipeline.assert_not_called()

    def test_overlay_not_closed_stops_before_capture_confirmation_and_candidate(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        capture_fn = Mock(return_value=self.capture_image())
        confirmation_fn = Mock(return_value="YES")
        candidate_open_fn = Mock(return_value=True)
        blocked_names = (
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
        )
        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "platform", "darwin"))
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["OCRKeywordDetector.detect"] = stack.enter_context(
                patch.object(simple_brush.OCRKeywordDetector, "detect")
            )
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            dry_pipeline = stack.enter_context(
                patch.object(simple_brush, "run_mac_safe_browse_dry_pipeline")
            )
            print_output = stack.enter_context(patch("builtins.print"))
            result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                self.valid_args(
                    mac_safe_browse_real_capture_once=True,
                    mac_safe_browse_open_candidate_once=True,
                ),
                diagnostics_fn=Mock(return_value=self.diagnostics()),
                select_region_fn=Mock(return_value=region),
                overlay_cleanup_check_fn=Mock(return_value=False),
                capture_fn=capture_fn,
                confirmation_fn=confirmation_fn,
                candidate_open_fn=candidate_open_fn,
            )

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIn("MAC_SAFE_BROWSE_CALIBRATION_OVERLAY_NOT_CLOSED", rendered)
        capture_fn.assert_not_called()
        confirmation_fn.assert_not_called()
        candidate_open_fn.assert_not_called()
        dry_pipeline.assert_not_called()
        for mocked in blocked.values():
            mocked.assert_not_called()

    def test_overlay_cleanup_check_exception_fails_closed(self):
        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            diagnostics_fn=Mock(return_value=self.diagnostics()),
            select_region_fn=Mock(
                return_value=simple_brush.ScreenRegion(10, 20, 300, 200)
            ),
            overlay_cleanup_check_fn=Mock(
                side_effect=RuntimeError("cleanup state unavailable")
            ),
            capture_fn=Mock(),
            confirmation_fn=Mock(),
        )

        self.assertFalse(result.published)
        self.assertFalse(result.overlay_cleanup_completed)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_TK_CLEANUP_FAILED",
        )

    def test_selector_cleanup_failure_is_reported_and_stops_calibration(self):
        capture_fn = Mock()
        confirmation_fn = Mock()

        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            diagnostics_fn=Mock(return_value=self.diagnostics()),
            select_region_fn=Mock(
                side_effect=ocr_calibration.CalibrationCleanupFailed(
                    "destroy failed"
                )
            ),
            capture_fn=capture_fn,
            confirmation_fn=confirmation_fn,
        )

        self.assertFalse(result.published)
        self.assertFalse(result.overlay_cleanup_completed)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_TK_CLEANUP_FAILED",
        )
        capture_fn.assert_not_called()
        confirmation_fn.assert_not_called()

    def test_candidate_open_requires_overlay_cleanup_evidence(self):
        candidate_open_fn = Mock(return_value=True)
        action_fns, build_result = simple_brush.build_mac_safe_browse_real_action_fns(
            self.calibrated_region(),
            candidate_open_fn=candidate_open_fn,
            open_candidate_once=True,
            overlay_cleanup_completed=False,
        )

        succeeded = action_fns["candidate_open"]()
        result = build_result()

        self.assertFalse(succeeded)
        candidate_open_fn.assert_not_called()
        self.assertFalse(result.candidate_open_attempted)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_OVERLAY_NOT_CLOSED",
        )

    def test_success_runs_dry_pipeline_but_still_returns_not_implemented(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        captured = self.capture_image(width=600, height=400)
        blocked_names = (
            "prepare_browser",
            "run_mac_safe_browse_only",
            "initialize_ocr",
            "ensure_ocr_region_calibrated",
            "save_region_preview",
            "human_click",
            "click_in_region",
            "click_first_candidate",
            "apply_batch_filter_and_open_first_candidate",
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
        )
        pyautogui_names = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "platform", "darwin"))
            stack.enter_context(
                patch.object(simple_brush, "ocr_calibrated_region", None)
            )
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["OCRKeywordDetector"] = stack.enter_context(
                patch.object(simple_brush, "OCRKeywordDetector")
            )
            blocked["OCRKeywordDetector.detect"] = stack.enter_context(
                patch.object(simple_brush.OCRKeywordDetector, "detect")
            )
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            print_output = stack.enter_context(patch("builtins.print"))
            result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                self.valid_args(),
                diagnostics_fn=Mock(return_value=self.diagnostics()),
                select_region_fn=Mock(return_value=region),
                capture_fn=Mock(return_value=captured),
                save_crop_preview_fn=Mock(
                    return_value=simple_brush.CropPreviewResult(
                        saved=True,
                        preview_path=(
                            "logs/macos-coordinate-diagnostics/mock/"
                            "crop_preview.png"
                        ),
                        crop_size=(600, 400),
                        message="saved",
                    )
                ),
                confirmation_fn=Mock(return_value="YES"),
                preview_dir="logs/macos-coordinate-diagnostics/mock",
            )
            published = simple_brush.ocr_calibrated_region

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIsInstance(published, simple_brush.CalibratedScreenRegion)
        self.assertTrue(published.coordinate_metadata.validated)
        self.assertTrue(published.coordinate_metadata.manually_confirmed)
        self.assertFalse(published.coordinate_metadata.business_ready)
        self.assertIn("calibration_published: True", rendered)
        self.assertIn("dry_pipeline_completed: True", rendered)
        self.assertIn("real_browsing_enabled: False", rendered)
        self.assertIn("forwarding_enabled: False", rendered)
        self.assertIn("MAC_SAFE_BROWSE_BROWSE_LOOP_NOT_IMPLEMENTED", rendered)
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()

    def test_real_capture_once_keeps_noop_path_off_when_flag_is_missing(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        captured = self.capture_image(width=600, height=400)
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(simple_brush, "ocr_calibrated_region", None),
            patch.object(
                simple_brush,
                "build_mac_safe_browse_real_action_fns",
            ) as build_actions,
            patch("builtins.print") as print_output,
        ):
            result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                self.valid_args(),
                diagnostics_fn=Mock(return_value=self.diagnostics()),
                select_region_fn=Mock(return_value=region),
                capture_fn=Mock(return_value=captured),
                save_crop_preview_fn=Mock(
                    return_value=simple_brush.CropPreviewResult(
                        saved=True,
                        preview_path=(
                            "logs/macos-coordinate-diagnostics/mock/"
                            "crop_preview.png"
                        ),
                        crop_size=(600, 400),
                        message="saved",
                    )
                ),
                confirmation_fn=Mock(return_value="YES"),
                preview_dir="logs/macos-coordinate-diagnostics/mock",
            )

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIn("real_capture_enabled: False", rendered)
        self.assertIn("candidate_open_enabled: False", rendered)
        self.assertIn("capture_completed: False", rendered)
        build_actions.assert_not_called()

    def test_real_capture_once_success_records_capture_size_without_saving_or_ocr(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        captured = self.capture_image(width=600, height=400)
        blocked_names = (
            "prepare_browser",
            "run_mac_safe_browse_only",
            "initialize_ocr",
            "ensure_ocr_region_calibrated",
            "save_region_preview",
            "human_click",
            "click_in_region",
            "click_first_candidate",
            "apply_batch_filter_and_open_first_candidate",
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
        )
        pyautogui_names = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        class CaptureStub:
            def capture(self, selected_region):
                self.selected_region = selected_region
                return captured

        capture_instance = CaptureStub()
        capture_factory = Mock(return_value=capture_instance)
        focus_fn = Mock(return_value=True)

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "platform", "darwin"))
            stack.enter_context(
                patch.object(simple_brush, "ocr_calibrated_region", None)
            )
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["OCRKeywordDetector"] = stack.enter_context(
                patch.object(simple_brush, "OCRKeywordDetector")
            )
            blocked["OCRKeywordDetector.detect"] = stack.enter_context(
                patch.object(simple_brush.OCRKeywordDetector, "detect")
            )
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            print_output = stack.enter_context(patch("builtins.print"))
            result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                self.valid_args(mac_safe_browse_real_capture_once=True),
                diagnostics_fn=Mock(return_value=self.diagnostics()),
                select_region_fn=Mock(return_value=region),
                capture_fn=Mock(return_value=captured),
                save_crop_preview_fn=Mock(
                    return_value=simple_brush.CropPreviewResult(
                        saved=True,
                        preview_path=(
                            "logs/macos-coordinate-diagnostics/mock/"
                            "crop_preview.png"
                        ),
                        crop_size=(600, 400),
                        message="saved",
                    )
                ),
                confirmation_fn=Mock(return_value="YES"),
                preview_dir="logs/macos-coordinate-diagnostics/mock",
                real_capture_focus_fn=focus_fn,
                real_capture_factory=capture_factory,
            )

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertEqual(capture_instance.selected_region, region)
        self.assertIn("real_capture_enabled: True", rendered)
        self.assertIn("capture_completed: True", rendered)
        self.assertIn("capture_size: (600, 400)", rendered)
        self.assertIn("real_browsing_enabled: False", rendered)
        self.assertIn("forwarding_enabled: False", rendered)
        self.assertIn("MAC_SAFE_BROWSE_BROWSE_LOOP_NOT_IMPLEMENTED", rendered)
        focus_fn.assert_called_once_with()
        capture_factory.assert_called_once_with()
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()

    def test_trial_plan_adds_candidate_open_only_when_enabled(self):
        config = simple_brush.build_mac_safe_browse_calibrate_and_dry_run_config(
            self.valid_args(),
            platform_name="darwin",
        )

        default_actions = tuple(
            step.action
            for step in simple_brush.build_mac_safe_browse_trial_plan(
                config,
                open_candidate_once=False,
            )
        )
        open_actions = tuple(
            step.action
            for step in simple_brush.build_mac_safe_browse_trial_plan(
                config,
                open_candidate_once=True,
            )
        )

        self.assertEqual(default_actions, ("focus_restore", "ocr_capture"))
        self.assertEqual(
            open_actions,
            ("focus_restore", "ocr_capture", "candidate_open"),
        )
        for forbidden in ("scroll", "next_candidate", "refresh", "filter_click", "forward"):
            self.assertNotIn(forbidden, open_actions)

    def test_real_capture_once_focus_failure_stops_pipeline(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        captured = self.capture_image(width=600, height=400)
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(simple_brush, "ocr_calibrated_region", None),
            patch("builtins.print") as print_output,
        ):
            result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                self.valid_args(mac_safe_browse_real_capture_once=True),
                diagnostics_fn=Mock(return_value=self.diagnostics()),
                select_region_fn=Mock(return_value=region),
                capture_fn=Mock(return_value=captured),
                save_crop_preview_fn=Mock(
                    return_value=simple_brush.CropPreviewResult(
                        saved=True,
                        preview_path=(
                            "logs/macos-coordinate-diagnostics/mock/"
                            "crop_preview.png"
                        ),
                        crop_size=(600, 400),
                        message="saved",
                    )
                ),
                confirmation_fn=Mock(return_value="YES"),
                preview_dir="logs/macos-coordinate-diagnostics/mock",
                real_capture_focus_fn=Mock(return_value=False),
                real_capture_factory=Mock(),
            )

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIn("real_capture_enabled: True", rendered)
        self.assertIn("dry_pipeline_completed: False", rendered)
        self.assertIn("MAC_SAFE_BROWSE_REAL_FOCUS_FAILED", rendered)

    def test_real_capture_once_empty_or_exception_capture_fails_closed(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        base_kwargs = {
            "diagnostics_fn": Mock(return_value=self.diagnostics()),
            "select_region_fn": Mock(return_value=region),
            "capture_fn": Mock(return_value=self.capture_image(width=600, height=400)),
            "save_crop_preview_fn": Mock(
                return_value=simple_brush.CropPreviewResult(
                    saved=True,
                    preview_path=(
                        "logs/macos-coordinate-diagnostics/mock/crop_preview.png"
                    ),
                    crop_size=(600, 400),
                    message="saved",
                )
            ),
            "confirmation_fn": Mock(return_value="YES"),
            "preview_dir": "logs/macos-coordinate-diagnostics/mock",
            "real_capture_focus_fn": Mock(return_value=True),
        }

        class EmptyCapture:
            def capture(self, _region):
                return None

        class ExplodingCapture:
            def capture(self, _region):
                raise RuntimeError("capture boom")

        cases = (
            (Mock(return_value=EmptyCapture()), "MAC_SAFE_BROWSE_REAL_CAPTURE_EMPTY"),
            (Mock(return_value=ExplodingCapture()), "MAC_SAFE_BROWSE_REAL_CAPTURE_FAILED"),
        )
        for capture_factory, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with (
                    patch.object(simple_brush.sys, "platform", "darwin"),
                    patch.object(simple_brush, "ocr_calibrated_region", None),
                    patch("builtins.print") as print_output,
                ):
                    result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                        self.valid_args(mac_safe_browse_real_capture_once=True),
                        real_capture_factory=capture_factory,
                        **base_kwargs,
                    )

                rendered = "\n".join(
                    " ".join(str(item) for item in entry.args)
                    for entry in print_output.call_args_list
                )
                self.assertEqual(result, 2)
                self.assertIn("dry_pipeline_completed: False", rendered)
                self.assertIn(expected_code, rendered)

    def test_open_candidate_once_success_records_candidate_opened_without_loop(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        captured = self.capture_image(width=600, height=400)
        blocked_names = (
            "prepare_browser",
            "run_mac_safe_browse_only",
            "initialize_ocr",
            "ensure_ocr_region_calibrated",
            "save_region_preview",
            "human_click",
            "click_in_region",
            "click_first_candidate",
            "view_candidate",
            "apply_batch_filter_and_open_first_candidate",
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
        )
        pyautogui_names = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        class CaptureStub:
            def capture(self, selected_region):
                self.selected_region = selected_region
                return captured

        capture_instance = CaptureStub()
        capture_factory = Mock(return_value=capture_instance)
        focus_fn = Mock(return_value=True)
        candidate_open_fn = Mock(return_value=True)

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "platform", "darwin"))
            stack.enter_context(
                patch.object(simple_brush, "ocr_calibrated_region", None)
            )
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["OCRKeywordDetector"] = stack.enter_context(
                patch.object(simple_brush, "OCRKeywordDetector")
            )
            blocked["OCRKeywordDetector.detect"] = stack.enter_context(
                patch.object(simple_brush.OCRKeywordDetector, "detect")
            )
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            print_output = stack.enter_context(patch("builtins.print"))
            result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                self.valid_args(
                    mac_safe_browse_real_capture_once=True,
                    mac_safe_browse_open_candidate_once=True,
                ),
                diagnostics_fn=Mock(return_value=self.diagnostics()),
                select_region_fn=Mock(return_value=region),
                capture_fn=Mock(return_value=captured),
                save_crop_preview_fn=Mock(
                    return_value=simple_brush.CropPreviewResult(
                        saved=True,
                        preview_path=(
                            "logs/macos-coordinate-diagnostics/mock/"
                            "crop_preview.png"
                        ),
                        crop_size=(600, 400),
                        message="saved",
                    )
                ),
                confirmation_fn=Mock(return_value="YES"),
                preview_dir="logs/macos-coordinate-diagnostics/mock",
                real_capture_focus_fn=focus_fn,
                real_capture_factory=capture_factory,
                candidate_open_fn=candidate_open_fn,
            )

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertEqual(capture_instance.selected_region, region)
        self.assertIn("real_capture_enabled: True", rendered)
        self.assertIn("candidate_open_enabled: True", rendered)
        self.assertIn("capture_completed: True", rendered)
        self.assertIn("capture_size: (600, 400)", rendered)
        self.assertIn("candidate_open_count: 1", rendered)
        self.assertIn("candidate_open_attempted: True", rendered)
        self.assertIn("candidate_open_verified: False", rendered)
        self.assertIn("candidate_opened: False", rendered)
        self.assertIn("browse_loop_enabled: False", rendered)
        self.assertIn("forwarding_enabled: False", rendered)
        self.assertIn("MAC_SAFE_BROWSE_BROWSE_LOOP_NOT_IMPLEMENTED", rendered)
        focus_fn.assert_called_once_with()
        capture_factory.assert_called_once_with()
        candidate_open_fn.assert_called_once_with()
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()

    def test_open_candidate_once_default_path_reads_point_and_clicks_once(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        captured = self.capture_image(width=600, height=400)
        blocked_names = (
            "prepare_browser",
            "run_mac_safe_browse_only",
            "initialize_ocr",
            "ensure_ocr_region_calibrated",
            "save_region_preview",
            "view_candidate",
            "apply_batch_filter_and_open_first_candidate",
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
        )
        pyautogui_names = (
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        class CaptureStub:
            def capture(self, selected_region):
                self.selected_region = selected_region
                return captured

        capture_instance = CaptureStub()
        capture_factory = Mock(return_value=capture_instance)
        click_first_candidate = Mock(return_value=True)
        candidate_focus_fn = Mock(
            return_value=simple_brush.MacOSChromeFocusResult(
                platform="macos",
                browser="chrome",
                activated=True,
                frontmost=True,
                message="focus ok",
            )
        )
        sleep_fn = Mock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "platform", "darwin"))
            stack.enter_context(
                patch.object(simple_brush, "ocr_calibrated_region", None)
            )
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["OCRKeywordDetector"] = stack.enter_context(
                patch.object(simple_brush, "OCRKeywordDetector")
            )
            blocked["OCRKeywordDetector.detect"] = stack.enter_context(
                patch.object(simple_brush.OCRKeywordDetector, "detect")
            )
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked["click_first_candidate"] = stack.enter_context(
                patch.object(simple_brush, "click_first_candidate", click_first_candidate)
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            print_output = stack.enter_context(patch("builtins.print"))
            result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                self.valid_args(
                    mac_safe_browse_real_capture_once=True,
                    mac_safe_browse_open_candidate_once=True,
                ),
                diagnostics_fn=Mock(return_value=self.diagnostics()),
                select_region_fn=Mock(return_value=region),
                capture_fn=Mock(return_value=captured),
                save_crop_preview_fn=Mock(
                    return_value=simple_brush.CropPreviewResult(
                        saved=True,
                        preview_path=(
                            "logs/macos-coordinate-diagnostics/mock/"
                            "crop_preview.png"
                        ),
                        crop_size=(600, 400),
                        message="saved",
                    )
                ),
                confirmation_fn=Mock(return_value="YES"),
                preview_dir="logs/macos-coordinate-diagnostics/mock",
                real_capture_focus_fn=Mock(return_value=True),
                real_capture_factory=capture_factory,
                candidate_focus_fn=candidate_focus_fn,
                candidate_open_confirm_fn=Mock(return_value="YES"),
                candidate_open_position_fn=Mock(
                    return_value=SimpleNamespace(x=321, y=654)
                ),
                candidate_open_sleep_fn=sleep_fn,
                candidate_open_countdown_seconds=5,
            )

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertEqual(capture_instance.selected_region, region)
        self.assertIn("candidate_open_enabled: True", rendered)
        self.assertIn("candidate_open_count: 1", rendered)
        self.assertIn("candidate_open_attempted: True", rendered)
        self.assertIn("candidate_open_verified: False", rendered)
        self.assertIn("candidate_opened: False", rendered)
        self.assertIn("MAC_SAFE_BROWSE_BROWSE_LOOP_NOT_IMPLEMENTED", rendered)
        sleep_fn.assert_called_once_with(5)
        candidate_focus_fn.assert_called_once_with()
        click_first_candidate.assert_called_once_with(321, 654)
        for name, mocked in blocked.items():
            if name == "click_first_candidate":
                continue
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()

    def test_open_candidate_once_default_path_confirmation_focus_or_click_failure_fails_closed(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        base_kwargs = {
            "diagnostics_fn": Mock(return_value=self.diagnostics()),
            "select_region_fn": Mock(return_value=region),
            "capture_fn": Mock(return_value=self.capture_image(width=600, height=400)),
            "save_crop_preview_fn": Mock(
                return_value=simple_brush.CropPreviewResult(
                    saved=True,
                    preview_path=(
                        "logs/macos-coordinate-diagnostics/mock/crop_preview.png"
                    ),
                    crop_size=(600, 400),
                    message="saved",
                )
            ),
            "confirmation_fn": Mock(return_value="YES"),
            "preview_dir": "logs/macos-coordinate-diagnostics/mock",
            "real_capture_focus_fn": Mock(return_value=True),
            "real_capture_factory": Mock(
                return_value=type(
                    "CaptureStub",
                    (),
                    {"capture": lambda self, _region: self.capture_image},
                )()
            ),
            "candidate_open_position_fn": Mock(return_value=(50, 60)),
            "candidate_open_sleep_fn": Mock(),
            "candidate_open_countdown_seconds": 5,
        }
        base_kwargs["real_capture_factory"].return_value.capture_image = self.capture_image(
            width=600,
            height=400,
        )

        cases = (
            (
                Mock(return_value="NO"),
                Mock(),
                Mock(return_value=True),
                "MAC_SAFE_BROWSE_CANDIDATE_OPEN_CONFIRMATION_REQUIRED",
                False,
                False,
            ),
            (
                Mock(return_value="YES"),
                Mock(
                    return_value=simple_brush.MacOSChromeFocusResult(
                        platform="macos",
                        browser="chrome",
                        activated=True,
                        frontmost=False,
                        message="focus failed",
                        error_code="MACOS_CHROME_NOT_FRONTMOST",
                    )
                ),
                Mock(return_value=True),
                "MAC_SAFE_BROWSE_CANDIDATE_OPEN_FOCUS_FAILED",
                False,
                True,
            ),
            (
                Mock(return_value="YES"),
                Mock(return_value=True),
                Mock(side_effect=RuntimeError("click boom")),
                "MAC_SAFE_BROWSE_CANDIDATE_OPEN_FAILED",
                True,
                True,
            ),
        )
        for (
            confirm_fn,
            focus_mock,
            click_mock,
            expected_code,
            should_call_click,
            should_call_focus,
        ) in cases:
            with self.subTest(expected_code=expected_code):
                with (
                    patch.object(simple_brush.sys, "platform", "darwin"),
                    patch.object(simple_brush, "ocr_calibrated_region", None),
                    patch.object(simple_brush, "click_first_candidate", click_mock),
                    patch("builtins.print") as print_output,
                ):
                    result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                        self.valid_args(
                            mac_safe_browse_real_capture_once=True,
                            mac_safe_browse_open_candidate_once=True,
                        ),
                        candidate_focus_fn=focus_mock,
                        candidate_open_confirm_fn=confirm_fn,
                        **base_kwargs,
                    )

                rendered = "\n".join(
                    " ".join(str(item) for item in entry.args)
                    for entry in print_output.call_args_list
                )
                self.assertEqual(result, 2)
                self.assertIn("dry_pipeline_completed: False", rendered)
                self.assertIn(expected_code, rendered)
                if should_call_focus:
                    focus_mock.assert_called_once_with()
                else:
                    focus_mock.assert_not_called()
                if should_call_click:
                    click_mock.assert_called_once_with(50, 60)
                else:
                    click_mock.assert_not_called()

    def test_open_candidate_once_false_or_exception_fails_closed(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        base_kwargs = {
            "diagnostics_fn": Mock(return_value=self.diagnostics()),
            "select_region_fn": Mock(return_value=region),
            "capture_fn": Mock(return_value=self.capture_image(width=600, height=400)),
            "save_crop_preview_fn": Mock(
                return_value=simple_brush.CropPreviewResult(
                    saved=True,
                    preview_path=(
                        "logs/macos-coordinate-diagnostics/mock/crop_preview.png"
                    ),
                    crop_size=(600, 400),
                    message="saved",
                )
            ),
            "confirmation_fn": Mock(return_value="YES"),
            "preview_dir": "logs/macos-coordinate-diagnostics/mock",
            "real_capture_focus_fn": Mock(return_value=True),
            "real_capture_factory": Mock(
                return_value=type(
                    "CaptureStub",
                    (),
                    {"capture": lambda self, _region: self.capture_image},
                )()
            ),
        }
        base_kwargs["real_capture_factory"].return_value.capture_image = self.capture_image(
            width=600,
            height=400,
        )

        cases = (
            (Mock(return_value=False), "MAC_SAFE_BROWSE_CANDIDATE_OPEN_FAILED"),
            (Mock(side_effect=RuntimeError("open boom")), "MAC_SAFE_BROWSE_CANDIDATE_OPEN_FAILED"),
        )
        for candidate_open_fn, expected_code in cases:
            with self.subTest(expected_code=expected_code):
                with (
                    patch.object(simple_brush.sys, "platform", "darwin"),
                    patch.object(simple_brush, "ocr_calibrated_region", None),
                    patch("builtins.print") as print_output,
                ):
                    result = simple_brush.run_mac_safe_browse_calibrate_and_dry_run(
                        self.valid_args(
                            mac_safe_browse_real_capture_once=True,
                            mac_safe_browse_open_candidate_once=True,
                        ),
                        candidate_open_fn=candidate_open_fn,
                        **base_kwargs,
                    )

                rendered = "\n".join(
                    " ".join(str(item) for item in entry.args)
                    for entry in print_output.call_args_list
                )
                self.assertEqual(result, 2)
                self.assertIn("dry_pipeline_completed: False", rendered)
                self.assertIn(expected_code, rendered)

    def test_open_candidate_once_budget_rejection_skips_action_fn(self):
        action_fn = Mock(return_value=True)
        budget = simple_brush.MacSafeBrowseActionBudget(
            max_candidates=1,
            max_runtime_seconds=300,
            max_candidate_open=0,
            max_scroll=0,
            max_next_candidate=0,
            max_refresh=0,
            max_filter_click=0,
            max_focus_restore=1,
            max_ocr_capture=1,
            max_forward=0,
        )
        result = simple_brush.execute_mac_safe_browse_action(
            budget,
            simple_brush.MacSafeBrowseActionState(started_at=0.0),
            "candidate_open",
            action_fn,
            now=1.0,
        )

        self.assertFalse(result.allowed)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_ACTION_LIMIT_REACHED",
        )
        action_fn.assert_not_called()

    def test_run_dispatches_calibrate_and_dry_run_before_normal_flow(self):
        argv = [
            "simple_brush.py",
            "--mac-safe-browse-calibrate-and-dry-run",
            "--no-forward",
            "--max-candidates",
            "1",
            "--max-runtime-minutes",
            "5",
        ]
        with (
            patch.object(simple_brush.sys, "argv", argv),
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(
                simple_brush,
                "run_mac_safe_browse_calibrate_and_dry_run",
                return_value=2,
            ) as combo_run,
            patch.object(simple_brush, "get_user_input") as get_user_input,
            patch.object(simple_brush, "run_mac_safe_browse_only") as safe_browse,
            patch.object(simple_brush, "run_mac_safe_browse_calibration_only") as calibrate_only,
            patch.object(simple_brush, "prepare_browser") as prepare_browser,
            patch.object(simple_brush.listener, "start") as listener_start,
        ):
            result = simple_brush.run()

        self.assertEqual(result, 2)
        combo_run.assert_called_once()
        get_user_input.assert_not_called()
        safe_browse.assert_not_called()
        calibrate_only.assert_not_called()
        prepare_browser.assert_not_called()
        listener_start.assert_not_called()

    def test_build_calibrate_and_dry_run_config_keeps_all_actions_disabled(self):
        config = simple_brush.build_mac_safe_browse_calibrate_and_dry_run_config(
            self.valid_args(),
            platform_name="darwin",
        )

        self.assertTrue(config.enabled)
        self.assertTrue(config.no_forward_required)
        self.assertEqual(config.max_candidates, 1)
        self.assertEqual(config.max_runtime_minutes, 5)
        self.assertTrue(config.require_page_allowed)
        self.assertTrue(config.require_coordinate_validated)
        self.assertTrue(config.require_manual_confirmation)
        self.assertFalse(config.allow_scroll)
        self.assertFalse(config.allow_next_candidate)
        self.assertFalse(config.allow_refresh)
        self.assertFalse(config.allow_filter)

    def test_run_dispatches_valid_safe_browse_before_normal_flow(self):
        argv = [
            "simple_brush.py",
            "--mac-safe-browse-only",
            "--no-forward",
            "--max-candidates",
            "1",
            "--max-runtime-minutes",
            "5",
        ]
        with (
            patch.object(simple_brush.sys, "argv", argv),
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(
                simple_brush,
                "run_mac_safe_browse_only",
                return_value=2,
            ) as safe_browse,
            patch.object(simple_brush, "get_user_input") as get_user_input,
            patch.object(simple_brush, "initialize_ocr") as initialize_ocr,
            patch.object(simple_brush.listener, "start") as listener_start,
            patch.object(simple_brush, "prepare_browser") as prepare_browser,
            patch.object(simple_brush, "run_preflight_only") as preflight,
            patch.object(
                simple_brush,
                "run_coordinate_diagnostics_only",
            ) as coordinate_diagnostics,
        ):
            result = simple_brush.run()

        self.assertEqual(result, 2)
        safe_browse.assert_called_once()
        get_user_input.assert_not_called()
        initialize_ocr.assert_not_called()
        listener_start.assert_not_called()
        prepare_browser.assert_not_called()
        preflight.assert_not_called()
        coordinate_diagnostics.assert_not_called()

    def test_valid_safe_browse_skeleton_is_not_implemented_and_has_no_side_effects(self):
        safe_browse_args = {
            "mac_safe_browse_only": True,
            "mac_safe_browse_calibrate_only": False,
            "mac_safe_browse_calibrate_and_dry_run": False,
            "no_forward": True,
            "auto": False,
            "preflight_only": False,
            "coordinate_diagnostics_only": False,
            "email": "",
            "max_candidates": 1,
            "max_runtime_minutes": 5,
        }
        blocked_names = (
            "get_user_input",
            "prepare_browser",
            "run_preflight_only",
            "capture_screen_coordinate_diagnostics",
            "run_coordinate_diagnostics_only",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
            "initialize_ocr",
            "select_screen_region",
            "save_region_preview",
            "MSSScreenCapture",
            "OCRKeywordDetector",
            "human_click",
            "click_in_region",
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
        )
        pyautogui_names = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )
        metadata = simple_brush.CoordinateCalibrationMetadata(
            display_fingerprint="display-fingerprint",
            scale_inference=None,
            tk_to_screenshot_mapping=None,
            crop_preview=None,
            validated=True,
            manually_confirmed=True,
            message="validated for test",
        )
        calibrated_region = simple_brush.CalibratedScreenRegion(
            region=simple_brush.ScreenRegion(10, 20, 300, 200),
            coordinate_metadata=metadata,
        )

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "platform", "darwin"))
            stack.enter_context(
                patch.object(
                    simple_brush,
                    "ocr_calibrated_region",
                    calibrated_region,
                )
            )
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            prompt = stack.enter_context(patch("builtins.input"))
            print_output = stack.enter_context(patch("builtins.print"))
            result = simple_brush.run_mac_safe_browse_only(safe_browse_args)

        self.assertEqual(result, 2)
        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertIn("NO FORWARDING ENABLED", rendered)
        self.assertIn("dry_pipeline_completed: True", rendered)
        self.assertIn("real_browsing_enabled: False", rendered)
        self.assertIn("forwarding_enabled: False", rendered)
        self.assertIn("MAC_SAFE_BROWSE_REAL_BROWSING_NOT_IMPLEMENTED", rendered)
        prompt.assert_not_called()
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()


class MacForwardUiSmokeTests(unittest.TestCase):
    def parse(self, *args):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", *args],
        ):
            return simple_brush.parse_args()

    def valid_args(self, **overrides):
        values = self.parse(
            "--mac-forward-ui-smoke-only",
            "--no-forward",
        )
        values.update(overrides)
        return values

    def assert_argument_error(self, error_code, args, *, platform="darwin"):
        with self.assertRaises(simple_brush.MacSafeBrowseArgumentError) as caught:
            simple_brush.build_mac_forward_ui_smoke_config(
                args,
                platform_name=platform,
            )
        self.assertEqual(caught.exception.error_code, error_code)

    def test_parse_args_recognizes_forward_ui_smoke_flags(self):
        defaults = self.parse()
        parsed = self.parse(
            "--mac-forward-ui-smoke-only",
            "--allow-invalid-forward-submit-smoke",
            "--no-forward",
        )

        self.assertFalse(defaults["mac_forward_ui_smoke_only"])
        self.assertFalse(defaults["allow_invalid_forward_submit_smoke"])
        self.assertTrue(parsed["mac_forward_ui_smoke_only"])
        self.assertTrue(parsed["allow_invalid_forward_submit_smoke"])

    def test_parse_args_rejects_forward_ui_smoke_conflicts(self):
        for conflicting_flag in (
            "--auto",
            "--preflight-only",
            "--coordinate-diagnostics-only",
            "--mac-safe-browse-only",
            "--mac-safe-browse-calibrate-only",
            "--mac-safe-browse-calibrate-and-dry-run",
        ):
            with self.subTest(conflicting_flag=conflicting_flag):
                with self.assertRaises(
                    simple_brush.MacSafeBrowseArgumentError
                ) as caught:
                    self.parse(
                        "--mac-forward-ui-smoke-only",
                        "--no-forward",
                        conflicting_flag,
                    )
                self.assertEqual(
                    caught.exception.error_code,
                    "MAC_FORWARD_UI_SMOKE_CONFLICTING_MODE",
                )
        with self.assertRaises(simple_brush.MacSafeBrowseArgumentError) as caught:
            self.parse("--allow-invalid-forward-submit-smoke")
        self.assertEqual(
            caught.exception.error_code,
            "MAC_FORWARD_UI_SMOKE_SUBMIT_CONFLICTING_MODE",
        )

    def test_build_forward_ui_smoke_config_rejects_platform_no_forward_and_email(self):
        self.assert_argument_error(
            "MAC_FORWARD_UI_SMOKE_UNSUPPORTED_PLATFORM",
            self.valid_args(),
            platform="win32",
        )
        self.assert_argument_error(
            "MAC_FORWARD_UI_SMOKE_NO_FORWARD_REQUIRED",
            self.valid_args(no_forward=False),
        )
        self.assert_argument_error(
            "MAC_FORWARD_UI_SMOKE_EMAIL_FORBIDDEN",
            self.valid_args(email="real@example.com"),
        )

    def test_forward_ui_smoke_point_waits_before_reading_position(self):
        order = []

        def sleep_fn(seconds):
            order.append(("sleep", seconds))

        def position_fn():
            order.append(("position", None))
            return SimpleNamespace(x=10, y=20)

        point = simple_brush.get_mac_forward_ui_smoke_point(
            action_label="filter_recent_unseen",
            instruction="mock instruction",
            confirm_fn=Mock(return_value="YES"),
            position_fn=position_fn,
            sleep_fn=sleep_fn,
            countdown_seconds=5,
        )

        self.assertEqual(point, (10, 20))
        self.assertEqual(order, [("sleep", 5), ("position", None)])

    def test_forward_ui_smoke_requires_explicit_confirmation(self):
        position_fn = Mock(return_value=(10, 20))
        with self.assertRaises(simple_brush.MacSafeBrowseRuntimeError) as caught:
            simple_brush.get_mac_forward_ui_smoke_point(
                action_label="filter_recent_unseen",
                instruction="mock instruction",
                confirm_fn=Mock(return_value="NO"),
                position_fn=position_fn,
                sleep_fn=Mock(),
            )
        self.assertEqual(
            caught.exception.error_code,
            "MAC_FORWARD_UI_SMOKE_CONFIRMATION_REQUIRED",
        )
        position_fn.assert_not_called()

    def test_forward_ui_smoke_success_runs_default_actions_once_without_submit(self):
        blocked_names = (
            "get_user_input",
            "prepare_browser",
            "run_preflight_only",
            "run_coordinate_diagnostics_only",
            "run_mac_safe_browse_only",
            "run_mac_safe_browse_calibration_only",
            "run_mac_safe_browse_calibrate_and_dry_run",
            "initialize_ocr",
            "forward_one_candidate",
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "apply_batch_filter_and_open_first_candidate",
            "OCRKeywordDetector",
        )
        click_fn = Mock()
        typewrite_fn = Mock()
        focus_fn = Mock(
            return_value=simple_brush.MacOSChromeFocusResult(
                platform="macos",
                browser="chrome",
                activated=True,
                frontmost=True,
                message="frontmost",
            )
        )
        position_fn = Mock(
            side_effect=[
                SimpleNamespace(x=10, y=20),
                SimpleNamespace(x=30, y=40),
                SimpleNamespace(x=50, y=60),
                SimpleNamespace(x=70, y=80),
            ]
        )
        confirm_fn = Mock(side_effect=["YES", "YES", "YES", "YES", "YES"])
        sleep_fn = Mock()

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "platform", "darwin"))
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            print_output = stack.enter_context(patch("builtins.print"))
            result = simple_brush.run_mac_forward_ui_smoke_only(
                self.valid_args(),
                focus_fn=focus_fn,
                click_fn=click_fn,
                typewrite_fn=typewrite_fn,
                position_fn=position_fn,
                confirm_fn=confirm_fn,
                sleep_fn=sleep_fn,
                now_fn=Mock(side_effect=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0]),
            )

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIn("filter_recent_unseen_attempted: True", rendered)
        self.assertIn("open_forward_modal_attempted: True", rendered)
        self.assertIn("focus_forward_email_field_attempted: True", rendered)
        self.assertIn("type_invalid_forward_email_attempted: True", rendered)
        self.assertIn("close_forward_modal_attempted: True", rendered)
        self.assertIn("forwarding_enabled: False", rendered)
        self.assertIn("invalid_submit_enabled: False", rendered)
        self.assertNotIn("submit_invalid_forward_attempted", rendered)
        click_fn.assert_has_calls(
            [
                unittest.mock.call(10, 20),
                unittest.mock.call(30, 40),
                unittest.mock.call(50, 60),
                unittest.mock.call(70, 80),
            ]
        )
        self.assertEqual(click_fn.call_count, 4)
        typewrite_fn.assert_called_once_with("invalid-test-address", interval=0.03)
        self.assertEqual(focus_fn.call_count, 5)
        self.assertEqual(sleep_fn.call_count, 4)
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()

    def test_forward_ui_smoke_unconfirmed_or_unfocused_fails_closed_before_click(self):
        base_kwargs = {
            "focus_fn": Mock(return_value=True),
            "click_fn": Mock(),
            "typewrite_fn": Mock(),
            "position_fn": Mock(return_value=(10, 20)),
            "sleep_fn": Mock(),
            "now_fn": Mock(side_effect=[100.0, 101.0, 102.0]),
        }
        cases = (
            (
                Mock(side_effect=["NO"]),
                base_kwargs["focus_fn"],
                "MAC_FORWARD_UI_SMOKE_CONFIRMATION_REQUIRED",
                False,
            ),
            (
                Mock(side_effect=["YES"]),
                Mock(
                    return_value=simple_brush.MacOSChromeFocusResult(
                        platform="macos",
                        browser="chrome",
                        activated=True,
                        frontmost=False,
                        message="not frontmost",
                    )
                ),
                "MAC_FORWARD_UI_SMOKE_CHROME_NOT_FRONTMOST",
                True,
            ),
        )
        for confirm_fn, focus_fn, expected_code, position_expected in cases:
            with self.subTest(expected_code=expected_code):
                click_fn = Mock()
                position_fn = Mock(return_value=(10, 20))
                with (
                    patch.object(simple_brush.sys, "platform", "darwin"),
                    patch("builtins.print") as print_output,
                ):
                    result = simple_brush.run_mac_forward_ui_smoke_only(
                        self.valid_args(),
                        focus_fn=focus_fn,
                        click_fn=click_fn,
                        typewrite_fn=Mock(),
                        position_fn=position_fn,
                        confirm_fn=confirm_fn,
                        sleep_fn=Mock(),
                        now_fn=Mock(side_effect=[100.0, 101.0, 102.0]),
                    )
                rendered = "\n".join(
                    " ".join(str(item) for item in entry.args)
                    for entry in print_output.call_args_list
                )
                self.assertEqual(result, 2)
                self.assertIn(expected_code, rendered)
                click_fn.assert_not_called()
                if position_expected:
                    position_fn.assert_called_once_with()
                else:
                    position_fn.assert_not_called()

    def test_invalid_submit_requires_explicit_flag_and_full_phrase(self):
        click_fn = Mock()
        focus_fn = Mock(return_value=True)
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch("builtins.print") as print_output,
        ):
            result = simple_brush.run_mac_forward_ui_smoke_only(
                self.valid_args(allow_invalid_forward_submit_smoke=True),
                focus_fn=focus_fn,
                click_fn=click_fn,
                typewrite_fn=Mock(),
                position_fn=Mock(
                    side_effect=[
                        (10, 20),
                        (30, 40),
                        (50, 60),
                        (70, 80),
                        (90, 100),
                    ]
                ),
                confirm_fn=Mock(side_effect=["YES", "YES", "YES", "YES", "YES"]),
                submit_confirm_fn=Mock(return_value="NOPE"),
                sleep_fn=Mock(),
                now_fn=Mock(
                    side_effect=[100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0]
                ),
            )
        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIn("submit_invalid_forward_attempted: False", rendered)
        self.assertIn(
            "submit_invalid_forward_error_code: MAC_FORWARD_UI_SMOKE_CONFIRMATION_REQUIRED",
            rendered,
        )
        self.assertEqual(click_fn.call_count, 4)

    def test_run_dispatches_forward_ui_smoke_before_normal_flow(self):
        argv = [
            "simple_brush.py",
            "--mac-forward-ui-smoke-only",
            "--no-forward",
        ]
        with (
            patch.object(simple_brush.sys, "argv", argv),
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(
                simple_brush,
                "run_mac_forward_ui_smoke_only",
                return_value=2,
            ) as smoke_run,
            patch.object(simple_brush, "get_user_input") as get_user_input,
            patch.object(simple_brush, "prepare_browser") as prepare_browser,
            patch.object(simple_brush.listener, "start") as listener_start,
        ):
            result = simple_brush.run()

        self.assertEqual(result, 2)
        smoke_run.assert_called_once()
        get_user_input.assert_not_called()
        prepare_browser.assert_not_called()
        listener_start.assert_not_called()


class MacSafeBrowseOcrEvidenceTests(unittest.TestCase):
    def make_metadata(self, **overrides):
        values = {
            "display_fingerprint": "display-fingerprint",
            "scale_inference": None,
            "tk_to_screenshot_mapping": None,
            "crop_preview": None,
            "validated": True,
            "manually_confirmed": True,
            "message": "validated for test",
        }
        values.update(overrides)
        return simple_brush.CoordinateCalibrationMetadata(**values)

    def make_region(self, metadata=None):
        if metadata is None:
            metadata = self.make_metadata()
        return simple_brush.CalibratedScreenRegion(
            region=simple_brush.ScreenRegion(10, 20, 300, 200),
            coordinate_metadata=metadata,
        )

    def safe_args(self):
        return {
            "mac_safe_browse_only": True,
            "no_forward": True,
            "max_candidates": 1,
            "max_runtime_minutes": 5,
            "auto": False,
            "preflight_only": False,
            "coordinate_diagnostics_only": False,
            "email": "",
        }

    def assert_evidence_failure(self, calibrated_region, error_code):
        evidence = simple_brush.collect_mac_safe_browse_ocr_evidence(
            calibrated_region
        )
        self.assertFalse(evidence.passed)
        self.assertEqual(evidence.error_code, error_code)
        return evidence

    def test_evidence_rejects_missing_calibrated_region(self):
        evidence = self.assert_evidence_failure(
            None,
            "MAC_SAFE_BROWSE_OCR_REGION_MISSING",
        )
        self.assertFalse(evidence.has_calibrated_region)
        self.assertFalse(evidence.has_coordinate_metadata)

    def test_evidence_rejects_missing_coordinate_metadata(self):
        region = simple_brush.CalibratedScreenRegion(
            region=simple_brush.ScreenRegion(10, 20, 300, 200),
            coordinate_metadata=None,
        )
        evidence = self.assert_evidence_failure(
            region,
            "MAC_SAFE_BROWSE_COORDINATE_METADATA_MISSING",
        )
        self.assertTrue(evidence.has_calibrated_region)
        self.assertFalse(evidence.has_coordinate_metadata)

    def test_evidence_rejects_unvalidated_or_unconfirmed_metadata(self):
        cases = (
            (
                {"validated": False},
                "MAC_SAFE_BROWSE_COORDINATE_NOT_VALIDATED",
            ),
            (
                {"manually_confirmed": False},
                "MAC_SAFE_BROWSE_PREVIEW_NOT_CONFIRMED",
            ),
        )
        for metadata_overrides, error_code in cases:
            with self.subTest(error_code=error_code):
                self.assert_evidence_failure(
                    self.make_region(self.make_metadata(**metadata_overrides)),
                    error_code,
                )

    def test_evidence_rejects_unexpected_business_ready(self):
        metadata = self.make_metadata()
        object.__setattr__(metadata, "business_ready", True)

        evidence = self.assert_evidence_failure(
            self.make_region(metadata),
            "MAC_SAFE_BROWSE_BUSINESS_READY_UNEXPECTED",
        )

        self.assertTrue(evidence.business_ready)

    def test_evidence_rejects_missing_display_fingerprint(self):
        for value in (None, "", "   "):
            with self.subTest(display_fingerprint=value):
                self.assert_evidence_failure(
                    self.make_region(
                        self.make_metadata(display_fingerprint=value)
                    ),
                    "MAC_SAFE_BROWSE_DISPLAY_FINGERPRINT_MISSING",
                )

    def test_complete_metadata_passes_read_only_evidence_check(self):
        evidence = simple_brush.collect_mac_safe_browse_ocr_evidence(
            self.make_region()
        )

        self.assertTrue(evidence.passed)
        self.assertTrue(evidence.has_calibrated_region)
        self.assertTrue(evidence.has_coordinate_metadata)
        self.assertTrue(evidence.coordinate_validated)
        self.assertTrue(evidence.manually_confirmed)
        self.assertFalse(evidence.business_ready)
        self.assertEqual(evidence.display_fingerprint, "display-fingerprint")
        self.assertIsNone(evidence.error_code)
        self.assertIn("不代表可浏览或业务 ready", evidence.message)

    def test_evidence_helper_has_no_runtime_or_io_side_effects(self):
        blocked_names = (
            "ensure_ocr_region_calibrated",
            "initialize_ocr",
            "select_screen_region",
            "save_region_preview",
            "prepare_browser",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
            "forward_one_candidate",
        )
        pyautogui_names = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        with ExitStack() as stack:
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["OCRKeywordDetector.detect"] = stack.enter_context(
                patch.object(simple_brush.OCRKeywordDetector, "detect")
            )
            blocked["MSSScreenCapture.capture"] = stack.enter_context(
                patch.object(simple_brush.MSSScreenCapture, "capture")
            )
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            evidence = simple_brush.collect_mac_safe_browse_ocr_evidence(
                self.make_region()
            )

        self.assertTrue(evidence.passed)
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()

    def test_run_safe_browse_reports_missing_ocr_region(self):
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(simple_brush, "ocr_calibrated_region", None),
            patch.object(
                simple_brush,
                "run_mac_safe_browse_dry_pipeline",
            ) as dry_pipeline,
            patch("builtins.print") as print_output,
        ):
            result = simple_brush.run_mac_safe_browse_only(self.safe_args())

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIn("MAC_SAFE_BROWSE_OCR_REGION_MISSING", rendered)
        self.assertNotIn("dry_pipeline_completed", rendered)
        dry_pipeline.assert_not_called()

    def test_run_safe_browse_with_complete_metadata_still_does_not_browse(self):
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(
                simple_brush,
                "ocr_calibrated_region",
                self.make_region(),
            ),
            patch.object(simple_brush, "prepare_browser") as prepare_browser,
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(
                simple_brush,
                "run_mac_safe_browse_dry_pipeline",
                wraps=simple_brush.run_mac_safe_browse_dry_pipeline,
            ) as dry_pipeline,
            patch.object(simple_brush.listener, "start") as listener_start,
            patch("builtins.print") as print_output,
        ):
            result = simple_brush.run_mac_safe_browse_only(self.safe_args())

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIn("NO FORWARDING ENABLED", rendered)
        self.assertIn("action_budget_ready: True", rendered)
        self.assertIn("dry_pipeline_completed: True", rendered)
        self.assertIn("real_browsing_enabled: False", rendered)
        self.assertIn("forwarding_enabled: False", rendered)
        self.assertIn("MAC_SAFE_BROWSE_REAL_BROWSING_NOT_IMPLEMENTED", rendered)
        prepare_browser.assert_not_called()
        forward.assert_not_called()
        dry_pipeline.assert_called_once()
        listener_start.assert_not_called()


class MacSafeBrowseActionBudgetTests(unittest.TestCase):
    def make_config(self, **overrides):
        values = {
            "enabled": True,
            "no_forward_required": True,
            "max_candidates": 5,
            "max_runtime_minutes": 15,
            "require_page_allowed": True,
            "require_coordinate_validated": True,
            "require_manual_confirmation": True,
        }
        values.update(overrides)
        return simple_brush.MacSafeBrowseConfig(**values)

    def make_budget(self):
        return simple_brush.build_default_mac_safe_browse_action_budget(
            self.make_config()
        )

    def make_state(self, **overrides):
        values = {"started_at": 100.0}
        values.update(overrides)
        return simple_brush.MacSafeBrowseActionState(**values)

    def test_default_budget_is_conservative_and_bounded_by_config(self):
        budget = self.make_budget()

        self.assertEqual(budget.max_candidates, 5)
        self.assertEqual(budget.max_runtime_seconds, 15 * 60)
        self.assertEqual(budget.max_candidate_open, 1)
        self.assertEqual(budget.max_scroll, 0)
        self.assertEqual(budget.max_next_candidate, 0)
        self.assertEqual(budget.max_refresh, 0)
        self.assertEqual(budget.max_filter_click, 0)
        self.assertEqual(budget.max_focus_restore, 1)
        self.assertEqual(budget.max_ocr_capture, 1)
        self.assertEqual(budget.max_forward, 0)

    def test_candidate_open_cannot_exceed_initial_limit_of_one(self):
        result = simple_brush.can_perform_mac_safe_browse_action(
            self.make_budget(),
            self.make_state(candidate_open=1),
            "candidate_open",
            now=101.0,
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.state.stopped)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_ACTION_LIMIT_REACHED",
        )

    def test_unknown_and_forward_actions_fail_closed(self):
        cases = (
            ("unknown", "MAC_SAFE_BROWSE_ACTION_UNKNOWN"),
            ("forward", "MAC_SAFE_BROWSE_FORWARDING_BLOCKED"),
        )
        for action, error_code in cases:
            with self.subTest(action=action):
                result = simple_brush.can_perform_mac_safe_browse_action(
                    self.make_budget(),
                    self.make_state(),
                    action,
                    now=101.0,
                )
                self.assertFalse(result.allowed)
                self.assertTrue(result.state.stopped)
                self.assertEqual(result.error_code, error_code)

    def test_already_stopped_state_rejects_every_action(self):
        state = self.make_state(
            stopped=True,
            stop_reason="first failure",
            error_code="FIRST_FAILURE",
        )
        result = simple_brush.can_perform_mac_safe_browse_action(
            self.make_budget(),
            state,
            "ocr_capture",
            now=101.0,
        )

        self.assertFalse(result.allowed)
        self.assertIs(result.state, state)
        self.assertEqual(result.error_code, "MAC_SAFE_BROWSE_ALREADY_STOPPED")
        self.assertEqual(result.state.stop_reason, "first failure")

    def test_runtime_limit_rejects_and_stops(self):
        budget = simple_brush.build_default_mac_safe_browse_action_budget(
            self.make_config(max_runtime_minutes=1)
        )
        result = simple_brush.can_perform_mac_safe_browse_action(
            budget,
            self.make_state(),
            "ocr_capture",
            now=160.0,
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.state.stopped)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_RUNTIME_LIMIT_REACHED",
        )

    def test_zero_budget_action_rejects_and_stops(self):
        result = simple_brush.reserve_mac_safe_browse_action(
            self.make_budget(),
            self.make_state(),
            "scroll",
            now=101.0,
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.state.stopped)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_ACTION_LIMIT_REACHED",
        )

    def test_reserve_success_does_not_increment_count(self):
        state = self.make_state()
        result = simple_brush.reserve_mac_safe_browse_action(
            self.make_budget(),
            state,
            "ocr_capture",
            now=101.0,
        )

        self.assertTrue(result.allowed)
        self.assertIs(result.state, state)
        self.assertEqual(result.state.ocr_capture, 0)

    def test_commit_success_increments_only_requested_count(self):
        state = self.make_state()
        committed = simple_brush.commit_mac_safe_browse_action_success(
            state,
            "focus_restore",
        )

        self.assertEqual(state.focus_restore, 0)
        self.assertEqual(committed.focus_restore, 1)
        self.assertEqual(committed.ocr_capture, 0)
        self.assertFalse(committed.stopped)

    def test_executor_success_commits_once(self):
        action_fn = Mock(return_value=True)
        result = simple_brush.execute_mac_safe_browse_action(
            self.make_budget(),
            self.make_state(),
            "ocr_capture",
            action_fn,
            now=101.0,
        )

        self.assertTrue(result.allowed)
        self.assertEqual(result.state.ocr_capture, 1)
        action_fn.assert_called_once_with()

    def test_executor_false_result_stops_without_retry(self):
        action_fn = Mock(return_value=False)
        result = simple_brush.execute_mac_safe_browse_action(
            self.make_budget(),
            self.make_state(),
            "ocr_capture",
            action_fn,
            now=101.0,
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.state.stopped)
        self.assertEqual(result.state.ocr_capture, 0)
        self.assertEqual(result.error_code, "MAC_SAFE_BROWSE_ACTION_FAILED")
        action_fn.assert_called_once_with()

    def test_executor_exception_stops_without_retry(self):
        action_fn = Mock(side_effect=RuntimeError("injected failure"))
        result = simple_brush.execute_mac_safe_browse_action(
            self.make_budget(),
            self.make_state(),
            "focus_restore",
            action_fn,
            now=101.0,
        )

        self.assertFalse(result.allowed)
        self.assertTrue(result.state.stopped)
        self.assertEqual(result.state.focus_restore, 0)
        self.assertEqual(result.error_code, "MAC_SAFE_BROWSE_ACTION_FAILED")
        action_fn.assert_called_once_with()

    def test_executor_budget_rejection_never_calls_action(self):
        action_fn = Mock(return_value=True)
        result = simple_brush.execute_mac_safe_browse_action(
            self.make_budget(),
            self.make_state(),
            "refresh",
            action_fn,
            now=101.0,
        )

        self.assertFalse(result.allowed)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_ACTION_LIMIT_REACHED",
        )
        action_fn.assert_not_called()


class MacSafeBrowseDryPipelineTests(unittest.TestCase):
    def make_config(self):
        return simple_brush.MacSafeBrowseConfig(
            enabled=True,
            no_forward_required=True,
            max_candidates=1,
            max_runtime_minutes=5,
            require_page_allowed=True,
            require_coordinate_validated=True,
            require_manual_confirmation=True,
        )

    def make_budget(self):
        return simple_brush.build_default_mac_safe_browse_action_budget(
            self.make_config()
        )

    def test_default_plan_contains_only_noop_budget_paths(self):
        plan = simple_brush.build_mac_safe_browse_dry_run_plan(
            self.make_config()
        )
        actions = tuple(step.action for step in plan)

        self.assertEqual(actions, ("focus_restore", "ocr_capture"))
        self.assertNotIn("candidate_open", actions)
        self.assertNotIn("scroll", actions)
        self.assertNotIn("next_candidate", actions)
        self.assertNotIn("refresh", actions)
        self.assertNotIn("filter_click", actions)
        self.assertNotIn("forward", actions)

    def test_dry_pipeline_success_commits_expected_counts(self):
        focus_noop = Mock(return_value=True)
        ocr_noop = Mock(return_value=True)
        result = simple_brush.run_mac_safe_browse_dry_pipeline(
            self.make_budget(),
            simple_brush.build_mac_safe_browse_dry_run_plan(self.make_config()),
            started_at=100.0,
            now=101.0,
            action_fns={
                "focus_restore": focus_noop,
                "ocr_capture": ocr_noop,
            },
        )

        self.assertTrue(result.completed)
        self.assertFalse(result.real_browsing_enabled)
        self.assertFalse(result.forwarding_enabled)
        self.assertEqual(result.state.focus_restore, 1)
        self.assertEqual(result.state.ocr_capture, 1)
        self.assertEqual(result.state.candidate_open, 0)
        self.assertEqual(result.state.forward, 0)
        self.assertIsNone(result.error_code)
        focus_noop.assert_called_once_with()
        ocr_noop.assert_called_once_with()

    def test_default_noop_pipeline_does_not_call_real_actions(self):
        blocked_names = (
            "prepare_browser",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
            "initialize_ocr",
            "ensure_ocr_region_calibrated",
            "select_screen_region",
            "save_region_preview",
            "human_click",
            "click_in_region",
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "click_first_candidate",
            "apply_batch_filter_and_open_first_candidate",
            "forward_one_candidate",
        )
        pyautogui_names = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        with ExitStack() as stack:
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["OCRKeywordDetector.detect"] = stack.enter_context(
                patch.object(simple_brush.OCRKeywordDetector, "detect")
            )
            blocked["MSSScreenCapture.capture"] = stack.enter_context(
                patch.object(simple_brush.MSSScreenCapture, "capture")
            )
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            result = simple_brush.run_mac_safe_browse_dry_pipeline(
                self.make_budget(),
                simple_brush.build_mac_safe_browse_dry_run_plan(
                    self.make_config()
                ),
                started_at=100.0,
                now=101.0,
            )

        self.assertTrue(result.completed)
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()

    def test_injected_false_or_exception_stops_pipeline(self):
        cases = (
            Mock(return_value=False),
            Mock(side_effect=RuntimeError("injected failure")),
        )
        plan = (
            simple_brush.MacSafeBrowseDryRunStep(
                action="focus_restore",
                description="injected failure test",
            ),
        )
        for action_fn in cases:
            with self.subTest(side_effect=action_fn.side_effect):
                result = simple_brush.run_mac_safe_browse_dry_pipeline(
                    self.make_budget(),
                    plan,
                    started_at=100.0,
                    now=101.0,
                    action_fns={"focus_restore": action_fn},
                )
                self.assertFalse(result.completed)
                self.assertFalse(result.real_browsing_enabled)
                self.assertFalse(result.forwarding_enabled)
                self.assertTrue(result.state.stopped)
                self.assertEqual(
                    result.error_code,
                    "MAC_SAFE_BROWSE_ACTION_FAILED",
                )
                action_fn.assert_called_once_with()

    def test_budget_rejection_does_not_call_injected_action(self):
        action_fn = Mock(return_value=True)
        budget = replace(self.make_budget(), max_focus_restore=0)
        plan = (
            simple_brush.MacSafeBrowseDryRunStep(
                action="focus_restore",
                description="zero budget test",
            ),
        )
        result = simple_brush.run_mac_safe_browse_dry_pipeline(
            budget,
            plan,
            started_at=100.0,
            now=101.0,
            action_fns={"focus_restore": action_fn},
        )

        self.assertFalse(result.completed)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_ACTION_LIMIT_REACHED",
        )
        action_fn.assert_not_called()

    def test_forward_step_is_hard_blocked_before_action_fn(self):
        action_fn = Mock(return_value=True)
        plan = (
            simple_brush.MacSafeBrowseDryRunStep(
                action="forward",
                description="must never run",
            ),
        )
        result = simple_brush.run_mac_safe_browse_dry_pipeline(
            self.make_budget(),
            plan,
            started_at=100.0,
            now=101.0,
            action_fns={"forward": action_fn},
        )

        self.assertFalse(result.completed)
        self.assertFalse(result.real_browsing_enabled)
        self.assertFalse(result.forwarding_enabled)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_FORWARDING_BLOCKED",
        )
        action_fn.assert_not_called()


class MacSafeBrowseCalibrationOnlyTests(unittest.TestCase):
    def parse(self, *args):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", *args],
        ):
            return simple_brush.parse_args()

    def args(self, **overrides):
        values = {
            "mac_safe_browse_calibrate_only": True,
            "mac_safe_browse_only": False,
            "no_forward": True,
            "auto": False,
            "preflight_only": False,
            "coordinate_diagnostics_only": False,
            "email": "",
            "max_candidates": None,
            "max_runtime_minutes": None,
        }
        values.update(overrides)
        return values

    def scale(self, passed=True):
        return simple_brush.RetinaScaleInference(
            request_size=(100, 80),
            image_size=(200, 160),
            scale_x=2.0,
            scale_y=2.0,
            passed=passed,
            message="scale test evidence",
            error_code=None if passed else "SCALE_FAILED",
        )

    def mapping(self, passed=True):
        selection = simple_brush.TkSelectionRegion(10, 10, 40, 30)
        crop = simple_brush.ScreenshotCropRegion(20, 20, 80, 60)
        return simple_brush.TkToScreenshotMapping(
            tk_selection=selection if passed else None,
            crop_region=crop if passed else None,
            passed=passed,
            message="mapping test evidence",
            error_code=None if passed else "MAPPING_FAILED",
        )

    def complete_kwargs(self, **overrides):
        values = {
            "display_fingerprint": "display-fingerprint",
            "scale_inference": self.scale(),
            "tk_to_screenshot_mapping": self.mapping(),
            "preview_confirmed": True,
        }
        values.update(overrides)
        return values

    def diagnostics(self, **overrides):
        values = {
            "platform": "darwin",
            "pyautogui_size": (1440, 900),
            "pyautogui_position": (100, 120),
            "mss_monitors": (
                {"left": 0, "top": 0, "width": 2880, "height": 1800},
            ),
            "primary_monitor": {
                "left": 0,
                "top": 0,
                "width": 2880,
                "height": 1800,
            },
            "tk_version": "8.6",
            "tcl_version": "8.6",
            "display_fingerprint": "display-fingerprint",
            "passed": True,
            "message": "diagnostics ok",
            "error_code": None,
        }
        values.update(overrides)
        return simple_brush.ScreenCoordinateDiagnostics(**values)

    def capture_image(self, width=600, height=400, channels=3):
        return np.zeros((height, width, channels), dtype=np.uint8)

    def test_parse_args_recognizes_calibration_only_without_limits(self):
        parsed = self.parse(
            "--mac-safe-browse-calibrate-only",
            "--no-forward",
        )

        self.assertTrue(parsed["mac_safe_browse_calibrate_only"])
        self.assertTrue(parsed["no_forward"])
        self.assertIsNone(parsed["max_candidates"])
        self.assertIsNone(parsed["max_runtime_minutes"])
        with patch.object(simple_brush.sys, "platform", "darwin"):
            self.assertIsNone(
                simple_brush.validate_mac_safe_browse_calibration_args(parsed)
            )

    def test_parse_args_rejects_calibration_mode_conflicts(self):
        for conflicting_flag in (
            "--mac-safe-browse-only",
            "--preflight-only",
            "--coordinate-diagnostics-only",
            "--auto",
        ):
            with self.subTest(conflicting_flag=conflicting_flag):
                with self.assertRaises(
                    simple_brush.MacSafeBrowseArgumentError
                ) as caught:
                    self.parse(
                        "--mac-safe-browse-calibrate-only",
                        "--no-forward",
                        conflicting_flag,
                    )
                self.assertEqual(
                    caught.exception.error_code,
                    "MAC_SAFE_BROWSE_CALIBRATION_CONFLICTING_MODE",
                )

    def test_calibration_args_reject_platform_no_forward_and_email(self):
        cases = (
            (
                self.args(),
                "win32",
                "MAC_SAFE_BROWSE_CALIBRATION_UNSUPPORTED_PLATFORM",
            ),
            (
                self.args(no_forward=False),
                "darwin",
                "MAC_SAFE_BROWSE_CALIBRATION_NO_FORWARD_REQUIRED",
            ),
            (
                self.args(email="forbidden@example.com"),
                "darwin",
                "MAC_SAFE_BROWSE_CALIBRATION_EMAIL_FORBIDDEN",
            ),
        )
        for args, platform_name, error_code in cases:
            with self.subTest(error_code=error_code):
                with self.assertRaises(
                    simple_brush.MacSafeBrowseArgumentError
                ) as caught:
                    simple_brush.validate_mac_safe_browse_calibration_args(
                        args,
                        platform_name=platform_name,
                    )
                self.assertEqual(caught.exception.error_code, error_code)

    def test_real_cli_shape_fails_before_gui_when_coordinate_evidence_missing(self):
        diagnostics = Mock(
            return_value=self.diagnostics(passed=False, message="diagnostics missing")
        )
        select_region = Mock()
        capture_region = Mock()
        save_crop_preview = Mock()
        with (
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch("builtins.print") as print_output,
        ):
            result = simple_brush.run_mac_safe_browse_calibration_only(
                self.args(),
                diagnostics_fn=diagnostics,
                select_region_fn=select_region,
                capture_fn=capture_region,
                save_crop_preview_fn=save_crop_preview,
            )

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 2)
        self.assertIn("MAC_SAFE_BROWSE_CALIBRATION_DIAGNOSTICS_FAILED", rendered)
        diagnostics.assert_called_once_with()
        select_region.assert_not_called()
        capture_region.assert_not_called()
        save_crop_preview.assert_not_called()

    def test_fingerprint_missing_fails_closed(self):
        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            diagnostics_fn=Mock(
                return_value=self.diagnostics(display_fingerprint="  ")
            ),
            select_region_fn=Mock(),
        )

        self.assertFalse(result.published)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_FINGERPRINT_MISSING",
        )

    def test_region_cancellation_fails_closed(self):
        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            **self.complete_kwargs(),
            select_region_fn=Mock(
                side_effect=simple_brush.CalibrationCancelled("cancelled")
            ),
        )

        self.assertFalse(result.published)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_REGION_CANCELLED",
        )

    def test_preview_failure_fails_closed(self):
        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            **self.complete_kwargs(),
            select_region_fn=Mock(
                return_value=simple_brush.ScreenRegion(10, 20, 300, 200)
            ),
            save_preview_fn=Mock(side_effect=RuntimeError("preview failed")),
            capture_fn=Mock(),
        )

        self.assertFalse(result.published)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_PREVIEW_FAILED",
        )

    def test_capture_failure_fails_closed(self):
        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            diagnostics_fn=Mock(return_value=self.diagnostics()),
            select_region_fn=Mock(
                return_value=simple_brush.ScreenRegion(10, 20, 300, 200)
            ),
            capture_fn=Mock(side_effect=RuntimeError("capture failed")),
        )

        self.assertFalse(result.published)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_CAPTURE_FAILED",
        )

    def test_scale_inference_failure_fails_closed(self):
        save_crop_preview = Mock()
        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            diagnostics_fn=Mock(return_value=self.diagnostics()),
            select_region_fn=Mock(
                return_value=simple_brush.ScreenRegion(10, 20, 300, 200)
            ),
            capture_fn=Mock(return_value=self.capture_image(width=600, height=120)),
            save_crop_preview_fn=save_crop_preview,
        )

        self.assertFalse(result.published)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_SCALE_FAILED",
        )
        save_crop_preview.assert_not_called()

    def test_mapping_failure_fails_closed(self):
        with patch.object(
            simple_brush,
            "map_tk_selection_to_screenshot_crop",
            return_value=simple_brush.TkToScreenshotMapping(
                tk_selection=None,
                crop_region=None,
                passed=False,
                message="mapping failed",
                error_code="TK_SELECTION_OUT_OF_BOUNDS",
            ),
        ):
            result = simple_brush.prepare_mac_safe_browse_calibrated_region(
                diagnostics_fn=Mock(return_value=self.diagnostics()),
                select_region_fn=Mock(
                    return_value=simple_brush.ScreenRegion(10, 20, 300, 200)
                ),
                capture_fn=Mock(
                    return_value=self.capture_image(width=600, height=400)
                ),
                save_crop_preview_fn=Mock(),
            )

        self.assertFalse(result.published)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_MAPPING_FAILED",
        )

    def test_preview_save_failure_in_supply_path_fails_closed(self):
        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            diagnostics_fn=Mock(return_value=self.diagnostics()),
            select_region_fn=Mock(
                return_value=simple_brush.ScreenRegion(10, 20, 300, 200)
            ),
            capture_fn=Mock(return_value=self.capture_image(width=600, height=400)),
            save_crop_preview_fn=Mock(
                return_value=simple_brush.CropPreviewResult(
                    saved=False,
                    preview_path=None,
                    crop_size=None,
                    message="preview save failed",
                    error_code="CROP_PREVIEW_SAVE_FAILED",
                )
            ),
        )

        self.assertFalse(result.published)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_PREVIEW_FAILED",
        )

    def test_incomplete_metadata_is_not_published(self):
        select_region = Mock(
            return_value=simple_brush.ScreenRegion(10, 20, 300, 200)
        )
        save_preview = Mock(return_value="/tmp/mock-preview.png")
        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            **self.complete_kwargs(preview_confirmed=False),
            select_region_fn=select_region,
            save_preview_fn=save_preview,
            capture_fn=Mock(),
        )

        self.assertFalse(result.published)
        self.assertIsNone(result.calibrated_region)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_METADATA_INCOMPLETE",
        )

    def test_confirmation_required_fails_closed_without_publish(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        result = simple_brush.prepare_mac_safe_browse_calibrated_region(
            diagnostics_fn=Mock(return_value=self.diagnostics()),
            select_region_fn=Mock(return_value=region),
            capture_fn=Mock(return_value=self.capture_image(width=600, height=400)),
            save_crop_preview_fn=Mock(
                return_value=simple_brush.CropPreviewResult(
                    saved=True,
                    preview_path="logs/macos-coordinate-diagnostics/mock/crop_preview.png",
                    crop_size=(600, 400),
                    message="saved",
                )
            ),
            confirmation_fn=Mock(return_value="NO"),
            preview_dir="logs/macos-coordinate-diagnostics/mock",
        )

        self.assertFalse(result.published)
        self.assertEqual(
            result.error_code,
            "MAC_SAFE_BROWSE_CALIBRATION_CONFIRMATION_REQUIRED",
        )

    def test_complete_mock_metadata_is_atomically_published_without_business_ready(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        select_region = Mock(return_value=region)
        capture = Mock(return_value="mock pixels")

        def save_preview(selected, destination, capture_fn):
            self.assertEqual(selected, region)
            capture_fn(selected)
            return destination

        blocked_names = (
            "prepare_browser",
            "run_mac_safe_browse_dry_pipeline",
            "initialize_ocr",
            "ensure_ocr_region_calibrated",
            "human_click",
            "click_in_region",
            "click_first_candidate",
            "apply_batch_filter_and_open_first_candidate",
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
        )
        pyautogui_names = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "platform", "darwin"))
            stack.enter_context(
                patch.object(simple_brush, "ocr_calibrated_region", None)
            )
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["OCRKeywordDetector"] = stack.enter_context(
                patch.object(simple_brush, "OCRKeywordDetector")
            )
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            print_output = stack.enter_context(patch("builtins.print"))
            result = simple_brush.run_mac_safe_browse_calibration_only(
                self.args(),
                **self.complete_kwargs(),
                select_region_fn=select_region,
                save_preview_fn=save_preview,
                capture_fn=capture,
                preview_path="/tmp/mock-preview.png",
            )
            published = simple_brush.ocr_calibrated_region

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 0)
        self.assertIsInstance(published, simple_brush.CalibratedScreenRegion)
        self.assertEqual(published.region, region)
        self.assertTrue(published.coordinate_metadata.validated)
        self.assertTrue(published.coordinate_metadata.manually_confirmed)
        self.assertFalse(published.coordinate_metadata.business_ready)
        self.assertIn(
            "MAC_SAFE_BROWSE_CALIBRATION_PUBLISHED_NOT_BUSINESS_READY",
            rendered,
        )
        select_region.assert_called_once_with()
        capture.assert_called_once_with(region)
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()

    def test_metadata_supply_path_publishes_after_explicit_yes_confirmation(self):
        region = simple_brush.ScreenRegion(10, 20, 300, 200)
        captured = self.capture_image(width=600, height=400)

        blocked_names = (
            "prepare_browser",
            "run_mac_safe_browse_only",
            "run_mac_safe_browse_dry_pipeline",
            "initialize_ocr",
            "ensure_ocr_region_calibrated",
            "save_region_preview",
            "human_click",
            "click_in_region",
            "click_first_candidate",
            "apply_batch_filter_and_open_first_candidate",
            "human_scroll_once",
            "next_candidate",
            "refresh_page",
            "forward_one_candidate",
            "run_osascript",
            "focus_chrome_window",
            "get_chrome_active_tab_identity",
        )
        pyautogui_names = (
            "position",
            "click",
            "moveTo",
            "mouseDown",
            "mouseUp",
            "press",
            "hotkey",
            "scroll",
            "typewrite",
        )

        with ExitStack() as stack:
            stack.enter_context(patch.object(simple_brush.sys, "platform", "darwin"))
            stack.enter_context(
                patch.object(simple_brush, "ocr_calibrated_region", None)
            )
            blocked = {
                name: stack.enter_context(patch.object(simple_brush, name))
                for name in blocked_names
            }
            blocked["OCRKeywordDetector"] = stack.enter_context(
                patch.object(simple_brush, "OCRKeywordDetector")
            )
            blocked["listener.start"] = stack.enter_context(
                patch.object(simple_brush.listener, "start")
            )
            blocked.update(
                {
                    f"pyautogui.{name}": stack.enter_context(
                        patch.object(simple_brush.pyautogui, name)
                    )
                    for name in pyautogui_names
                }
            )
            print_output = stack.enter_context(patch("builtins.print"))
            result = simple_brush.run_mac_safe_browse_calibration_only(
                self.args(),
                diagnostics_fn=Mock(return_value=self.diagnostics()),
                select_region_fn=Mock(return_value=region),
                capture_fn=Mock(return_value=captured),
                save_crop_preview_fn=Mock(
                    return_value=simple_brush.CropPreviewResult(
                        saved=True,
                        preview_path=(
                            "logs/macos-coordinate-diagnostics/mock/"
                            "crop_preview.png"
                        ),
                        crop_size=(600, 400),
                        message="saved",
                    )
                ),
                confirmation_fn=Mock(return_value="YES"),
                preview_dir="logs/macos-coordinate-diagnostics/mock",
            )
            published = simple_brush.ocr_calibrated_region

        rendered = "\n".join(
            " ".join(str(item) for item in entry.args)
            for entry in print_output.call_args_list
        )
        self.assertEqual(result, 0)
        self.assertIsInstance(published, simple_brush.CalibratedScreenRegion)
        self.assertEqual(published.region, region)
        self.assertTrue(published.coordinate_metadata.validated)
        self.assertTrue(published.coordinate_metadata.manually_confirmed)
        self.assertFalse(published.coordinate_metadata.business_ready)
        self.assertEqual(
            published.coordinate_metadata.crop_preview.preview_path,
            "logs/macos-coordinate-diagnostics/mock/crop_preview.png",
        )
        self.assertIn("preview_path:", rendered)
        self.assertNotIn("array(", rendered)
        for name, mocked in blocked.items():
            with self.subTest(blocked_action=name):
                mocked.assert_not_called()

    def test_run_dispatches_calibration_only_before_ordinary_business(self):
        argv = [
            "simple_brush.py",
            "--mac-safe-browse-calibrate-only",
            "--no-forward",
        ]
        with (
            patch.object(simple_brush.sys, "argv", argv),
            patch.object(simple_brush.sys, "platform", "darwin"),
            patch.object(
                simple_brush,
                "run_mac_safe_browse_calibration_only",
                return_value=2,
            ) as calibration_only,
            patch.object(simple_brush, "get_user_input") as get_user_input,
            patch.object(simple_brush, "run_mac_safe_browse_only") as safe_browse,
            patch.object(simple_brush, "prepare_browser") as prepare_browser,
            patch.object(simple_brush.listener, "start") as listener_start,
        ):
            result = simple_brush.run()

        self.assertEqual(result, 2)
        calibration_only.assert_called_once()
        get_user_input.assert_not_called()
        safe_browse.assert_not_called()
        prepare_browser.assert_not_called()
        listener_start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
