import unittest

import numpy as np

from ocr_text import (
    OCRItem,
    exact_keyword_match,
    keyword_rule_matches,
    matching_keyword_rule,
    normalize_text,
    parse_keyword_rules,
    searchable_text,
)


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

    def test_numpy_boxes_from_rapidocr_are_supported(self):
        items = [
            OCRItem(
                "Python",
                0.99,
                np.asarray([[10, 20], [100, 20], [100, 50], [10, 50]]),
            )
        ]
        self.assertEqual(searchable_text(items, min_confidence=0.85), "python")

    def test_large_same_line_boxes_use_left_to_right_order(self):
        items = [
            OCRItem(
                "OCR Test",
                0.99,
                np.asarray([[256, 49], [626, 52], [625, 163], [255, 160]]),
            ),
            OCRItem(
                "Python",
                0.99,
                np.asarray([[22, 60], [287, 62], [286, 168], [21, 166]]),
            ),
        ]
        self.assertEqual(searchable_text(items), "pythonocrtest")

    def test_single_quoted_keyword_rule_matches(self):
        rule = parse_keyword_rules('"剪映"')[0]
        self.assertTrue(keyword_rule_matches("熟练使用剪映", rule))
        self.assertFalse(keyword_rule_matches("熟练使用PR", rule))

    def test_and_rule_requires_every_keyword(self):
        rule = parse_keyword_rules('"PR" and "AE"')[0]
        self.assertTrue(keyword_rule_matches("PR、AE后期制作", rule))
        self.assertFalse(keyword_rule_matches("只会PR", rule))

    def test_or_rule_accepts_any_keyword(self):
        rule = parse_keyword_rules('"短剧" or "带货"')[0]
        self.assertTrue(keyword_rule_matches("直播带货", rule))

    def test_and_has_higher_precedence_than_or(self):
        rule = parse_keyword_rules('"A" or "B" and "C"')[0]
        self.assertTrue(keyword_rule_matches("只有A", rule))
        self.assertFalse(keyword_rule_matches("只有B", rule))
        self.assertTrue(keyword_rule_matches("B和C", rule))

    def test_semicolon_rules_match_independently_in_input_order(self):
        rules = parse_keyword_rules(
            '"剪映" and "信息流"; "短剧" or "带货";'
        )
        matched = matching_keyword_rule("短剧运营", rules)
        self.assertEqual(matched, rules[1])
        self.assertEqual(matched.source, '"短剧" or "带货"')

    def test_connector_text_inside_quotes_is_one_keyword(self):
        rule = parse_keyword_rules('"research and development"')[0]
        self.assertTrue(keyword_rule_matches("Research and Development", rule))

    def test_rule_matching_preserves_nfkc_normalization(self):
        rule = parse_keyword_rules('"ＰＲ"')[0]
        self.assertTrue(keyword_rule_matches("PR", rule))

    def test_connectors_are_case_insensitive_and_source_is_canonical(self):
        rule = parse_keyword_rules('  "A" AND "B" Or "C"  ')[0]
        self.assertEqual(rule.source, '"A" and "B" or "C"')

    def test_invalid_rule_formats_are_rejected_with_a_position(self):
        invalid_values = (
            "剪映",
            "“剪映”",
            '"剪映',
            '"剪映" and',
            'and "剪映"',
            '"剪映" "短剧"',
            '"剪映" xor "短剧"',
            '""',
            '"   "',
            '"剪映";;"短剧"',
            '("剪映" or "短剧")',
        )
        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "位置"):
                    parse_keyword_rules(value)

    def test_unquoted_legacy_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_keyword_rules("Python;短剧")


if __name__ == "__main__":
    unittest.main()
