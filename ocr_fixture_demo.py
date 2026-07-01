"""Run the OCR pipeline against local screenshots as simulated scroll pages."""

import argparse
from pathlib import Path
import sys

from ocr_calibration import ScreenRegion
from ocr_detector import OCRKeywordDetector, RapidOCRBackend


class ImageSequenceCapture:
    def __init__(self, paths):
        self.paths = [Path(path) for path in paths]
        self.index = 0

    def capture(self, _region):
        try:
            from PIL import Image
            import numpy as np
        except ImportError as exc:
            raise RuntimeError("Pillow and NumPy are required") from exc
        path = self.paths[min(self.index, len(self.paths) - 1)]
        image = np.asarray(Image.open(str(path)).convert("RGB"))
        # Keep the same BGR convention as MSSScreenCapture.
        return image[:, :, ::-1].copy()

    def advance(self):
        self.index = min(self.index + 1, len(self.paths) - 1)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Use local images to simulate fixed-count resume OCR scanning"
    )
    parser.add_argument("images", nargs="+", help="Ordered visible-page screenshots")
    parser.add_argument("--keywords", required=True, help="Semicolon-separated keywords")
    parser.add_argument("--min-confidence", type=float, default=0.85)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    missing = [path for path in args.images if not Path(path).is_file()]
    if missing:
        print(f"Missing screenshot: {missing[0]}", file=sys.stderr)
        return 2

    capture = ImageSequenceCapture(args.images)
    detector = OCRKeywordDetector(
        backend=RapidOCRBackend(),
        capture=capture,
        region=ScreenRegion(0, 0, 1, 1),
        max_scans=len(args.images),
        min_confidence=args.min_confidence,
        scroll=capture.advance,
        wait=lambda _seconds: None,
    )
    keywords = [item.strip() for item in args.keywords.split(";") if item.strip()]
    result = detector.detect(keywords)

    for observation in result.observations:
        print(
            f"scan={observation.scan_number} items={observation.item_count} "
            f"elapsed={observation.elapsed_seconds:.3f}s "
            f"match={observation.matched_keyword or '-'}"
        )
    print(f"success={result.success}")
    print(f"confirmed_match={result.confirmed_match}")
    print(f"matched_keyword={result.matched_keyword or '-'}")
    if result.error:
        print(f"error={result.error}", file=sys.stderr)
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
