import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import calibration_profiles
from calibration_profiles import (
    CalibrationProfileError,
    ProfileExistsError,
    ProfileJsonError,
    ProfileValidationError,
)
from ocr_calibration import ScreenRegion


def sample_region(offset=0):
    return ScreenRegion(left=10 + offset, top=20 + offset, width=30, height=40)


def sample_areas():
    return {
        field_name: sample_region(index)
        for index, field_name in enumerate(calibration_profiles.REQUIRED_AREA_FIELDS)
    }


def sample_system_info(**overrides):
    info = {
        "os": "Windows",
        "screen_width": 1920,
        "screen_height": 1080,
        "dpi_scale": 1.25,
    }
    info.update(overrides)
    return info


class CalibrationProfileTests(unittest.TestCase):
    def test_safe_profile_filename_removes_unsafe_characters(self):
        self.assertEqual(
            calibration_profiles.safe_profile_filename(' Team: A/B* "Main" '),
            "Team_A_B_Main.json",
        )
        self.assertEqual(
            calibration_profiles.safe_profile_filename("CON"),
            "CON_profile.json",
        )
        self.assertEqual(
            calibration_profiles.safe_profile_filename("   "),
            "profile.json",
        )

    def test_region_roundtrip_uses_left_top_width_height(self):
        region = ScreenRegion(left=1, top=2, width=3, height=4)
        encoded = calibration_profiles.screen_region_to_dict(region)
        self.assertEqual(
            encoded,
            {"left": 1, "top": 2, "width": 3, "height": 4},
        )
        self.assertNotIn("x", encoded)
        self.assertNotIn("y", encoded)
        self.assertEqual(
            calibration_profiles.screen_region_from_dict(encoded),
            region,
        )

    def test_region_rejects_missing_fields_non_ints_and_empty_sizes(self):
        with self.assertRaises(ProfileValidationError):
            calibration_profiles.screen_region_from_dict(
                {"top": 2, "width": 3, "height": 4}
            )
        with self.assertRaises(ProfileValidationError):
            calibration_profiles.screen_region_from_dict(
                {"left": 1, "top": 2, "width": "3", "height": 4}
            )
        with self.assertRaises(ProfileValidationError):
            calibration_profiles.screen_region_from_dict(
                {"left": 1, "top": 2, "width": 0, "height": 4}
            )

    def test_build_profile_requires_all_tid_area_fields(self):
        areas = sample_areas()
        del areas["favorite_button_region"]
        with self.assertRaisesRegex(ProfileValidationError, "favorite_button_region"):
            calibration_profiles.build_profile(
                "main",
                areas,
                system_info=sample_system_info(),
                created_at="2026-07-10T00:00:00",
            )

    def test_profile_dict_roundtrip_validates_schema_and_areas(self):
        profile = calibration_profiles.build_profile(
            "main",
            sample_areas(),
            system_info=sample_system_info(),
            created_at="2026-07-10T00:00:00",
        )
        data = calibration_profiles.profile_to_dict(profile)
        self.assertEqual(data["schema_version"], "1.0")
        self.assertEqual(
            set(data["areas"]),
            set(calibration_profiles.REQUIRED_AREA_FIELDS),
        )
        decoded = calibration_profiles.profile_from_dict(data)
        self.assertEqual(decoded.profile_name, "main")
        self.assertEqual(decoded.areas["forward_icon"], sample_areas()["forward_icon"])

    def test_profile_rejects_unsupported_schema_version(self):
        profile = calibration_profiles.build_profile(
            "main",
            sample_areas(),
            system_info=sample_system_info(),
            created_at="2026-07-10T00:00:00",
        )
        data = calibration_profiles.profile_to_dict(profile)
        data["schema_version"] = "2.0"
        with self.assertRaisesRegex(ProfileValidationError, "schema_version"):
            calibration_profiles.profile_from_dict(data)

    def test_profile_rejects_missing_system_info_and_areas(self):
        profile = calibration_profiles.build_profile(
            "main",
            sample_areas(),
            system_info=sample_system_info(),
            created_at="2026-07-10T00:00:00",
        )
        data = calibration_profiles.profile_to_dict(profile)

        missing_system_info = dict(data)
        del missing_system_info["system_info"]
        with self.assertRaisesRegex(ProfileValidationError, "system_info"):
            calibration_profiles.profile_from_dict(missing_system_info)

        missing_areas = dict(data)
        del missing_areas["areas"]
        with self.assertRaisesRegex(ProfileValidationError, "areas"):
            calibration_profiles.profile_from_dict(missing_areas)

    def test_profile_rejects_region_type_errors_and_non_positive_sizes(self):
        profile = calibration_profiles.build_profile(
            "main",
            sample_areas(),
            system_info=sample_system_info(),
            created_at="2026-07-10T00:00:00",
        )
        data = calibration_profiles.profile_to_dict(profile)

        data["areas"]["forward_icon"]["width"] = "30"
        with self.assertRaisesRegex(ProfileValidationError, "forward_icon"):
            calibration_profiles.profile_from_dict(data)

        data = calibration_profiles.profile_to_dict(profile)
        data["areas"]["forward_icon"]["height"] = -1
        with self.assertRaisesRegex(ProfileValidationError, "forward_icon"):
            calibration_profiles.profile_from_dict(data)

    def test_save_profile_creates_directory_and_refuses_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp) / "calibration_profiles"
            profile = calibration_profiles.build_profile(
                "main",
                sample_areas(),
                system_info=sample_system_info(),
                created_at="2026-07-10T00:00:00",
            )
            path = calibration_profiles.save_profile(profile, base_dir=base_dir)
            self.assertTrue(path.exists())
            self.assertEqual(path.parent, base_dir)
            with self.assertRaises(ProfileExistsError):
                calibration_profiles.save_profile(profile, base_dir=base_dir)

            overwritten = calibration_profiles.save_profile(
                profile,
                base_dir=base_dir,
                overwrite=True,
            )
            self.assertEqual(overwritten, path)

    def test_default_profile_dir_remains_cwd_relative_and_creatable(self):
        original_cwd = Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                os.chdir(tmp)
                self.assertEqual(
                    calibration_profiles.profile_path("main"),
                    Path("calibration_profiles/main.json"),
                )
                directory = calibration_profiles.ensure_profile_dir()
                self.assertEqual(directory, Path("calibration_profiles"))
                self.assertTrue((Path(tmp) / directory).is_dir())
            finally:
                os.chdir(original_cwd)

    def test_load_profile_reads_saved_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            profile = calibration_profiles.build_profile(
                "Team A",
                sample_areas(),
                system_info=sample_system_info(),
                created_at="2026-07-10T00:00:00",
            )
            calibration_profiles.save_profile(profile, base_dir=base_dir)
            loaded = calibration_profiles.load_profile("Team A", base_dir=base_dir)
            self.assertEqual(loaded.profile_name, "Team A")
            self.assertEqual(loaded.areas["input_box"], sample_areas()["input_box"])

    def test_load_profile_reports_json_parse_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.json"
            path.write_text("{bad json", encoding="utf-8")
            with self.assertRaises(ProfileJsonError):
                calibration_profiles.load_profile_file(path)

    def test_scan_profiles_skips_damaged_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            good = calibration_profiles.build_profile(
                "good",
                sample_areas(),
                system_info=sample_system_info(),
                created_at="2026-07-10T00:00:00",
            )
            calibration_profiles.save_profile(good, base_dir=base_dir)
            (base_dir / "broken.json").write_text("{bad json", encoding="utf-8")
            (base_dir / "wrong_schema.json").write_text(
                json.dumps({"schema_version": "2.0"}),
                encoding="utf-8",
            )

            scan = calibration_profiles.scan_profiles(base_dir)
            self.assertEqual([item.profile_name for item in scan.profiles], ["good"])
            self.assertEqual(len(scan.invalid_profiles), 2)
            self.assertEqual(
                [item.profile_name for item in calibration_profiles.list_profiles(base_dir)],
                ["good"],
            )

    def test_scan_profiles_lists_multiple_valid_templates(self):
        with tempfile.TemporaryDirectory() as tmp:
            base_dir = Path(tmp)
            alpha = calibration_profiles.build_profile(
                "alpha",
                sample_areas(),
                system_info=sample_system_info(),
                created_at="2026-07-10T00:00:00",
            )
            beta = calibration_profiles.build_profile(
                "beta",
                sample_areas(),
                system_info=sample_system_info(),
                created_at="2026-07-10T00:00:00",
            )

            calibration_profiles.save_profile(beta, base_dir=base_dir)
            calibration_profiles.save_profile(alpha, base_dir=base_dir)

            scan = calibration_profiles.scan_profiles(base_dir)
            self.assertEqual([item.profile_name for item in scan.profiles], ["alpha", "beta"])
            self.assertEqual(scan.invalid_profiles, [])

    def test_scan_profiles_missing_directory_returns_empty_lists(self):
        with tempfile.TemporaryDirectory() as tmp:
            scan = calibration_profiles.scan_profiles(Path(tmp) / "missing")
            self.assertEqual(scan.profiles, [])
            self.assertEqual(scan.invalid_profiles, [])

    def test_compare_system_info_matches_exact_values(self):
        info = sample_system_info()
        match = calibration_profiles.compare_system_info(info, info)
        self.assertTrue(match.matches)
        self.assertEqual(match.mismatches, {})

    def test_compare_system_info_reports_mismatches(self):
        match = calibration_profiles.compare_system_info(
            sample_system_info(),
            sample_system_info(screen_width=2560, dpi_scale=1.5),
        )
        self.assertFalse(match.matches)
        self.assertEqual(match.mismatches["screen_width"], (1920, 2560))
        self.assertEqual(match.mismatches["dpi_scale"], (1.25, 1.5))

    def test_compare_system_info_warns_when_both_dpi_values_are_missing(self):
        info = sample_system_info(dpi_scale=None)
        match = calibration_profiles.compare_system_info(info, info)
        self.assertTrue(match.matches)
        self.assertIn("dpi_scale", match.warnings[0])

    def test_compare_system_info_rejects_missing_dpi_on_only_one_side(self):
        match = calibration_profiles.compare_system_info(
            sample_system_info(os="Darwin", dpi_scale=None),
            sample_system_info(os="Darwin", dpi_scale=2.0),
        )
        self.assertFalse(match.matches)
        self.assertEqual(match.mismatches["dpi_scale"], (None, 2.0))

    def test_compare_system_info_rejects_os_and_resolution_mismatches(self):
        match = calibration_profiles.compare_system_info(
            sample_system_info(os="Darwin", screen_width=1728),
            sample_system_info(os="Windows", screen_width=1920),
        )
        self.assertFalse(match.matches)
        self.assertEqual(match.mismatches["os"], ("Darwin", "Windows"))
        self.assertEqual(match.mismatches["screen_width"], (1728, 1920))

    def test_get_system_info_uses_primary_monitor_and_platform(self):
        with (
            patch.object(calibration_profiles.platform, "system", return_value="Windows"),
            patch.object(
                calibration_profiles,
                "primary_monitor_region",
                return_value=ScreenRegion(left=0, top=0, width=1920, height=1080),
            ),
            patch.object(calibration_profiles, "_windows_dpi_scale", return_value=1.25),
        ):
            self.assertEqual(
                calibration_profiles.get_system_info(),
                {
                    "os": "Windows",
                    "screen_width": 1920,
                    "screen_height": 1080,
                    "dpi_scale": 1.25,
                },
            )

    def test_get_system_info_on_darwin_keeps_monitor_size_and_null_dpi(self):
        with (
            patch.object(calibration_profiles.platform, "system", return_value="Darwin"),
            patch.object(
                calibration_profiles,
                "primary_monitor_region",
                return_value=ScreenRegion(left=0, top=0, width=1728, height=1117),
            ),
        ):
            self.assertEqual(
                calibration_profiles.get_system_info(),
                {
                    "os": "Darwin",
                    "screen_width": 1728,
                    "screen_height": 1117,
                    "dpi_scale": None,
                },
            )

    def test_profile_json_serializes_missing_dpi_as_null(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile = calibration_profiles.build_profile(
                "darwin",
                sample_areas(),
                system_info=sample_system_info(os="Darwin", dpi_scale=None),
                created_at="2026-07-10T00:00:00",
            )
            path = calibration_profiles.save_profile(profile, base_dir=Path(tmp))
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertIsNone(saved["system_info"]["dpi_scale"])


if __name__ == "__main__":
    unittest.main()
