"""Calibration profile JSON read/write and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import ctypes
import json
from pathlib import Path
import platform
import re
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from ocr_calibration import ScreenRegion, primary_monitor_region


SCHEMA_VERSION = "1.0"
PROFILE_DIR = Path("calibration_profiles")

REQUIRED_AREA_FIELDS = (
    "first_candidate",
    "open_filter",
    "unseen_filter",
    "confirm_filter",
    "forward_icon",
    "email_tab",
    "recent_email",
    "input_box",
    "forward_button",
    "focus_restore_region",
    "favorite_button_region",
)

REGION_KEYS = ("left", "top", "width", "height")
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class CalibrationProfileError(ValueError):
    """Base class for calibration profile errors."""


class ProfileExistsError(CalibrationProfileError):
    """Raised when saving would overwrite an existing profile."""


class ProfileJsonError(CalibrationProfileError):
    """Raised when a profile file is not valid JSON."""


class ProfileValidationError(CalibrationProfileError):
    """Raised when a profile JSON object does not match the schema."""


@dataclass(frozen=True)
class CalibrationProfile:
    schema_version: str
    profile_name: str
    created_at: str
    system_info: Dict[str, Any]
    areas: Dict[str, ScreenRegion]


@dataclass(frozen=True)
class ProfileSummary:
    profile_name: str
    path: Path
    created_at: str
    system_info: Dict[str, Any]


@dataclass(frozen=True)
class InvalidProfile:
    path: Path
    error: str


@dataclass(frozen=True)
class ProfileScan:
    profiles: List[ProfileSummary]
    invalid_profiles: List[InvalidProfile]


@dataclass(frozen=True)
class SystemInfoMatch:
    matches: bool
    mismatches: Dict[str, Tuple[Any, Any]]
    warnings: List[str]


def safe_profile_filename(profile_name: str) -> str:
    """Return a stable safe JSON filename for a user-provided profile name."""

    raw = "" if profile_name is None else str(profile_name).strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", raw)
    cleaned = re.sub(r"\s+", "_", cleaned)
    cleaned = re.sub(r"_+", "_", cleaned)
    cleaned = cleaned.strip(" ._")
    if not cleaned:
        cleaned = "profile"
    if cleaned.lower() in WINDOWS_RESERVED_NAMES:
        cleaned = f"{cleaned}_profile"
    if len(cleaned) > 80:
        cleaned = cleaned[:80].rstrip(" ._") or "profile"
    return f"{cleaned}.json"


def ensure_profile_dir(base_dir: Path = PROFILE_DIR) -> Path:
    path = Path(base_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def profile_path(profile_name: str, base_dir: Path = PROFILE_DIR) -> Path:
    return Path(base_dir) / safe_profile_filename(profile_name)


def screen_region_to_dict(region: ScreenRegion) -> Dict[str, int]:
    return {
        "left": int(region.left),
        "top": int(region.top),
        "width": int(region.width),
        "height": int(region.height),
    }


def screen_region_from_dict(value: Mapping[str, Any]) -> ScreenRegion:
    if not isinstance(value, Mapping):
        raise ProfileValidationError("region must be an object")

    missing = [key for key in REGION_KEYS if key not in value]
    if missing:
        raise ProfileValidationError(f"region missing fields: {', '.join(missing)}")

    parsed: Dict[str, int] = {}
    for key in REGION_KEYS:
        item = value[key]
        if isinstance(item, bool) or not isinstance(item, int):
            raise ProfileValidationError(f"region.{key} must be an integer")
        parsed[key] = item

    if parsed["width"] <= 0 or parsed["height"] <= 0:
        raise ProfileValidationError("region width and height must be positive")

    return ScreenRegion(
        left=parsed["left"],
        top=parsed["top"],
        width=parsed["width"],
        height=parsed["height"],
    )


def _normalize_areas(areas: Mapping[str, Any]) -> Dict[str, ScreenRegion]:
    if not isinstance(areas, Mapping):
        raise ProfileValidationError("areas must be an object")

    normalized: Dict[str, ScreenRegion] = {}
    for field_name in REQUIRED_AREA_FIELDS:
        if field_name not in areas:
            raise ProfileValidationError(f"areas missing required field: {field_name}")
        value = areas[field_name]
        if isinstance(value, ScreenRegion):
            region = value
            if region.width <= 0 or region.height <= 0:
                raise ProfileValidationError(
                    f"areas.{field_name} width and height must be positive"
                )
        else:
            try:
                region = screen_region_from_dict(value)
            except ProfileValidationError as exc:
                raise ProfileValidationError(f"areas.{field_name}: {exc}") from exc
        normalized[field_name] = region

    return normalized


def _areas_to_dict(areas: Mapping[str, ScreenRegion]) -> Dict[str, Dict[str, int]]:
    return {
        field_name: screen_region_to_dict(areas[field_name])
        for field_name in REQUIRED_AREA_FIELDS
    }


def profile_to_dict(profile: CalibrationProfile) -> Dict[str, Any]:
    return {
        "schema_version": profile.schema_version,
        "profile_name": profile.profile_name,
        "created_at": profile.created_at,
        "system_info": dict(profile.system_info),
        "areas": _areas_to_dict(profile.areas),
    }


def profile_from_dict(value: Mapping[str, Any]) -> CalibrationProfile:
    if not isinstance(value, Mapping):
        raise ProfileValidationError("profile must be an object")

    schema_version = value.get("schema_version")
    if schema_version != SCHEMA_VERSION:
        raise ProfileValidationError(f"unsupported schema_version: {schema_version!r}")

    profile_name = value.get("profile_name")
    if not isinstance(profile_name, str) or not profile_name.strip():
        raise ProfileValidationError("profile_name must be a non-empty string")

    created_at = value.get("created_at")
    if not isinstance(created_at, str) or not created_at.strip():
        raise ProfileValidationError("created_at must be a non-empty string")

    system_info = value.get("system_info")
    if not isinstance(system_info, Mapping):
        raise ProfileValidationError("system_info must be an object")

    areas = _normalize_areas(value.get("areas"))
    return CalibrationProfile(
        schema_version=SCHEMA_VERSION,
        profile_name=profile_name,
        created_at=created_at,
        system_info=dict(system_info),
        areas=areas,
    )


def build_profile(
    profile_name: str,
    areas: Mapping[str, Any],
    *,
    system_info: Optional[Mapping[str, Any]] = None,
    created_at: Optional[str] = None,
) -> CalibrationProfile:
    name = "" if profile_name is None else str(profile_name).strip()
    if not name:
        raise ProfileValidationError("profile_name must be a non-empty string")

    info = dict(system_info) if system_info is not None else get_system_info()
    timestamp = created_at or datetime.now().isoformat(timespec="seconds")
    return CalibrationProfile(
        schema_version=SCHEMA_VERSION,
        profile_name=name,
        created_at=timestamp,
        system_info=info,
        areas=_normalize_areas(areas),
    )


def save_profile(
    profile: CalibrationProfile,
    *,
    base_dir: Path = PROFILE_DIR,
    overwrite: bool = False,
) -> Path:
    directory = ensure_profile_dir(base_dir)
    path = directory / safe_profile_filename(profile.profile_name)
    if path.exists() and not overwrite:
        raise ProfileExistsError(f"profile already exists: {profile.profile_name}")

    profile_from_dict(profile_to_dict(profile))
    path.write_text(
        json.dumps(profile_to_dict(profile), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def load_profile_file(path: Path) -> CalibrationProfile:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise CalibrationProfileError(f"cannot read profile: {path}") from exc

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProfileJsonError(f"invalid JSON in profile: {path}") from exc

    return profile_from_dict(value)


def load_profile(profile_name: str, *, base_dir: Path = PROFILE_DIR) -> CalibrationProfile:
    return load_profile_file(profile_path(profile_name, base_dir))


def scan_profiles(base_dir: Path = PROFILE_DIR) -> ProfileScan:
    directory = Path(base_dir)
    if not directory.exists():
        return ProfileScan(profiles=[], invalid_profiles=[])

    profiles: List[ProfileSummary] = []
    invalid_profiles: List[InvalidProfile] = []
    for path in sorted(directory.glob("*.json")):
        try:
            profile = load_profile_file(path)
        except CalibrationProfileError as exc:
            invalid_profiles.append(InvalidProfile(path=path, error=str(exc)))
            continue
        profiles.append(
            ProfileSummary(
                profile_name=profile.profile_name,
                path=path,
                created_at=profile.created_at,
                system_info=dict(profile.system_info),
            )
        )

    return ProfileScan(profiles=profiles, invalid_profiles=invalid_profiles)


def list_profiles(base_dir: Path = PROFILE_DIR) -> List[ProfileSummary]:
    return scan_profiles(base_dir).profiles


def _windows_dpi_scale() -> Optional[float]:
    if platform.system() != "Windows":
        return None
    try:
        dpi = ctypes.windll.user32.GetDpiForSystem()
        if dpi:
            return round(float(dpi) / 96.0, 4)
    except (AttributeError, OSError):
        return None
    return None


def get_system_info() -> Dict[str, Any]:
    width = None
    height = None
    try:
        monitor = primary_monitor_region()
        width = monitor.width
        height = monitor.height
    except Exception:
        try:
            import pyautogui

            size = pyautogui.size()
            width = int(size.width)
            height = int(size.height)
        except Exception:
            width = None
            height = None

    return {
        "os": platform.system(),
        "screen_width": width,
        "screen_height": height,
        "dpi_scale": _windows_dpi_scale(),
    }


def compare_system_info(
    saved_info: Mapping[str, Any],
    current_info: Optional[Mapping[str, Any]] = None,
) -> SystemInfoMatch:
    if not isinstance(saved_info, Mapping):
        raise ProfileValidationError("saved system_info must be an object")

    current = dict(current_info) if current_info is not None else get_system_info()
    mismatches: Dict[str, Tuple[Any, Any]] = {}
    warnings: List[str] = []

    for key in ("os", "screen_width", "screen_height"):
        saved_value = saved_info.get(key)
        current_value = current.get(key)
        if saved_value != current_value:
            mismatches[key] = (saved_value, current_value)

    saved_dpi = saved_info.get("dpi_scale")
    current_dpi = current.get("dpi_scale")
    if saved_dpi is None and current_dpi is None:
        warnings.append("dpi_scale unavailable in saved and current environment")
    elif saved_dpi is None or current_dpi is None:
        mismatches["dpi_scale"] = (saved_dpi, current_dpi)
    else:
        try:
            dpi_matches = abs(float(saved_dpi) - float(current_dpi)) <= 0.01
        except (TypeError, ValueError):
            dpi_matches = False
        if not dpi_matches:
            mismatches["dpi_scale"] = (saved_dpi, current_dpi)

    return SystemInfoMatch(
        matches=not mismatches,
        mismatches=mismatches,
        warnings=warnings,
    )


def required_area_fields() -> Tuple[str, ...]:
    return REQUIRED_AREA_FIELDS
