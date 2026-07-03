import unittest
from unittest.mock import patch

import simple_brush


class BrowserPrepareTests(unittest.TestCase):
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

    def test_macos_is_fail_closed_without_calling_windows_path(self):
        with patch.object(simple_brush, "bring_edge_foreground") as bring_edge:
            result = simple_brush.prepare_browser("darwin")

        bring_edge.assert_not_called()
        self.assertFalse(result.ready)
        self.assertEqual(result.platform, "macos")
        self.assertEqual(result.browser, "chrome")
        self.assertFalse(result.launched)
        self.assertEqual(result.executable_path, "")
        self.assertEqual(result.error_code, "MACOS_BROWSER_NOT_IMPLEMENTED")
        self.assertTrue(result.message)

    def test_unknown_platform_is_fail_closed(self):
        with patch.object(simple_brush, "bring_edge_foreground") as bring_edge:
            result = simple_brush.prepare_browser("linux")

        bring_edge.assert_not_called()
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
            message="not implemented",
            error_code="MACOS_BROWSER_NOT_IMPLEMENTED",
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
