import unittest

import calibration_steps


EXPECTED_FIELDS = {
    "first_candidate",
    "focus_restore_region",
    "favorite_button_region",
    "forward_icon",
    "email_tab",
    "recent_email",
    "input_box",
    "forward_button",
    "open_filter",
    "unseen_filter",
    "confirm_filter",
}


class CalibrationStepsTests(unittest.TestCase):
    def test_field_set_matches_tid_fields(self):
        self.assertEqual(
            set(calibration_steps.calibration_field_names()),
            EXPECTED_FIELDS,
        )

    def test_no_duplicate_fields(self):
        field_names = calibration_steps.calibration_field_names()
        self.assertEqual(len(field_names), len(set(field_names)))

    def test_all_steps_are_required(self):
        self.assertTrue(
            all(step.required for step in calibration_steps.calibration_steps())
        )

    def test_all_steps_have_display_instruction_stage_and_feature(self):
        for step in calibration_steps.calibration_steps():
            with self.subTest(field_name=step.field_name):
                self.assertTrue(step.display_name.strip())
                self.assertTrue(step.instruction.strip())
                self.assertTrue(step.stage.strip())
                self.assertTrue(step.feature.strip())
                self.assertTrue(step.precondition.strip())
                self.assertTrue(step.manual_transition.strip())
                self.assertIsInstance(step.min_size, int)
                self.assertGreater(step.min_size, 0)

    def test_stages_include_tid_stage_design(self):
        self.assertEqual(
            set(calibration_steps.calibration_stages()),
            {"A", "C", "B"},
        )

    def test_steps_by_field_indexes_all_steps(self):
        by_field = calibration_steps.calibration_steps_by_field()
        self.assertEqual(set(by_field), EXPECTED_FIELDS)
        self.assertEqual(by_field["recent_email"].display_name, "最近联系邮箱标签")

    def test_order_keeps_candidate_forward_filter_stage_sequence(self):
        self.assertEqual(
            calibration_steps.calibration_stages(),
            ("A", "C", "B"),
        )


if __name__ == "__main__":
    unittest.main()
