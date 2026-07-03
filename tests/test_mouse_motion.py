import math
import unittest
from unittest.mock import call, patch

import simple_brush


def midpoint(low, high):
    return (low + high) / 2.0


class HumanMouseMotionTests(unittest.TestCase):
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
            simple_brush.human_move_to(410.4, 220.6)

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
            simple_brush.human_move_to(600, 0)

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
            simple_brush.human_move_to(500, 300)

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
            simple_brush.human_move_to(25, 30)

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
            simple_brush.human_move_to(13, 14)

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
                    simple_brush.human_move_to(*target)
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
                simple_brush.human_move_to(200, 100)

        move.assert_called_once()
        sleep.assert_not_called()

    def test_simple_argument_keeps_single_legacy_move_available(self):
        with (
            patch.object(simple_brush.pyautogui, "position") as position,
            patch.object(simple_brush.pyautogui, "moveTo") as move,
            patch.object(simple_brush.time, "sleep") as sleep,
            patch.object(simple_brush.random, "uniform", return_value=0.25) as uniform,
            patch.object(simple_brush.random, "choice") as choice,
        ):
            simple_brush.human_move_to(20.2, 30.8, simple=True)

        move.assert_called_once_with(20, 31, duration=0.25)
        uniform.assert_called_once_with(0.15, 0.35)
        position.assert_not_called()
        sleep.assert_not_called()
        choice.assert_not_called()


if __name__ == "__main__":
    unittest.main()
