import unittest
from unittest.mock import Mock, call, patch

import mouse_motion
import simple_brush


class FakeController:
    instances = []

    def __init__(self, start_x, start_y, dest_x, dest_y, **params):
        self.start = (start_x, start_y)
        self.destination = (dest_x, dest_y)
        self.params = params
        self.calls = []
        self.__class__.instances.append(self)

    def move_to_target(self, **kwargs):
        self.calls.append(kwargs)


class WindMouseMotionTests(unittest.TestCase):
    def setUp(self):
        FakeController.instances = []
        self.mouse = Mock()
        self.mouse.position.return_value = (0, 0)
        self.logger = Mock()

    def move(self, target, *, region_size=None, fallback=None):
        if fallback is None:
            fallback = Mock()
        with patch.object(mouse_motion, "_load_windmouse", return_value=(FakeController, int)):
            result = mouse_motion.move_to_target(
                self.mouse, *target, region_size=region_size, fallback=fallback, logger=self.logger
            )
        return result, fallback

    def test_short_distance_uses_one_stable_segment_and_final_integer_move(self):
        result, fallback = self.move((120.4, 80.6))
        self.assertTrue(result)
        fallback.assert_not_called()
        self.assertEqual(len(FakeController.instances), 1)
        controller = FakeController.instances[0]
        self.assertEqual(controller.start, (0, 0))
        self.assertEqual(controller.destination, (120, 81))
        self.assertEqual(controller.params, mouse_motion.SHORT_PARAMS)
        self.assertEqual(controller.calls, [{"tick_delay": 0, "step_duration": 0}])
        self.mouse.moveTo.assert_called_once_with(120, 81, duration=0)

    def test_regular_far_move_uses_two_segments_and_regular_clamp(self):
        result, fallback = self.move((1000, 0), region_size=(100, 100))
        self.assertTrue(result)
        fallback.assert_not_called()
        self.assertEqual(len(FakeController.instances), 2)
        first, second = FakeController.instances
        self.assertEqual(first.destination, (900, 0))  # clamp(1000 * .10, 60, 120)
        self.assertEqual(first.params, mouse_motion.APPROACH_PARAMS)
        self.assertEqual(second.start, (900, 0))
        self.assertEqual(second.destination, (1000, 0))
        self.assertEqual(second.params, mouse_motion.FINISH_PARAMS)
        self.assertEqual(first.calls, [{"tick_delay": 0, "step_duration": 0}])
        self.assertEqual(second.calls, [{"tick_delay": 0, "step_duration": 0}])
        self.mouse.moveTo.assert_called_once_with(1000, 0, duration=0)

    def test_regular_far_clamp_honours_lower_and_upper_bounds(self):
        for target, expected_x in ((300, 240), (2000, 1880)):
            with self.subTest(target=target):
                FakeController.instances = []
                self.mouse.reset_mock()
                self.mouse.position.return_value = (0, 0)
                self.move((target, 0), region_size=(100, 100))
                self.assertEqual(FakeController.instances[0].destination, (expected_x, 0))

    def test_small_region_far_move_uses_small_region_clamp(self):
        result, fallback = self.move((1000, 0), region_size=(80, 100))
        self.assertTrue(result)
        fallback.assert_not_called()
        self.assertEqual(FakeController.instances[0].destination, (880, 0))

    def test_small_region_clamp_honours_lower_and_upper_bounds(self):
        for target, expected_x in ((300, 220), (2000, 1860)):
            with self.subTest(target=target):
                FakeController.instances = []
                self.mouse.reset_mock()
                self.mouse.position.return_value = (0, 0)
                self.move((target, 0), region_size=(100, 40))
                self.assertEqual(FakeController.instances[0].destination, (expected_x, 0))

    def test_import_failure_logs_warning_and_uses_fallback(self):
        fallback = Mock()
        with patch.object(mouse_motion, "_load_windmouse", side_effect=ImportError("missing")):
            result = mouse_motion.move_to_target(self.mouse, 20, 30, fallback=fallback, logger=self.logger)
        self.assertFalse(result)
        fallback.assert_called_once_with()
        self.logger.warning.assert_called_once()
        self.mouse.moveTo.assert_not_called()

    def test_first_segment_failure_logs_warning_and_uses_fallback(self):
        fallback = Mock()
        failing = Mock(side_effect=RuntimeError("first failed"))
        with patch.object(mouse_motion, "_move_segment", failing), patch.object(mouse_motion, "_load_windmouse", return_value=(FakeController, int)):
            result = mouse_motion.move_to_target(self.mouse, 500, 0, fallback=fallback, logger=self.logger)
        self.assertFalse(result)
        fallback.assert_called_once_with()
        self.logger.warning.assert_called_once()

    def test_second_segment_failure_logs_warning_and_uses_fallback(self):
        fallback = Mock()
        original = mouse_motion._move_segment
        with patch.object(mouse_motion, "_load_windmouse", return_value=(FakeController, int)), patch.object(mouse_motion, "_move_segment", side_effect=[None, RuntimeError("second failed")]) as move:
            result = mouse_motion.move_to_target(self.mouse, 500, 0, fallback=fallback, logger=self.logger)
        self.assertFalse(result)
        self.assertEqual(move.call_count, 2)
        fallback.assert_called_once_with()
        self.logger.warning.assert_called_once()


class HumanMouseEntryPointTests(unittest.TestCase):
    def setUp(self):
        self.saved_simple = simple_brush.simple_mouse_enabled
        simple_brush.simple_mouse_enabled = False

    def tearDown(self):
        simple_brush.simple_mouse_enabled = self.saved_simple

    def test_simple_mouse_bypasses_windmouse(self):
        with patch.object(simple_brush.pyautogui, "moveTo") as move, patch.object(simple_brush.mouse_motion, "move_to_target") as wind, patch.object(simple_brush.random, "uniform", return_value=.2):
            simple_brush.human_move_to(20.2, 30.8, simple=True)
        move.assert_called_once_with(20, 31, duration=.2)
        wind.assert_not_called()

    def test_runtime_simple_mouse_bypasses_windmouse(self):
        simple_brush.simple_mouse_enabled = True
        with patch.object(simple_brush.pyautogui, "moveTo") as move, patch.object(simple_brush.mouse_motion, "move_to_target") as wind, patch.object(simple_brush.random, "uniform", return_value=.2):
            simple_brush.human_move_to(20, 30)
        move.assert_called_once_with(20, 30, duration=.2)
        wind.assert_not_called()

    def test_human_click_reuses_integer_target_for_move_press_and_release(self):
        with patch.object(simple_brush.random, "randint", side_effect=[3, -2]), patch.object(simple_brush.random, "uniform", return_value=.05), patch.object(simple_brush, "human_move_to") as move, patch.object(simple_brush.pyautogui, "mouseDown") as down, patch.object(simple_brush.pyautogui, "mouseUp") as up, patch.object(simple_brush.time, "sleep"):
            simple_brush.human_click(100, 200, offset=5, region_size=(30, 40))
        move.assert_called_once_with(103, 198, region_size=(30, 40))
        down.assert_called_once_with(103, 198)
        up.assert_called_once_with(103, 198)

    def test_region_click_preserves_random_point_and_passes_only_dimensions(self):
        region = simple_brush.ScreenRegion(left=10, top=20, width=30, height=40)
        with patch.object(simple_brush, "random_point_in_region", return_value=(22, 35)) as pick, patch.object(simple_brush, "human_click") as click:
            simple_brush.click_in_region(region)
        pick.assert_called_once_with(region)
        click.assert_called_once_with(22, 35, offset=0, region_size=(30, 40))

    def test_legacy_direct_click_boundary_is_unchanged(self):
        with patch.object(simple_brush, "stop_event", False), patch.object(simple_brush.pyautogui, "click") as direct, patch.object(simple_brush, "human_click") as human, patch.object(simple_brush, "safe_wait", return_value=True):
            self.assertTrue(simple_brush.click_first_candidate(100, 200))
        direct.assert_called_once_with(100, 200, duration=0)
        human.assert_not_called()

    def test_simple_mouse_argument_is_parsed(self):
        with patch.object(simple_brush.sys, "argv", ["simple_brush.py", "--simple-mouse", "--no-forward"]):
            args = simple_brush.parse_args()
        self.assertTrue(args["simple_mouse"])
        self.assertTrue(args["no_forward"])


if __name__ == "__main__":
    unittest.main()
