"""Screen-only RapidOCR keyword detector with injectable test backends."""

from dataclasses import dataclass, field
import logging
import time
from typing import Callable, Iterable, List, Optional, Protocol, Sequence

from ocr_calibration import ScreenRegion
from ocr_text import OCRItem, exact_keyword_match, searchable_text


logger = logging.getLogger(__name__)


class OCRBackend(Protocol):
    def recognize(self, image: object) -> Sequence[OCRItem]:
        ...


class ScreenCapture(Protocol):
    def capture(self, region: ScreenRegion) -> object:
        ...


@dataclass
class ScanObservation:
    scan_number: int
    text: str
    item_count: int
    elapsed_seconds: float
    matched_keyword: Optional[str] = None


@dataclass
class DetectionResult:
    success: bool
    confirmed_match: bool
    matched_keyword: Optional[str] = None
    scans_completed: int = 0
    observations: List[ScanObservation] = field(default_factory=list)
    error: Optional[str] = None


class MSSScreenCapture:
    """Capture only physical pixels visible inside the selected rectangle."""

    def capture(self, region: ScreenRegion):
        try:
            import mss
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("mss and NumPy are required for screen capture") from exc
        with mss.mss() as sct:
            shot = sct.grab(region.as_mss_monitor())
        # Drop alpha. MSS byte order is BGRA, which RapidOCR accepts as BGR.
        return np.asarray(shot)[:, :, :3].copy()


class RapidOCRBackend:
    """Lazy RapidOCR adapter supporting modern and legacy result shapes."""

    def __init__(self, engine=None):
        if engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError as exc:
                raise RuntimeError(
                    "RapidOCR is not installed; install the Mac OCR requirements"
                ) from exc
            engine = RapidOCR()
        self.engine = engine

    def recognize(self, image: object) -> Sequence[OCRItem]:
        result = self.engine(image)
        if result is None:
            return []

        # RapidOCR 3.x result object.
        txts = getattr(result, "txts", None)
        scores = getattr(result, "scores", None)
        boxes = getattr(result, "boxes", None)
        if txts is not None:
            scores = scores if scores is not None else [1.0] * len(txts)
            boxes = boxes if boxes is not None else [None] * len(txts)
            return [
                OCRItem(str(text), float(score), box)
                for text, score, box in zip(txts, scores, boxes)
            ]

        # Older releases return (lines, elapsed), where each line is
        # [box, text, score]. Some wrappers return lines directly.
        lines = result
        if isinstance(result, tuple) and len(result) == 2:
            lines = result[0]
        if not lines:
            return []
        parsed = []
        for line in lines:
            if not isinstance(line, (list, tuple)) or len(line) < 2:
                continue
            box, text = line[0], line[1]
            score = line[2] if len(line) > 2 else 1.0
            parsed.append(OCRItem(str(text), float(score), box))
        return parsed


class OCRKeywordDetector:
    """Scan a calibrated screen region and confirm exact keyword matches."""

    def __init__(
        self,
        backend: OCRBackend,
        capture: ScreenCapture,
        region: ScreenRegion,
        max_scans: int = 8,
        min_confidence: float = 0.85,
        scroll: Optional[Callable[[], None]] = None,
        wait: Callable[[float], None] = time.sleep,
        settle_seconds: float = 0.6,
        confirmation_seconds: float = 0.7,
    ):
        if max_scans < 1:
            raise ValueError("max_scans must be at least 1")
        self.backend = backend
        self.capture = capture
        self.region = region
        self.max_scans = max_scans
        self.min_confidence = min_confidence
        self.scroll = scroll
        self.wait = wait
        self.settle_seconds = settle_seconds
        self.confirmation_seconds = confirmation_seconds

    def _observe(self, scan_number: int, keywords: Iterable[str]):
        started = time.perf_counter()
        image = self.capture.capture(self.region)
        items = list(self.backend.recognize(image))
        text = searchable_text(items, min_confidence=self.min_confidence)
        keyword = exact_keyword_match(text, keywords)
        return ScanObservation(
            scan_number=scan_number,
            text=text,
            item_count=len(items),
            elapsed_seconds=time.perf_counter() - started,
            matched_keyword=keyword,
        )

    def detect(self, keywords: Iterable[str]) -> DetectionResult:
        keywords = [keyword.strip() for keyword in keywords if keyword.strip()]
        if not keywords:
            return DetectionResult(success=True, confirmed_match=False)

        observations = []
        try:
            for scan_number in range(1, self.max_scans + 1):
                if scan_number > 1:
                    if self.scroll is None:
                        break
                    self.scroll()
                    self.wait(self.settle_seconds)

                first = self._observe(scan_number, keywords)
                observations.append(first)
                logger.info(
                    "OCR scan %s/%s: %s items, %.3fs, match=%r",
                    scan_number,
                    self.max_scans,
                    first.item_count,
                    first.elapsed_seconds,
                    first.matched_keyword,
                )
                if not first.matched_keyword:
                    continue

                self.wait(self.confirmation_seconds)
                confirmation = self._observe(scan_number, [first.matched_keyword])
                observations.append(confirmation)
                confirmed = confirmation.matched_keyword == first.matched_keyword
                return DetectionResult(
                    success=True,
                    confirmed_match=confirmed,
                    matched_keyword=first.matched_keyword if confirmed else None,
                    scans_completed=scan_number,
                    observations=observations,
                    error=None if confirmed else "second OCR pass did not confirm the match",
                )

            return DetectionResult(
                success=True,
                confirmed_match=False,
                scans_completed=min(self.max_scans, len(observations)),
                observations=observations,
            )
        except Exception as exc:
            logger.exception("OCR keyword detection failed")
            return DetectionResult(
                success=False,
                confirmed_match=False,
                scans_completed=len([item for item in observations if item.scan_number]),
                observations=observations,
                error=str(exc),
            )
