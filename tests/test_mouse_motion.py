import importlib.util
import math
import sys
import unittest
from unittest.mock import MagicMock, call, patch

import mouse_motion
import simple_brush


def midpoint(low, high):
    return (low + high) / 2.0


class HumanMouseMotionTests(unittest.TestCase):
    def setUp(self):
        self.saved_simple_mouse_enabled = simple_brush.simple_mouse_enabled
        self.saved_unavailable_warning = (
            simple_brush._windmouse_unavailable_warning_logged
        )
        simple_brush.simple_mouse_enabled = False
        simple_brush._windmouse_unavailable_warning_logged = False

    def tearDown(self):
        simple_brush.simple_mouse_enabled = self.saved_simple_mouse_enabled
        simple_brush._windmouse_unavailable_warning_logged = (
            self.saved_unavailable_warning
        )

    def move_patches(self, *, start=(0, 0), uniform=midpoint):
        return (
            patch.object(simple_brush.pyautogui, "position", return_value=start),
            patch.object(simple_brush.pyautogui, "moveTo"),
            patch.object(simple_brush.time, "sleep"),
            patch.object(simple_brush.random, "uniform", side_effect=uniform),
            patch.object(simple_brush.random, "choice", return_value=1.0),
        )

    def test_bezier_move_uses_intermediate_points_and_exact_integer_target(self):
        position_patch, move_patch, sleep_patch, uniform_patch, choice_patch = (
            self.move_patches(start=(10, 20))
        )
        with (
            position_patch as position,
            move_patch as move,
            sleep_patch as sleep,
            uniform_patch,
            choice_patch,
        ):
            simple_brush.move_to_bezier_fallback(410.4, 220.6)

        position.assert_called_once_with()
        self.assertGreater(move.call_count, 2)
        self.assertEqual(move.call_args_list[-1], call(410, 221, duration=0))
        self.assertEqual(sleep.call_count, move.call_count - 1)
        for movement in move.call_args_list:
            self.assertIsInstance(movement.args[0], int)
            self.assertIsInstance(movement.args[1], int)

    def test_easing_has_shorter_endpoint_steps_than_middle_steps(self):
        position_patch, move_patch, sleep_patch, uniform_patch, choice_patch = (
            self.move_patches(start=(0, 0))
        )
        with (
            position_patch,
            move_patch as move,
            sleep_patch,
            uniform_patch,
            choice_patch,
        ):
            simple_brush.move_to_bezier_fallback(600, 0)

        points = [(0, 0)] + [entry.args[:2] for entry in move.call_args_list]
        distances = [
            math.hypot(end[0] - start[0], end[1] - start[1])
            for start, end in zip(points, points[1:])
        ]
        middle = distances[len(distances) // 2]
        self.assertLess(distances[0], middle)
        self.assertLess(distances[-1], middle)

    def test_intermediate_jitter_never_changes_forced_target(self):
        def maximum(low, high):
            return high

        position_patch, move_patch, sleep_patch, uniform_patch, choice_patch = (
            self.move_patches(start=(50, 50), uniform=maximum)
        )
        with (
            position_patch,
            move_patch as move,
            sleep_patch,
            uniform_patch,
            choice_patch,
        ):
            simple_brush.move_to_bezier_fallback(500, 300)

        self.assertEqual(move.call_args_list[-1], call(500, 300, duration=0))
        self.assertGreater(len(set(entry.args[:2] for entry in move.call_args_list)), 2)

    def test_zero_distance_moves_exactly_once_without_sleep_or_randomness(self):
        position_patch, move_patch, sleep_patch, uniform_patch, choice_patch = (
            self.move_patches(start=(25, 30))
        )
        with (
            position_patch,
            move_patch as move,
            sleep_patch as sleep,
            uniform_patch as uniform,
            choice_patch as choice,
        ):
            simple_brush.move_to_bezier_fallback(25, 30)

        move.assert_called_once_with(25, 30, duration=0)
        sleep.assert_not_called()
        uniform.assert_not_called()
        choice.assert_not_called()

    def test_very_short_distance_stays_stable_without_curve_randomness(self):
        position_patch, move_patch, sleep_patch, uniform_patch, choice_patch = (
            self.move_patches(start=(10, 10))
        )
        with (
            position_patch,
            move_patch as move,
            sleep_patch,
            uniform_patch as uniform,
            choice_patch as choice,
        ):
            simple_brush.move_to_bezier_fallback(13, 14)

        self.assertEqual(move.call_args_list[-1], call(13, 14, duration=0))
        uniform.assert_not_called()
        choice.assert_not_called()
        self.assertEqual(move.call_count, simple_brush.MOUSE_MOVE_MIN_STEPS)

    def test_distance_calculation_respects_step_bounds(self):
        for target, expected_steps in (
            ((20, 0), simple_brush.MOUSE_MOVE_MIN_STEPS),
            ((10000, 0), simple_brush.MOUSE_MOVE_MAX_STEPS),
        ):
            with self.subTest(target=target):
                patches = self.move_patches(start=(0, 0))
                with (
                    patches[0],
                    patches[1] as move,
                    patches[2],
                    patches[3],
                    patches[4],
                ):
                    simple_brush.move_to_bezier_fallback(*target)
                self.assertEqual(move.call_count, expected_steps)

    def test_move_exception_propagates_and_stops_the_path(self):
        with (
            patch.object(simple_brush.pyautogui, "position", return_value=(0, 0)),
            patch.object(
                simple_brush.pyautogui,
                "moveTo",
                side_effect=RuntimeError("move failed"),
            ) as move,
            patch.object(simple_brush.time, "sleep") as sleep,
            patch.object(simple_brush.random, "uniform", side_effect=midpoint),
            patch.object(simple_brush.random, "choice", return_value=1.0),
        ):
            with self.assertRaisesRegex(RuntimeError, "move failed"):
                simple_brush.move_to_bezier_fallback(200, 100)

        move.assert_called_once()
        sleep.assert_not_called()

    def test_default_mode_uses_windmouse_branch(self):
        with (
            patch.object(simple_brush, "windmouse_available", return_value=True),
            patch.object(simple_brush, "move_to_observable") as windmouse_move,
            patch.object(simple_brush, "move_to_bezier_fallback") as fallback,
        ):
            simple_brush.human_move_to(20.2, 30.8)

        windmouse_move.assert_called_once_with(20, 31)
        fallback.assert_not_called()

    def test_missing_windmouse_logs_once_and_uses_bezier_fallback(self):
        with (
            patch.object(simple_brush, "windmouse_available", return_value=False),
            patch.object(
                simple_brush,
                "windmouse_unavailable_reason",
                return_value="ImportError: missing",
            ),
            patch.object(simple_brush, "move_to_bezier_fallback") as fallback,
            patch.object(simple_brush.logger, "warning") as warning,
        ):
            simple_brush.human_move_to(10, 11)
            simple_brush.human_move_to(12, 13)

        self.assertEqual(
            fallback.call_args_list,
            [call(10, 11), call(12, 13)],
        )
        warning.assert_called_once()
        self.assertIn("ImportError: missing", warning.call_args.args[1])

    def test_mouse_motion_module_loads_when_windmouse_is_missing(self):
        spec = importlib.util.spec_from_file_location(
            "mouse_motion_without_windmouse",
            mouse_motion.__file__,
        )
        isolated_module = importlib.util.module_from_spec(spec)
        with patch.dict(
            sys.modules,
            {
                "windmouse": None,
                "windmouse.pyautogui_controller": None,
            },
        ):
            spec.loader.exec_module(isolated_module)

        self.assertFalse(isolated_module.windmouse_available())
        with self.assertRaises(isolated_module.WindMouseUnavailableError):
            isolated_module.move_to_observable(10, 20)

    def test_windmouse_exception_logs_warning_and_uses_bezier_fallback(self):
        with (
            patch.object(simple_brush, "windmouse_available", return_value=True),
            patch.object(
                simple_brush,
                "move_to_observable",
                side_effect=RuntimeError("controller failed"),
            ),
            patch.object(simple_brush, "move_to_bezier_fallback") as fallback,
            patch.object(simple_brush.logger, "warning") as warning,
        ):
            simple_brush.human_move_to(10.4, 20.6)

        fallback.assert_called_once_with(10, 21)
        warning.assert_called_once()
        self.assertIn("controller failed", warning.call_args.args[1].args[0])

    def test_windmouse_short_distance_uses_one_stable_segment(self):
        controller = MagicMock()
        with (
            patch.object(
                mouse_motion,
                "PyautoguiMouseController",
                return_value=controller,
            ) as controller_class,
            patch.object(mouse_motion, "Coordinate", side_effect=lambda value: value),
            patch.object(
                mouse_motion.pyautogui,
                "position",
                return_value=(0, 0),
            ) as position,
            patch.object(mouse_motion.pyautogui, "moveTo") as final_move,
        ):
            mouse_motion.move_to_observable(299, 0)

        position.assert_called_once_with()
        controller_class.assert_called_once_with(
            gravity_magnitude=10,
            wind_magnitude=0,
            max_step=16,
            damped_distance=12,
        )
        self.assertEqual(controller.dest_position, (299, 0))
        controller.move_to_target.assert_called_once_with(
            tick_delay=0,
            step_duration=0,
        )
        final_move.assert_called_once_with(299, 0, duration=0)

    def assert_two_stage_approach(
        self,
        target_x,
        expected_pre_target_x,
        *,
        region_width=None,
        region_height=None,
    ):
        approach = MagicMock()
        finish = MagicMock()
        with (
            patch.object(
                mouse_motion,
                "PyautoguiMouseController",
                side_effect=[approach, finish],
            ) as controller_class,
            patch.object(mouse_motion, "Coordinate", side_effect=lambda value: value),
            patch.object(mouse_motion.pyautogui, "position", return_value=(0, 0)),
            patch.object(mouse_motion.pyautogui, "moveTo") as final_move,
        ):
            mouse_motion.move_to_observable(
                target_x,
                0,
                region_width=region_width,
                region_height=region_height,
            )

        self.assertEqual(
            controller_class.call_args_list,
            [
                call(
                    gravity_magnitude=20,
                    wind_magnitude=3,
                    max_step=45,
                    damped_distance=24,
                ),
                call(
                    gravity_magnitude=10,
                    wind_magnitude=0,
                    max_step=18,
                    damped_distance=18,
                ),
            ],
        )
        self.assertEqual(approach.dest_position, (expected_pre_target_x, 0))
        self.assertEqual(finish.dest_position, (target_x, 0))
        approach.move_to_target.assert_called_once_with(
            tick_delay=0,
            step_duration=0,
        )
        finish.move_to_target.assert_called_once_with(
            tick_delay=0,
            step_duration=0,
        )
        final_move.assert_called_once_with(target_x, 0, duration=0)

    def test_normal_far_distance_uses_60_to_120_pixel_approach(self):
        for target_x, expected_pre_target_x in ((300, 240), (2000, 1880)):
            with self.subTest(target_x=target_x):
                self.assert_two_stage_approach(target_x, expected_pre_target_x)

    def test_small_region_far_distance_uses_80_to_140_pixel_approach(self):
        for target_x, expected_pre_target_x in ((300, 220), (2000, 1860)):
            with self.subTest(target_x=target_x):
                self.assert_two_stage_approach(
                    target_x,
                    expected_pre_target_x,
                    region_width=80,
                    region_height=100,
                )

    def assert_windmouse_segment_failure_falls_back(self, failing_segment):
        approach = MagicMock()
        finish = MagicMock()
        failed_controller = approach if failing_segment == 1 else finish
        failed_controller.move_to_target.side_effect = RuntimeError(
            f"segment {failing_segment} failed"
        )
        with (
            patch.object(simple_brush, "windmouse_available", return_value=True),
            patch.object(
                mouse_motion,
                "PyautoguiMouseController",
                side_effect=[approach, finish],
            ) as controller_class,
            patch.object(mouse_motion, "Coordinate", side_effect=lambda value: value),
            patch.object(mouse_motion.pyautogui, "position", return_value=(0, 0)),
            patch.object(mouse_motion.pyautogui, "moveTo") as final_move,
            patch.object(simple_brush, "move_to_bezier_fallback") as fallback,
            patch.object(simple_brush.logger, "warning") as warning,
        ):
            simple_brush.human_move_to(1000, 0)

        self.assertEqual(controller_class.call_count, failing_segment)
        fallback.assert_called_once_with(1000, 0)
        final_move.assert_not_called()
        warning.assert_called_once()
        self.assertIn(
            f"segment {failing_segment} failed",
            str(warning.call_args.args[1]),
        )

    def test_first_windmouse_segment_failure_uses_bezier_fallback(self):
        self.assert_windmouse_segment_failure_falls_back(1)

    def test_second_windmouse_segment_failure_uses_bezier_fallback(self):
        self.assert_windmouse_segment_failure_falls_back(2)

    def test_simple_argument_keeps_single_legacy_move_available(self):
        with (
            patch.object(simple_brush.pyautogui, "position") as position,
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.time, "sleep") as sleep,
            patch.object(simple_brush.random, "uniform", return_value=0.25) as uniform,
            patch.object(simple_brush.random, "choice") as choice,
            patch.object(simple_brush, "move_to_observable") as windmouse_move,
        ):
            simple_brush.human_move_to(
                20.2,
                30.8,
                simple=True,
                region_width=10,
                region_height=10,
            )

        move.assert_called_once_with(20, 31, duration=0.25)
        uniform.assert_called_once_with(0.15, 0.35)
        position.assert_not_called()
        sleep.assert_not_called()
        choice.assert_not_called()
        windmouse_move.assert_not_called()

    def test_default_mode_reads_simple_mouse_runtime_state(self):
        simple_brush.simple_mouse_enabled = True
        with (
            patch.object(simple_brush.pyautogui, "position") as position,
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.time, "sleep") as sleep,
            patch.object(simple_brush.random, "uniform", return_value=0.20),
            patch.object(simple_brush.random, "choice") as choice,
            patch.object(simple_brush, "move_to_observable") as windmouse_move,
        ):
            simple_brush.human_move_to(80, 90)

        move.assert_called_once_with(80, 90, duration=0.20)
        position.assert_not_called()
        sleep.assert_not_called()
        choice.assert_not_called()
        windmouse_move.assert_not_called()

    def test_human_click_reuses_move_target_for_press_and_release(self):
        with (
            patch.object(simple_brush.random, "randint", side_effect=[3, -2]),
            patch.object(simple_brush.random, "uniform", return_value=0.05),
            patch.object(simple_brush, "human_move_to") as move,
            patch.object(simple_brush.pyautogui, "mouseDown") as mouse_down,
            patch.object(simple_brush.pyautogui, "mouseUp") as mouse_up,
            patch.object(simple_brush.time, "sleep") as sleep,
        ):
            simple_brush.human_click(100, 200, offset=5)

        move.assert_called_once_with(103, 198)
        mouse_down.assert_called_once_with(103, 198)
        mouse_up.assert_called_once_with(103, 198)
        self.assertEqual(sleep.call_count, 2)

    def test_human_click_with_zero_offset_keeps_exact_target(self):
        with (
            patch.object(simple_brush.random, "randint", return_value=0) as randint,
            patch.object(simple_brush.random, "uniform", return_value=0.05),
            patch.object(simple_brush, "human_move_to") as move,
            patch.object(simple_brush.pyautogui, "mouseDown") as mouse_down,
            patch.object(simple_brush.pyautogui, "mouseUp") as mouse_up,
            patch.object(simple_brush.time, "sleep"),
        ):
            simple_brush.human_click(
                12,
                24,
                offset=0,
                region_width=30,
                region_height=40,
            )

        self.assertEqual(randint.call_args_list, [call(0, 0), call(0, 0)])
        move.assert_called_once_with(
            12,
            24,
            region_width=30,
            region_height=40,
        )
        mouse_down.assert_called_once_with(12, 24)
        mouse_up.assert_called_once_with(12, 24)

    def test_human_click_rounds_once_and_clicks_one_integer_target(self):
        with (
            patch.object(simple_brush.random, "randint", return_value=0),
            patch.object(simple_brush.random, "uniform", return_value=0.05),
            patch.object(simple_brush, "human_move_to") as move,
            patch.object(simple_brush.pyautogui, "mouseDown") as mouse_down,
            patch.object(simple_brush.pyautogui, "mouseUp") as mouse_up,
            patch.object(simple_brush.time, "sleep"),
        ):
            simple_brush.human_click(12.4, 24.6, offset=0)

        move.assert_called_once_with(12, 25)
        mouse_down.assert_called_once_with(12, 25)
        mouse_up.assert_called_once_with(12, 25)

    def test_human_click_does_not_press_when_movement_fails(self):
        with (
            patch.object(simple_brush.random, "randint", return_value=0),
            patch.object(
                simple_brush,
                "human_move_to",
                side_effect=RuntimeError("move failed"),
            ),
            patch.object(simple_brush.pyautogui, "mouseDown") as mouse_down,
            patch.object(simple_brush.pyautogui, "mouseUp") as mouse_up,
            patch.object(simple_brush.time, "sleep") as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "move failed"):
                simple_brush.human_click(12, 24, offset=0)

        mouse_down.assert_not_called()
        mouse_up.assert_not_called()
        sleep.assert_not_called()

    def test_simple_mouse_argument_is_parsed_and_defaults_off(self):
        with patch.object(simple_brush.sys, "argv", ["simple_brush.py"]):
            default_args = simple_brush.parse_args()
        with patch.object(
            simple_brush.sys,
            "argv",
            ["simple_brush.py", "--simple-mouse", "--no-forward"],
        ):
            simple_args = simple_brush.parse_args()

        self.assertFalse(default_args["simple_mouse"])
        self.assertTrue(simple_args["simple_mouse"])
        self.assertTrue(simple_args["no_forward"])

    def test_run_resets_simple_mouse_state_before_input_failure(self):
        simple_brush.simple_mouse_enabled = True
        with (
            patch.object(simple_brush, "parse_args", side_effect=ValueError("bad args")),
            patch.object(simple_brush, "reset_focus_restore_calibration"),
            patch.object(simple_brush, "reset_forward_click_calibration"),
            patch.object(simple_brush, "reset_batch_filter_calibration"),
        ):
            result = simple_brush.run()

        self.assertEqual(result, 2)
        self.assertFalse(simple_brush.simple_mouse_enabled)

    def test_region_click_routes_one_exact_point_through_human_click(self):
        region = simple_brush.ScreenRegion(left=10, top=20, width=30, height=40)
        with (
            patch.object(
                simple_brush,
                "random_point_in_region",
                return_value=(22, 35),
            ) as choose_point,
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush.pyautogui, "click") as direct_click,
        ):
            simple_brush.click_in_region(region)

        choose_point.assert_called_once_with(region)
        click.assert_called_once_with(
            22,
            35,
            offset=0,
            region_width=30,
            region_height=40,
        )
        direct_click.assert_not_called()

    def test_batch_filter_region_path_reaches_human_click_in_order(self):
        regions = simple_brush.BatchFilterRegions(
            first_candidate=simple_brush.ScreenRegion(10, 10, 10, 10),
            open_filter=simple_brush.ScreenRegion(20, 20, 10, 10),
            unseen_filter=simple_brush.ScreenRegion(30, 30, 10, 10),
            confirm_filter=simple_brush.ScreenRegion(40, 40, 10, 10),
        )
        selected_points = [(21, 21), (31, 31), (41, 41), (11, 11)]
        with (
            patch.object(simple_brush, "stop_event", False),
            patch.object(simple_brush, "batch_filter_enabled", True),
            patch.object(simple_brush, "batch_filter_regions", regions),
            patch.object(
                simple_brush,
                "random_point_in_region",
                side_effect=selected_points,
            ) as choose_point,
            patch.object(simple_brush, "human_click") as click,
            patch.object(simple_brush, "human_delay", return_value=True),
            patch.object(simple_brush, "safe_wait", return_value=True),
            patch.object(simple_brush.pyautogui, "click") as direct_click,
        ):
            result = simple_brush.apply_batch_filter_and_open_first_candidate()

        self.assertTrue(result)
        self.assertEqual(
            choose_point.call_args_list,
            [
                call(regions.open_filter),
                call(regions.unseen_filter),
                call(regions.confirm_filter),
                call(regions.first_candidate),
            ],
        )
        self.assertEqual(
            click.call_args_list,
            [
                call(21, 21, offset=0, region_width=10, region_height=10),
                call(31, 31, offset=0, region_width=10, region_height=10),
                call(41, 41, offset=0, region_width=10, region_height=10),
                call(11, 11, offset=0, region_width=10, region_height=10),
            ],
        )
        direct_click.assert_not_called()

    def test_legacy_first_candidate_keeps_direct_click_boundary(self):
        with (
            patch.object(simple_brush, "stop_event", False),
            patch.object(simple_brush.pyautogui, "click") as direct_click,
            patch.object(simple_brush, "human_click") as human_click,
            patch.object(simple_brush, "human_move_to") as human_move,
            patch.object(simple_brush, "safe_wait", return_value=True) as wait,
        ):
            result = simple_brush.click_first_candidate(100, 200)

        self.assertTrue(result)
        direct_click.assert_called_once_with(100, 200, duration=0)
        human_click.assert_not_called()
        human_move.assert_not_called()
        wait.assert_called_once_with(simple_brush.CLICK_WAIT_SECONDS)

    def test_simple_mouse_is_compatible_with_existing_cli_flags(self):
        argv = [
            "simple_brush.py",
            "--keywords",
            '"Python"',
            "--email",
            "backup@example.com",
            "--duration-seconds",
            "60",
            "--no-forward",
            "--no-batch-filter",
            "--simple-mouse",
            "--auto",
        ]
        with patch.object(simple_brush.sys, "argv", argv):
            args = simple_brush.parse_args()

        self.assertEqual(args["keywords"], '"Python"')
        self.assertEqual(args["email"], "backup@example.com")
        self.assertEqual(args["duration_seconds"], "60")
        self.assertTrue(args["no_forward"])
        self.assertTrue(args["no_batch_filter"])
        self.assertTrue(args["simple_mouse"])
        self.assertTrue(args["auto"])


if __name__ == "__main__":
    unittest.main()
