import unittest
from unittest.mock import Mock, call, patch

import simple_brush
from ocr_detector import DetectionResult, ScanObservation


WINDOWS_BROWSER_READY = simple_brush.BrowserPrepareResult(
    ready=True,
    platform="windows",
    browser="edge",
)


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
                "forward_click_regions",
                "forward_click_calibration_requested",
                "forward_click_calibration_attempted",
                "forward_click_calibration_in_progress",
                "batch_filter_regions",
                "batch_filter_calibration_requested",
                "batch_filter_calibration_attempted",
                "batch_filter_calibration_in_progress",
                "batch_filter_enabled",
                "focus_restore_region",
                "focus_restore_calibration_requested",
                "focus_restore_calibration_attempted",
                "focus_restore_calibration_in_progress",
                "ocr_backend",
                "ocr_capture",
                "ocr_detector",
                "ocr_initialization_attempted",
                "ocr_calibration_attempted",
                "ocr_calibration_in_progress",
                "stop_event",
                "paused",
                "run_duration_seconds",
                "_programmatic_esc",
            )
        }
        simple_brush.forward_enabled = True
        simple_brush.forward_keywords = simple_brush.parse_keyword_rules('"Python"')
        simple_brush.forward_consecutive = 0
        simple_brush.backup_email = ""
        simple_brush.no_forward_mode = False
        simple_brush.reset_forward_click_calibration()
        simple_brush.reset_batch_filter_calibration()
        simple_brush.reset_focus_restore_calibration()
        simple_brush.stop_event = False
        simple_brush.paused = False
        simple_brush.run_duration_seconds = 0
        simple_brush._programmatic_esc = False

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
        detector.detect.assert_called_once_with(simple_brush.forward_keywords)

    def test_detect_keywords_passes_the_complete_not_rule_to_ocr(self):
        rules = simple_brush.parse_keyword_rules('"短剧" and not "销售"')
        detector = Mock()
        detector.detect.return_value = DetectionResult(
            success=True,
            confirmed_match=True,
            matched_keyword='"短剧" and not "销售"',
            scans_completed=1,
            observations=[],
        )
        simple_brush.forward_keywords = rules
        simple_brush.ocr_detector = detector

        self.assertTrue(simple_brush.detect_keywords())
        detector.detect.assert_called_once_with(rules)

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

    def assert_focus_restored_twice(self, click, choose_point):
        focus_call = call(500, 400, offset=0)
        self.assertEqual(
            choose_point.call_args_list,
            [
                call(simple_brush.focus_restore_region),
                call(simple_brush.focus_restore_region),
            ],
        )
        self.assertEqual(click.call_args_list, [focus_call, focus_call])

    def test_forward_restores_focus_after_success(self):
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value="test@example.com"),
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertTrue(simple_brush.forward_one_candidate())

        self.assertEqual(
            region_click.call_args_list,
            [
                call(simple_brush.forward_click_regions.forward_icon),
                call(simple_brush.forward_click_regions.email_tab),
                call(simple_brush.forward_click_regions.recent_email),
                call(simple_brush.forward_click_regions.input_box),
                call(simple_brush.forward_click_regions.forward_button),
            ],
        )
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_uses_calibrated_regions_and_reuses_input_box_region(self):
        calibrated = simple_brush.ForwardClickRegions(
            forward_icon=simple_brush.ScreenRegion(10, 20, 12, 12),
            email_tab=simple_brush.ScreenRegion(30, 40, 12, 12),
            input_box=simple_brush.ScreenRegion(50, 60, 20, 12),
            recent_email=simple_brush.ScreenRegion(70, 80, 12, 12),
            forward_button=simple_brush.ScreenRegion(90, 100, 20, 12),
        )
        simple_brush.forward_click_regions = calibrated
        simple_brush.backup_email = "backup@example.com"
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value=""),
            patch.object(simple_brush, "type_text_human", return_value=True),
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertTrue(simple_brush.forward_one_candidate())

        self.assertEqual(
            region_click.call_args_list,
            [
                call(calibrated.forward_icon),
                call(calibrated.email_tab),
                call(calibrated.recent_email),
                call(calibrated.input_box),
                call(calibrated.input_box),
                call(calibrated.forward_button),
            ],
        )
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_restores_focus_at_consecutive_limit(self):
        simple_brush.forward_consecutive = simple_brush.FORWARD_MAX_CONSEC
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        region_click.assert_not_called()
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_restores_focus_without_backup_email(self):
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value=""),
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        self.assertEqual(
            region_click.call_args_list,
            [
                call(simple_brush.forward_click_regions.forward_icon),
                call(simple_brush.forward_click_regions.email_tab),
                call(simple_brush.forward_click_regions.recent_email),
                call(simple_brush.forward_click_regions.input_box),
            ],
        )
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_restores_focus_when_wait_is_interrupted(self):
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=False),
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        region_click.assert_called_once_with(simple_brush.forward_click_regions.forward_icon)
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_restores_focus_when_forwarding_raises(self):
        with (
            patch.object(
                simple_brush,
                "click_in_region",
                side_effect=RuntimeError("forward failed"),
            ) as region_click,
            patch.object(
                simple_brush,
                "human_click",
            ) as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(500, 400),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
        ):
            with self.assertRaisesRegex(RuntimeError, "forward failed"):
                simple_brush.forward_one_candidate()

        region_click.assert_called_once_with(simple_brush.forward_click_regions.forward_icon)
        self.assert_focus_restored_twice(click, choose_point)

    def test_forward_restores_focus_from_calibrated_runtime_region(self):
        simple_brush.focus_restore_region = simple_brush.ScreenRegion(
            left=600,
            top=300,
            width=120,
            height=60,
        )
        with (
            patch.object(simple_brush, "click_in_region") as region_click,
            patch.object(simple_brush, "human_click") as click,
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(650, 330),
            ) as choose_point,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "get_clipboard_text", return_value="test@example.com"),
            patch.object(simple_brush.pyautogui, "hotkey") as hotkey,
            patch.object(simple_brush.time, "sleep"),
        ):
            self.assertTrue(simple_brush.forward_one_candidate())

        self.assertEqual(region_click.call_count, 5)
        self.assertEqual(
            hotkey.call_args_list,
            [call("ctrl", "a"), call("ctrl", "c")],
        )
        self.assertEqual(
            choose_point.call_args_list,
            [
                call(simple_brush.focus_restore_region),
                call(simple_brush.focus_restore_region),
            ],
        )
        focus_call = call(650, 330, offset=0)
        self.assertEqual(click.call_args_list, [focus_call, focus_call])

    def test_second_focus_restore_is_attempted_when_first_click_raises(self):
        simple_brush.forward_consecutive = simple_brush.FORWARD_MAX_CONSEC
        with (
            patch.object(
                simple_brush,
                "random_point_in_region",
                side_effect=[(500, 400), (501, 401)],
            ) as choose_point,
            patch.object(
                simple_brush,
                "human_click",
                side_effect=[RuntimeError("first restore failed"), None],
            ) as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
            patch.object(simple_brush.logger, "error") as log_error,
        ):
            self.assertFalse(simple_brush.forward_one_candidate())

        self.assertEqual(
            choose_point.call_args_list,
            [
                call(simple_brush.focus_restore_region),
                call(simple_brush.focus_restore_region),
            ],
        )
        self.assertEqual(
            click.call_args_list,
            [call(500, 400, offset=0), call(501, 401, offset=0)],
        )
        delay.assert_called_once_with(0.3, 0.5)
        log_error.assert_called_once()
        self.assertIn("第 1 次", log_error.call_args.args[0])

    def test_calibration_escape_does_not_stop_browsing(self):
        simple_brush.ocr_calibration_in_progress = True
        result = simple_brush.on_press(simple_brush.keyboard.Key.esc)
        self.assertTrue(result)
        self.assertFalse(simple_brush.stop_event)

    def test_focus_restore_default_region_includes_original_boundaries(self):
        self.assertEqual(
            simple_brush.DEFAULT_FOCUS_RESTORE_REGION,
            simple_brush.ScreenRegion(left=400, top=350, width=101, height=51),
        )

    def test_default_forward_click_regions_preserve_existing_click_ranges(self):
        regions = simple_brush.DEFAULT_FORWARD_CLICK_REGIONS
        self.assertEqual(
            regions.forward_icon,
            simple_brush.ScreenRegion(left=1665, top=255, width=11, height=11),
        )
        self.assertEqual(
            regions.email_tab,
            simple_brush.ScreenRegion(left=695, top=595, width=11, height=11),
        )
        self.assertEqual(
            regions.input_box,
            simple_brush.ScreenRegion(left=897, top=387, width=7, height=7),
        )
        self.assertEqual(
            regions.recent_email,
            simple_brush.ScreenRegion(left=995, top=435, width=11, height=11),
        )
        self.assertEqual(
            regions.forward_button,
            simple_brush.ScreenRegion(left=1205, top=735, width=11, height=11),
        )

    def test_region_around_rejects_negative_radius(self):
        with self.assertRaisesRegex(ValueError, "半径不能为负数"):
            simple_brush.region_around(10, 20, -1)

    def test_click_in_region_chooses_once_and_disables_second_offset(self):
        region = simple_brush.ScreenRegion(left=10, top=20, width=5, height=6)
        with (
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(12, 24),
            ) as choose_point,
            patch.object(simple_brush, "human_click") as click,
        ):
            simple_brush.click_in_region(region)
        choose_point.assert_called_once_with(region)
        click.assert_called_once_with(12, 24, offset=0)

    def test_reset_forward_click_calibration_restores_defaults(self):
        simple_brush.forward_click_regions = simple_brush.ForwardClickRegions(
            forward_icon=simple_brush.ScreenRegion(1, 2, 3, 4),
            email_tab=simple_brush.ScreenRegion(5, 6, 7, 8),
            input_box=simple_brush.ScreenRegion(9, 10, 11, 12),
            recent_email=simple_brush.ScreenRegion(13, 14, 15, 16),
            forward_button=simple_brush.ScreenRegion(17, 18, 19, 20),
        )
        simple_brush.forward_click_calibration_requested = True
        simple_brush.forward_click_calibration_attempted = True
        simple_brush.forward_click_calibration_in_progress = True
        simple_brush.reset_forward_click_calibration()
        self.assertEqual(
            simple_brush.forward_click_regions,
            simple_brush.DEFAULT_FORWARD_CLICK_REGIONS,
        )
        self.assertFalse(simple_brush.forward_click_calibration_requested)
        self.assertFalse(simple_brush.forward_click_calibration_attempted)
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)

    def test_forward_click_calibration_selects_in_order_and_publishes_atomically(self):
        regions = [
            simple_brush.ScreenRegion(index * 10, index * 20, 12, 12)
            for index in range(1, 6)
        ]
        simple_brush.forward_click_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=regions,
            ) as select,
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
            patch.object(
                simple_brush,
                "close_forward_dialog_after_calibration",
            ) as close_dialog,
        ):
            result = simple_brush.ensure_forward_click_regions_calibrated()

        self.assertEqual(
            result,
            simple_brush.ForwardClickRegions(
                forward_icon=regions[0],
                email_tab=regions[1],
                input_box=regions[2],
                recent_email=regions[3],
                forward_button=regions[4],
            ),
        )
        self.assertEqual(select.call_count, 5)
        self.assertEqual(
            [item.kwargs["subtitle"].split(" · ")[0] for item in select.call_args_list],
            ["校准 1/5", "校准 2/5", "校准 3/5", "校准 4/5", "校准 5/5"],
        )
        self.assertEqual(click.call_args_list, [call(regions[0]), call(regions[1])])
        self.assertNotIn(call(regions[4]), click.call_args_list)
        self.assertEqual(delay.call_args_list, [call(0.8, 1.2), call(0.5, 0.8)])
        close_dialog.assert_called_once_with()
        self.assertTrue(simple_brush.forward_click_calibration_attempted)
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)

    def test_cancelled_forward_click_calibration_falls_back_atomically_and_once(self):
        first = simple_brush.ScreenRegion(10, 20, 12, 12)
        simple_brush.forward_click_regions = simple_brush.ForwardClickRegions(
            forward_icon=simple_brush.ScreenRegion(1, 2, 3, 4),
            email_tab=simple_brush.ScreenRegion(5, 6, 7, 8),
            input_box=simple_brush.ScreenRegion(9, 10, 11, 12),
            recent_email=simple_brush.ScreenRegion(13, 14, 15, 16),
            forward_button=simple_brush.ScreenRegion(17, 18, 19, 20),
        )
        simple_brush.forward_click_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=[first, simple_brush.CalibrationCancelled],
            ) as select,
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "close_forward_dialog_after_calibration") as close,
        ):
            first_result = simple_brush.ensure_forward_click_regions_calibrated()
            second_result = simple_brush.ensure_forward_click_regions_calibrated()

        self.assertEqual(first_result, simple_brush.DEFAULT_FORWARD_CLICK_REGIONS)
        self.assertEqual(second_result, simple_brush.DEFAULT_FORWARD_CLICK_REGIONS)
        self.assertEqual(select.call_count, 2)
        click.assert_called_once_with(first)
        close.assert_called_once_with()
        self.assertTrue(simple_brush.forward_click_calibration_attempted)
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)
        self.assertFalse(simple_brush.stop_event)

    def test_failed_forward_click_calibration_falls_back_without_stopping(self):
        simple_brush.forward_click_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=RuntimeError("overlay failed"),
            ),
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "close_forward_dialog_after_calibration") as close,
            patch.object(simple_brush.logger, "exception") as log_exception,
        ):
            result = simple_brush.ensure_forward_click_regions_calibrated()

        self.assertEqual(result, simple_brush.DEFAULT_FORWARD_CLICK_REGIONS)
        click.assert_not_called()
        close.assert_called_once_with()
        log_exception.assert_called_once()
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)
        self.assertFalse(simple_brush.stop_event)

    def test_forward_click_calibration_is_skipped_when_not_requested(self):
        with (
            patch.object(simple_brush, "select_screen_region") as select,
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "close_forward_dialog_after_calibration") as close,
        ):
            result = simple_brush.ensure_forward_click_regions_calibrated()
        self.assertEqual(result, simple_brush.DEFAULT_FORWARD_CLICK_REGIONS)
        select.assert_not_called()
        click.assert_not_called()
        close.assert_not_called()

    def test_forward_click_calibration_escape_does_not_stop_browsing(self):
        simple_brush.forward_click_calibration_in_progress = True
        result = simple_brush.on_press(simple_brush.keyboard.Key.esc)
        self.assertTrue(result)
        self.assertFalse(simple_brush.stop_event)

    def test_calibration_dialog_close_uses_programmatic_escape(self):
        with patch.object(simple_brush.pyautogui, "press") as press:
            simple_brush.close_forward_dialog_after_calibration()
        press.assert_called_once_with("esc")
        self.assertFalse(simple_brush._programmatic_esc)

    def test_reset_batch_filter_calibration_clears_runtime_state(self):
        simple_brush.batch_filter_regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(1, 2, 20, 20),
            open_filter=simple_brush.ScreenRegion(3, 4, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(5, 6, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(7, 8, 12, 12),
        )
        simple_brush.batch_filter_calibration_requested = True
        simple_brush.batch_filter_calibration_attempted = True
        simple_brush.batch_filter_calibration_in_progress = True
        simple_brush.batch_filter_enabled = True

        simple_brush.reset_batch_filter_calibration()

        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)
        self.assertFalse(simple_brush.batch_filter_calibration_attempted)
        self.assertFalse(simple_brush.batch_filter_calibration_in_progress)
        self.assertFalse(simple_brush.batch_filter_enabled)

    def test_batch_filter_calibration_selects_in_order_and_publishes_atomically(self):
        regions = [
            simple_brush.ScreenRegion(index * 10, index * 20, 24, 24)
            for index in range(1, 5)
        ]
        simple_brush.batch_filter_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=regions,
            ) as select,
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
            patch.object(
                simple_brush,
                "close_batch_filter_panel_after_calibration",
            ) as close_panel,
        ):
            result = simple_brush.ensure_batch_filter_regions_calibrated()

        expected = simple_brush.BatchFilterRegions(
            first_candidate=regions[0],
            open_filter=regions[1],
            unseen_filter=regions[2],
            confirm_filter=regions[3],
        )
        self.assertEqual(result, expected)
        self.assertEqual(simple_brush.batch_filter_regions, expected)
        self.assertTrue(simple_brush.batch_filter_enabled)
        self.assertTrue(simple_brush.batch_filter_calibration_attempted)
        self.assertFalse(simple_brush.batch_filter_calibration_in_progress)
        self.assertEqual(
            [item.kwargs["subtitle"].split(" · ")[0] for item in select.call_args_list],
            ["校准 1/4", "校准 2/4", "校准 3/4", "校准 4/4"],
        )
        click.assert_called_once_with(regions[1])
        self.assertNotIn(call(regions[0]), click.call_args_list)
        self.assertNotIn(call(regions[2]), click.call_args_list)
        self.assertNotIn(call(regions[3]), click.call_args_list)
        delay.assert_called_once_with(0.5, 1.0)
        close_panel.assert_called_once_with()

    def test_batch_filter_calibration_cancellation_is_atomic_at_every_region(self):
        regions = [
            simple_brush.ScreenRegion(index * 10, index * 20, 24, 24)
            for index in range(1, 5)
        ]
        for cancelled_index in range(4):
            with self.subTest(cancelled_index=cancelled_index):
                simple_brush.reset_batch_filter_calibration()
                simple_brush.batch_filter_calibration_requested = True
                side_effect = regions[:cancelled_index] + [
                    simple_brush.CalibrationCancelled()
                ]
                with (
                    patch.object(
                        simple_brush,
                        "select_screen_region",
                        side_effect=side_effect,
                    ),
                    patch.object(simple_brush, "click_in_region") as click,
                    patch.object(simple_brush, "human_delay", return_value=True),
                    patch.object(
                        simple_brush,
                        "close_batch_filter_panel_after_calibration",
                    ) as close_panel,
                ):
                    result = simple_brush.ensure_batch_filter_regions_calibrated()

                self.assertIsNone(result)
                self.assertIsNone(simple_brush.batch_filter_regions)
                self.assertFalse(simple_brush.batch_filter_enabled)
                self.assertTrue(simple_brush.batch_filter_calibration_attempted)
                self.assertFalse(simple_brush.batch_filter_calibration_in_progress)
                self.assertFalse(simple_brush.stop_event)
                if cancelled_index < 2:
                    click.assert_not_called()
                    close_panel.assert_not_called()
                else:
                    click.assert_called_once_with(regions[1])
                    close_panel.assert_called_once_with()

    def test_batch_filter_calibration_exception_before_open_does_not_press_escape(self):
        simple_brush.batch_filter_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=RuntimeError("overlay failed"),
            ),
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(
                simple_brush,
                "close_batch_filter_panel_after_calibration",
            ) as close_panel,
            patch.object(simple_brush.logger, "exception") as log_exception,
        ):
            result = simple_brush.ensure_batch_filter_regions_calibrated()

        self.assertIsNone(result)
        self.assertFalse(simple_brush.batch_filter_enabled)
        click.assert_not_called()
        close_panel.assert_not_called()
        log_exception.assert_called_once()
        self.assertFalse(simple_brush.stop_event)

    def test_batch_filter_calibration_wait_interruption_closes_and_falls_back(self):
        first = simple_brush.ScreenRegion(10, 20, 24, 24)
        open_filter = simple_brush.ScreenRegion(30, 40, 12, 12)
        simple_brush.batch_filter_calibration_requested = True
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=[first, open_filter],
            ),
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=False),
            patch.object(
                simple_brush,
                "close_batch_filter_panel_after_calibration",
            ) as close_panel,
        ):
            result = simple_brush.ensure_batch_filter_regions_calibrated()

        self.assertIsNone(result)
        self.assertFalse(simple_brush.batch_filter_enabled)
        click.assert_called_once_with(open_filter)
        close_panel.assert_called_once_with()

    def test_batch_filter_calibration_close_failure_prevents_publish(self):
        regions = [
            simple_brush.ScreenRegion(index * 10, index * 20, 24, 24)
            for index in range(1, 5)
        ]
        simple_brush.batch_filter_calibration_requested = True
        with (
            patch.object(simple_brush, "select_screen_region", side_effect=regions),
            patch.object(simple_brush, "click_in_region"),
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(
                simple_brush,
                "close_batch_filter_panel_after_calibration",
                side_effect=RuntimeError("escape failed"),
            ) as close_panel,
        ):
            result = simple_brush.ensure_batch_filter_regions_calibrated()

        self.assertIsNone(result)
        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_enabled)
        close_panel.assert_called_once_with()

    def test_batch_filter_calibration_is_only_attempted_once(self):
        simple_brush.batch_filter_calibration_requested = True
        with patch.object(
            simple_brush,
            "select_screen_region",
            side_effect=simple_brush.CalibrationCancelled(),
        ) as select:
            self.assertIsNone(simple_brush.ensure_batch_filter_regions_calibrated())
            self.assertIsNone(simple_brush.ensure_batch_filter_regions_calibrated())
        select.assert_called_once()
        self.assertTrue(simple_brush.batch_filter_calibration_attempted)

    def test_batch_filter_calibration_escape_does_not_stop_browsing(self):
        simple_brush.batch_filter_calibration_in_progress = True
        result = simple_brush.on_press(simple_brush.keyboard.Key.esc)
        self.assertTrue(result)
        self.assertFalse(simple_brush.stop_event)

    def test_batch_filter_panel_close_uses_programmatic_escape(self):
        with patch.object(simple_brush.pyautogui, "press") as press:
            simple_brush.close_batch_filter_panel_after_calibration()
        press.assert_called_once_with("esc")
        self.assertFalse(simple_brush._programmatic_esc)

    def test_apply_batch_filter_clicks_regions_in_order(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )
        simple_brush.batch_filter_regions = regions
        simple_brush.batch_filter_enabled = True
        with (
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(simple_brush, "human_delay", return_value=True) as delay,
            patch.object(simple_brush, "safe_wait", return_value=True) as wait,
        ):
            self.assertTrue(
                simple_brush.apply_batch_filter_and_open_first_candidate()
            )

        self.assertEqual(
            click.call_args_list,
            [
                call(regions.open_filter),
                call(regions.unseen_filter),
                call(regions.confirm_filter),
                call(regions.first_candidate),
            ],
        )
        self.assertEqual(
            delay.call_args_list,
            [
                call(
                    simple_brush.FILTER_OPEN_DELAY_MIN,
                    simple_brush.FILTER_OPEN_DELAY_MAX,
                ),
                call(
                    simple_brush.FILTER_OPTION_DELAY_MIN,
                    simple_brush.FILTER_OPTION_DELAY_MAX,
                ),
                call(
                    simple_brush.FILTER_RESULTS_DELAY_MIN,
                    simple_brush.FILTER_RESULTS_DELAY_MAX,
                ),
            ],
        )
        wait.assert_called_once_with(simple_brush.CLICK_WAIT_SECONDS)

    def test_apply_batch_filter_stops_after_interrupted_wait(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )
        simple_brush.batch_filter_regions = regions
        simple_brush.batch_filter_enabled = True
        with (
            patch.object(simple_brush, "click_in_region") as click,
            patch.object(
                simple_brush,
                "human_delay",
                side_effect=[True, False],
            ),
            patch.object(simple_brush, "safe_wait") as wait,
        ):
            self.assertFalse(
                simple_brush.apply_batch_filter_and_open_first_candidate()
            )

        self.assertEqual(
            click.call_args_list,
            [call(regions.open_filter), call(regions.unseen_filter)],
        )
        wait.assert_not_called()

    def test_apply_batch_filter_exception_fails_closed(self):
        simple_brush.batch_filter_regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )
        simple_brush.batch_filter_enabled = True
        with (
            patch.object(
                simple_brush,
                "click_in_region",
                side_effect=RuntimeError("click failed"),
            ) as click,
            patch.object(simple_brush, "human_delay") as delay,
            patch.object(simple_brush, "safe_wait") as wait,
            patch.object(simple_brush.logger, "exception") as log_exception,
        ):
            self.assertFalse(
                simple_brush.apply_batch_filter_and_open_first_candidate()
            )
        click.assert_called_once_with(simple_brush.batch_filter_regions.open_filter)
        delay.assert_not_called()
        wait.assert_not_called()
        log_exception.assert_called_once()

    def test_random_focus_restore_point_uses_half_open_region_bounds(self):
        region = simple_brush.ScreenRegion(left=400, top=350, width=101, height=51)
        with patch.object(
            simple_brush.random,
            "randint",
            side_effect=[500, 400],
        ) as randint:
            self.assertEqual(simple_brush.random_point_in_region(region), (500, 400))
        self.assertEqual(
            randint.call_args_list,
            [call(400, 500), call(350, 400)],
        )

    def test_random_focus_restore_point_rejects_empty_region(self):
        with self.assertRaisesRegex(ValueError, "尺寸必须为正数"):
            simple_brush.random_point_in_region(
                simple_brush.ScreenRegion(left=400, top=350, width=0, height=51)
            )

    def test_focus_restore_calibration_is_skipped_when_not_requested(self):
        with patch.object(simple_brush, "select_screen_region") as select:
            region = simple_brush.ensure_focus_restore_region_calibrated()
        self.assertEqual(region, simple_brush.DEFAULT_FOCUS_RESTORE_REGION)
        select.assert_not_called()
        self.assertFalse(simple_brush.focus_restore_calibration_attempted)

    def test_focus_restore_calibration_updates_runtime_region(self):
        calibrated = simple_brush.ScreenRegion(left=600, top=300, width=120, height=60)
        simple_brush.focus_restore_calibration_requested = True
        with patch.object(
            simple_brush,
            "select_screen_region",
            return_value=calibrated,
        ) as select:
            self.assertEqual(
                simple_brush.ensure_focus_restore_region_calibrated(),
                calibrated,
            )
        select.assert_called_once_with(
            min_size=20,
            instruction="拖动框选候选人详情页空白区域 · Esc 使用默认区域",
            subtitle="第一版仅支持主显示器",
        )
        self.assertEqual(simple_brush.focus_restore_region, calibrated)
        self.assertTrue(simple_brush.focus_restore_calibration_attempted)
        self.assertFalse(simple_brush.focus_restore_calibration_in_progress)

    def test_cancelled_focus_restore_calibration_keeps_default_and_runs_once(self):
        simple_brush.focus_restore_calibration_requested = True
        with patch.object(
            simple_brush,
            "select_screen_region",
            side_effect=simple_brush.CalibrationCancelled,
        ) as select:
            self.assertEqual(
                simple_brush.ensure_focus_restore_region_calibrated(),
                simple_brush.DEFAULT_FOCUS_RESTORE_REGION,
            )
            self.assertEqual(
                simple_brush.ensure_focus_restore_region_calibrated(),
                simple_brush.DEFAULT_FOCUS_RESTORE_REGION,
            )
        self.assertEqual(select.call_count, 1)
        self.assertFalse(simple_brush.focus_restore_calibration_in_progress)
        self.assertFalse(simple_brush.stop_event)

    def test_failed_focus_restore_calibration_keeps_default_region(self):
        simple_brush.focus_restore_calibration_requested = True
        simple_brush.focus_restore_region = simple_brush.ScreenRegion(1, 2, 3, 4)
        with (
            patch.object(
                simple_brush,
                "select_screen_region",
                side_effect=RuntimeError("overlay failed"),
            ),
            patch.object(simple_brush.logger, "exception") as log_exception,
        ):
            region = simple_brush.ensure_focus_restore_region_calibrated()
        self.assertEqual(region, simple_brush.DEFAULT_FOCUS_RESTORE_REGION)
        self.assertTrue(simple_brush.focus_restore_calibration_attempted)
        self.assertFalse(simple_brush.focus_restore_calibration_in_progress)
        log_exception.assert_called_once()

    def test_run_resets_focus_restore_calibration_state(self):
        simple_brush.forward_click_regions = simple_brush.ForwardClickRegions(
            forward_icon=simple_brush.ScreenRegion(1, 2, 3, 4),
            email_tab=simple_brush.ScreenRegion(5, 6, 7, 8),
            input_box=simple_brush.ScreenRegion(9, 10, 11, 12),
            recent_email=simple_brush.ScreenRegion(13, 14, 15, 16),
            forward_button=simple_brush.ScreenRegion(17, 18, 19, 20),
        )
        simple_brush.forward_click_calibration_requested = True
        simple_brush.forward_click_calibration_attempted = True
        simple_brush.forward_click_calibration_in_progress = True
        simple_brush.focus_restore_region = simple_brush.ScreenRegion(1, 2, 3, 4)
        simple_brush.focus_restore_calibration_requested = True
        simple_brush.focus_restore_calibration_attempted = True
        simple_brush.focus_restore_calibration_in_progress = True
        simple_brush.batch_filter_regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(1, 2, 20, 20),
            open_filter=simple_brush.ScreenRegion(3, 4, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(5, 6, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(7, 8, 12, 12),
        )
        simple_brush.batch_filter_calibration_requested = True
        simple_brush.batch_filter_calibration_attempted = True
        simple_brush.batch_filter_calibration_in_progress = True
        simple_brush.batch_filter_enabled = True
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--duration-seconds", "invalid", "--auto"],
        ):
            self.assertEqual(simple_brush.run(), 2)
        self.assertEqual(
            simple_brush.focus_restore_region,
            simple_brush.DEFAULT_FOCUS_RESTORE_REGION,
        )
        self.assertFalse(simple_brush.focus_restore_calibration_requested)
        self.assertFalse(simple_brush.focus_restore_calibration_attempted)
        self.assertFalse(simple_brush.focus_restore_calibration_in_progress)
        self.assertEqual(
            simple_brush.forward_click_regions,
            simple_brush.DEFAULT_FORWARD_CLICK_REGIONS,
        )
        self.assertFalse(simple_brush.forward_click_calibration_requested)
        self.assertFalse(simple_brush.forward_click_calibration_attempted)
        self.assertFalse(simple_brush.forward_click_calibration_in_progress)
        self.assertIsNone(simple_brush.batch_filter_regions)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)
        self.assertFalse(simple_brush.batch_filter_calibration_attempted)
        self.assertFalse(simple_brush.batch_filter_calibration_in_progress)
        self.assertFalse(simple_brush.batch_filter_enabled)

    def test_focus_restore_calibration_escape_does_not_stop_browsing(self):
        simple_brush.focus_restore_calibration_in_progress = True
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

    def test_no_batch_filter_argument_is_parsed(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--no-batch-filter"],
        ):
            args = simple_brush.parse_args()
        self.assertTrue(args["no_batch_filter"])

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
        with patch("builtins.input", side_effect=["", "n", "invalid", "3"]):
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

    def test_auto_mode_parses_quoted_keyword_rules(self):
        simple_brush.get_user_input(
            keywords_str='"PR" and "AE"; "剪映"',
            auto=True,
        )
        self.assertTrue(simple_brush.forward_enabled)
        self.assertEqual(
            simple_brush.keyword_rule_sources(),
            ['"PR" and "AE"', '"剪映"'],
        )

    def test_auto_mode_parses_complete_not_keyword_rules(self):
        simple_brush.get_user_input(
            keywords_str='"A" or not "B" and "C"',
            auto=True,
        )
        self.assertTrue(simple_brush.forward_enabled)
        self.assertEqual(
            simple_brush.keyword_rule_sources(),
            ['"A" or not "B" and "C"'],
        )

    def test_auto_mode_rejects_unquoted_legacy_keywords(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--keywords", "Python;短剧", "--auto"],
        ), patch.object(simple_brush, "bring_edge_foreground") as bring_edge:
            self.assertEqual(simple_brush.run(), 2)
        bring_edge.assert_not_called()

    def test_auto_mode_rejects_pure_not_branch_before_opening_edge(self):
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--keywords", 'not "销售" or "短剧"', "--auto"],
        ), patch.object(simple_brush, "bring_edge_foreground") as bring_edge:
            self.assertEqual(simple_brush.run(), 2)
        bring_edge.assert_not_called()

    def test_interactive_keyword_rules_retry_invalid_input(self):
        with patch(
            "builtins.input",
            side_effect=["Python", '"Python" or "短剧"', "n", "n", ""],
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(
            simple_brush.keyword_rule_sources(),
            ['"Python" or "短剧"'],
        )

    def test_interactive_keyword_rules_retry_pure_not_branch(self):
        with patch(
            "builtins.input",
            side_effect=[
                'not "销售"',
                '"短剧" and not "销售"',
                "n",
                "n",
                "",
            ],
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(
            simple_brush.keyword_rule_sources(),
            ['"短剧" and not "销售"'],
        )

    def test_interactive_mode_can_request_focus_restore_calibration(self):
        with patch(
            "builtins.input",
            side_effect=['"Python"', "y", "n", ""],
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertTrue(simple_brush.focus_restore_calibration_requested)
        self.assertTrue(simple_brush.forward_click_calibration_requested)

    def test_interactive_mode_defaults_to_focus_restore_region_fallback(self):
        with patch(
            "builtins.input",
            side_effect=['"Python"', "", "n", ""],
        ):
            simple_brush.get_user_input(no_forward=True)
        self.assertFalse(simple_brush.focus_restore_calibration_requested)
        self.assertFalse(simple_brush.forward_click_calibration_requested)

    def test_auto_mode_never_prompts_for_focus_restore_calibration(self):
        simple_brush.focus_restore_calibration_requested = True
        simple_brush.forward_click_calibration_requested = True
        simple_brush.batch_filter_calibration_requested = True
        with patch("builtins.input") as user_input:
            simple_brush.get_user_input(keywords_str='"Python"', auto=True)
        user_input.assert_not_called()
        self.assertFalse(simple_brush.focus_restore_calibration_requested)
        self.assertFalse(simple_brush.forward_click_calibration_requested)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_interactive_mode_without_keywords_does_not_offer_forward_calibration(self):
        with patch("builtins.input", side_effect=["", "n", ""]) as user_input:
            simple_brush.get_user_input(no_forward=True)
        self.assertEqual(user_input.call_count, 3)
        self.assertFalse(simple_brush.forward_click_calibration_requested)
        self.assertFalse(simple_brush.focus_restore_calibration_requested)

    def test_no_keywords_and_no_forward_can_request_batch_filter_calibration(self):
        with patch("builtins.input", side_effect=["", "y", ""]):
            simple_brush.get_user_input(no_forward=True)
        self.assertTrue(simple_brush.batch_filter_calibration_requested)

    def test_no_batch_filter_skips_prompt_in_interactive_mode(self):
        with patch("builtins.input", side_effect=["", ""]) as user_input:
            simple_brush.get_user_input(
                no_forward=True,
                no_batch_filter=True,
            )
        self.assertEqual(user_input.call_count, 2)
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_cli_keywords_noninteractive_mode_never_prompts_for_batch_filter(self):
        simple_brush.batch_filter_calibration_requested = True
        with patch("builtins.input") as user_input:
            simple_brush.get_user_input(keywords_str='"Python"')
        user_input.assert_not_called()
        self.assertFalse(simple_brush.batch_filter_calibration_requested)

    def test_run_calibrates_after_first_detail_opens_before_viewing(self):
        events = []

        def configure_input(**_kwargs):
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True

        def open_detail(_x, _y):
            events.append("detail")
            return True

        def calibrate():
            events.append("focus_calibrate")
            return simple_brush.DEFAULT_FOCUS_RESTORE_REGION

        def calibrate_forward():
            events.append("forward_calibrate")
            return simple_brush.DEFAULT_FORWARD_CLICK_REGIONS

        def calibrate_ocr():
            events.append("ocr_calibrate")
            return True

        def start_timer(_duration):
            events.append("timer_start")
            return None

        def view(_index):
            events.append("view")
            return False

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "click_first_candidate", side_effect=open_detail),
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
                side_effect=calibrate,
            ) as ensure,
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
                side_effect=calibrate_forward,
            ) as ensure_forward,
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                side_effect=calibrate_ocr,
            ) as ensure_ocr,
            patch.object(simple_brush, "start_run_timer", side_effect=start_timer),
            patch.object(simple_brush, "view_candidate", side_effect=view),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)
        self.assertEqual(
            events,
            [
                "detail",
                "focus_calibrate",
                "forward_calibrate",
                "ocr_calibrate",
                "timer_start",
                "view",
            ],
        )
        ensure.assert_called_once_with()
        ensure_forward.assert_called_once_with()
        ensure_ocr.assert_called_once_with()

    def test_run_does_not_calibrate_when_first_detail_fails_to_open(self):
        def configure_input(**_kwargs):
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(simple_brush, "click_first_candidate", return_value=False),
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
            ) as ensure,
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
            ) as ensure_forward,
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
            ) as ensure_ocr,
            patch.object(simple_brush, "start_run_timer") as start_timer,
        ):
            self.assertEqual(simple_brush.run(), 0)
        ensure.assert_not_called()
        ensure_forward.assert_not_called()
        ensure_ocr.assert_not_called()
        start_timer.assert_not_called()

    def test_run_batch_filter_success_prepares_before_timer_and_view(self):
        events = []
        timer = Mock()
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.batch_filter_calibration_requested = True
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True
            simple_brush.forward_enabled = True

        def calibrate_batch():
            events.append("batch_calibrate")
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True
            return regions

        def record(name, result=True):
            def action(*_args, **_kwargs):
                events.append(name)
                return result
            return action

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(
                simple_brush,
                "ensure_batch_filter_regions_calibrated",
                side_effect=calibrate_batch,
            ),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                side_effect=record("apply_filter"),
            ),
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(15, 25),
            ),
            patch.object(simple_brush.pyautogui, "position") as position,
            patch.object(simple_brush, "click_first_candidate") as legacy_click,
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
                side_effect=record("focus_calibrate"),
            ),
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
                side_effect=record("forward_calibrate"),
            ),
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                side_effect=record("ocr_calibrate"),
            ),
            patch.object(
                simple_brush,
                "start_run_timer",
                side_effect=record("timer_start", timer),
            ),
            patch.object(
                simple_brush,
                "view_candidate",
                side_effect=record("view", False),
            ),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            events,
            [
                "batch_calibrate",
                "apply_filter",
                "focus_calibrate",
                "forward_calibrate",
                "ocr_calibrate",
                "timer_start",
                "view",
            ],
        )
        position.assert_not_called()
        legacy_click.assert_not_called()
        timer.cancel.assert_called_once_with()

    def test_run_first_batch_filter_failure_stops_before_calibration_and_timer(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.batch_filter_calibration_requested = True
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True

        def calibrate_batch():
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True
            return regions

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(
                simple_brush,
                "ensure_batch_filter_regions_calibrated",
                side_effect=calibrate_batch,
            ),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                return_value=False,
            ),
            patch.object(simple_brush.pyautogui, "position") as position,
            patch.object(simple_brush, "click_first_candidate") as legacy_click,
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
            ) as focus_calibrate,
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
            ) as forward_calibrate,
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
            ) as ocr_calibrate,
            patch.object(simple_brush, "start_run_timer") as start_timer,
            patch.object(simple_brush, "view_candidate") as view,
        ):
            self.assertEqual(simple_brush.run(), 0)

        position.assert_not_called()
        legacy_click.assert_not_called()
        focus_calibrate.assert_not_called()
        forward_calibrate.assert_not_called()
        ocr_calibrate.assert_not_called()
        start_timer.assert_not_called()
        view.assert_not_called()

    def test_run_batch_filter_fallback_starts_timer_after_legacy_preparation(self):
        events = []
        timer = Mock()

        def configure_input(**_kwargs):
            simple_brush.batch_filter_calibration_requested = True
            simple_brush.focus_restore_calibration_requested = True
            simple_brush.forward_click_calibration_requested = True
            simple_brush.forward_enabled = True

        def calibrate_batch():
            events.append("batch_calibrate")
            simple_brush.batch_filter_regions = None
            simple_brush.batch_filter_enabled = False

        def record(name, result=True):
            def action(*_args, **_kwargs):
                events.append(name)
                return result
            return action

        with (
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush, "initialize_ocr"),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(
                simple_brush,
                "ensure_batch_filter_regions_calibrated",
                side_effect=calibrate_batch,
            ),
            patch.object(simple_brush, "safe_wait", side_effect=record("countdown")),
            patch.object(
                simple_brush.pyautogui,
                "position",
                side_effect=record("position", (10, 20)),
            ),
            patch.object(
                simple_brush,
                "click_first_candidate",
                side_effect=record("legacy_click"),
            ),
            patch.object(
                simple_brush,
                "ensure_focus_restore_region_calibrated",
                side_effect=record("focus_calibrate"),
            ),
            patch.object(
                simple_brush,
                "ensure_forward_click_regions_calibrated",
                side_effect=record("forward_calibrate"),
            ),
            patch.object(
                simple_brush,
                "ensure_ocr_region_calibrated",
                side_effect=record("ocr_calibrate"),
            ),
            patch.object(
                simple_brush,
                "start_run_timer",
                side_effect=record("timer_start", timer),
            ),
            patch.object(
                simple_brush,
                "view_candidate",
                side_effect=record("view", False),
            ),
            patch.object(simple_brush, "refresh_page", return_value=False),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            events,
            [
                "batch_calibrate",
                "countdown",
                "position",
                "legacy_click",
                "focus_calibrate",
                "forward_calibrate",
                "ocr_calibrate",
                "timer_start",
                "view",
            ],
        )
        timer.cancel.assert_called_once_with()

    def test_run_reapplies_batch_filter_after_refresh_before_next_batch(self):
        events = []
        view_calls = 0
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = False
            simple_brush.forward_keywords = []
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True

        def apply_filter():
            events.append("apply_filter")
            return True

        def view(index):
            nonlocal view_calls
            view_calls += 1
            events.append(f"view({index})")
            if view_calls == 3:
                simple_brush.stop_event = True
                return False
            return True

        def next_candidate():
            events.append("next")
            return True

        def refresh():
            self.assertEqual(simple_brush.forward_consecutive, 0)
            events.append("refresh")
            return True

        def start_timer(_duration):
            events.append("timer_start")
            return None

        with (
            patch.object(simple_brush, "BATCH_SIZE", 2),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                side_effect=apply_filter,
            ),
            patch.object(simple_brush, "start_run_timer", side_effect=start_timer),
            patch.object(simple_brush, "view_candidate", side_effect=view),
            patch.object(simple_brush, "next_candidate", side_effect=next_candidate),
            patch.object(simple_brush, "refresh_page", side_effect=refresh),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            events,
            [
                "apply_filter",
                "timer_start",
                "view(0)",
                "next",
                "view(1)",
                "refresh",
                "apply_filter",
                "view(0)",
            ],
        )

    def test_run_does_not_filter_next_batch_when_refresh_fails(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = False
            simple_brush.forward_keywords = []
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True

        with (
            patch.object(simple_brush, "BATCH_SIZE", 1),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                return_value=True,
            ) as apply_filter,
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(simple_brush, "view_candidate", return_value=True) as view,
            patch.object(simple_brush, "refresh_page", return_value=False) as refresh,
        ):
            self.assertEqual(simple_brush.run(), 0)

        apply_filter.assert_called_once_with()
        view.assert_called_once_with(0)
        refresh.assert_called_once_with()

    def test_run_stops_before_next_view_when_batch_filter_reapply_fails(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 20, 30, 40),
            open_filter=simple_brush.ScreenRegion(50, 60, 12, 12),
            unseen_filter=simple_brush.ScreenRegion(70, 80, 12, 12),
            confirm_filter=simple_brush.ScreenRegion(90, 100, 12, 12),
        )

        def configure_input(**_kwargs):
            simple_brush.forward_enabled = False
            simple_brush.forward_keywords = []
            simple_brush.batch_filter_regions = regions
            simple_brush.batch_filter_enabled = True

        with (
            patch.object(simple_brush, "BATCH_SIZE", 1),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(
                simple_brush,
                "apply_batch_filter_and_open_first_candidate",
                side_effect=[True, False],
            ) as apply_filter,
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(simple_brush, "view_candidate", return_value=True) as view,
            patch.object(simple_brush, "refresh_page", return_value=True) as refresh,
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(apply_filter.call_count, 2)
        view.assert_called_once_with(0)
        refresh.assert_called_once_with()

    def test_run_legacy_path_reuses_same_point_after_refresh(self):
        def configure_input(**_kwargs):
            simple_brush.forward_enabled = False
            simple_brush.forward_keywords = []
            simple_brush.batch_filter_enabled = False

        with (
            patch.object(simple_brush, "BATCH_SIZE", 1),
            patch.object(simple_brush, "parse_args", return_value={
                "keywords": "",
                "email": "",
                "duration_seconds": "",
                "no_forward": True,
                "auto": False,
            }),
            patch.object(simple_brush, "get_user_input", side_effect=configure_input),
            patch.object(simple_brush.listener, "start"),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "position", return_value=(10, 20)),
            patch.object(
                simple_brush,
                "click_first_candidate",
                side_effect=[True, False],
            ) as legacy_click,
            patch.object(simple_brush, "start_run_timer", return_value=None),
            patch.object(simple_brush, "view_candidate", return_value=True),
            patch.object(simple_brush, "refresh_page", return_value=True),
        ):
            self.assertEqual(simple_brush.run(), 0)

        self.assertEqual(
            legacy_click.call_args_list,
            [call(10, 20), call(10, 20)],
        )

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

    def test_run_does_not_start_timer_when_countdown_is_interrupted(self):
        with (
            patch.object(
                simple_brush.sys,
                "argv",
                ["simple_brush.py", "--duration-seconds", "5", "--auto"],
            ),
            patch.object(
                simple_brush,
                "prepare_browser",
                return_value=WINDOWS_BROWSER_READY,
            ),
            patch.object(simple_brush, "start_run_timer") as start_timer,
            patch.object(simple_brush, "safe_wait", return_value=False),
            patch.object(simple_brush.listener, "start"),
        ):
            self.assertEqual(simple_brush.run(), 0)
        start_timer.assert_not_called()

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
