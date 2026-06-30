"""Cross-platform drag-to-select OCR screen region calibration."""

from dataclasses import dataclass
from pathlib import Path
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


def select_screen_region(min_size: int = 80) -> ScreenRegion:
    """Show a translucent Tk overlay and return the user's drag rectangle."""

    import tkinter as tk

    root = tk.Tk()
    root.attributes("-fullscreen", True)
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
        text="拖动框选候选人详情区域 · Esc 取消",
    )

    state = {"start": None, "rect": None, "region": None, "cancelled": False}

    def on_press(event):
        state["start"] = (event.x_root, event.y_root)
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
        local_start_x = state["start"][0] - root.winfo_rootx()
        local_start_y = state["start"][1] - root.winfo_rooty()
        canvas.coords(state["rect"], local_start_x, local_start_y, event.x, event.y)

    def on_release(event):
        if state["start"] is None:
            return
        try:
            state["region"] = region_from_points(
                state["start"], (event.x_root, event.y_root), min_size=min_size
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
