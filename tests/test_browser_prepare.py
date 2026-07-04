from contextlib import ExitStack
import unittest
from unittest.mock import patch

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
        self.assertIn("does not validate window focus", rendered)

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
        ):
            result = simple_brush.prepare_browser("darwin")

        bring_edge.assert_not_called()
        resolve.assert_called_once_with()
        launch.assert_not_called()
        self.assertFalse(result.ready)
        self.assertEqual(result.platform, "macos")
        self.assertEqual(result.browser, "chrome")
        self.assertFalse(result.launched)
        self.assertEqual(result.error_code, "CHROME_NOT_FOUND")
        self.assertTrue(result.message)

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

    def test_macos_successful_launch_is_started_but_not_ready(self):
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
            message="started but not ready",
            error_code="MACOS_BROWSER_STARTED_NOT_READY",
        )
        with (
            patch.object(
                simple_brush, "resolve_chrome_executable", return_value=resolved
            ) as resolve,
            patch.object(
                simple_brush, "launch_chrome_safe_target", return_value=launched
            ) as launch,
        ):
            result = simple_brush.prepare_browser("darwin")

        resolve.assert_called_once_with()
        launch.assert_called_once_with(simple_brush.MACOS_CHROME_EXECUTABLE)
        self.assertFalse(result.ready)
        self.assertTrue(result.launched)
        self.assertEqual(result.browser, "chrome")
        self.assertEqual(result.error_code, "MACOS_PERMISSIONS_NOT_READY")
        self.assertIn("accessibility=unknown", result.message)

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
        ):
            result = simple_brush.prepare_browser("darwin")

        self.assertFalse(result.ready)
        self.assertTrue(result.launched)
        self.assertEqual(result.error_code, "MACOS_PERMISSION_CHECK_FAILED")
        self.assertIn("diagnostic failed", result.message)
        self.assertIn("完全退出并重启宿主进程", result.message)

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
        ):
            result = simple_brush.prepare_browser("darwin")

        self.assertFalse(result.ready)
        self.assertTrue(result.launched)
        self.assertEqual(result.error_code, "MACOS_BROWSER_STARTED_NOT_READY")
        self.assertIn("窗口和页面尚未验证", result.message)

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
        ):
            result = simple_brush.prepare_browser("linux")

        bring_edge.assert_not_called()
        permissions.assert_not_called()
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
        ):
            result = simple_brush.prepare_browser("win32")

        bring_edge.assert_called_once_with()
        resolve.assert_not_called()
        popen.assert_not_called()
        permissions.assert_not_called()
        self.assertTrue(result.ready)

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
            message="started but not ready",
            error_code="MACOS_BROWSER_STARTED_NOT_READY",
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


if __name__ == "__main__":
    unittest.main()
