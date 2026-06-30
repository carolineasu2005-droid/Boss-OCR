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
        if not self.box:
            return (0.0, 0.0)
        xs = [float(point[0]) for point in self.box]
        ys = [float(point[1]) for point in self.box]
        return (min(xs), min(ys))


def normalize_text(value: str) -> str:
    """Normalize layout noise without introducing fuzzy matching."""

    normalized = unicodedata.normalize("NFKC", value or "").lower()
    return re.sub(r"\s+", "", normalized)


def order_items(items: Iterable[OCRItem]) -> List[OCRItem]:
    """Return OCR boxes in a stable top-to-bottom, left-to-right order."""

    return sorted(items, key=lambda item: (round(item.anchor[1] / 8.0), item.anchor[0]))


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
