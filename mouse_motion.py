"""WindMouse-backed pointer movement with a caller-provided safe fallback."""
from __future__ import annotations

import math


SHORT_DISTANCE = 300.0
SHORT_PARAMS = {"gravity_magnitude": 10, "wind_magnitude": 0, "max_step": 16, "damped_distance": 12}
APPROACH_PARAMS = {"gravity_magnitude": 20, "wind_magnitude": 3, "max_step": 45, "damped_distance": 24}
FINISH_PARAMS = {"gravity_magnitude": 10, "wind_magnitude": 0, "max_step": 18, "damped_distance": 18}


def _load_windmouse():
    """Return the compatible upstream types, or raise the import failure."""
    from windmouse.pyautogui_controller import PyautoguiMouseController
    try:
        from windmouse import Coordinate
    except ImportError:
        from windmouse.core import Coordinate
    return PyautoguiMouseController, Coordinate


def _clamp(value, lower, upper):
    return min(max(value, lower), upper)


def _move_segment(controller_type, coordinate_type, start, destination, params):
    controller = controller_type(
        coordinate_type(int(round(start[0]))), coordinate_type(int(round(start[1]))),
        coordinate_type(int(round(destination[0]))), coordinate_type(int(round(destination[1]))),
        **params,
    )
    controller.move_to_target(tick_delay=0, step_duration=0)


def move_to_target(pyautogui, target_x, target_y, *, region_size=None, fallback, logger):
    """Move through WindMouse, or use the caller's legacy movement fallback.

    Region dimensions only select the finishing distance; they never influence
    the target point chosen by the caller.  Returns whether WindMouse succeeded.
    """
    target = (int(round(target_x)), int(round(target_y)))
    try:
        controller_type, coordinate_type = _load_windmouse()
        current = pyautogui.position()
        start = (float(current[0]), float(current[1]))
        distance = math.hypot(target[0] - start[0], target[1] - start[1])
        if distance < SHORT_DISTANCE:
            _move_segment(controller_type, coordinate_type, start, target, SHORT_PARAMS)
        else:
            width, height = region_size if region_size is not None else (None, None)
            small_region = width is not None and height is not None and (width <= 80 or height <= 40)
            approach_distance = _clamp(distance * (0.12 if small_region else 0.10), 80 if small_region else 60, 140 if small_region else 120)
            unit_x = (target[0] - start[0]) / distance
            unit_y = (target[1] - start[1]) / distance
            pre_target = (target[0] - unit_x * approach_distance, target[1] - unit_y * approach_distance)
            _move_segment(controller_type, coordinate_type, start, pre_target, APPROACH_PARAMS)
            _move_segment(controller_type, coordinate_type, pre_target, target, FINISH_PARAMS)
        # Protect clicks from any intermediate rounding in the upstream path.
        pyautogui.moveTo(target[0], target[1], duration=0)
        return True
    except Exception as error:  # dependency and GUI backends can fail at runtime
        logger.warning("WindMouse unavailable or movement failed; using legacy mouse path: %s", error, exc_info=True)
        fallback()
        return False
