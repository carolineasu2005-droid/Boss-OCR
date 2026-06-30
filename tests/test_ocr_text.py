import unittest

from ocr_text import OCRItem, exact_keyword_match, normalize_text, searchable_text


class OCRTextTests(unittest.TestCase):
    def test_normalization_removes_layout_whitespace_and_folds_width(self):
        self.assertEqual(normalize_text("广东 工贸\n职业技术学院 ＡＩ"), "广东工贸职业技术学院ai")

    def test_exact_match_accepts_keyword_split_across_ocr_lines(self):
        text = "广东工贸职业\n技术学院"
        self.assertEqual(exact_keyword_match(text, ["广东工贸职业技术学院"]), "广东工贸职业技术学院")

    def test_exact_match_does_not_use_fuzzy_similarity(self):
        self.assertIsNone(exact_keyword_match("数字媒休", ["数字媒体"]))

    def test_low_confidence_items_are_excluded(self):
        items = [
            OCRItem("错误关键词", 0.4, [[0, 0], [10, 0], [10, 10], [0, 10]]),
            OCRItem("有效文字", 0.96, [[0, 20], [10, 20], [10, 30], [0, 30]]),
        ]
        self.assertEqual(searchable_text(items, min_confidence=0.85), "有效文字")

    def test_items_are_ordered_by_position(self):
        items = [
            OCRItem("学院", 0.9, [[100, 20], [150, 20], [150, 30], [100, 30]]),
            OCRItem("广东", 0.9, [[0, 10], [50, 10], [50, 20], [0, 20]]),
        ]
        self.assertEqual(searchable_text(items), "广东学院")


if __name__ == "__main__":
    unittest.main()
