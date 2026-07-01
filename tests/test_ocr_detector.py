import unittest

from ocr_calibration import ScreenRegion
from ocr_detector import OCRKeywordDetector, RapidOCRBackend
from ocr_text import OCRItem, parse_keyword_rules


def single_rule(keyword):
    return parse_keyword_rules(f'"{keyword}"')


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
        result = detector.detect(single_rule("数字媒体"))
        self.assertTrue(result.success)
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.matched_keyword, '"数字媒体"')
        self.assertEqual(len(result.observations), 2)

    def test_unconfirmed_match_does_not_trigger(self):
        detector = self.make_detector(["数字媒体", "其他内容"])
        result = detector.detect(single_rule("数字媒体"))
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
        result = detector.detect(single_rule("不存在"))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertEqual(result.scans_completed, 3)
        self.assertEqual(len(scroll_calls), 2)

    def test_keyword_on_later_screen_is_confirmed(self):
        scroll_calls = []
        detector = self.make_detector(
            ["第一页", "第二页 Python", "第二页 Python"],
            max_scans=8,
            scroll=lambda: scroll_calls.append(True),
        )
        result = detector.detect(single_rule("Python"))
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.scans_completed, 2)
        self.assertEqual(len(scroll_calls), 1)

    def test_eight_screens_without_keyword_never_match(self):
        scroll_calls = []
        detector = self.make_detector(
            [f"第{number}页" for number in range(1, 9)],
            max_scans=8,
            scroll=lambda: scroll_calls.append(True),
        )
        result = detector.detect(single_rule("不存在"))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertEqual(result.scans_completed, 8)
        self.assertEqual(len(scroll_calls), 7)

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
        result = detector.detect(single_rule("关键词"))
        self.assertFalse(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIn("OCR unavailable", result.error)

    def test_empty_ocr_result_does_not_match(self):
        detector = self.make_detector([""], max_scans=1)
        result = detector.detect(single_rule("关键词"))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)

    def test_low_confidence_match_does_not_trigger(self):
        class LowConfidenceBackend:
            def recognize(self, _image):
                return [OCRItem("关键词", 0.4)]

        detector = OCRKeywordDetector(
            backend=LowConfidenceBackend(),
            capture=FakeCapture(),
            region=self.region,
            wait=lambda _seconds: None,
            max_scans=1,
            min_confidence=0.85,
        )
        result = detector.detect(single_rule("关键词"))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)

    def test_combination_rule_requires_full_second_confirmation(self):
        detector = self.make_detector(["PR AE", "只有 PR"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"PR" and "AE"'))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)

    def test_same_combination_rule_is_confirmed(self):
        detector = self.make_detector(["PR AE", "AE 与 PR"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"PR" and "AE"'))
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.matched_keyword, '"PR" and "AE"')

    def test_different_rule_cannot_complete_confirmation(self):
        detector = self.make_detector(["技能 A", "技能 B"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"A"; "B"'))
        self.assertFalse(result.confirmed_match)

    def test_not_rule_is_confirmed_when_both_passes_satisfy_the_full_rule(self):
        detector = self.make_detector(["短剧编导", "短剧制作"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"短剧" and not "销售"'))
        self.assertTrue(result.success)
        self.assertTrue(result.confirmed_match)
        self.assertEqual(result.matched_keyword, '"短剧" and not "销售"')
        self.assertEqual(len(result.observations), 2)

    def test_not_rule_fails_confirmation_when_excluded_keyword_appears(self):
        detector = self.make_detector(["短剧编导", "短剧销售"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"短剧" and not "销售"'))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)
        self.assertEqual(len(result.observations), 2)

    def test_not_rule_fails_confirmation_when_positive_keyword_disappears(self):
        detector = self.make_detector(["短剧编导", "其他岗位"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"短剧" and not "销售"'))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)

    def test_mixed_not_rule_is_rechecked_as_the_same_complete_rule(self):
        detector = self.make_detector(["只有 C", "B 和 C"], max_scans=1)
        result = detector.detect(
            parse_keyword_rules('"A" or not "B" and "C"')
        )
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertIsNone(result.matched_keyword)

    def test_not_rule_does_not_start_confirmation_when_first_pass_is_excluded(self):
        detector = self.make_detector(["短剧销售"], max_scans=1)
        result = detector.detect(parse_keyword_rules('"短剧" and not "销售"'))
        self.assertTrue(result.success)
        self.assertFalse(result.confirmed_match)
        self.assertEqual(len(result.observations), 1)


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
