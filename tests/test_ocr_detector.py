import unittest

from ocr_calibration import ScreenRegion
from ocr_detector import OCRKeywordDetector, RapidOCRBackend
from ocr_text import OCRItem


class FakeCapture:
    def __init__(self):
        self.calls = 0

    def capture(self, region):
        self.calls += 1
        return self.calls


class FakeBackend:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = 0

    def recognize(self, _image):
        page = self.pages[min(self.calls, len(self.pages) - 1)]
        self.calls += 1
        return [OCRItem(page, 0.99)]


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.region = ScreenRegion(10, 20, 800, 600)

    def make_detector(self, pages, max_scans=8, scroll=None):
        return OCRKeywordDetector(
            backend=FakeBackend(pages),
            capture=FakeCapture(),
            region=self.region,
            max_scans=max_scans,
            scroll=scroll,
            wait=lambda _seconds: None,
        )

    def test_match_requires_second_confirmation(self):
        detector = self.make_detector(["数字媒体", "数字媒体"])
        result = detector.detect(["数字媒体"])
        self.assertTrue(result.success)
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.matched_keyword, "数字媒体")
        self.assertEqual(len(result.observations), 2)

    def test_unconfirmed_match_does_not_trigger(self):
        detector = self.make_detector(["数字媒体", "其他内容"])
        result = detector.detect(["数字媒体"])
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)

    def test_scans_fixed_number_and_scrolls_between_pages(self):
        scroll_calls = []
        detector = self.make_detector(
            ["第一页", "第二页", "第三页"],
            max_scans=3,
            scroll=lambda: scroll_calls.append(True),
        )
        result = detector.detect(["不存在"])
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertEqual(result.scans_completed, 3)
        self.assertEqual(len(scroll_calls), 2)

    def test_backend_failure_is_fail_closed(self):
        class BrokenBackend:
            def recognize(self, _image):
                raise RuntimeError("OCR unavailable")

        detector = OCRKeywordDetector(
            backend=BrokenBackend(),
            capture=FakeCapture(),
            region=self.region,
            wait=lambda _seconds: None,
        )
        result = detector.detect(["关键词"])
        self.assertFalse(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIn("OCR unavailable", result.error)


class RapidOCRAdapterTests(unittest.TestCase):
    def test_modern_result_object(self):
        class Result:
            txts = ["数字媒体"]
            scores = [0.98]
            boxes = [[[0, 0], [20, 0], [20, 10], [0, 10]]]

        backend = RapidOCRBackend(engine=lambda _image: Result())
        items = backend.recognize(object())
        self.assertEqual(items[0].text, "数字媒体")
        self.assertEqual(items[0].confidence, 0.98)

    def test_legacy_tuple_result(self):
        lines = [[[[0, 0], [20, 0], [20, 10], [0, 10]], "Python", 0.97]]
        backend = RapidOCRBackend(engine=lambda _image: (lines, 0.1))
        items = backend.recognize(object())
        self.assertEqual(items[0].text, "Python")
        self.assertEqual(items[0].confidence, 0.97)


if __name__ == "__main__":
    unittest.main()
