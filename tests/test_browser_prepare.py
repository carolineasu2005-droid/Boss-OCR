from contextlib import ExitStack
import tempfile
import subprocess
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np
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


if __name__ == "__main__":
    unittest.main()
