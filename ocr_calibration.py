"""Cross-platform drag-to-select OCR screen region calibration."""

from dataclasses import dataclass
from pathlib import Path
import platform
from typing import Callable, Optional, Tuple


@dataclass(frozen=True)
class ScreenRegion:
    left: int
    top: int
    width: int
    height: int

    def as_mss_monitor(self):
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }


def enable_windows_dpi_awareness() -> str:
    """Make Tk and MSS use the same physical-pixel coordinate space on Windows."""

    if platform.system() != "Windows":
        return "not-windows"

    import ctypes

    try:
        # PER_MONITOR_AWARE_V2. This must be attempted before creating Tk windows.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        return "per-monitor-v2"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except (AttributeError, OSError):
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
        return "system"
    except (AttributeError, OSError):
        return "unavailable"


def primary_monitor_region() -> ScreenRegion:
    """Return the physical-pixel bounds of the primary monitor."""

    try:
        import mss
    except ImportError as exc:
        raise RuntimeError("mss is required for OCR calibration") from exc

    with mss.MSS() as capture:
        monitors = capture.monitors[1:]
        monitor = next(
            (item for item in monitors if item.get("is_primary")),
            monitors[0] if monitors else None,
        )
    if monitor is None:
        raise RuntimeError("no monitor is available for OCR calibration")
    return ScreenRegion(
        left=int(monitor["left"]),
        top=int(monitor["top"]),
        width=int(monitor["width"]),
        height=int(monitor["height"]),
    )


def physical_point_from_overlay(
    point: Tuple[int, int],
    overlay_size: Tuple[int, int],
    monitor: ScreenRegion,
) -> Tuple[int, int]:
    """Scale a Tk overlay-local point into MSS physical-pixel coordinates."""

    overlay_width, overlay_height = overlay_size
    if overlay_width <= 0 or overlay_height <= 0:
        raise ValueError("overlay dimensions must be positive")
    x = monitor.left + round(point[0] * monitor.width / overlay_width)
    y = monitor.top + round(point[1] * monitor.height / overlay_height)
    return (x, y)


def region_from_points(
    start: Tuple[int, int], end: Tuple[int, int], min_size: int = 80
) -> ScreenRegion:
    left = min(start[0], end[0])
    top = min(start[1], end[1])
    width = abs(end[0] - start[0])
    height = abs(end[1] - start[1])
    if width < min_size or height < min_size:
        raise ValueError("OCR selection is too small")
    return ScreenRegion(left=left, top=top, width=width, height=height)


class CalibrationCancelled(RuntimeError):
    pass


def select_screen_region(
    min_size: int = 80,
    instruction: str = "拖动框选候选人详情区域 · Esc 取消",
    subtitle: str = "第一版仅支持主显示器",
) -> ScreenRegion:
    """Show a primary-monitor Tk overlay and return physical MSS coordinates."""

    enable_windows_dpi_awareness()
    import tkinter as tk

    monitor = primary_monitor_region()
    root = tk.Tk()
    root.overrideredirect(True)
    root.geometry(
        f"{monitor.width}x{monitor.height}{monitor.left:+d}{monitor.top:+d}"
    )
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", 0.28)
    except tk.TclError:
        pass
    root.configure(cursor="crosshair", bg="black")

    canvas = tk.Canvas(root, bg="black", highlightthickness=0, cursor="crosshair")
    canvas.pack(fill=tk.BOTH, expand=True)
    canvas.create_text(
        24,
        24,
        anchor="nw",
        fill="white",
        font=("Arial", 18, "bold"),
        text=instruction,
    )
    size_text = canvas.create_text(
        24,
        56,
        anchor="nw",
        fill="white",
        font=("Arial", 13),
        text=subtitle,
    )

    state = {
        "start": None,
        "rect": None,
        "region": None,
        "cancelled": False,
    }

    def on_press(event):
        state["start"] = (event.x, event.y)
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(
            event.x,
            event.y,
            event.x,
            event.y,
            outline="#00ff88",
            width=3,
        )

    def on_drag(event):
        if state["start"] is None or state["rect"] is None:
            return
        local_start_x, local_start_y = state["start"]
        canvas.coords(state["rect"], local_start_x, local_start_y, event.x, event.y)
        canvas.itemconfigure(
            size_text,
            text=f"{abs(event.x - local_start_x)} × {abs(event.y - local_start_y)}",
        )

    def on_release(event):
        if state["start"] is None:
            return
        try:
            # Tk reports a placeholder 1x1 canvas before the event loop starts.
            # Read the realized size at release time so DPI scaling stays correct.
            overlay_size = (canvas.winfo_width(), canvas.winfo_height())
            physical_start = physical_point_from_overlay(
                state["start"], overlay_size, monitor
            )
            physical_end = physical_point_from_overlay(
                (event.x, event.y), overlay_size, monitor
            )
            state["region"] = region_from_points(
                physical_start, physical_end, min_size=min_size
            )
        except ValueError:
            state["start"] = None
            return
        root.quit()

    def on_cancel(_event=None):
        state["cancelled"] = True
        root.quit()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Escape>", on_cancel)
    root.lift()
    root.focus_force()
    root.mainloop()
    root.destroy()

    if state["cancelled"] or state["region"] is None:
        raise CalibrationCancelled("OCR region calibration cancelled")
    return state["region"]


def save_region_preview(
    region: ScreenRegion,
    destination: Path,
    capture: Optional[Callable[[ScreenRegion], object]] = None,
) -> Path:
    """Capture and save the selected pixels for calibration verification."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    if capture is None:
        from ocr_detector import MSSScreenCapture

        capture = MSSScreenCapture().capture
    image = capture(region)
    try:
        from PIL import Image
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Pillow and NumPy are required to save OCR previews") from exc

    array = np.asarray(image)
    if array.ndim != 3:
        raise ValueError("Captured preview must be a color image")
    if array.shape[2] == 4:
        array = array[:, :, :3]
    # MSS provides BGR pixels; convert them for Pillow.
    Image.fromarray(array[:, :, ::-1]).save(str(destination))
    return destination
