"""Optional WindMouse-backed pointer movement for Windows GUI observability."""

import math

import pyautogui


WINDMOUSE_TWO_STAGE_DISTANCE = 300

WINDMOUSE_SHORT_STABLE = {
    "gravity_magnitude": 10,
    "wind_magnitude": 0,
    "max_step": 16,
    "damped_distance": 12,
    "tick_delay": 0,
    "step_duration": 0,
}
WINDMOUSE_FAST_APPROACH = {
    "gravity_magnitude": 20,
    "wind_magnitude": 3,
    "max_step": 45,
    "damped_distance": 24,
    "tick_delay": 0,
    "step_duration": 0,
}
WINDMOUSE_STABLE_FINISH = {
    "gravity_magnitude": 10,
    "wind_magnitude": 0,
    "max_step": 18,
    "damped_distance": 18,
    "tick_delay": 0,
    "step_duration": 0,
}


class WindMouseUnavailableError(RuntimeError):
    """Raised when the optional WindMouse backend cannot be imported."""


_windmouse_import_error = None

try:
    import windmouse
    from windmouse.pyautogui_controller import PyautoguiMouseController

    # Prefer the public package-root export documented upstream without making
    # PyInstaller interpret a missing attribute as an optional submodule.
    Coordinate = getattr(windmouse, "Coordinate", None)
    if Coordinate is None:
        # windmouse 1.0.2 does not export Coordinate from its package root.
        from windmouse.core import Coordinate
except (ImportError, OSError) as exc:
    Coordinate = None
    PyautoguiMouseController = None
    _windmouse_import_error = exc


def windmouse_available():
    """Return whether the WindMouse PyAutoGUI backend imported successfully."""
    return PyautoguiMouseController is not None and Coordinate is not None


def windmouse_unavailable_reason():
    """Return a concise reason suitable for an application warning log."""
    if _windmouse_import_error is None:
        return "WindMouse PyAutoGUI backend 未加载"
    return f"{type(_windmouse_import_error).__name__}: {_windmouse_import_error}"


def _clamp(value, minimum, maximum):
    return min(maximum, max(minimum, value))


def _move_windmouse_segment(target_x, target_y, parameters):
    """Move one WindMouse segment with a selected parameter profile."""
    controller = PyautoguiMouseController(
        gravity_magnitude=parameters["gravity_magnitude"],
        wind_magnitude=parameters["wind_magnitude"],
        max_step=parameters["max_step"],
        damped_distance=parameters["damped_distance"],
    )
    controller.dest_position = (Coordinate(target_x), Coordinate(target_y))
    controller.move_to_target(
        tick_delay=parameters["tick_delay"],
        step_duration=parameters["step_duration"],
    )


def move_to_observable(x, y, *, region_width=None, region_height=None):
    """Move with one or two WindMouse stages, then force the exact target."""
    target_x = int(round(x))
    target_y = int(round(y))
    if not windmouse_available():
        raise WindMouseUnavailableError(windmouse_unavailable_reason())

    start_x, start_y = pyautogui.position()
    delta_x = target_x - start_x
    delta_y = target_y - start_y
    distance = math.hypot(delta_x, delta_y)

    if distance < WINDMOUSE_TWO_STAGE_DISTANCE:
        _move_windmouse_segment(target_x, target_y, WINDMOUSE_SHORT_STABLE)
    else:
        small_region = (
            region_width is not None and region_width <= 80
        ) or (
            region_height is not None and region_height <= 40
        )
        if small_region:
            approach_distance = _clamp(distance * 0.12, 80, 140)
        else:
            approach_distance = _clamp(distance * 0.10, 60, 120)

        unit_x = delta_x / distance
        unit_y = delta_y / distance
        pre_target_x = int(round(target_x - unit_x * approach_distance))
        pre_target_y = int(round(target_y - unit_y * approach_distance))
        _move_windmouse_segment(
            pre_target_x,
            pre_target_y,
            WINDMOUSE_FAST_APPROACH,
        )
        _move_windmouse_segment(
            target_x,
            target_y,
            WINDMOUSE_STABLE_FINISH,
        )

    # The generated path may stop less than one pixel from its destination.
    pyautogui.moveTo(target_x, target_y, duration=0)
