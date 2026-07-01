import unittest
from unittest.mock import Mock, call, patch

import simple_brush
from ocr_detector import DetectionResult, ScanObservation


class SimpleBrushOCRTests(unittest.TestCase):
    def setUp(self):
        self.saved = {
            name: getattr(simple_brush, name)
            for name in (
                "forward_enabled",
                "forward_keywords",
                "forward_consecutive",
                "backup_email",
                "no_forward_mode",
                "ocr_backend",
                "ocr_capture",
                "ocr_detector",
                "ocr_initialization_attempted",
                "ocr_calibration_attempted",
                "ocr_calibration_in_progress",
                "stop_event",
                "paused",
                "run_duration_seconds",
            )
        }
        simple_brush.forward_enabled = True
        simple_brush.forward_keywords = ["Python"]
        simple_brush.forward_consecutive = 0
        simple_brush.backup_email = ""
        simple_brush.no_forward_mode = False
        simple_brush.stop_event = False
        simple_brush.paused = False
        simple_brush.run_duration_seconds = 0

    def tearDown(self):
        for name, value in self.saved.items():
            setattr(simple_brush, name, value)

    def test_detect_keywords_uses_ocr_without_clipboard(self):
        observation = ScanObservation(1, "python", 1, 0.05, "Python")
        detector = Mock()
        detector.detect.return_value = DetectionResult(
            success=True,
            confirmed_match=True,
            matched_keyword="Python",
            scans_completed=1,
            observations=[observation, observation],
        )
        simple_brush.ocr_detector = detector

        with patch.object(simple_brush, "get_clipboard_text") as clipboard:
            self.assertTrue(simple_brush.detect_keywords())
        clipboard.assert_not_called()
        detector.detect.assert_called_once_with(["Python"])

    def test_no_forward_mode_never_calls_real_forward(self):
        simple_brush.no_forward_mode = True
        with (
            patch.object(simple_brush, "detect_keywords", return_value=True),
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush.random, "uniform", return_value=0.0),
        ):
            self.assertTrue(simple_brush.view_candidate(0))
        forward.assert_not_called()

    def test_ocr_failure_never_calls_real_forward(self):
        with (
            patch.object(simple_brush, "detect_keywords", return_value=False),
            patch.object(simple_brush, "forward_one_candidate") as forward,
            patch.object(simple_brush.random, "uniform", return_value=0.0),
        ):
            self.assertTrue(simple_brush.view_candidate(0))
        forward.assert_not_called()

    def assert_focus_restored_once(self, click):
        focus_call = call(450, 375, offset=3)
        self.assertEqual(click.call_args_list.count(focus_call), 1)
        self.assertEqual(click.call_args_list[-1], focus_call)

    def test_forward_restores_focus_after_success(self):
        with (
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value="test@example.com"),
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertTrue(simple_brush.forward_one_candidate())

        self.assert_focus_restored_once(click)

    def test_forward_restores_focus_at_consecutive_limit(self):
        simple_brush.forward_consecutive = simple_brush.FORWARD_MAX_CONSEC
        with (
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush, "human_delay", return_value=True),
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        self.assert_focus_restored_once(click)

    def test_forward_restores_focus_without_backup_email(self):
        with (
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value=""),
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        self.assert_focus_restored_once(click)

    def test_forward_restores_focus_when_wait_is_interrupted(self):
        with (
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush, "human_delay", return_value=False),
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        self.assert_focus_restored_once(click)

    def test_forward_restores_focus_when_forwarding_raises(self):
        with (
            patch.object(
                simple_brush,
                "human_click",
                side_effect=[RuntimeError("forward failed"), None],
            ) as click,
            patch.object(simple_brush, "human_delay", return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "forward failed"):
                simple_brush.forward_one_candidate()

        self.assert_focus_restored_once(click)

    def test_calibration_escape_does_not_stop_browsing(self):
        simple_brush.ocr_calibration_in_progress = True
        result = simple_brush.on_press(simple_brush.keyboard.Key.esc)
        self.assertTrue(result)
        self.assertFalse(simple_brush.stop_event)

    def test_cancelled_calibration_is_only_attempted_once(self):
        simple_brush.ocr_backend = Mock()
        simple_brush.ocr_capture = Mock()
        simple_brush.ocr_detector = None
        simple_brush.ocr_initialization_attempted = True
        simple_brush.ocr_calibration_attempted = False

        with patch.object(
            simple_brush,
            "select_screen_region",
            side_effect=simple_brush.CalibrationCancelled,
        ) as select:
            self.assertFalse(simple_brush.ensure_ocr_region_calibrated())
            self.assertFalse(simple_brush.ensure_ocr_region_calibrated())
        self.assertEqual(select.call_count, 1)
        self.assertFalse(simple_brush.stop_event)

    def test_no_forward_argument_is_parsed(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--keywords", "Python", "--no-forward", "--auto"],
        ):
            args = simple_brush.parse_args()
        self.assertTrue(args["no_forward"])
        self.assertEqual(args["keywords"], "Python")

    def test_duration_argument_is_parsed(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--duration-seconds", "60", "--auto"],
        ):
            args = simple_brush.parse_args()
        self.assertEqual(args["duration_seconds"], "60")

    def test_duration_argument_requires_a_value(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--duration-seconds"],
        ):
            with self.assertRaisesRegex(ValueError, "缺少秒数"):
                simple_brush.parse_args()

    def test_duration_parser_accepts_empty_zero_and_positive_integer(self):
        self.assertEqual(simple_brush.parse_duration_seconds(""), 0)
        self.assertEqual(simple_brush.parse_duration_seconds(" 0 "), 0)
        self.assertEqual(simple_brush.parse_duration_seconds("3600"), 3600)

    def test_duration_parser_rejects_invalid_values(self):
        for value in ("-1", "1.5", "abc", "10秒", "+1", "１"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    simple_brush.parse_duration_seconds(value)

    def test_interactive_duration_retries_invalid_input(self):
        with patch("builtins.input", side_effect=["", "invalid", "3"]):
            simple_brush.get_user_input()
        self.assertEqual(simple_brush.run_duration_seconds, 3)

    def test_auto_mode_rejects_invalid_duration(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--duration-seconds", "invalid", "--auto"],
        ), patch.object(simple_brush, "bring_edge_foreground") as bring_edge:
            self.assertEqual(simple_brush.run(), 2)
        bring_edge.assert_not_called()

    def test_zero_duration_does_not_create_timer(self):
        with patch.object(simple_brush.threading, "Timer") as timer_factory:
            self.assertIsNone(simple_brush.start_run_timer(0))
        timer_factory.assert_not_called()

    def test_positive_duration_starts_timer(self):
        timer = Mock()
        with patch.object(simple_brush.threading, "Timer", return_value=timer) as factory:
            self.assertIs(simple_brush.start_run_timer(60), timer)
        factory.assert_called_once_with(60, simple_brush.request_timed_stop)
        self.assertTrue(timer.daemon)
        timer.start.assert_called_once_with()

    def test_timed_stop_sets_existing_stop_flag(self):
        simple_brush.request_timed_stop()
        self.assertTrue(simple_brush.stop_event)

    def test_run_cancels_timer_when_countdown_is_interrupted(self):
        timer = Mock()
        with (
            patch.object(
                simple_brush.sys,
                "argv",
                ["simple_brush.py", "--duration-seconds", "5", "--auto"],
            ),
            patch.object(simple_brush, "bring_edge_foreground", return_value=True),
            patch.object(simple_brush, "start_run_timer", return_value=timer),
            patch.object(simple_brush, "safe_wait", return_value=False),
            patch.object(simple_brush.listener, "start"),
        ):
            self.assertEqual(simple_brush.run(), 0)
        timer.cancel.assert_called_once_with()

    def test_stop_prevents_new_navigation_actions(self):
        simple_brush.stop_event = True
        with (
            patch.object(simple_brush.pyautogui, "click") as click,
            patch.object(simple_brush.pyautogui, "press") as press,
            patch.object(simple_brush.pyautogui, "scroll") as scroll,
        ):
            self.assertFalse(simple_brush.click_first_candidate(10, 20))
            self.assertFalse(simple_brush.next_candidate())
            self.assertFalse(simple_brush.refresh_page())
            simple_brush.human_scroll_once()
        click.assert_not_called()
        press.assert_not_called()
        scroll.assert_not_called()

    def test_ocr_time_is_deducted_from_stay_budget(self):
        self.assertEqual(simple_brush.remaining_stay_seconds(12.0, 100.0, 107.5), 4.5)
        self.assertEqual(simple_brush.remaining_stay_seconds(12.0, 100.0, 115.0), 0.0)

    def test_ocr_wait_stops_when_escape_was_requested(self):
        with patch.object(simple_brush, "safe_wait", return_value=False):
            with self.assertRaises(simple_brush.OCRInterrupted):
                simple_brush.ocr_wait(0.6)

    def test_ocr_scroll_uses_twenty_times_the_previous_range(self):
        for steps in (100, 140):
            with self.subTest(steps=steps):
                with (
                    patch.object(simple_brush.random, "randint", return_value=steps) as randint,
                    patch.object(simple_brush.pyautogui, "scroll") as scroll,
                ):
                    simple_brush.ocr_scroll_down()

                randint.assert_called_once_with(100, 140)
                scroll.assert_called_once_with(-steps)

    def test_window_match_rejects_vscode_project_title(self):
        self.assertFalse(
            simple_brush.is_boss_edge_window(
                "BossOCR.spec - BOSSOCR - Visual Studio Code", "code.exe"
            )
        )

    def test_window_match_accepts_boss_in_edge(self):
        self.assertTrue(
            simple_brush.is_boss_edge_window(
                "BOSS直聘 - 个人 - Microsoft Edge", "msedge.exe"
            )
        )


if __name__ == "__main__":
    unittest.main()
