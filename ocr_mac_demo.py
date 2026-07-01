"""Mac development entry point for calibration and one-region RapidOCR tests."""

import argparse
from pathlib import Path
import sys

from ocr_calibration import CalibrationCancelled, save_region_preview, select_screen_region
from ocr_detector import MSSScreenCapture, OCRKeywordDetector, RapidOCRBackend


def parse_args():
    parser = argparse.ArgumentParser(description="Calibrate a screen region and test RapidOCR")
    parser.add_argument(
        "--keywords",
        required=True,
        help="Semicolon-separated exact keywords, for example: Python;数字媒体",
    )
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument(
        "--preview",
        default="logs/ocr_calibration_preview.png",
        help="Calibration preview path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    keywords = [item.strip() for item in args.keywords.split(";") if item.strip()]
    try:
        region = select_screen_region()
    except CalibrationCancelled:
        print("OCR calibration cancelled")
        return 2

    capture = MSSScreenCapture()
    print(f"Selected region: {region}")
    preview = save_region_preview(region, Path(args.preview), capture.capture)
    print(f"Preview saved to: {preview}")

    detector = OCRKeywordDetector(
        backend=RapidOCRBackend(),
        capture=capture,
        region=region,
        max_scans=1,
        min_confidence=args.min_confidence,
    )
    result = detector.detect(keywords)
    print(f"OCR success: {result.success}")
    print(f"Confirmed match: {result.confirmed_match}")
    print(f"Matched keyword: {result.matched_keyword or '(none)'}")
    if result.error:
        print(f"Error: {result.error}", file=sys.stderr)
    return 0 if result.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
