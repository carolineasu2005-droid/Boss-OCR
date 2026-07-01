"""Pure text processing for screen-based OCR keyword detection."""

from dataclasses import dataclass
import re
import unicodedata
from typing import Iterable, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class OCRItem:
    """One OCR text box in screen coordinates."""

    text: str
    confidence: float = 1.0
    box: Optional[Sequence[Sequence[float]]] = None

    @property
    def anchor(self) -> Tuple[float, float]:
        if self.box is None or len(self.box) == 0:
            return (0.0, 0.0)
        xs = [float(point[0]) for point in self.box]
        ys = [float(point[1]) for point in self.box]
        return (min(xs), min(ys))

    @property
    def vertical_bounds(self) -> Optional[Tuple[float, float]]:
        if self.box is None or len(self.box) == 0:
            return None
        ys = [float(point[1]) for point in self.box]
        return (min(ys), max(ys))


def normalize_text(value: str) -> str:
    """Normalize layout noise without introducing fuzzy matching."""

    normalized = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"\s+", "", normalized)


def order_items(items: Iterable[OCRItem]) -> List[OCRItem]:
    """Return OCR boxes in adaptive line order, then left-to-right order."""

    items = list(items)
    positioned = [item for item in items if item.vertical_bounds is not None]
    unpositioned = [item for item in items if item.vertical_bounds is None]
    positioned.sort(key=lambda item: (item.anchor[1], item.anchor[0]))

    lines = []
    for item in positioned:
        top, bottom = item.vertical_bounds
        center = (top + bottom) / 2.0
        height = max(1.0, bottom - top)
        target = None
        for line in lines:
            tolerance = max(8.0, min(height, line["height"]) * 0.5)
            if abs(center - line["center"]) <= tolerance:
                target = line
                break
        if target is None:
            lines.append(
                {"items": [item], "center": center, "height": height}
            )
        else:
            target["items"].append(item)
            count = len(target["items"])
            target["center"] = ((target["center"] * (count - 1)) + center) / count
            target["height"] = ((target["height"] * (count - 1)) + height) / count

    ordered = []
    for line in sorted(lines, key=lambda value: value["center"]):
        ordered.extend(sorted(line["items"], key=lambda item: item.anchor[0]))
    ordered.extend(unpositioned)
    return ordered


def searchable_text(items: Iterable[OCRItem], min_confidence: float = 0.0) -> str:
    """Build normalized searchable text from accepted OCR boxes."""

    accepted = [item for item in items if item.confidence >= min_confidence]
    return normalize_text("\n".join(item.text for item in order_items(accepted)))


def exact_keyword_match(text: str, keywords: Iterable[str]) -> Optional[str]:
    """Return the first normalized exact substring match, otherwise None."""

    normalized_text = normalize_text(text)
    for keyword in keywords:
        cleaned = keyword.strip()
        if cleaned and normalize_text(cleaned) in normalized_text:
            return cleaned
    return None
