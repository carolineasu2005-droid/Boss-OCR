# -*- coding: utf-8 -*-
"""
BOSS 直聘推荐牛人自动刷简历 v4 —— 键盘翻页 + 智能邮件转发版

交互方案：
1. 启动时输入触发关键词规则（规则用 ; 分隔）和备选邮箱
2. 鼠标保持不动，脚本只执行一次左键点击打开第一位候选人
3. 后续全部用键盘右方向键（→）切换下一位候选人
4. 每位候选人详情页停留 12-18 秒（随机），期间随机滚动
5. 停留期间检测详情页内容，命中任意关键词规则则触发邮件转发
6. 转发完成后右键恢复键盘焦点，继续用右方向键翻页
7. 每 100 人自动 F5 刷新
8. ESC 停止 / 空格暂停
"""
import sys
import io
import os
import json
import hashlib
import ctypes
from ctypes import wintypes
import time
import random
import math
import logging
import subprocess
import threading
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import urlparse

IS_WINDOWS = sys.platform == 'win32'
IS_MACOS = sys.platform == 'darwin'
ACTION_MODE_FAVORITE = 'favorite'
ACTION_MODE_FORWARD = 'forward'
MACOS_CHROME_EXECUTABLE = Path(
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
)
CHROME_SAFE_TARGET = 'about:blank'
MACOS_PERMISSION_GUIDANCE = (
    'macOS 权限绑定实际运行宿主：Terminal / iTerm / VS Code / Python / '
    '打包 App 可能被视为不同授权主体。权限变更后可能需要完全退出并重启宿主进程。'
    '辅助功能：系统设置 → 隐私与安全性 → 辅助功能；'
    '屏幕录制：系统设置 → 隐私与安全性 → 屏幕录制；'
    '键盘监听失败时请检查输入监控或辅助功能授权。'
)

if IS_WINDOWS:
    import win32clipboard
    import win32con
    import win32gui
    import win32process
else:
    win32clipboard = None
    win32con = None
    win32gui = None
    win32process = None

import pyautogui
from pynput import keyboard
import mouse_motion

from ocr_calibration import (
    CalibrationCancelled,
    CalibrationCleanupFailed,
    ScreenRegion,
    enable_windows_dpi_awareness,
    is_tk_overlay_cleanup_complete,
    save_region_preview,
    select_screen_region,
)
from ocr_detector import MSSScreenCapture, OCRKeywordDetector, RapidOCRBackend
from ocr_text import parse_keyword_rules


class MacSafeBrowseArgumentError(ValueError):
    """Fail-closed CLI validation error for the future macOS safe mode."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


class MacSafeBrowseRuntimeError(RuntimeError):
    """Fail-closed runtime error for bounded macOS safe-browse helpers."""

    def __init__(self, error_code: str, message: str):
        super().__init__(message)
        self.error_code = error_code


def _parse_mac_safe_browse_limit(raw_value, option_name):
    """Parse one bounded CLI limit without consulting runtime state."""
    value = str(raw_value).strip() if raw_value is not None else ''
    if not value.isascii() or not value.isdigit():
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_LIMIT_INVALID',
            f'{option_name} 必须是正整数',
        )
    return int(value)


# ─── 命令行参数解析 ───────────────────────────────
def parse_args():
    """解析命令行参数"""
    args = {
        'keywords': '',
        'email': '',
        'forwarding_email': '',
        'duration_seconds': '',
        'action_mode': ACTION_MODE_FORWARD,
        'no_forward': False,
        'no_batch_filter': False,
        'simple_mouse': False,
        'auto': False,
        'preflight_only': False,
        'coordinate_diagnostics_only': False,
        'mac_safe_browse_only': False,
        'mac_safe_browse_calibrate_only': False,
        'mac_safe_browse_calibrate_and_dry_run': False,
        'mac_safe_browse_real_capture_once': False,
        'mac_safe_browse_open_candidate_once': False,
        'mac_forward_ui_smoke_only': False,
        'mac_single_candidate_forward_smoke': False,
        'allow_invalid_forward_submit_smoke': False,
        'allow_test_forward_submit': False,
        'max_candidates': None,
        'max_runtime_minutes': None,
    }
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--keywords' and i + 1 < len(sys.argv):
            args['keywords'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--email' and i + 1 < len(sys.argv):
            args['email'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--forwarding-email' and i + 1 < len(sys.argv):
            args['forwarding_email'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--duration-seconds':
            if i + 1 >= len(sys.argv):
                raise ValueError('--duration-seconds 缺少秒数')
            args['duration_seconds'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--action-mode':
            if i + 1 >= len(sys.argv):
                raise ValueError('--action-mode 缺少模式值')
            action_mode_value = sys.argv[i + 1].strip().lower()
            if action_mode_value not in (
                ACTION_MODE_FAVORITE,
                ACTION_MODE_FORWARD,
            ):
                raise ValueError('--action-mode 必须是 favorite 或 forward')
            args['action_mode'] = action_mode_value
            i += 2
        elif sys.argv[i] == '--no-forward':
            args['no_forward'] = True
            i += 1
        elif sys.argv[i] == '--no-batch-filter':
            args['no_batch_filter'] = True
            i += 1
        elif sys.argv[i] == '--simple-mouse':
            args['simple_mouse'] = True
            i += 1
        elif sys.argv[i] == '--auto':
            args['auto'] = True  # 跳过所有交互
            i += 1
        elif sys.argv[i] == '--preflight-only':
            args['preflight_only'] = True
            i += 1
        elif sys.argv[i] == '--coordinate-diagnostics-only':
            args['coordinate_diagnostics_only'] = True
            i += 1
        elif sys.argv[i] == '--mac-safe-browse-only':
            args['mac_safe_browse_only'] = True
            i += 1
        elif sys.argv[i] == '--mac-safe-browse-calibrate-only':
            args['mac_safe_browse_calibrate_only'] = True
            i += 1
        elif sys.argv[i] == '--mac-safe-browse-calibrate-and-dry-run':
            args['mac_safe_browse_calibrate_and_dry_run'] = True
            i += 1
        elif sys.argv[i] == '--mac-safe-browse-real-capture-once':
            args['mac_safe_browse_real_capture_once'] = True
            i += 1
        elif sys.argv[i] == '--mac-safe-browse-open-candidate-once':
            args['mac_safe_browse_open_candidate_once'] = True
            i += 1
        elif sys.argv[i] == '--mac-forward-ui-smoke-only':
            args['mac_forward_ui_smoke_only'] = True
            i += 1
        elif sys.argv[i] == '--mac-single-candidate-forward-smoke':
            args['mac_single_candidate_forward_smoke'] = True
            i += 1
        elif sys.argv[i] == '--allow-invalid-forward-submit-smoke':
            args['allow_invalid_forward_submit_smoke'] = True
            i += 1
        elif sys.argv[i] == '--allow-test-forward-submit':
            args['allow_test_forward_submit'] = True
            i += 1
        elif sys.argv[i] == '--max-candidates':
            if i + 1 >= len(sys.argv) or sys.argv[i + 1].startswith('--'):
                raise MacSafeBrowseArgumentError(
                    'MAC_SAFE_BROWSE_LIMIT_INVALID',
                    '--max-candidates 缺少正整数',
                )
            args['max_candidates'] = _parse_mac_safe_browse_limit(
                sys.argv[i + 1],
                '--max-candidates',
            )
            i += 2
        elif sys.argv[i] == '--max-runtime-minutes':
            if i + 1 >= len(sys.argv) or sys.argv[i + 1].startswith('--'):
                raise MacSafeBrowseArgumentError(
                    'MAC_SAFE_BROWSE_LIMIT_INVALID',
                    '--max-runtime-minutes 缺少正整数',
                )
            args['max_runtime_minutes'] = _parse_mac_safe_browse_limit(
                sys.argv[i + 1],
                '--max-runtime-minutes',
            )
            i += 2
        else:
            i += 1
    if args['mac_safe_browse_calibrate_and_dry_run'] and (
        args['mac_safe_browse_only']
        or args['mac_safe_browse_calibrate_only']
        or args['auto']
        or args['preflight_only']
        or args['coordinate_diagnostics_only']
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_CALIBRATE_AND_DRY_RUN_CONFLICTING_MODE',
            '--mac-safe-browse-calibrate-and-dry-run 不能与 safe browse、'
            'calibrate-only、--auto、--preflight-only 或 '
            '--coordinate-diagnostics-only 同时使用',
        )
    if args['mac_safe_browse_real_capture_once'] and (
        not args['mac_safe_browse_calibrate_and_dry_run']
        or args['mac_safe_browse_only']
        or args['mac_safe_browse_calibrate_only']
        or args['auto']
        or args['preflight_only']
        or args['coordinate_diagnostics_only']
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_REAL_CAPTURE_CONFLICTING_MODE',
            '--mac-safe-browse-real-capture-once 只能与 '
            '--mac-safe-browse-calibrate-and-dry-run 同用，且不能与 '
            '--auto、--preflight-only 或 --coordinate-diagnostics-only 共用',
        )
    if args['mac_safe_browse_open_candidate_once'] and (
        not args['mac_safe_browse_calibrate_and_dry_run']
        or args['mac_safe_browse_only']
        or args['mac_safe_browse_calibrate_only']
        or args['auto']
        or args['preflight_only']
        or args['coordinate_diagnostics_only']
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_OPEN_CANDIDATE_CONFLICTING_MODE',
            '--mac-safe-browse-open-candidate-once 只能与 '
            '--mac-safe-browse-calibrate-and-dry-run 同用，且不能与 '
            '--auto、--preflight-only 或 --coordinate-diagnostics-only 共用',
        )
    if args['mac_forward_ui_smoke_only'] and (
        args['mac_single_candidate_forward_smoke']
        or args['mac_safe_browse_only']
        or args['mac_safe_browse_calibrate_only']
        or args['mac_safe_browse_calibrate_and_dry_run']
        or args['auto']
        or args['preflight_only']
        or args['coordinate_diagnostics_only']
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_FORWARD_UI_SMOKE_CONFLICTING_MODE',
            '--mac-forward-ui-smoke-only 不能与 safe browse、--auto、'
            '--preflight-only 或 --coordinate-diagnostics-only 同时使用',
        )
    if args['mac_single_candidate_forward_smoke'] and (
        args['mac_forward_ui_smoke_only']
        or args['mac_safe_browse_only']
        or args['mac_safe_browse_calibrate_only']
        or args['mac_safe_browse_calibrate_and_dry_run']
        or args['auto']
        or args['preflight_only']
        or args['coordinate_diagnostics_only']
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_SMOKE_CONFLICTING_MODE',
            '--mac-single-candidate-forward-smoke 不能与 safe browse、'
            '--mac-forward-ui-smoke-only、--auto、--preflight-only 或 '
            '--coordinate-diagnostics-only 同时使用',
        )
    if args['allow_invalid_forward_submit_smoke'] and (
        not args['mac_forward_ui_smoke_only']
        or args['mac_safe_browse_only']
        or args['mac_safe_browse_calibrate_only']
        or args['mac_safe_browse_calibrate_and_dry_run']
        or args['auto']
        or args['preflight_only']
        or args['coordinate_diagnostics_only']
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_FORWARD_UI_SMOKE_SUBMIT_CONFLICTING_MODE',
            '--allow-invalid-forward-submit-smoke 只能与 '
            '--mac-forward-ui-smoke-only 同用',
        )
    if args['allow_test_forward_submit'] and (
        not args['mac_single_candidate_forward_smoke']
        or args['mac_forward_ui_smoke_only']
        or args['mac_safe_browse_only']
        or args['mac_safe_browse_calibrate_only']
        or args['mac_safe_browse_calibrate_and_dry_run']
        or args['auto']
        or args['preflight_only']
        or args['coordinate_diagnostics_only']
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_SUBMIT_CONFLICTING_MODE',
            '--allow-test-forward-submit 只能与 '
            '--mac-single-candidate-forward-smoke 同用',
        )
    if args['mac_safe_browse_calibrate_only'] and (
        args['mac_safe_browse_only']
        or args['mac_safe_browse_calibrate_and_dry_run']
        or args['auto']
        or args['preflight_only']
        or args['coordinate_diagnostics_only']
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_CALIBRATION_CONFLICTING_MODE',
            '--mac-safe-browse-calibrate-only 不能与 safe browse、calibrate '
            'and dry run、--auto、--preflight-only 或 '
            '--coordinate-diagnostics-only 同时使用',
        )
    if args['mac_safe_browse_only'] and (
        args['auto']
        or args['preflight_only']
        or args['coordinate_diagnostics_only']
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_CONFLICTING_MODE',
            '--mac-safe-browse-only 不能与 --auto、--preflight-only 或 '
            '--coordinate-diagnostics-only 同时使用',
        )
    if args['preflight_only'] and args['coordinate_diagnostics_only']:
        raise ValueError(
            '--coordinate-diagnostics-only 不能与 --preflight-only 同时使用'
        )
    return args

# 修复 Windows 终端 UTF-8 输出
try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
except Exception:
    pass  # PyInstaller 打包后可能无 buffer，静默忽略

# ─── 配置 ───────────────────────────────────────────
MIN_STAY_SECONDS = 12
MAX_STAY_SECONDS = 18
BATCH_SIZE = 100
REFRESH_WAIT_SECONDS = 5
CLICK_WAIT_SECONDS = 2
COUNTDOWN_SECONDS = 3
FILTER_OPEN_DELAY_MIN = 0.5
FILTER_OPEN_DELAY_MAX = 1.0
FILTER_OPTION_DELAY_MIN = 0.3
FILTER_OPTION_DELAY_MAX = 0.7
FILTER_RESULTS_DELAY_MIN = 2.0
FILTER_RESULTS_DELAY_MAX = 3.0

# OCR 关键词检测
OCR_MAX_SCANS = 8
OCR_MIN_CONFIDENCE = 0.85
OCR_SCROLL_MIN_STEPS = 100
OCR_SCROLL_MAX_STEPS = 140
OCR_SETTLE_SECONDS = 0.6
OCR_CONFIRMATION_SECONDS = 0.7
OCR_PREVIEW_PATH = Path('logs/ocr_calibration_preview.png')

# 滚动
SCROLL_PROBABILITY = 0.8
SCROLL_MIN_STEPS = 10
SCROLL_MAX_STEPS = 40
SCROLL_MAX_TIMES = 3

# ─── 转发功能配置 ────────────────────────────────────
@dataclass(frozen=True)
class ForwardClickRegions:
    """Runtime click regions for the mail-forwarding workflow."""

    forward_icon: ScreenRegion
    email_tab: ScreenRegion
    input_box: ScreenRegion
    recent_email: ScreenRegion
    forward_button: ScreenRegion


@dataclass(frozen=True)
class BatchFilterRegions:
    """Runtime click regions for filtering and opening the first candidate."""

    first_candidate: ScreenRegion
    open_filter: ScreenRegion
    unseen_filter: ScreenRegion
    confirm_filter: ScreenRegion


@dataclass(frozen=True)
class BrowserPrepareResult:
    """Structured result for the platform-specific browser preparation step."""

    ready: bool
    platform: str
    browser: str
    launched: bool = False
    executable_path: str = ''
    message: str = ''
    error_code: str = ''
    focus_frontmost: bool | None = None
    page_url: str | None = None
    page_title: str | None = None
    page_allowed: bool | None = None
    page_error_code: str | None = None


@dataclass(frozen=True)
class MacOSPermissionStatus:
    """Side-effect-free macOS capability diagnostic state."""

    accessibility: str
    screen_recording: str
    keyboard_listener: str
    ready: bool
    message: str = ''


@dataclass(frozen=True)
class MacOSChromeFocusResult:
    """Structured result for macOS Chrome activate/frontmost checks."""

    platform: str
    browser: str
    activated: bool
    frontmost: bool
    message: str = ''
    error_code: str = ''


@dataclass(frozen=True)
class MacOSChromeTabIdentity:
    """Structured result for macOS Chrome active tab metadata queries."""

    platform: str
    browser: str
    url: str = ''
    title: str = ''
    message: str = ''
    error_code: str = ''


@dataclass(frozen=True)
class ScreenCoordinateDiagnostics:
    """Structured result for read-only screen coordinate diagnostics."""

    platform: str
    pyautogui_size: tuple[int, int] | None
    pyautogui_position: tuple[int, int] | None
    mss_monitors: tuple[dict, ...]
    primary_monitor: dict | None
    tk_version: str | None
    tcl_version: str | None
    display_fingerprint: str | None
    passed: bool
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class RetinaScaleInference:
    """Pure metadata result for MSS request-to-image scale inference."""

    request_size: tuple[int, int] | None
    image_size: tuple[int, int] | None
    scale_x: float | None
    scale_y: float | None
    passed: bool
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class TkSelectionRegion:
    """Normalized rectangle in Tk overlay-local coordinates."""

    left: float
    top: float
    width: float
    height: float


@dataclass(frozen=True)
class ScreenshotCropRegion:
    """Half-open integer rectangle in screenshot image pixels."""

    left: int
    top: int
    width: int
    height: int


@dataclass(frozen=True)
class TkToScreenshotMapping:
    """Structured pure-data result for Tk selection-to-crop mapping."""

    tk_selection: TkSelectionRegion | None
    crop_region: ScreenshotCropRegion | None
    passed: bool
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class CropPreviewResult:
    """Structured result for local crop preview saving."""

    saved: bool
    preview_path: str | None
    crop_size: tuple[int, int] | None
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class CoordinateCalibrationMetadata:
    """Coordinate evidence attached to a calibration, never business approval."""

    display_fingerprint: str | None
    scale_inference: RetinaScaleInference | None
    tk_to_screenshot_mapping: TkToScreenshotMapping | None
    crop_preview: CropPreviewResult | None
    validated: bool
    manually_confirmed: bool
    message: str
    error_code: str | None = None
    business_ready: bool = field(default=False, init=False)


@dataclass(frozen=True)
class CalibratedScreenRegion:
    """Backward-compatible ScreenRegion plus optional coordinate evidence."""

    region: ScreenRegion
    coordinate_metadata: CoordinateCalibrationMetadata | None = None


@dataclass(frozen=True)
class MacSafeBrowseConfig:
    """Pure configuration for a future, separately guarded macOS browse mode."""

    enabled: bool
    no_forward_required: bool
    max_candidates: int | None
    max_runtime_minutes: int | None
    require_page_allowed: bool
    require_coordinate_validated: bool
    require_manual_confirmation: bool
    allow_scroll: bool = False
    allow_next_candidate: bool = False
    allow_refresh: bool = False
    allow_filter: bool = False
    message: str = ''


@dataclass(frozen=True)
class MacSafeBrowseEvidence:
    """Caller-supplied facts; collecting them is outside this pure guard."""

    platform: str
    no_forward_enabled: bool
    forwarding_email_present: bool
    page_allowed: bool
    page_stage_allowed: bool
    chrome_frontmost: bool
    coordinate_validated: bool
    manual_confirmed: bool
    listener_available: bool
    profile_unique: bool | None = None
    display_fingerprint_matches: bool | None = None


@dataclass(frozen=True)
class MacSafeBrowseGuard:
    """Fail-closed result that never changes browser or business readiness."""

    passed: bool
    ready_for_browse: bool
    no_forward_enforced: bool
    page_allowed: bool
    coordinate_validated: bool
    manual_confirmed: bool
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class MacSafeBrowseOcrEvidence:
    """Read-only evidence extracted from an existing OCR calibration."""

    passed: bool
    has_calibrated_region: bool
    has_coordinate_metadata: bool
    coordinate_validated: bool
    manually_confirmed: bool
    business_ready: bool
    display_fingerprint: str | None
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class MacSafeBrowseActionBudget:
    """Hard limits for an injected safe-browse action shell."""

    max_candidates: int
    max_runtime_seconds: int
    max_candidate_open: int
    max_scroll: int
    max_next_candidate: int
    max_refresh: int
    max_filter_click: int
    max_focus_restore: int
    max_ocr_capture: int
    max_forward: int = 0
    max_filter_recent_unseen: int = 0
    max_open_forward_modal: int = 0
    max_focus_forward_email_field: int = 0
    max_type_invalid_forward_email: int = 0
    max_submit_test_forward: int = 0
    max_close_forward_modal: int = 0
    max_submit_invalid_forward: int = 0


@dataclass(frozen=True)
class MacSafeBrowseActionState:
    """Immutable action counts and first hard-stop reason."""

    started_at: float
    candidate_open: int = 0
    scroll: int = 0
    next_candidate: int = 0
    refresh: int = 0
    filter_click: int = 0
    focus_restore: int = 0
    ocr_capture: int = 0
    forward: int = 0
    filter_recent_unseen: int = 0
    open_forward_modal: int = 0
    focus_forward_email_field: int = 0
    type_invalid_forward_email: int = 0
    submit_test_forward: int = 0
    close_forward_modal: int = 0
    submit_invalid_forward: int = 0
    stopped: bool = False
    stop_reason: str | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class MacSafeBrowseActionResult:
    """Authorization or injected-execution result for one action."""

    allowed: bool
    state: MacSafeBrowseActionState
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class MacSafeBrowseDryRunStep:
    """One named noop-only step in the 5F-1 audit pipeline."""

    action: str
    description: str


@dataclass(frozen=True)
class MacSafeBrowseDryRunResult:
    """Dry pipeline result that can never enable browsing or forwarding."""

    completed: bool
    state: MacSafeBrowseActionState
    real_browsing_enabled: bool
    forwarding_enabled: bool
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class MacSafeBrowseCalibrationResult:
    """Atomic calibration-only preparation result."""

    published: bool
    calibrated_region: CalibratedScreenRegion | None
    message: str
    overlay_cleanup_completed: bool = False
    error_code: str | None = None


@dataclass(frozen=True)
class MacSafeBrowseCalibrationMetadataSupplyResult:
    """Structured metadata supply result for calibration-only wiring."""

    metadata: CoordinateCalibrationMetadata | None
    preview_path: str | None
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class MacSafeBrowseRealCaptureResult:
    """Structured summary for the one-shot real focus/capture wiring."""

    focus_restored: bool
    capture_completed: bool
    capture_size: tuple[int, int] | None
    message: str
    candidate_open_attempted: bool = False
    candidate_open_verified: bool = False
    candidate_opened: bool = False
    browse_loop_enabled: bool = False
    error_code: str | None = None


@dataclass(frozen=True)
class MacForwardUiSmokeConfig:
    """Validated configuration for macOS forward/filter UI smoke-only mode."""

    enabled: bool
    no_forward_required: bool
    allow_invalid_submit: bool
    invalid_email_text: str
    countdown_seconds: int
    message: str


@dataclass(frozen=True)
class MacForwardUiSmokeActionStatus:
    """Per-action smoke status without implying business success."""

    attempted: bool
    verified: bool
    count: int
    error_code: str | None = None
    message: str = ''


@dataclass(frozen=True)
class MacForwardUiSmokeResult:
    """Result for the independent macOS forward/filter smoke entry."""

    completed: bool
    state: MacSafeBrowseActionState
    statuses: dict[str, MacForwardUiSmokeActionStatus]
    forwarding_enabled: bool
    invalid_submit_enabled: bool
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class MacForwardActionConfig:
    """Reusable single-candidate macOS forward action configuration."""

    allow_invalid_submit: bool
    invalid_email_text: str
    countdown_seconds: int
    message: str


@dataclass(frozen=True)
class MacForwardActionState:
    """Forward-only action counts without implying delivery success."""

    open_forward_modal_count: int
    focus_forward_email_field_count: int
    type_forward_email_count: int
    submit_invalid_forward_count: int
    close_forward_modal_count: int


@dataclass(frozen=True)
class MacForwardActionResult:
    """Result for a bounded single-candidate forward UI attempt."""

    completed: bool
    state: MacForwardActionState
    statuses: dict[str, MacForwardUiSmokeActionStatus]
    forwarding_enabled: bool
    invalid_submit_enabled: bool
    message: str
    error_code: str | None = None


@dataclass(frozen=True)
class MacSingleCandidateForwardSmokeConfig:
    """Validated config for one real test-email submit smoke on macOS."""

    enabled: bool
    forwarding_email: str
    masked_forwarding_email: str
    countdown_seconds: int
    submit_confirm_phrase: str
    message: str


@dataclass(frozen=True)
class MacSingleCandidateForwardSmokeResult:
    """One-candidate real test submit result without delivery verification."""

    completed: bool
    state: MacSafeBrowseActionState
    statuses: dict[str, MacForwardUiSmokeActionStatus]
    test_email_used: str
    stopped_after_single_candidate: bool
    forwarding_submit_attempted: bool
    forwarding_success_verified: bool
    message: str
    error_code: str | None = None


MAC_SAFE_BROWSE_ACTIONS = (
    'candidate_open',
    'scroll',
    'next_candidate',
    'refresh',
    'filter_click',
    'focus_restore',
    'ocr_capture',
    'forward',
    'filter_recent_unseen',
    'open_forward_modal',
    'focus_forward_email_field',
    'type_invalid_forward_email',
    'submit_test_forward',
    'close_forward_modal',
    'submit_invalid_forward',
)


def build_default_mac_safe_browse_action_budget(
    config: MacSafeBrowseConfig,
) -> MacSafeBrowseActionBudget:
    """Build the non-configurable 5E action budget from validated CLI limits."""
    if not isinstance(config, MacSafeBrowseConfig):
        raise TypeError('config 必须是 MacSafeBrowseConfig')
    valid_candidates = (
        isinstance(config.max_candidates, int)
        and not isinstance(config.max_candidates, bool)
        and 1 <= config.max_candidates <= 5
    )
    valid_runtime = (
        isinstance(config.max_runtime_minutes, int)
        and not isinstance(config.max_runtime_minutes, bool)
        and 1 <= config.max_runtime_minutes <= 15
    )
    if not valid_candidates or not valid_runtime:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_LIMIT_INVALID',
            '无法从无效 safe browse limit 构造动作预算',
        )
    return MacSafeBrowseActionBudget(
        max_candidates=config.max_candidates,
        max_runtime_seconds=config.max_runtime_minutes * 60,
        max_candidate_open=min(config.max_candidates, 1),
        max_scroll=0,
        max_next_candidate=0,
        max_refresh=0,
        max_filter_click=0,
        max_focus_restore=1,
        max_ocr_capture=1,
        max_forward=0,
    )


def stop_mac_safe_browse(
    state: MacSafeBrowseActionState,
    reason: str,
    error_code: str,
) -> MacSafeBrowseActionState:
    """Return a stopped copy while preserving the first stop reason."""
    if not isinstance(state, MacSafeBrowseActionState):
        raise TypeError('state 必须是 MacSafeBrowseActionState')
    if state.stopped:
        return state
    return replace(
        state,
        stopped=True,
        stop_reason=reason,
        error_code=error_code,
    )


def can_perform_mac_safe_browse_action(
    budget: MacSafeBrowseActionBudget,
    state: MacSafeBrowseActionState,
    action: str,
    *,
    now: float,
) -> MacSafeBrowseActionResult:
    """Authorize one action without incrementing its count or doing I/O."""
    if not isinstance(budget, MacSafeBrowseActionBudget):
        raise TypeError('budget 必须是 MacSafeBrowseActionBudget')
    if not isinstance(state, MacSafeBrowseActionState):
        raise TypeError('state 必须是 MacSafeBrowseActionState')

    if state.stopped:
        return MacSafeBrowseActionResult(
            allowed=False,
            state=state,
            message=f'safe browse 已停止: {state.stop_reason or "unknown"}',
            error_code='MAC_SAFE_BROWSE_ALREADY_STOPPED',
        )

    if (
        not isinstance(now, (int, float))
        or isinstance(now, bool)
        or not math.isfinite(now)
        or not math.isfinite(state.started_at)
        or now < state.started_at
    ):
        stopped = stop_mac_safe_browse(
            state,
            '运行时钟无效',
            'MAC_SAFE_BROWSE_ACTION_FAILED',
        )
        return MacSafeBrowseActionResult(
            allowed=False,
            state=stopped,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    if now - state.started_at >= budget.max_runtime_seconds:
        stopped = stop_mac_safe_browse(
            state,
            'safe browse 已达到运行时限',
            'MAC_SAFE_BROWSE_RUNTIME_LIMIT_REACHED',
        )
        return MacSafeBrowseActionResult(
            allowed=False,
            state=stopped,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    if action not in MAC_SAFE_BROWSE_ACTIONS:
        stopped = stop_mac_safe_browse(
            state,
            f'未知 safe browse action: {action}',
            'MAC_SAFE_BROWSE_ACTION_UNKNOWN',
        )
        return MacSafeBrowseActionResult(
            allowed=False,
            state=stopped,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    if action == 'forward':
        stopped = stop_mac_safe_browse(
            state,
            'safe browse 永久禁止 forwarding action',
            'MAC_SAFE_BROWSE_FORWARDING_BLOCKED',
        )
        return MacSafeBrowseActionResult(
            allowed=False,
            state=stopped,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    if (
        action == 'candidate_open'
        and state.candidate_open >= budget.max_candidates
    ):
        stopped = stop_mac_safe_browse(
            state,
            '候选人数达到 safe browse 上限',
            'MAC_SAFE_BROWSE_ACTION_LIMIT_REACHED',
        )
        return MacSafeBrowseActionResult(
            allowed=False,
            state=stopped,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    action_limit = getattr(budget, f'max_{action}')
    action_count = getattr(state, action)
    if action_count >= action_limit:
        stopped = stop_mac_safe_browse(
            state,
            f'{action} 达到动作预算上限 {action_limit}',
            'MAC_SAFE_BROWSE_ACTION_LIMIT_REACHED',
        )
        return MacSafeBrowseActionResult(
            allowed=False,
            state=stopped,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    return MacSafeBrowseActionResult(
        allowed=True,
        state=state,
        message=f'{action} 已预留预算，尚未提交计数',
    )


def reserve_mac_safe_browse_action(
    budget: MacSafeBrowseActionBudget,
    state: MacSafeBrowseActionState,
    action: str,
    *,
    now: float,
) -> MacSafeBrowseActionResult:
    """Reserve authorization without changing the immutable count state."""
    return can_perform_mac_safe_browse_action(
        budget,
        state,
        action,
        now=now,
    )


def commit_mac_safe_browse_action_success(
    state: MacSafeBrowseActionState,
    action: str,
) -> MacSafeBrowseActionState:
    """Increment one known, non-forward action after injected success."""
    if not isinstance(state, MacSafeBrowseActionState):
        raise TypeError('state 必须是 MacSafeBrowseActionState')
    if state.stopped:
        return state
    if action not in MAC_SAFE_BROWSE_ACTIONS:
        return stop_mac_safe_browse(
            state,
            f'无法提交未知 action: {action}',
            'MAC_SAFE_BROWSE_ACTION_UNKNOWN',
        )
    if action == 'forward':
        return stop_mac_safe_browse(
            state,
            'safe browse 永久禁止提交 forwarding action',
            'MAC_SAFE_BROWSE_FORWARDING_BLOCKED',
        )
    return replace(state, **{action: getattr(state, action) + 1})


def execute_mac_safe_browse_action(
    budget: MacSafeBrowseActionBudget,
    state: MacSafeBrowseActionState,
    action: str,
    action_fn,
    *,
    now: float,
) -> MacSafeBrowseActionResult:
    """Run one injected callable once; never binds to a real input function."""
    reservation = reserve_mac_safe_browse_action(
        budget,
        state,
        action,
        now=now,
    )
    if not reservation.allowed:
        return reservation

    if not callable(action_fn):
        stopped = stop_mac_safe_browse(
            state,
            f'{action} action_fn 不可调用',
            'MAC_SAFE_BROWSE_ACTION_FAILED',
        )
        return MacSafeBrowseActionResult(
            allowed=False,
            state=stopped,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    try:
        succeeded = bool(action_fn())
    except Exception as exc:
        stopped = stop_mac_safe_browse(
            state,
            f'{action} 执行异常: {exc}',
            'MAC_SAFE_BROWSE_ACTION_FAILED',
        )
        return MacSafeBrowseActionResult(
            allowed=False,
            state=stopped,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    if not succeeded:
        stopped = stop_mac_safe_browse(
            state,
            f'{action} 执行失败',
            'MAC_SAFE_BROWSE_ACTION_FAILED',
        )
        return MacSafeBrowseActionResult(
            allowed=False,
            state=stopped,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    committed = commit_mac_safe_browse_action_success(state, action)
    return MacSafeBrowseActionResult(
        allowed=True,
        state=committed,
        message=f'{action} 执行成功并提交计数',
    )


def build_mac_safe_browse_dry_run_plan(
    config: MacSafeBrowseConfig,
) -> tuple[MacSafeBrowseDryRunStep, ...]:
    """Build the fixed 5F-1 noop plan; config cannot add real actions."""
    if not isinstance(config, MacSafeBrowseConfig):
        raise TypeError('config 必须是 MacSafeBrowseConfig')
    return (
        MacSafeBrowseDryRunStep(
            action='focus_restore',
            description='noop audit of the focus_restore budget path',
        ),
        MacSafeBrowseDryRunStep(
            action='ocr_capture',
            description='noop audit of the ocr_capture budget path',
        ),
    )


def build_mac_safe_browse_trial_plan(
    config: MacSafeBrowseConfig,
    *,
    open_candidate_once=False,
) -> tuple[MacSafeBrowseDryRunStep, ...]:
    """Build the bounded same-process browse trial plan."""
    plan = list(build_mac_safe_browse_dry_run_plan(config))
    if open_candidate_once:
        plan.append(
            MacSafeBrowseDryRunStep(
                action='candidate_open',
                description='single candidate_open browse-only pilot action',
            )
        )
    return tuple(plan)


def run_mac_safe_browse_dry_pipeline(
    budget: MacSafeBrowseActionBudget,
    plan: tuple[MacSafeBrowseDryRunStep, ...],
    *,
    started_at: float,
    now: float,
    action_fns=None,
) -> MacSafeBrowseDryRunResult:
    """Execute injected/noop callables only; never bind real browser actions."""
    if not isinstance(budget, MacSafeBrowseActionBudget):
        raise TypeError('budget 必须是 MacSafeBrowseActionBudget')
    state = MacSafeBrowseActionState(started_at=started_at)
    if not isinstance(plan, tuple):
        stopped = stop_mac_safe_browse(
            state,
            'dry run plan 必须是 tuple',
            'MAC_SAFE_BROWSE_DRY_PIPELINE_FAILED',
        )
        return MacSafeBrowseDryRunResult(
            completed=False,
            state=stopped,
            real_browsing_enabled=False,
            forwarding_enabled=False,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )
    if action_fns is not None and not isinstance(action_fns, dict):
        stopped = stop_mac_safe_browse(
            state,
            'action_fns 必须是 dict 或 None',
            'MAC_SAFE_BROWSE_DRY_PIPELINE_FAILED',
        )
        return MacSafeBrowseDryRunResult(
            completed=False,
            state=stopped,
            real_browsing_enabled=False,
            forwarding_enabled=False,
            message=stopped.stop_reason,
            error_code=stopped.error_code,
        )

    def noop_action():
        return True

    injected = action_fns or {}
    for step in plan:
        if not isinstance(step, MacSafeBrowseDryRunStep):
            stopped = stop_mac_safe_browse(
                state,
                'dry run plan 包含无效 step',
                'MAC_SAFE_BROWSE_DRY_PIPELINE_FAILED',
            )
            return MacSafeBrowseDryRunResult(
                completed=False,
                state=stopped,
                real_browsing_enabled=False,
                forwarding_enabled=False,
                message=stopped.stop_reason,
                error_code=stopped.error_code,
            )
        action_fn = injected.get(step.action, noop_action)
        action_result = execute_mac_safe_browse_action(
            budget,
            state,
            step.action,
            action_fn,
            now=now,
        )
        state = action_result.state
        if not action_result.allowed:
            return MacSafeBrowseDryRunResult(
                completed=False,
                state=state,
                real_browsing_enabled=False,
                forwarding_enabled=False,
                message=(
                    f'dry pipeline step {step.action} failed: '
                    f'{action_result.message}'
                ),
                error_code=action_result.error_code,
            )

    return MacSafeBrowseDryRunResult(
        completed=True,
        state=state,
        real_browsing_enabled=False,
        forwarding_enabled=False,
        message=(
            'noop dry pipeline completed; real browsing and forwarding remain '
            'disabled'
        ),
    )


def collect_mac_safe_browse_ocr_evidence(
    calibrated_region: CalibratedScreenRegion | None,
) -> MacSafeBrowseOcrEvidence:
    """Inspect existing calibration metadata without OCR, capture, or GUI I/O."""
    if not isinstance(calibrated_region, CalibratedScreenRegion):
        return MacSafeBrowseOcrEvidence(
            passed=False,
            has_calibrated_region=False,
            has_coordinate_metadata=False,
            coordinate_validated=False,
            manually_confirmed=False,
            business_ready=False,
            display_fingerprint=None,
            message='safe browse 缺少已校准 OCR 区域',
            error_code='MAC_SAFE_BROWSE_OCR_REGION_MISSING',
        )

    metadata = calibrated_region.coordinate_metadata
    if not isinstance(metadata, CoordinateCalibrationMetadata):
        return MacSafeBrowseOcrEvidence(
            passed=False,
            has_calibrated_region=True,
            has_coordinate_metadata=False,
            coordinate_validated=False,
            manually_confirmed=False,
            business_ready=False,
            display_fingerprint=None,
            message='OCR 区域缺少 coordinate metadata',
            error_code='MAC_SAFE_BROWSE_COORDINATE_METADATA_MISSING',
        )

    coordinate_validated = metadata.validated is True
    manually_confirmed = metadata.manually_confirmed is True
    business_ready = metadata.business_ready is True
    fingerprint = (
        metadata.display_fingerprint.strip()
        if isinstance(metadata.display_fingerprint, str)
        and metadata.display_fingerprint.strip()
        else None
    )

    def failed(message, error_code):
        return MacSafeBrowseOcrEvidence(
            passed=False,
            has_calibrated_region=True,
            has_coordinate_metadata=True,
            coordinate_validated=coordinate_validated,
            manually_confirmed=manually_confirmed,
            business_ready=business_ready,
            display_fingerprint=fingerprint,
            message=message,
            error_code=error_code,
        )

    if not coordinate_validated:
        return failed(
            'OCR coordinate metadata 未通过验证',
            'MAC_SAFE_BROWSE_COORDINATE_NOT_VALIDATED',
        )
    if not manually_confirmed:
        return failed(
            'OCR crop preview 尚未人工确认',
            'MAC_SAFE_BROWSE_PREVIEW_NOT_CONFIRMED',
        )
    if business_ready:
        return failed(
            'coordinate metadata 意外标记为 business ready，拒绝继续',
            'MAC_SAFE_BROWSE_BUSINESS_READY_UNEXPECTED',
        )
    if fingerprint is None:
        return failed(
            'OCR coordinate metadata 缺少 display fingerprint',
            'MAC_SAFE_BROWSE_DISPLAY_FINGERPRINT_MISSING',
        )

    return MacSafeBrowseOcrEvidence(
        passed=True,
        has_calibrated_region=True,
        has_coordinate_metadata=True,
        coordinate_validated=True,
        manually_confirmed=True,
        business_ready=False,
        display_fingerprint=fingerprint,
        message=(
            'OCR 区域与 coordinate metadata 前置检查通过；'
            '仅可供下一实现步骤使用，不代表可浏览或业务 ready'
        ),
    )


def validate_mac_safe_browse_guard(
    config: MacSafeBrowseConfig,
    evidence: MacSafeBrowseEvidence,
) -> MacSafeBrowseGuard:
    """Validate supplied safe-browse facts without I/O or global state changes.

    ``ready_for_browse`` belongs only to this future restricted mode. It does
    not imply ``BrowserPrepareResult.ready`` or coordinate ``business_ready``.
    """
    if not isinstance(config, MacSafeBrowseConfig):
        raise TypeError('config 必须是 MacSafeBrowseConfig')
    if not isinstance(evidence, MacSafeBrowseEvidence):
        raise TypeError('evidence 必须是 MacSafeBrowseEvidence')

    no_forward_enforced = (
        config.no_forward_required is True
        and evidence.no_forward_enabled is True
        and evidence.forwarding_email_present is False
    )

    def failed(message, error_code):
        return MacSafeBrowseGuard(
            passed=False,
            ready_for_browse=False,
            no_forward_enforced=no_forward_enforced,
            page_allowed=evidence.page_allowed is True,
            coordinate_validated=evidence.coordinate_validated is True,
            manual_confirmed=evidence.manual_confirmed is True,
            message=message,
            error_code=error_code,
        )

    if config.enabled is not True:
        return failed('macOS safe browse 未启用', 'MAC_SAFE_BROWSE_DISABLED')
    if evidence.platform != 'darwin':
        return failed(
            'macOS safe browse 仅支持 darwin 平台',
            'MAC_SAFE_BROWSE_UNSUPPORTED_PLATFORM',
        )
    if (
        config.no_forward_required is not True
        or evidence.no_forward_enabled is not True
    ):
        return failed(
            'safe browse 必须显式并强制启用 no-forward',
            'MAC_SAFE_BROWSE_NO_FORWARD_REQUIRED',
        )
    if evidence.forwarding_email_present is not False:
        return failed(
            'safe browse 不允许存在转发邮箱',
            'MAC_SAFE_BROWSE_FORWARDING_EMAIL_PRESENT',
        )

    def valid_limit(value, hard_limit):
        return (
            isinstance(value, int)
            and not isinstance(value, bool)
            and 1 <= value <= hard_limit
        )

    if not valid_limit(config.max_candidates, 5):
        return failed(
            'max_candidates 必须是 1 到 5 的整数',
            'MAC_SAFE_BROWSE_LIMIT_INVALID',
        )
    if not valid_limit(config.max_runtime_minutes, 15):
        return failed(
            'max_runtime_minutes 必须是 1 到 15 的整数',
            'MAC_SAFE_BROWSE_LIMIT_INVALID',
        )
    if config.require_page_allowed and evidence.page_allowed is not True:
        return failed(
            '当前页面未通过 BOSS allowlist',
            'MAC_SAFE_BROWSE_PAGE_NOT_ALLOWED',
        )
    if evidence.page_stage_allowed is not True:
        return failed(
            '当前页面状态不属于本阶段允许范围',
            'MAC_SAFE_BROWSE_PAGE_STATE_AMBIGUOUS',
        )
    if evidence.chrome_frontmost is not True:
        return failed(
            'Chrome 不是 frontmost 窗口',
            'MAC_SAFE_BROWSE_CHROME_NOT_FRONTMOST',
        )
    if (
        config.require_coordinate_validated
        and evidence.coordinate_validated is not True
    ):
        return failed(
            '坐标 metadata 未通过验证',
            'MAC_SAFE_BROWSE_COORDINATE_NOT_VALIDATED',
        )
    if (
        config.require_manual_confirmation
        and evidence.manual_confirmed is not True
    ):
        return failed(
            'crop preview 尚未人工确认',
            'MAC_SAFE_BROWSE_PREVIEW_NOT_CONFIRMED',
        )
    if evidence.listener_available is not True:
        return failed(
            '安全中止 Listener 不可用',
            'MAC_SAFE_BROWSE_LISTENER_UNAVAILABLE',
        )
    if evidence.profile_unique is not True:
        return failed(
            'Chrome Profile 或窗口归属不唯一',
            'MAC_SAFE_BROWSE_PROFILE_AMBIGUOUS',
        )
    if evidence.display_fingerprint_matches is not True:
        return failed(
            '显示器 fingerprint 缺失或不匹配',
            'MAC_SAFE_BROWSE_DISPLAY_FINGERPRINT_MISMATCH',
        )

    return MacSafeBrowseGuard(
        passed=True,
        ready_for_browse=True,
        no_forward_enforced=True,
        page_allowed=evidence.page_allowed is True,
        coordinate_validated=evidence.coordinate_validated is True,
        manual_confirmed=evidence.manual_confirmed is True,
        message=(
            'safe browse guard 已通过；仅允许进入后续受控浏览，'
            '不代表业务 ready，且禁止转发'
        ),
    )


def build_mac_safe_browse_config(
    args: dict,
    *,
    platform_name: str | None = None,
) -> MacSafeBrowseConfig:
    """Build a side-effect-free 5C config or reject the CLI fail closed."""
    if not isinstance(args, dict):
        raise TypeError('args 必须是 dict')
    if args.get('mac_safe_browse_only') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_DISABLED',
            '未启用 --mac-safe-browse-only',
        )

    current_platform = sys.platform if platform_name is None else platform_name
    if current_platform != 'darwin':
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_UNSUPPORTED_PLATFORM',
            '--mac-safe-browse-only 仅支持 macOS darwin',
        )
    if (
        args.get('auto')
        or args.get('preflight_only')
        or args.get('coordinate_diagnostics_only')
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_CONFLICTING_MODE',
            'safe browse 不能与 auto、preflight 或 coordinate diagnostics 共用',
        )
    if args.get('no_forward') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_NO_FORWARD_REQUIRED',
            'safe browse 必须显式传入 --no-forward',
        )
    if str(args.get('email') or '').strip():
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_FORWARDING_EMAIL_PRESENT',
            'safe browse 不接受邮箱参数',
        )

    max_candidates = args.get('max_candidates')
    max_runtime_minutes = args.get('max_runtime_minutes')
    valid_candidates = (
        isinstance(max_candidates, int)
        and not isinstance(max_candidates, bool)
        and 1 <= max_candidates <= 5
    )
    valid_runtime = (
        isinstance(max_runtime_minutes, int)
        and not isinstance(max_runtime_minutes, bool)
        and 1 <= max_runtime_minutes <= 15
    )
    if not valid_candidates:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_LIMIT_INVALID',
            '--max-candidates 必须存在且为 1 到 5 的整数',
        )
    if not valid_runtime:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_LIMIT_INVALID',
            '--max-runtime-minutes 必须存在且为 1 到 15 的整数',
        )

    return MacSafeBrowseConfig(
        enabled=True,
        no_forward_required=True,
        max_candidates=max_candidates,
        max_runtime_minutes=max_runtime_minutes,
        require_page_allowed=True,
        require_coordinate_validated=True,
        require_manual_confirmation=True,
        allow_scroll=False,
        allow_next_candidate=False,
        allow_refresh=False,
        allow_filter=False,
        message=(
            '5C CLI 参数已验证；真实 evidence 与浏览链路尚未实施，'
            '不得进入真实浏览'
        ),
    )


def build_mac_safe_browse_calibrate_and_dry_run_config(
    args: dict,
    *,
    platform_name: str | None = None,
) -> MacSafeBrowseConfig:
    """Build the same bounded safe-browse config for the combined noop path."""
    if not isinstance(args, dict):
        raise TypeError('args 必须是 dict')
    if args.get('mac_safe_browse_calibrate_and_dry_run') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_DISABLED',
            '未启用 --mac-safe-browse-calibrate-and-dry-run',
        )

    current_platform = sys.platform if platform_name is None else platform_name
    if current_platform != 'darwin':
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_UNSUPPORTED_PLATFORM',
            '--mac-safe-browse-calibrate-and-dry-run 仅支持 macOS darwin',
        )
    if (
        args.get('mac_safe_browse_only')
        or args.get('mac_safe_browse_calibrate_only')
        or args.get('auto')
        or args.get('preflight_only')
        or args.get('coordinate_diagnostics_only')
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_CALIBRATE_AND_DRY_RUN_CONFLICTING_MODE',
            'calibrate and dry run 不能与其他运行模式共用',
        )
    if args.get('no_forward') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_NO_FORWARD_REQUIRED',
            'calibrate and dry run 必须显式传入 --no-forward',
        )
    if str(args.get('email') or '').strip():
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_FORWARDING_EMAIL_PRESENT',
            'calibrate and dry run 不接受邮箱参数',
        )

    max_candidates = args.get('max_candidates')
    max_runtime_minutes = args.get('max_runtime_minutes')
    valid_candidates = (
        isinstance(max_candidates, int)
        and not isinstance(max_candidates, bool)
        and 1 <= max_candidates <= 5
    )
    valid_runtime = (
        isinstance(max_runtime_minutes, int)
        and not isinstance(max_runtime_minutes, bool)
        and 1 <= max_runtime_minutes <= 15
    )
    if not valid_candidates:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_LIMIT_INVALID',
            '--max-candidates 必须存在且为 1 到 5 的整数',
        )
    if not valid_runtime:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_LIMIT_INVALID',
            '--max-runtime-minutes 必须存在且为 1 到 15 的整数',
        )
    if args.get('mac_safe_browse_open_candidate_once'):
        if max_candidates != 1:
            raise MacSafeBrowseArgumentError(
                'MAC_SAFE_BROWSE_OPEN_CANDIDATE_LIMIT_INVALID',
                '--mac-safe-browse-open-candidate-once 要求 --max-candidates 必须为 1',
            )
        if max_runtime_minutes > 5:
            raise MacSafeBrowseArgumentError(
                'MAC_SAFE_BROWSE_OPEN_CANDIDATE_LIMIT_INVALID',
                '--mac-safe-browse-open-candidate-once 要求 --max-runtime-minutes 不超过 5',
            )

    return MacSafeBrowseConfig(
        enabled=True,
        no_forward_required=True,
        max_candidates=max_candidates,
        max_runtime_minutes=max_runtime_minutes,
        require_page_allowed=True,
        require_coordinate_validated=True,
        require_manual_confirmation=True,
        allow_scroll=False,
        allow_next_candidate=False,
        allow_refresh=False,
        allow_filter=False,
        message=(
            'calibrate-and-dry-run 参数已验证；仅允许同进程校准后执行 '
            'noop dry pipeline，不得进入真实浏览'
        ),
    )


def build_mac_forward_ui_smoke_config(
    args: dict,
    *,
    platform_name: str | None = None,
) -> MacForwardUiSmokeConfig:
    """Validate the independent macOS UI smoke mode fail closed."""
    if not isinstance(args, dict):
        raise TypeError('args 必须是 dict')
    if args.get('mac_forward_ui_smoke_only') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_FORWARD_UI_SMOKE_DISABLED',
            '未启用 --mac-forward-ui-smoke-only',
        )

    current_platform = sys.platform if platform_name is None else platform_name
    if current_platform != 'darwin':
        raise MacSafeBrowseArgumentError(
            'MAC_FORWARD_UI_SMOKE_UNSUPPORTED_PLATFORM',
            '--mac-forward-ui-smoke-only 仅支持 macOS darwin',
        )
    if (
        args.get('mac_safe_browse_only')
        or args.get('mac_safe_browse_calibrate_only')
        or args.get('mac_safe_browse_calibrate_and_dry_run')
        or args.get('auto')
        or args.get('preflight_only')
        or args.get('coordinate_diagnostics_only')
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_FORWARD_UI_SMOKE_CONFLICTING_MODE',
            'mac forward ui smoke 不能与其他运行模式共用',
        )
    if args.get('no_forward') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_FORWARD_UI_SMOKE_NO_FORWARD_REQUIRED',
            'mac forward ui smoke 必须显式传入 --no-forward',
        )
    if str(args.get('email') or '').strip():
        raise MacSafeBrowseArgumentError(
            'MAC_FORWARD_UI_SMOKE_EMAIL_FORBIDDEN',
            'mac forward ui smoke 不接受邮箱参数',
        )

    return MacForwardUiSmokeConfig(
        enabled=True,
        no_forward_required=True,
        allow_invalid_submit=(args.get('allow_invalid_forward_submit_smoke') is True),
        invalid_email_text='invalid-test-address',
        countdown_seconds=5,
        message=(
            'macOS forward/filter UI smoke 已验证；仅允许手工确认驱动的 '
            '单次真实点击/输入，不允许业务循环或真实转发'
        ),
    )


def build_mac_forward_action_config(
    *,
    allow_invalid_submit: bool = False,
    invalid_email_text: str = 'invalid-test-address',
    countdown_seconds: int = 5,
) -> MacForwardActionConfig:
    """Build a reusable bounded config for one candidate forward UI path."""
    if not isinstance(allow_invalid_submit, bool):
        raise TypeError('allow_invalid_submit 必须是 bool')
    if (
        not isinstance(invalid_email_text, str)
        or not invalid_email_text.strip()
    ):
        raise TypeError('invalid_email_text 必须是非空字符串')
    if (
        not isinstance(countdown_seconds, int)
        or isinstance(countdown_seconds, bool)
        or countdown_seconds < 0
    ):
        raise TypeError('countdown_seconds 必须是非负整数')

    return MacForwardActionConfig(
        allow_invalid_submit=allow_invalid_submit,
        invalid_email_text=invalid_email_text,
        countdown_seconds=countdown_seconds,
        message=(
            'macOS 单次转发 UI action 已封装；仅允许无效测试邮箱与手工确认，'
            '不代表真实发送或业务 ready'
        ),
    )


def mask_forwarding_email(email: str) -> str:
    """Mask the local part while preserving only minimal test-email context."""
    if not isinstance(email, str) or not email.strip():
        raise TypeError('email 必须是非空字符串')
    local_part, _, domain = email.strip().partition('@')
    if not local_part or not domain:
        raise ValueError('email 缺少有效的本地部分或域名')
    if len(local_part) == 1:
        masked_local = f'{local_part[0]}***'
    else:
        masked_local = f'{local_part[0]}***{local_part[-1]}'
    return f'{masked_local}@{domain}'


def is_probably_valid_test_email(email: str) -> bool:
    """Conservative syntax-only check for explicit test forwarding email."""
    if not isinstance(email, str):
        return False
    candidate = email.strip()
    if not candidate or ' ' in candidate or candidate.count('@') != 1:
        return False
    local_part, _, domain = candidate.partition('@')
    if not local_part or not domain or '.' not in domain:
        return False
    if domain.startswith('.') or domain.endswith('.'):
        return False
    if '..' in candidate:
        return False
    return True


def build_mac_single_candidate_forward_smoke_config(
    args: dict,
    *,
    platform_name: str | None = None,
) -> MacSingleCandidateForwardSmokeConfig:
    """Validate the real test-email single-candidate submit smoke mode."""
    if not isinstance(args, dict):
        raise TypeError('args 必须是 dict')
    if args.get('mac_single_candidate_forward_smoke') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_SMOKE_DISABLED',
            '未启用 --mac-single-candidate-forward-smoke',
        )
    current_platform = sys.platform if platform_name is None else platform_name
    if current_platform != 'darwin':
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_SMOKE_UNSUPPORTED_PLATFORM',
            '--mac-single-candidate-forward-smoke 仅支持 macOS darwin',
        )
    if args.get('allow_test_forward_submit') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_SUBMIT_CONFIRMATION_FLAG_REQUIRED',
            '真实 test email submit 必须显式传入 --allow-test-forward-submit',
        )
    if args.get('no_forward') is True:
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_NO_FORWARD_CONFLICT',
            '真实 test email submit smoke 不能与 --no-forward 同用',
        )
    if (
        args.get('mac_forward_ui_smoke_only')
        or args.get('mac_safe_browse_only')
        or args.get('mac_safe_browse_calibrate_only')
        or args.get('mac_safe_browse_calibrate_and_dry_run')
        or args.get('auto')
        or args.get('preflight_only')
        or args.get('coordinate_diagnostics_only')
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_SMOKE_CONFLICTING_MODE',
            '单候选人真实 test email submit smoke 不能与其他运行模式共用',
        )
    forwarding_email = str(args.get('forwarding_email') or '').strip()
    if not forwarding_email:
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_EMAIL_REQUIRED',
            '必须显式传入 --forwarding-email <TEST_EMAIL>',
        )
    if not is_probably_valid_test_email(forwarding_email):
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_EMAIL_INVALID',
            'forwarding-email 看起来不是有效的测试邮箱地址',
        )
    if str(args.get('email') or '').strip():
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_EMAIL_ARG_FORBIDDEN',
            '本模式不接受 --email；请只使用 --forwarding-email',
        )
    max_candidates = args.get('max_candidates')
    if max_candidates not in (None, 1):
        raise MacSafeBrowseArgumentError(
            'MAC_SINGLE_CANDIDATE_FORWARD_LIMIT_INVALID',
            '单候选人真实 submit smoke 仅允许 --max-candidates 1',
        )
    return MacSingleCandidateForwardSmokeConfig(
        enabled=True,
        forwarding_email=forwarding_email,
        masked_forwarding_email=mask_forwarding_email(forwarding_email),
        countdown_seconds=5,
        submit_confirm_phrase='SEND TEST EMAIL',
        message=(
            'macOS 单候选人真实 test email submit smoke 已验证；'
            '仅允许单次 submit attempted，不代表发送成功或业务 ready'
        ),
    )


def validate_mac_safe_browse_calibration_args(
    args: dict,
    *,
    platform_name: str | None = None,
) -> None:
    """Validate the independent calibration-only CLI without business setup."""
    if not isinstance(args, dict):
        raise TypeError('args 必须是 dict')
    if args.get('mac_safe_browse_calibrate_only') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_DISABLED',
            '未启用 --mac-safe-browse-calibrate-only',
        )
    current_platform = sys.platform if platform_name is None else platform_name
    if current_platform != 'darwin':
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_CALIBRATION_UNSUPPORTED_PLATFORM',
            'safe browse calibration-only 仅支持 macOS darwin',
        )
    if (
        args.get('mac_safe_browse_only')
        or args.get('auto')
        or args.get('preflight_only')
        or args.get('coordinate_diagnostics_only')
    ):
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_CALIBRATION_CONFLICTING_MODE',
            'calibration-only 不能与其他运行模式共用',
        )
    if args.get('no_forward') is not True:
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_CALIBRATION_NO_FORWARD_REQUIRED',
            'calibration-only 必须显式传入 --no-forward',
        )
    if str(args.get('email') or '').strip():
        raise MacSafeBrowseArgumentError(
            'MAC_SAFE_BROWSE_CALIBRATION_EMAIL_FORBIDDEN',
            'calibration-only 不接受邮箱参数',
        )


def build_mac_safe_browse_calibration_metadata_from_selection(
    *,
    diagnostics,
    region,
    captured_image,
    preview_dir=None,
    save_crop_preview_fn=None,
):
    """Build coordinate metadata from one selected region capture only."""
    if not isinstance(diagnostics, ScreenCoordinateDiagnostics) or not diagnostics.passed:
        return MacSafeBrowseCalibrationMetadataSupplyResult(
            metadata=None,
            preview_path=None,
            message='coordinate diagnostics 未通过，拒绝生成 calibration metadata',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_DIAGNOSTICS_FAILED',
        )

    fingerprint = (
        diagnostics.display_fingerprint.strip()
        if isinstance(diagnostics.display_fingerprint, str)
        and diagnostics.display_fingerprint.strip()
        else None
    )
    if fingerprint is None:
        return MacSafeBrowseCalibrationMetadataSupplyResult(
            metadata=None,
            preview_path=None,
            message='coordinate diagnostics 缺少 display fingerprint',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_FINGERPRINT_MISSING',
        )

    if not isinstance(region, ScreenRegion):
        return MacSafeBrowseCalibrationMetadataSupplyResult(
            metadata=None,
            preview_path=None,
            message='calibration region 非法',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_REGION_CANCELLED',
        )

    try:
        import numpy as np
    except ImportError as exc:
        return MacSafeBrowseCalibrationMetadataSupplyResult(
            metadata=None,
            preview_path=None,
            message=f'NumPy 不可用，无法构造 calibration metadata: {exc}',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_CAPTURE_FAILED',
        )

    if not isinstance(captured_image, np.ndarray) or captured_image.ndim not in (2, 3):
        return MacSafeBrowseCalibrationMetadataSupplyResult(
            metadata=None,
            preview_path=None,
            message='captured region image 非法，无法推断 scale 或保存 preview',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_CAPTURE_FAILED',
        )

    image_height, image_width = captured_image.shape[:2]
    scale = infer_retina_scale(
        (region.width, region.height),
        (image_width, image_height),
    )
    if not scale.passed:
        return MacSafeBrowseCalibrationMetadataSupplyResult(
            metadata=None,
            preview_path=None,
            message=f'calibration-only scale inference 未通过: {scale.message}',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_SCALE_FAILED',
        )

    selection = TkSelectionRegion(
        left=0.0,
        top=0.0,
        width=float(region.width),
        height=float(region.height),
    )
    mapping = map_tk_selection_to_screenshot_crop(
        selection,
        (region.width, region.height),
        (image_width, image_height),
    )
    if not mapping.passed or mapping.crop_region is None:
        return MacSafeBrowseCalibrationMetadataSupplyResult(
            metadata=None,
            preview_path=None,
            message=(
                'calibration-only full-region Tk-to-screenshot mapping 未通过: '
                f'{mapping.message}'
            ),
            error_code='MAC_SAFE_BROWSE_CALIBRATION_MAPPING_FAILED',
        )

    preview_dir_path = (
        build_coordinate_diagnostics_dir()
        if preview_dir is None
        else Path(preview_dir)
    )
    preview_saver = save_crop_preview_fn or save_crop_preview_for_manual_check
    preview = preview_saver(
        captured_image,
        mapping.crop_region,
        output_dir=preview_dir_path,
    )
    if not isinstance(preview, CropPreviewResult) or not preview.saved:
        return MacSafeBrowseCalibrationMetadataSupplyResult(
            metadata=None,
            preview_path=(
                preview.preview_path
                if isinstance(preview, CropPreviewResult)
                else None
            ),
            message=(
                preview.message
                if isinstance(preview, CropPreviewResult)
                else 'crop preview 保存失败'
            ),
            error_code='MAC_SAFE_BROWSE_CALIBRATION_PREVIEW_FAILED',
        )

    metadata = build_coordinate_calibration_metadata(
        display_fingerprint=fingerprint,
        scale_inference=scale,
        tk_to_screenshot_mapping=mapping,
        crop_preview=preview,
        preview_confirmed=False,
    )
    if not metadata.validated:
        return MacSafeBrowseCalibrationMetadataSupplyResult(
            metadata=None,
            preview_path=preview.preview_path,
            message=f'coordinate metadata 构造失败: {metadata.message}',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_METADATA_INCOMPLETE',
        )

    metadata = replace(
        metadata,
        message=(
            'safe browse calibration-only metadata 已构造；'
            '使用 full-region mapping，仅等待人工确认'
        ),
        error_code='MAC_SAFE_BROWSE_CALIBRATION_CONFIRMATION_REQUIRED',
    )
    return MacSafeBrowseCalibrationMetadataSupplyResult(
        metadata=metadata,
        preview_path=preview.preview_path,
        message=metadata.message,
        error_code=metadata.error_code,
    )


def verify_mac_safe_browse_overlay_cleanup(
    *,
    used_default_selector: bool,
    cleanup_check_fn=None,
) -> bool:
    """Require explicit Tk cleanup evidence before preview or candidate actions."""
    if cleanup_check_fn is None:
        if not used_default_selector:
            # Injected selectors are test seams and have no Tk overlay by default.
            return True
        cleanup_check_fn = is_tk_overlay_cleanup_complete
    if not callable(cleanup_check_fn):
        raise MacSafeBrowseRuntimeError(
            'MAC_SAFE_BROWSE_CALIBRATION_TK_CLEANUP_FAILED',
            'overlay cleanup check 不可调用',
        )
    try:
        completed = cleanup_check_fn() is True
    except Exception as exc:
        raise MacSafeBrowseRuntimeError(
            'MAC_SAFE_BROWSE_CALIBRATION_TK_CLEANUP_FAILED',
            f'overlay cleanup check 执行失败: {exc}',
        ) from exc
    if not completed:
        raise MacSafeBrowseRuntimeError(
            'MAC_SAFE_BROWSE_CALIBRATION_OVERLAY_NOT_CLOSED',
            'Tk overlay 未确认关闭；拒绝 preview、确认和 candidate_open',
        )
    return True


def prepare_mac_safe_browse_calibrated_region(
    *,
    display_fingerprint=None,
    scale_inference=None,
    tk_to_screenshot_mapping=None,
    preview_confirmed=False,
    select_region_fn=None,
    save_preview_fn=None,
    capture_fn=None,
    preview_path=None,
    diagnostics_fn=None,
    save_crop_preview_fn=None,
    confirmation_fn=None,
    preview_dir=None,
    overlay_cleanup_check_fn=None,
) -> MacSafeBrowseCalibrationResult:
    """Prepare calibration evidence only; never initialize or run OCR."""
    fingerprint_valid = (
        isinstance(display_fingerprint, str) and bool(display_fingerprint.strip())
    )
    scale_valid = (
        isinstance(scale_inference, RetinaScaleInference)
        and scale_inference.passed
    )
    mapping_valid = (
        isinstance(tk_to_screenshot_mapping, TkToScreenshotMapping)
        and tk_to_screenshot_mapping.passed
        and tk_to_screenshot_mapping.crop_region is not None
    )
    used_default_selector = select_region_fn is None
    region_selector = select_region_fn or select_screen_region
    if fingerprint_valid and scale_valid and mapping_valid:
        preview_saver = save_preview_fn or save_region_preview
        destination = OCR_PREVIEW_PATH if preview_path is None else Path(preview_path)
        try:
            region = region_selector()
        except CalibrationCleanupFailed as exc:
            return MacSafeBrowseCalibrationResult(
                published=False,
                calibrated_region=None,
                message=f'Tk overlay cleanup 失败: {exc}',
                error_code='MAC_SAFE_BROWSE_CALIBRATION_TK_CLEANUP_FAILED',
            )
        except CalibrationCancelled:
            return MacSafeBrowseCalibrationResult(
                published=False,
                calibrated_region=None,
                message='safe browse calibration-only 已由用户取消',
                error_code='MAC_SAFE_BROWSE_CALIBRATION_REGION_CANCELLED',
            )
        except Exception as exc:
            return MacSafeBrowseCalibrationResult(
                published=False,
                calibrated_region=None,
                message=f'safe browse calibration-only 框选失败: {exc}',
                error_code='MAC_SAFE_BROWSE_CALIBRATION_REGION_CANCELLED',
            )
        try:
            overlay_cleanup_completed = verify_mac_safe_browse_overlay_cleanup(
                used_default_selector=used_default_selector,
                cleanup_check_fn=overlay_cleanup_check_fn,
            )
        except MacSafeBrowseRuntimeError as exc:
            return MacSafeBrowseCalibrationResult(
                published=False,
                calibrated_region=None,
                message=str(exc),
                error_code=exc.error_code,
            )
        if not isinstance(region, ScreenRegion):
            return MacSafeBrowseCalibrationResult(
                published=False,
                calibrated_region=None,
                message='框选结果不是有效 ScreenRegion',
                error_code='MAC_SAFE_BROWSE_CALIBRATION_METADATA_INCOMPLETE',
            )

        try:
            if capture_fn is None:
                capture_fn = MSSScreenCapture().capture
            saved_path = preview_saver(region, destination, capture_fn)
            if saved_path is None:
                raise RuntimeError('preview saver 未返回路径')
        except Exception as exc:
            return MacSafeBrowseCalibrationResult(
                published=False,
                calibrated_region=None,
                message=f'safe browse calibration preview 失败: {exc}',
                error_code='MAC_SAFE_BROWSE_CALIBRATION_PREVIEW_FAILED',
            )

        crop = tk_to_screenshot_mapping.crop_region
        crop_preview = CropPreviewResult(
            saved=True,
            preview_path=str(saved_path),
            crop_size=(crop.width, crop.height),
            message='safe browse calibration crop preview 已保存到本地',
        )
        metadata = build_coordinate_calibration_metadata(
            display_fingerprint=display_fingerprint,
            scale_inference=scale_inference,
            tk_to_screenshot_mapping=tk_to_screenshot_mapping,
            crop_preview=crop_preview,
            preview_confirmed=preview_confirmed,
        )
        if (
            not metadata.validated
            or not metadata.manually_confirmed
            or metadata.business_ready
        ):
            return MacSafeBrowseCalibrationResult(
                published=False,
                calibrated_region=None,
                message=(
                    'coordinate metadata 未完整验证或 preview 未人工确认；'
                    '不发布 calibration'
                ),
                error_code='MAC_SAFE_BROWSE_CALIBRATION_METADATA_INCOMPLETE',
            )

        calibrated = attach_coordinate_metadata_to_region(region, metadata)
        return MacSafeBrowseCalibrationResult(
            published=True,
            calibrated_region=calibrated,
            message=(
                'safe browse calibration metadata 已准备；仍非 business ready，'
                '未执行 OCR 或浏览'
            ),
            overlay_cleanup_completed=overlay_cleanup_completed,
            error_code='MAC_SAFE_BROWSE_CALIBRATION_PUBLISHED_NOT_BUSINESS_READY',
        )

    diagnostics_reader = diagnostics_fn or capture_screen_coordinate_diagnostics
    diagnostics = diagnostics_reader()
    if (
        not isinstance(diagnostics, ScreenCoordinateDiagnostics)
        or not diagnostics.passed
    ):
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message=(
                diagnostics.message
                if isinstance(diagnostics, ScreenCoordinateDiagnostics)
                else 'coordinate diagnostics 读取失败'
            ),
            error_code='MAC_SAFE_BROWSE_CALIBRATION_DIAGNOSTICS_FAILED',
        )
    fingerprint = (
        diagnostics.display_fingerprint.strip()
        if isinstance(diagnostics.display_fingerprint, str)
        and diagnostics.display_fingerprint.strip()
        else None
    )
    if fingerprint is None:
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message='coordinate diagnostics 缺少 display fingerprint',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_FINGERPRINT_MISSING',
        )

    try:
        region = region_selector()
    except CalibrationCleanupFailed as exc:
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message=f'Tk overlay cleanup 失败: {exc}',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_TK_CLEANUP_FAILED',
        )
    except CalibrationCancelled:
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message='safe browse calibration-only 已由用户取消',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_REGION_CANCELLED',
        )
    except Exception as exc:
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message=f'safe browse calibration-only 框选失败: {exc}',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_REGION_CANCELLED',
        )
    try:
        overlay_cleanup_completed = verify_mac_safe_browse_overlay_cleanup(
            used_default_selector=used_default_selector,
            cleanup_check_fn=overlay_cleanup_check_fn,
        )
    except MacSafeBrowseRuntimeError as exc:
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message=str(exc),
            error_code=exc.error_code,
        )
    if not isinstance(region, ScreenRegion):
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message='框选结果不是有效 ScreenRegion',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_REGION_CANCELLED',
        )

    try:
        region_capture = capture_fn or MSSScreenCapture().capture
        captured_image = region_capture(region)
    except Exception as exc:
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message=f'safe browse calibration-only 区域截图失败: {exc}',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_CAPTURE_FAILED',
        )

    metadata_supply = build_mac_safe_browse_calibration_metadata_from_selection(
        diagnostics=diagnostics,
        region=region,
        captured_image=captured_image,
        preview_dir=preview_dir,
        save_crop_preview_fn=save_crop_preview_fn,
    )
    if metadata_supply.metadata is None:
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message=metadata_supply.message,
            error_code=metadata_supply.error_code,
        )

    confirm = confirmation_fn or input
    confirmed_text = str(
        confirm('请打开 crop preview，确认裁剪区域正确。输入 YES 继续：')
    ).strip()
    if confirmed_text != 'YES':
        return MacSafeBrowseCalibrationResult(
            published=False,
            calibrated_region=None,
            message='未收到 YES，拒绝发布 calibration metadata',
            error_code='MAC_SAFE_BROWSE_CALIBRATION_CONFIRMATION_REQUIRED',
        )

    metadata = replace(
        metadata_supply.metadata,
        manually_confirmed=True,
        message=(
            'safe browse calibration-only metadata 已验证并人工确认；'
            '仍非 business ready，未执行 OCR 或浏览'
        ),
        error_code='COORDINATE_CALIBRATION_VALIDATED_NOT_BUSINESS_READY',
    )
    calibrated = attach_coordinate_metadata_to_region(region, metadata)
    return MacSafeBrowseCalibrationResult(
        published=True,
        calibrated_region=calibrated,
        message=(
            'safe browse calibration metadata 已准备；preview 已人工确认，'
            '仍非 business ready，未执行 OCR 或浏览'
        ),
        overlay_cleanup_completed=overlay_cleanup_completed,
        error_code='MAC_SAFE_BROWSE_CALIBRATION_PUBLISHED_NOT_BUSINESS_READY',
    )


def publish_mac_safe_browse_calibration(
    *,
    display_fingerprint=None,
    scale_inference=None,
    tk_to_screenshot_mapping=None,
    preview_confirmed=False,
    select_region_fn=None,
    save_preview_fn=None,
    capture_fn=None,
    preview_path=None,
    diagnostics_fn=None,
    save_crop_preview_fn=None,
    confirmation_fn=None,
    preview_dir=None,
    overlay_cleanup_check_fn=None,
) -> MacSafeBrowseCalibrationResult:
    """Prepare and publish calibration metadata into current-process state."""
    global ocr_calibrated_region
    result = prepare_mac_safe_browse_calibrated_region(
        display_fingerprint=display_fingerprint,
        scale_inference=scale_inference,
        tk_to_screenshot_mapping=tk_to_screenshot_mapping,
        preview_confirmed=preview_confirmed,
        select_region_fn=select_region_fn,
        save_preview_fn=save_preview_fn,
        capture_fn=capture_fn,
        preview_path=preview_path,
        diagnostics_fn=diagnostics_fn,
        save_crop_preview_fn=save_crop_preview_fn,
        confirmation_fn=confirmation_fn,
        preview_dir=preview_dir,
        overlay_cleanup_check_fn=overlay_cleanup_check_fn,
    )
    if result.published and result.calibrated_region is not None:
        ocr_calibrated_region = result.calibrated_region
    return result


def get_mac_safe_browse_candidate_open_point(
    confirm_fn=input,
    position_fn=pyautogui.position,
    sleep_fn=time.sleep,
    countdown_seconds=5,
):
    """Confirm one-shot browse intent and read the current candidate point."""
    if not callable(confirm_fn):
        raise TypeError('confirm_fn 必须可调用')
    if not callable(position_fn):
        raise TypeError('position_fn 必须可调用')
    if not callable(sleep_fn):
        raise TypeError('sleep_fn 必须可调用')
    if (
        not isinstance(countdown_seconds, int)
        or isinstance(countdown_seconds, bool)
        or countdown_seconds < 0
    ):
        raise TypeError('countdown_seconds 必须是非负整数')

    print('请把鼠标放到第一位候选人位置，确认只打开 1 位候选人；输入 YES 继续。')
    response = str(confirm_fn()).strip()
    if response != 'YES':
        raise MacSafeBrowseRuntimeError(
            'MAC_SAFE_BROWSE_CANDIDATE_OPEN_CONFIRMATION_REQUIRED',
            'candidate_open 需要用户输入 YES 确认；未确认时 fail closed',
        )

    print(
        f'请在 {countdown_seconds} 秒内切回 Chrome，并把鼠标放到第一位候选人位置。'
    )
    sleep_fn(countdown_seconds)

    try:
        point = position_fn()
    except Exception as exc:
        raise MacSafeBrowseRuntimeError(
            'MAC_SAFE_BROWSE_CANDIDATE_OPEN_POINT_UNAVAILABLE',
            f'无法读取当前鼠标位置: {exc}',
        ) from exc

    x = getattr(point, 'x', None)
    y = getattr(point, 'y', None)
    if x is None or y is None:
        try:
            x, y = point
        except Exception as exc:
            raise MacSafeBrowseRuntimeError(
                'MAC_SAFE_BROWSE_CANDIDATE_OPEN_POINT_UNAVAILABLE',
                '当前鼠标位置缺少可用 x/y 坐标',
            ) from exc

    try:
        return (int(x), int(y))
    except Exception as exc:
        raise MacSafeBrowseRuntimeError(
            'MAC_SAFE_BROWSE_CANDIDATE_OPEN_POINT_UNAVAILABLE',
            f'当前鼠标位置无法转换为整数坐标: {exc}',
        ) from exc


def build_mac_forward_ui_smoke_budget(
    config: MacForwardUiSmokeConfig,
) -> MacSafeBrowseActionBudget:
    """Build the bounded manual smoke budget with all non-smoke actions off."""
    if not isinstance(config, MacForwardUiSmokeConfig):
        raise TypeError('config 必须是 MacForwardUiSmokeConfig')
    return MacSafeBrowseActionBudget(
        max_candidates=1,
        max_runtime_seconds=15 * 60,
        max_candidate_open=0,
        max_scroll=0,
        max_next_candidate=0,
        max_refresh=0,
        max_filter_click=0,
        max_focus_restore=0,
        max_ocr_capture=0,
        max_forward=0,
        max_filter_recent_unseen=1,
        max_open_forward_modal=1,
        max_focus_forward_email_field=1,
        max_type_invalid_forward_email=1,
        max_close_forward_modal=1,
        max_submit_invalid_forward=1 if config.allow_invalid_submit else 0,
    )


def build_mac_forward_action_budget(
    config: MacForwardActionConfig,
) -> MacSafeBrowseActionBudget:
    """Build the forward-only budget with every action capped at one."""
    if not isinstance(config, MacForwardActionConfig):
        raise TypeError('config 必须是 MacForwardActionConfig')
    return MacSafeBrowseActionBudget(
        max_candidates=1,
        max_runtime_seconds=15 * 60,
        max_candidate_open=0,
        max_scroll=0,
        max_next_candidate=0,
        max_refresh=0,
        max_filter_click=0,
        max_focus_restore=0,
        max_ocr_capture=0,
        max_forward=0,
        max_filter_recent_unseen=0,
        max_open_forward_modal=1,
        max_focus_forward_email_field=1,
        max_type_invalid_forward_email=1,
        max_close_forward_modal=1,
        max_submit_invalid_forward=1 if config.allow_invalid_submit else 0,
    )


def get_mac_forward_ui_smoke_point(
    *,
    action_label: str,
    instruction: str,
    confirm_phrase: str = 'YES',
    confirm_fn=input,
    position_fn=pyautogui.position,
    sleep_fn=time.sleep,
    countdown_seconds=5,
):
    """Wait for explicit confirmation, then capture one manual smoke point."""
    if not isinstance(action_label, str) or not action_label:
        raise TypeError('action_label 必须是非空字符串')
    if not isinstance(instruction, str) or not instruction:
        raise TypeError('instruction 必须是非空字符串')
    if not isinstance(confirm_phrase, str) or not confirm_phrase:
        raise TypeError('confirm_phrase 必须是非空字符串')
    if not callable(confirm_fn):
        raise TypeError('confirm_fn 必须可调用')
    if not callable(position_fn):
        raise TypeError('position_fn 必须可调用')
    if not callable(sleep_fn):
        raise TypeError('sleep_fn 必须可调用')
    if (
        not isinstance(countdown_seconds, int)
        or isinstance(countdown_seconds, bool)
        or countdown_seconds < 0
    ):
        raise TypeError('countdown_seconds 必须是非负整数')

    print(f'{action_label}: {instruction}')
    print(f'{action_label}: 输入 {confirm_phrase} 继续。')
    response = str(confirm_fn()).strip()
    if response != confirm_phrase:
        raise MacSafeBrowseRuntimeError(
            'MAC_FORWARD_UI_SMOKE_CONFIRMATION_REQUIRED',
            f'{action_label} 需要输入 {confirm_phrase} 确认；未确认时 fail closed',
        )

    print(
        f'{action_label}: 请在 {countdown_seconds} 秒内切回 Chrome，并把鼠标放到目标位置。'
    )
    sleep_fn(countdown_seconds)
    try:
        point = position_fn()
    except Exception as exc:
        raise MacSafeBrowseRuntimeError(
            'MAC_FORWARD_UI_SMOKE_POINT_UNAVAILABLE',
            f'{action_label} 无法读取当前鼠标位置: {exc}',
        ) from exc

    x = getattr(point, 'x', None)
    y = getattr(point, 'y', None)
    if x is None or y is None:
        try:
            x, y = point
        except Exception as exc:
            raise MacSafeBrowseRuntimeError(
                'MAC_FORWARD_UI_SMOKE_POINT_UNAVAILABLE',
                f'{action_label} 当前鼠标位置缺少可用 x/y 坐标',
            ) from exc
    try:
        return (int(x), int(y))
    except Exception as exc:
        raise MacSafeBrowseRuntimeError(
            'MAC_FORWARD_UI_SMOKE_POINT_UNAVAILABLE',
            f'{action_label} 当前鼠标位置无法转换为整数坐标: {exc}',
        ) from exc


def build_mac_forward_ui_smoke_plan(
    config: MacForwardUiSmokeConfig,
) -> tuple[MacSafeBrowseDryRunStep, ...]:
    """Build the bounded manual UI smoke plan."""
    if not isinstance(config, MacForwardUiSmokeConfig):
        raise TypeError('config 必须是 MacForwardUiSmokeConfig')
    plan = [
        MacSafeBrowseDryRunStep(
            action='filter_recent_unseen',
            description='single click on the recent-unseen filter entry',
        ),
        MacSafeBrowseDryRunStep(
            action='open_forward_modal',
            description='single click on the forward UI entry point',
        ),
        MacSafeBrowseDryRunStep(
            action='focus_forward_email_field',
            description='single click on the forward email input field',
        ),
        MacSafeBrowseDryRunStep(
            action='type_invalid_forward_email',
            description='single invalid test email typing action',
        ),
        MacSafeBrowseDryRunStep(
            action='close_forward_modal',
            description='single click on a blank area to close the modal',
        ),
    ]
    if config.allow_invalid_submit:
        plan.append(
            MacSafeBrowseDryRunStep(
                action='submit_invalid_forward',
                description='single invalid forward submit click',
            )
        )
    return tuple(plan)


def build_mac_forward_single_candidate_plan(
    config: MacForwardActionConfig,
) -> tuple[MacSafeBrowseDryRunStep, ...]:
    """Build the forward-only action order for one candidate."""
    if not isinstance(config, MacForwardActionConfig):
        raise TypeError('config 必须是 MacForwardActionConfig')
    plan = [
        MacSafeBrowseDryRunStep(
            action='open_forward_modal',
            description='single click on the forward UI entry point',
        ),
        MacSafeBrowseDryRunStep(
            action='focus_forward_email_field',
            description='single click on the forward email input field',
        ),
        MacSafeBrowseDryRunStep(
            action='type_invalid_forward_email',
            description='single invalid test email typing action',
        ),
    ]
    if config.allow_invalid_submit:
        plan.append(
            MacSafeBrowseDryRunStep(
                action='submit_invalid_forward',
                description='single invalid forward submit click',
            )
        )
    plan.append(
        MacSafeBrowseDryRunStep(
            action='close_forward_modal',
            description='single click on a blank area to close the modal',
        )
    )
    return tuple(plan)


def build_mac_forward_ui_smoke_action_fns(
    config: MacForwardUiSmokeConfig,
    *,
    focus_fn=None,
    click_fn=None,
    typewrite_fn=None,
    position_fn=pyautogui.position,
    confirm_fn=input,
    submit_confirm_fn=input,
    sleep_fn=time.sleep,
):
    """Build the manual smoke actions with per-step confirmation and recheck."""
    if not isinstance(config, MacForwardUiSmokeConfig):
        raise TypeError('config 必须是 MacForwardUiSmokeConfig')

    click_action_fn = click_fn
    if click_action_fn is None:
        def click_action_fn(x, y):
            human_click(x, y, offset=0)
    if typewrite_fn is None:
        def typewrite_fn(text, interval=0.03):
            pyautogui.typewrite(text, interval=interval)

    statuses = {
        step.action: MacForwardUiSmokeActionStatus(
            attempted=False,
            verified=False,
            count=0,
        )
        for step in build_mac_forward_ui_smoke_plan(config)
    }

    def set_status(action, *, attempted=None, verified=None, error_code=None, message=None):
        current = statuses[action]
        statuses[action] = MacForwardUiSmokeActionStatus(
            attempted=current.attempted if attempted is None else attempted,
            verified=current.verified if verified is None else verified,
            count=current.count,
            error_code=current.error_code if error_code is None else error_code,
            message=current.message if message is None else message,
        )

    def apply_count(state):
        for action in statuses:
            current = statuses[action]
            statuses[action] = MacForwardUiSmokeActionStatus(
                attempted=current.attempted,
                verified=current.verified,
                count=getattr(state, action),
                error_code=current.error_code,
                message=current.message,
            )

    def ensure_frontmost(action_label):
        focus_result = focus_chrome_window() if focus_fn is None else focus_fn()
        if isinstance(focus_result, MacOSChromeFocusResult):
            if focus_result.frontmost is not True:
                raise MacSafeBrowseRuntimeError(
                    'MAC_FORWARD_UI_SMOKE_CHROME_NOT_FRONTMOST',
                    focus_result.message,
                )
            return
        if not bool(focus_result):
            raise MacSafeBrowseRuntimeError(
                'MAC_FORWARD_UI_SMOKE_CHROME_NOT_FRONTMOST',
                f'{action_label} 前 Chrome frontmost 校验失败',
            )

    def make_click_action(action, instruction, *, confirm_phrase='YES'):
        def action_fn():
            try:
                x, y = get_mac_forward_ui_smoke_point(
                    action_label=action,
                    instruction=instruction,
                    confirm_phrase=confirm_phrase,
                    confirm_fn=(
                        submit_confirm_fn
                        if confirm_phrase != 'YES'
                        else confirm_fn
                    ),
                    position_fn=position_fn,
                    sleep_fn=sleep_fn,
                    countdown_seconds=config.countdown_seconds,
                )
                ensure_frontmost(action)
                click_action_fn(x, y)
            except Exception as exc:
                set_status(
                    action,
                    attempted=False,
                    verified=False,
                    error_code=getattr(
                        exc,
                        'error_code',
                        'MAC_FORWARD_UI_SMOKE_ACTION_FAILED',
                    ),
                    message=str(exc),
                )
                return False
            set_status(
                action,
                attempted=True,
                verified=False,
                error_code=None,
                message=f'{action} 点击已尝试一次；未做页面状态验证',
            )
            return True
        return action_fn

    def type_invalid_forward_email_action():
        action = 'type_invalid_forward_email'
        try:
            print(f'{action}: 输入 YES 继续。')
            response = str(confirm_fn()).strip()
            if response != 'YES':
                raise MacSafeBrowseRuntimeError(
                    'MAC_FORWARD_UI_SMOKE_CONFIRMATION_REQUIRED',
                    f'{action} 需要输入 YES 确认；未确认时 fail closed',
                )
            ensure_frontmost(action)
            typewrite_fn(config.invalid_email_text, interval=0.03)
        except Exception as exc:
            set_status(
                action,
                attempted=False,
                verified=False,
                error_code=getattr(
                    exc,
                    'error_code',
                    'MAC_FORWARD_UI_SMOKE_ACTION_FAILED',
                ),
                message=str(exc),
            )
            return False
        set_status(
            action,
            attempted=True,
            verified=False,
            error_code=None,
            message='无效测试邮箱字符串已尝试输入；不代表提交或发送',
        )
        return True

    action_fns = {
        'filter_recent_unseen': make_click_action(
            'filter_recent_unseen',
            '请切回 Chrome/BOSS，并把鼠标放到“最近没看过”筛选点击位置。',
        ),
        'open_forward_modal': make_click_action(
            'open_forward_modal',
            '请切回 Chrome/BOSS，并把鼠标放到候选人页面里的转发入口。',
        ),
        'focus_forward_email_field': make_click_action(
            'focus_forward_email_field',
            '请切回 Chrome/BOSS，并把鼠标放到转发弹窗的邮箱输入框。',
        ),
        'type_invalid_forward_email': type_invalid_forward_email_action,
        'close_forward_modal': make_click_action(
            'close_forward_modal',
            '请切回 Chrome/BOSS，并把鼠标放到用于关闭弹窗的空白区域。',
        ),
    }
    if config.allow_invalid_submit:
        action_fns['submit_invalid_forward'] = make_click_action(
            'submit_invalid_forward',
            '请切回 Chrome/BOSS，并把鼠标放到最终发送/确认按钮。',
            confirm_phrase='SEND INVALID TEST',
        )
    return action_fns, statuses, apply_count


def run_mac_forward_ui_smoke_pipeline(
    budget: MacSafeBrowseActionBudget,
    plan: tuple[MacSafeBrowseDryRunStep, ...],
    *,
    started_at: float,
    now_fn=time.time,
    action_fns=None,
    apply_count_fn=None,
    statuses=None,
) -> MacForwardUiSmokeResult:
    """Run the manual smoke plan with the shared action executor."""
    if not isinstance(budget, MacSafeBrowseActionBudget):
        raise TypeError('budget 必须是 MacSafeBrowseActionBudget')
    if not isinstance(plan, tuple):
        raise TypeError('plan 必须是 tuple')
    if not callable(now_fn):
        raise TypeError('now_fn 必须可调用')
    state = MacSafeBrowseActionState(started_at=started_at)
    injected = action_fns or {}
    count_updater = apply_count_fn or (lambda _state: None)
    status_map = statuses or {}
    for step in plan:
        action_result = execute_mac_safe_browse_action(
            budget,
            state,
            step.action,
            injected[step.action],
            now=now_fn(),
        )
        state = action_result.state
        count_updater(state)
        if not action_result.allowed:
            return MacForwardUiSmokeResult(
                completed=False,
                state=state,
                statuses=status_map,
                forwarding_enabled=False,
                invalid_submit_enabled='submit_invalid_forward' in injected,
                message=action_result.message,
                error_code=action_result.error_code,
            )
    return MacForwardUiSmokeResult(
        completed=True,
        state=state,
        statuses=status_map,
        forwarding_enabled=False,
        invalid_submit_enabled='submit_invalid_forward' in injected,
        message='manual UI smoke completed; real forwarding remains disabled',
    )


def _map_mac_forward_action_name(action: str) -> str:
    """Map internal bounded smoke actions to forward-only public names."""
    if action == 'type_invalid_forward_email':
        return 'type_forward_email'
    return action


def _build_mac_forward_action_state(
    state: MacSafeBrowseActionState,
) -> MacForwardActionState:
    """Project the shared executor state into the forward-only result shape."""
    if not isinstance(state, MacSafeBrowseActionState):
        raise TypeError('state 必须是 MacSafeBrowseActionState')
    return MacForwardActionState(
        open_forward_modal_count=state.open_forward_modal,
        focus_forward_email_field_count=state.focus_forward_email_field,
        type_forward_email_count=state.type_invalid_forward_email,
        submit_invalid_forward_count=state.submit_invalid_forward,
        close_forward_modal_count=state.close_forward_modal,
    )


def _project_mac_forward_action_statuses(
    statuses: dict[str, MacForwardUiSmokeActionStatus],
    plan: tuple[MacSafeBrowseDryRunStep, ...],
) -> dict[str, MacForwardUiSmokeActionStatus]:
    """Keep only forward-only plan statuses and expose stable 6B names."""
    if not isinstance(statuses, dict):
        raise TypeError('statuses 必须是 dict')
    if not isinstance(plan, tuple):
        raise TypeError('plan 必须是 tuple')
    projected = {}
    for step in plan:
        projected[_map_mac_forward_action_name(step.action)] = statuses[step.action]
    return projected


def run_mac_forward_single_candidate_action(
    config: MacForwardActionConfig,
    *,
    focus_fn=None,
    click_fn=None,
    typewrite_fn=None,
    position_fn=pyautogui.position,
    confirm_fn=input,
    submit_confirm_fn=input,
    sleep_fn=time.sleep,
    now_fn=time.time,
) -> MacForwardActionResult:
    """Run one bounded candidate forward UI path without business looping."""
    if not isinstance(config, MacForwardActionConfig):
        raise TypeError('config 必须是 MacForwardActionConfig')
    budget = build_mac_forward_action_budget(config)
    plan = build_mac_forward_single_candidate_plan(config)
    shared_config = MacForwardUiSmokeConfig(
        enabled=True,
        no_forward_required=True,
        allow_invalid_submit=config.allow_invalid_submit,
        invalid_email_text=config.invalid_email_text,
        countdown_seconds=config.countdown_seconds,
        message=config.message,
    )
    action_fns, statuses, apply_count = build_mac_forward_ui_smoke_action_fns(
        shared_config,
        focus_fn=focus_fn,
        click_fn=click_fn,
        typewrite_fn=typewrite_fn,
        position_fn=position_fn,
        confirm_fn=confirm_fn,
        submit_confirm_fn=submit_confirm_fn,
        sleep_fn=sleep_fn,
    )
    result = run_mac_forward_ui_smoke_pipeline(
        budget,
        plan,
        started_at=now_fn(),
        now_fn=now_fn,
        action_fns=action_fns,
        apply_count_fn=apply_count,
        statuses=statuses,
    )
    return MacForwardActionResult(
        completed=result.completed,
        state=_build_mac_forward_action_state(result.state),
        statuses=_project_mac_forward_action_statuses(result.statuses, plan),
        forwarding_enabled=False,
        invalid_submit_enabled=result.invalid_submit_enabled,
        message=result.message,
        error_code=result.error_code,
    )


def build_mac_single_candidate_forward_smoke_budget(
    config: MacSingleCandidateForwardSmokeConfig,
) -> MacSafeBrowseActionBudget:
    """Build the one-candidate real test-submit budget with hard stop at one."""
    if not isinstance(config, MacSingleCandidateForwardSmokeConfig):
        raise TypeError('config 必须是 MacSingleCandidateForwardSmokeConfig')
    return MacSafeBrowseActionBudget(
        max_candidates=1,
        max_runtime_seconds=15 * 60,
        max_candidate_open=0,
        max_scroll=0,
        max_next_candidate=0,
        max_refresh=0,
        max_filter_click=0,
        max_focus_restore=0,
        max_ocr_capture=0,
        max_forward=0,
        max_filter_recent_unseen=0,
        max_open_forward_modal=1,
        max_focus_forward_email_field=1,
        max_type_invalid_forward_email=1,
        max_submit_test_forward=1,
        max_close_forward_modal=1,
        max_submit_invalid_forward=0,
    )


def build_mac_single_candidate_forward_smoke_plan(
    config: MacSingleCandidateForwardSmokeConfig,
) -> tuple[MacSafeBrowseDryRunStep, ...]:
    """Build the bounded real submit smoke plan for exactly one candidate."""
    if not isinstance(config, MacSingleCandidateForwardSmokeConfig):
        raise TypeError('config 必须是 MacSingleCandidateForwardSmokeConfig')
    return (
        MacSafeBrowseDryRunStep(
            action='open_forward_modal',
            description='single click on the forward UI entry point',
        ),
        MacSafeBrowseDryRunStep(
            action='focus_forward_email_field',
            description='single click on the forward email input field',
        ),
        MacSafeBrowseDryRunStep(
            action='type_invalid_forward_email',
            description='single test email typing action',
        ),
        MacSafeBrowseDryRunStep(
            action='submit_test_forward',
            description='single real test-email submit click',
        ),
        MacSafeBrowseDryRunStep(
            action='close_forward_modal',
            description='single best-effort cleanup click after submit',
        ),
    )


def build_mac_single_candidate_forward_smoke_action_fns(
    config: MacSingleCandidateForwardSmokeConfig,
    *,
    focus_fn=None,
    click_fn=None,
    typewrite_fn=None,
    position_fn=pyautogui.position,
    confirm_fn=input,
    submit_confirm_fn=input,
    sleep_fn=time.sleep,
):
    """Build real test-email submit actions with per-step confirmation."""
    if not isinstance(config, MacSingleCandidateForwardSmokeConfig):
        raise TypeError('config 必须是 MacSingleCandidateForwardSmokeConfig')

    click_action_fn = click_fn
    if click_action_fn is None:
        def click_action_fn(x, y):
            human_click(x, y, offset=0)
    if typewrite_fn is None:
        def typewrite_fn(text, interval=0.03):
            pyautogui.typewrite(text, interval=interval)

    plan = build_mac_single_candidate_forward_smoke_plan(config)
    statuses = {
        step.action: MacForwardUiSmokeActionStatus(
            attempted=False,
            verified=False,
            count=0,
        )
        for step in plan
    }

    def set_status(action, *, attempted=None, verified=None, error_code=None, message=None):
        current = statuses[action]
        statuses[action] = MacForwardUiSmokeActionStatus(
            attempted=current.attempted if attempted is None else attempted,
            verified=current.verified if verified is None else verified,
            count=current.count,
            error_code=current.error_code if error_code is None else error_code,
            message=current.message if message is None else message,
        )

    def apply_count(state):
        for action in statuses:
            current = statuses[action]
            statuses[action] = MacForwardUiSmokeActionStatus(
                attempted=current.attempted,
                verified=current.verified,
                count=getattr(state, action),
                error_code=current.error_code,
                message=current.message,
            )

    def ensure_frontmost(action_label):
        focus_result = focus_chrome_window() if focus_fn is None else focus_fn()
        if isinstance(focus_result, MacOSChromeFocusResult):
            if focus_result.frontmost is not True:
                raise MacSafeBrowseRuntimeError(
                    'MAC_SINGLE_CANDIDATE_FORWARD_CHROME_NOT_FRONTMOST',
                    focus_result.message,
                )
            return
        if not bool(focus_result):
            raise MacSafeBrowseRuntimeError(
                'MAC_SINGLE_CANDIDATE_FORWARD_CHROME_NOT_FRONTMOST',
                f'{action_label} 前 Chrome frontmost 校验失败',
            )

    def make_click_action(action, instruction, *, confirm_phrase='YES', confirm_callable=None):
        def action_fn():
            try:
                x, y = get_mac_forward_ui_smoke_point(
                    action_label=action,
                    instruction=instruction,
                    confirm_phrase=confirm_phrase,
                    confirm_fn=confirm_callable or confirm_fn,
                    position_fn=position_fn,
                    sleep_fn=sleep_fn,
                    countdown_seconds=config.countdown_seconds,
                )
                ensure_frontmost(action)
                click_action_fn(x, y)
            except Exception as exc:
                set_status(
                    action,
                    attempted=False,
                    verified=False,
                    error_code=getattr(
                        exc,
                        'error_code',
                        'MAC_SINGLE_CANDIDATE_FORWARD_ACTION_FAILED',
                    ),
                    message=str(exc),
                )
                return False
            set_status(
                action,
                attempted=True,
                verified=False,
                error_code=None,
                message=f'{action} 已尝试一次；未做页面或邮箱侧成功验证',
            )
            return True
        return action_fn

    def type_forward_email_action():
        action = 'type_invalid_forward_email'
        try:
            print(f'{action}: 输入 YES 继续。')
            response = str(confirm_fn()).strip()
            if response != 'YES':
                raise MacSafeBrowseRuntimeError(
                    'MAC_SINGLE_CANDIDATE_FORWARD_CONFIRMATION_REQUIRED',
                    f'{action} 需要输入 YES 确认；未确认时 fail closed',
                )
            ensure_frontmost(action)
            typewrite_fn(config.forwarding_email, interval=0.03)
        except Exception as exc:
            set_status(
                action,
                attempted=False,
                verified=False,
                error_code=getattr(
                    exc,
                    'error_code',
                    'MAC_SINGLE_CANDIDATE_FORWARD_ACTION_FAILED',
                ),
                message=str(exc),
            )
            return False
        set_status(
            action,
            attempted=True,
            verified=False,
            error_code=None,
            message='测试邮箱字符串已尝试输入；不代表邮件已发送或送达',
        )
        return True

    action_fns = {
        'open_forward_modal': make_click_action(
            'open_forward_modal',
            '请切回 Chrome/BOSS，并把鼠标放到候选人页面里的转发入口。',
        ),
        'focus_forward_email_field': make_click_action(
            'focus_forward_email_field',
            '请切回 Chrome/BOSS，并把鼠标放到转发弹窗的邮箱输入框。',
        ),
        'type_invalid_forward_email': type_forward_email_action,
        'submit_test_forward': make_click_action(
            'submit_test_forward',
            '请切回 Chrome/BOSS，并把鼠标放到最终发送/确认按钮。',
            confirm_phrase=config.submit_confirm_phrase,
            confirm_callable=submit_confirm_fn,
        ),
        'close_forward_modal': make_click_action(
            'close_forward_modal',
            '请切回 Chrome/BOSS，并把鼠标放到用于关闭弹窗的空白区域。',
        ),
    }
    return action_fns, statuses, apply_count


def run_mac_single_candidate_forward_smoke_only(
    cli_args,
    *,
    focus_fn=None,
    click_fn=None,
    typewrite_fn=None,
    position_fn=pyautogui.position,
    confirm_fn=input,
    submit_confirm_fn=input,
    sleep_fn=time.sleep,
    now_fn=time.time,
) -> int:
    """Run one real test-email submit smoke without entering business loops."""
    try:
        config = build_mac_single_candidate_forward_smoke_config(cli_args)
    except MacSafeBrowseArgumentError as exc:
        print('MAC SINGLE CANDIDATE FORWARD SMOKE — FAIL CLOSED')
        print(f'  error_code: {exc.error_code}')
        print(f'  message: {exc}')
        return 2

    print('MAC SINGLE CANDIDATE FORWARD SMOKE — REAL TEST SUBMIT ATTEMPT')
    print('  warning: 将尝试向测试邮箱执行一次真实 submit；程序不会声称发送成功。')
    print(f'  test_email_used: {config.masked_forwarding_email}')
    budget = build_mac_single_candidate_forward_smoke_budget(config)
    plan = build_mac_single_candidate_forward_smoke_plan(config)
    action_fns, statuses, apply_count = build_mac_single_candidate_forward_smoke_action_fns(
        config,
        focus_fn=focus_fn,
        click_fn=click_fn,
        typewrite_fn=typewrite_fn,
        position_fn=position_fn,
        confirm_fn=confirm_fn,
        submit_confirm_fn=submit_confirm_fn,
        sleep_fn=sleep_fn,
    )
    result = run_mac_forward_ui_smoke_pipeline(
        budget,
        plan,
        started_at=now_fn(),
        now_fn=now_fn,
        action_fns=action_fns,
        apply_count_fn=apply_count,
        statuses=statuses,
    )
    for action, status in result.statuses.items():
        public_name = _map_mac_forward_action_name(action)
        print(f'  {public_name}_attempted: {status.attempted}')
        print(f'  {public_name}_count: {status.count}')
        print(f'  {public_name}_error_code: {status.error_code}')
    submit_attempted = result.statuses['submit_test_forward'].attempted
    print(f'  test_email_used: {config.masked_forwarding_email}')
    print('  stopped_after_single_candidate: True')
    print(f'  forwarding_submit_attempted: {submit_attempted}')
    print('  forwarding_success_verified: False')
    if not result.completed:
        print(f'  error_code: {result.error_code}')
        print(f'  message: {result.message}')
        return 2

    print('  error_code: MAC_SINGLE_CANDIDATE_FORWARD_SUBMIT_ATTEMPTED_UNVERIFIED')
    print(
        '  message: 单候选人真实 test email submit 已尝试；程序未验证是否发送成功，'
        '请人工检查测试邮箱。'
    )
    return 2


def build_mac_safe_browse_real_action_fns(
    calibrated_region: CalibratedScreenRegion,
    *,
    focus_fn=None,
    capture_factory=None,
    candidate_open_fn=None,
    candidate_focus_fn=None,
    candidate_open_confirm_fn=input,
    candidate_open_position_fn=pyautogui.position,
    candidate_open_sleep_fn=time.sleep,
    candidate_open_countdown_seconds=5,
    open_candidate_once=False,
    overlay_cleanup_completed=False,
):
    """Build bounded real actions without OCR, forwarding, or browse loops."""
    if not isinstance(calibrated_region, CalibratedScreenRegion):
        raise TypeError('calibrated_region 必须是 CalibratedScreenRegion')
    if not isinstance(calibrated_region.region, ScreenRegion):
        raise TypeError('calibrated_region.region 必须是 ScreenRegion')

    metadata = calibrated_region.coordinate_metadata
    if not isinstance(metadata, CoordinateCalibrationMetadata):
        raise ValueError('calibrated_region 缺少 coordinate metadata')
    if (
        metadata.validated is not True
        or metadata.manually_confirmed is not True
        or metadata.business_ready is not False
    ):
        raise ValueError('coordinate metadata 未满足 real capture once 前置条件')

    state = {
        'focus_restored': False,
        'capture_completed': False,
        'capture_size': None,
        'candidate_open_attempted': False,
        'candidate_open_verified': False,
        'candidate_opened': False,
        'error_code': None,
        'message': 'real capture once actions prepared',
    }

    def focus_restore_action():
        if focus_fn is None:
            state['focus_restored'] = True
            state['message'] = (
                'focus_restore 使用 no-op 上下文确认；未点击、未按键、未切换候选人'
            )
            return True
        succeeded = bool(focus_fn())
        if not succeeded:
            state['error_code'] = 'MAC_SAFE_BROWSE_REAL_FOCUS_FAILED'
            state['message'] = 'focus_restore 验证失败'
            return False
        state['focus_restored'] = True
        state['message'] = 'focus_restore 验证成功'
        return True

    def ocr_capture_action():
        factory = capture_factory or MSSScreenCapture
        try:
            capture = factory()
        except Exception as exc:
            state['error_code'] = 'MAC_SAFE_BROWSE_REAL_CAPTURE_FAILED'
            state['message'] = f'capture factory 创建失败: {exc}'
            return False
        if not hasattr(capture, 'capture') or not callable(capture.capture):
            state['error_code'] = 'MAC_SAFE_BROWSE_REAL_CAPTURE_FAILED'
            state['message'] = 'capture factory 未返回可用 capture 对象'
            return False
        try:
            image = capture.capture(calibrated_region.region)
        except Exception as exc:
            state['error_code'] = 'MAC_SAFE_BROWSE_REAL_CAPTURE_FAILED'
            state['message'] = f'ocr_capture 执行异常: {exc}'
            return False
        if image is None:
            state['error_code'] = 'MAC_SAFE_BROWSE_REAL_CAPTURE_EMPTY'
            state['message'] = 'ocr_capture 未返回图像'
            return False
        try:
            import numpy as np

            array = np.asarray(image)
        except Exception as exc:
            state['error_code'] = 'MAC_SAFE_BROWSE_REAL_CAPTURE_FAILED'
            state['message'] = f'ocr_capture 图像解析失败: {exc}'
            return False
        if array.ndim not in (2, 3) or array.shape[0] <= 0 or array.shape[1] <= 0:
            state['error_code'] = 'MAC_SAFE_BROWSE_REAL_CAPTURE_EMPTY'
            state['message'] = 'ocr_capture 返回空图或无效图像'
            return False
        state['capture_completed'] = True
        state['capture_size'] = (int(array.shape[1]), int(array.shape[0]))
        state['message'] = 'ocr_capture 已完成一次区域截图；未保存、未 OCR'
        return True

    def candidate_open_action():
        if not open_candidate_once:
            state['message'] = 'candidate_open 未启用'
            return True
        if overlay_cleanup_completed is not True:
            state['error_code'] = (
                'MAC_SAFE_BROWSE_CALIBRATION_OVERLAY_NOT_CLOSED'
            )
            state['message'] = (
                'candidate_open 前未取得 Tk overlay cleanup 完成证据；'
                '拒绝点击'
            )
            return False
        try:
            if candidate_open_fn is None:
                x, y = get_mac_safe_browse_candidate_open_point(
                    confirm_fn=candidate_open_confirm_fn,
                    position_fn=candidate_open_position_fn,
                    sleep_fn=candidate_open_sleep_fn,
                    countdown_seconds=candidate_open_countdown_seconds,
                )
                focus_check = (
                    focus_chrome_window()
                    if candidate_focus_fn is None
                    else candidate_focus_fn()
                )
                if isinstance(focus_check, MacOSChromeFocusResult):
                    focus_succeeded = focus_check.frontmost is True
                else:
                    focus_succeeded = bool(focus_check)
                if not focus_succeeded:
                    message = (
                        focus_check.message
                        if isinstance(focus_check, MacOSChromeFocusResult)
                        else 'candidate_open 前 Chrome focus/frontmost 校验失败'
                    )
                    raise MacSafeBrowseRuntimeError(
                        'MAC_SAFE_BROWSE_CANDIDATE_OPEN_FOCUS_FAILED',
                        message,
                    )
                succeeded = bool(click_first_candidate(x, y))
            else:
                succeeded = bool(candidate_open_fn())
        except Exception as exc:
            state['error_code'] = getattr(
                exc,
                'error_code',
                'MAC_SAFE_BROWSE_CANDIDATE_OPEN_FAILED',
            )
            state['message'] = f'candidate_open 执行异常: {exc}'
            return False
        if not succeeded:
            state['error_code'] = 'MAC_SAFE_BROWSE_CANDIDATE_OPEN_FAILED'
            state['message'] = 'candidate_open 执行失败'
            return False
        state['candidate_open_attempted'] = True
        state['candidate_open_verified'] = False
        state['candidate_opened'] = False
        state['message'] = (
            'candidate_open 点击已尝试一次；页面是否真正打开尚未验证，'
            '未进入浏览循环'
        )
        return True

    def build_result():
        return MacSafeBrowseRealCaptureResult(
            focus_restored=state['focus_restored'],
            capture_completed=state['capture_completed'],
            capture_size=state['capture_size'],
            candidate_open_attempted=state['candidate_open_attempted'],
            candidate_open_verified=state['candidate_open_verified'],
            candidate_opened=state['candidate_opened'],
            browse_loop_enabled=False,
            message=state['message'],
            error_code=state['error_code'],
        )

    action_fns = {
        'focus_restore': focus_restore_action,
        'ocr_capture': ocr_capture_action,
    }
    if open_candidate_once:
        action_fns['candidate_open'] = candidate_open_action
    return (action_fns, build_result)


def is_allowed_boss_page(url: str | None, title: str | None) -> bool:
    """Return whether a URL passes the conservative BOSS page identity gate.

    The title is intentionally not used for authorization: it may be empty, and
    a BOSS-looking title cannot make an untrusted URL safe. Passing this gate is
    only a read-only identity check and does not make business actions ready.
    """
    del title
    if not isinstance(url, str) or not url or url != url.strip():
        return False

    try:
        parsed = urlparse(url)
        port = parsed.port
    except (TypeError, ValueError):
        return False

    if parsed.scheme != 'https' or parsed.hostname != 'www.zhipin.com':
        return False
    # Require the exact authority too: reject credentials, explicit ports, and
    # lookalike authorities even when ``hostname`` happens to parse safely.
    if parsed.netloc != 'www.zhipin.com' or port is not None:
        return False

    if parsed.path == '/':
        return True

    bounded_prefixes = (
        '/web/chat/recommend',
    )
    for prefix in bounded_prefixes:
        if parsed.path == prefix or parsed.path.startswith(f'{prefix}/'):
            return True

    allowed_prefixes = (
        '/web/geek/',
        '/web/jobs',
        '/geek/',
        '/job_detail/',
        '/chat/',
        '/boss/',
    )
    return parsed.path.startswith(allowed_prefixes)


def region_around(x, y, radius):
    """Return the inclusive +/- radius around a point as a ScreenRegion."""
    if radius < 0:
        raise ValueError('点击区域半径不能为负数')
    return ScreenRegion(
        left=x - radius,
        top=y - radius,
        width=radius * 2 + 1,
        height=radius * 2 + 1,
    )


# 坐标由用户手动从 1920×1080 截图读出（2026-06-30 校准）
# 转发牛人图标（候选人详情页右上角最右边的第3个图标）
FORWARD_ICON_X   = 1670
FORWARD_ICON_Y   = 260
# 弹窗左侧"邮件转发" Tab（高亮蓝色）
EMAIL_TAB_X      = 700
EMAIL_TAB_Y      = 600
# 弹窗顶部邮箱输入框
INPUT_BOX_X      = 900
INPUT_BOX_Y      = 390
# "最近联系"区域右侧第一个邮箱标签
RECENT_EMAIL_X   = 1000
RECENT_EMAIL_Y   = 440
# 弹窗右下角"转发"按钮（绿色）
FORWARD_BTN_X    = 1210
FORWARD_BTN_Y    = 740
# 转发后右键恢复键盘焦点位置（详情页中央偏右）
RIGHT_CLICK_X    = 960
RIGHT_CLICK_Y    = 500
# 候选人详情页空白区域（转发处理函数退出前统一恢复焦点）
DEFAULT_FOCUS_RESTORE_REGION = ScreenRegion(
    left=400,
    top=350,
    width=101,
    height=51,
)

# 鼠标点击与转发步骤配置
FORWARD_CLICK_OFFSET = 5    # 点击位置随机偏移范围（像素）
FORWARD_MIN_DELAY   = 0.5   # 步骤间最短延迟（秒）
FORWARD_MAX_DELAY   = 1.5   # 步骤间最长延迟（秒）
FORWARD_MAX_CONSEC  = 5     # 连续转发上限（超出跳过）

# 单次鼠标移动参数
MOUSE_MOVE_MIN_DURATION = 0.20
MOUSE_MOVE_MAX_DURATION = 0.75
MOUSE_MOVE_BASE_DURATION = 0.18
MOUSE_MOVE_DISTANCE_DIVISOR = 1800.0
MOUSE_MOVE_SAMPLE_RATE = 60
MOUSE_MOVE_MIN_STEPS = 12
MOUSE_MOVE_MAX_STEPS = 45
MOUSE_MOVE_SHORT_DISTANCE = 8.0
MOUSE_MOVE_CURVE_MIN_DISTANCE = 40.0
MOUSE_MOVE_CURVE_RATIO_MIN = 0.04
MOUSE_MOVE_CURVE_RATIO_MAX = 0.10
MOUSE_MOVE_CURVE_OFFSET_MIN = 4.0
MOUSE_MOVE_CURVE_OFFSET_MAX = 40.0
MOUSE_MOVE_JITTER_MIN = 0.5
MOUSE_MOVE_JITTER_MAX = 1.5

DEFAULT_FORWARD_CLICK_REGIONS = ForwardClickRegions(
    forward_icon=region_around(FORWARD_ICON_X, FORWARD_ICON_Y, 5),
    email_tab=region_around(EMAIL_TAB_X, EMAIL_TAB_Y, 5),
    input_box=region_around(INPUT_BOX_X, INPUT_BOX_Y, 3),
    recent_email=region_around(RECENT_EMAIL_X, RECENT_EMAIL_Y, 5),
    forward_button=region_around(FORWARD_BTN_X, FORWARD_BTN_Y, 5),
)

# 日志
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    filename='logs/simple_brush.log',
    filemode='a',
    format='%(asctime)s [%(levelname)s] %(message)s',
    level=logging.INFO,
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

console = logging.StreamHandler(sys.stdout)
console.setFormatter(logging.Formatter('%(asctime)s %(message)s', datefmt='%H:%M:%S'))
logger.addHandler(console)

# ─── 运行时状态 ─────────────────────────────────────
stop_event = False
paused = False
run_duration_seconds = 0
simple_mouse_enabled = False
action_mode = ACTION_MODE_FORWARD

# 转发状态（全局）
forward_keywords = []       # 启动时解析完成的关键词规则列表
backup_email = ""           # 备选邮箱
forward_enabled = False     # 是否启用转发
forward_consecutive = 0     # 连续转发计数
no_forward_mode = False     # 只检测，不执行真实邮件转发

# 转发关键点击区域（仅在当前运行期间有效）
forward_click_regions = DEFAULT_FORWARD_CLICK_REGIONS
forward_click_calibration_requested = False
forward_click_calibration_attempted = False
forward_click_calibration_in_progress = False

# 候选人列表筛选与首位归位区域（仅在当前运行期间有效）
batch_filter_regions = None
batch_filter_calibration_requested = False
batch_filter_calibration_attempted = False
batch_filter_calibration_in_progress = False
batch_filter_enabled = False

# 焦点恢复区域状态（仅在当前运行期间有效）
focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
focus_restore_calibration_requested = False
focus_restore_calibration_attempted = False
focus_restore_calibration_in_progress = False

# 收藏按钮区域状态（仅在当前运行期间有效）
favorite_button_region = None
favorite_button_calibration_attempted = False
favorite_button_calibration_in_progress = False

# OCR 状态（每次运行只初始化、校准一次）
ocr_backend = None
ocr_capture = None
ocr_detector = None
ocr_calibrated_region = None
ocr_initialization_attempted = False
ocr_calibration_attempted = False
ocr_calibration_in_progress = False


# ─── 安全控制 ───────────────────────────────────────
_programmatic_esc = False  # 程序按的 ESC，不触发停止

def on_press(key):
    global stop_event, paused
    if key == keyboard.Key.esc:
        if _programmatic_esc:
            return True  # 程序触发的 ESC，忽略
        if (
            ocr_calibration_in_progress
            or focus_restore_calibration_in_progress
            or forward_click_calibration_in_progress
            or batch_filter_calibration_in_progress
            or favorite_button_calibration_in_progress
        ):
            return True  # 交给 Tk 校准窗口处理，只取消校准，不停止浏览
        stop_event = True
        logger.info('⚡ 收到 ESC，准备停止')
        return False
    if key == keyboard.Key.space:
        paused = not paused
        logger.info(f'{"▶ 继续" if not paused else "⏸ 暂停"}')


listener = keyboard.Listener(on_press=on_press)
# 注意：listener.start() 在 run() 中调用，避免 exe 闪退


# ─── 用户交互输入 ───────────────────────────────────
def parse_duration_seconds(raw_value):
    """Parse an optional non-negative integer duration in seconds."""
    value = '' if raw_value is None else str(raw_value).strip()
    if not value:
        return 0
    if not value.isascii() or not value.isdigit():
        raise ValueError('运行时间必须为 0、正整数秒数或留空')
    return int(value)


def parse_action_mode_choice(raw):
    """Parse the interactive action-mode choice."""
    value = '' if raw is None else str(raw).strip()
    if value == '1':
        return ACTION_MODE_FAVORITE
    if value == '2':
        return ACTION_MODE_FORWARD
    raise ValueError('请选择 1（收藏模式）或 2（转发模式）')


def prompt_action_mode():
    """Prompt until the user selects a valid candidate action mode."""
    while True:
        try:
            return parse_action_mode_choice(
                input(
                    '\n请选择候选人处理模式：\n'
                    '1 = 收藏模式\n'
                    '2 = 转发模式\n'
                    '请输入 1 或 2：\n> '
                )
            )
        except ValueError as exc:
            print(f'  输入无效：{exc}，请重新输入。')


def keyword_rule_sources():
    """Return stable display strings for the configured keyword rules."""
    return [rule.source for rule in forward_keywords]


def get_user_input(
    keywords_str='',
    email_str='',
    duration_str='',
    auto=False,
    no_forward=False,
    no_batch_filter=False,
    action_mode_value=ACTION_MODE_FORWARD,
):
    """
    获取关键词、备选邮箱和本次运行时间。
    auto=True 或 keywords 已传入时跳过交互。
    """
    global forward_keywords, backup_email, forward_enabled, run_duration_seconds
    global action_mode
    global focus_restore_calibration_requested
    global forward_click_calibration_requested
    global batch_filter_calibration_requested

    # ── 非交互模式（命令行传参或 --auto） ──
    if auto or keywords_str:
        if action_mode_value not in (
            ACTION_MODE_FAVORITE,
            ACTION_MODE_FORWARD,
        ):
            raise ValueError('action_mode 必须是 favorite 或 forward')
        action_mode = action_mode_value
        focus_restore_calibration_requested = False
        forward_click_calibration_requested = False
        batch_filter_calibration_requested = False
        run_duration_seconds = parse_duration_seconds(duration_str)
        if keywords_str:
            forward_keywords = parse_keyword_rules(keywords_str)
            forward_enabled = bool(forward_keywords)
        else:
            forward_keywords = []
            forward_enabled = False
        backup_email = email_str
        print()
        print(f'  关键词规则: {keyword_rule_sources() if forward_keywords else "(无，转发已禁用)"}')
        print(f'  备选邮箱: {backup_email if backup_email else "(未设置)"}')
        print(f'  运行时间: {run_duration_seconds or "持续运行"}')
        print()
        return

    # ── 交互模式 ──
    print()
    action_mode = prompt_action_mode()
    while True:
        raw = input(
            '请输入触发转发的关键词规则（关键词用英文双引号包裹，'
            '支持 and、or、not，规则用 ; 分隔，留空跳过转发）:\n> '
        ).strip()
        if not raw:
            forward_keywords = []
            forward_enabled = False
            print('  未设置关键词规则，转发功能已禁用')
            break
        try:
            forward_keywords = parse_keyword_rules(raw)
            forward_enabled = True
            print(f'  已录入 {len(forward_keywords)} 条关键词规则: {keyword_rule_sources()}')
            break
        except ValueError as exc:
            print(f'  关键词规则格式错误：{exc}')
            print('  格式示例："Python"; "短剧" and not "销售"')

    if action_mode == ACTION_MODE_FORWARD and forward_enabled and not no_forward:
        backup_email = input('\n请输入备选邮箱（最近联系中无邮箱时兜底）:\n> ').strip()
        print(f'  备选邮箱: {backup_email if backup_email else "(未设置)"}')
    else:
        backup_email = ""

    if action_mode == ACTION_MODE_FORWARD and forward_enabled:
        calibrate_forward = input(
            '\n是否校准完整邮件转发点击区域（包含焦点恢复区域）？[y/N]\n> '
        ).strip().lower()
        calibrate_requested = calibrate_forward in ('y', 'yes')
        focus_restore_calibration_requested = calibrate_requested
        forward_click_calibration_requested = calibrate_requested
        if calibrate_requested:
            print('  将在第一位候选人详情页打开后进行完整转发点击区域校准')
        else:
            print('  完整转发点击将使用默认区域')
    else:
        focus_restore_calibration_requested = False
        forward_click_calibration_requested = False

    if no_batch_filter:
        batch_filter_calibration_requested = False
        print('  自动筛选归位已禁用，本次运行使用旧首位候选人流程')
    else:
        calibrate_batch_filter = input(
            '\n是否校准“最近没看过”筛选和首位候选人区域？[y/N]\n> '
        ).strip().lower()
        batch_filter_calibration_requested = calibrate_batch_filter in ('y', 'yes')
        if batch_filter_calibration_requested:
            print('  将在候选人列表页依次校准四个自动筛选归位区域')
        else:
            print('  本次运行使用旧首位候选人流程')

    while True:
        duration_raw = input('\n请输入本次运行时间（秒，留空或 0 表示持续运行）:\n> ')
        try:
            run_duration_seconds = parse_duration_seconds(duration_raw)
            break
        except ValueError as exc:
            print(f'  输入错误：{exc}')

    print(f'  运行时间: {run_duration_seconds or "持续运行"}')

    print()


# ─── 窗口操作 ───────────────────────────────────────

def require_windows_window_api():
    """Fail clearly when a Windows-only window API is used elsewhere."""
    if not IS_WINDOWS:
        raise RuntimeError('此功能依赖 Windows 窗口 API，当前平台尚未支持')

def get_window_process_name(hwnd):
    """Return the executable name for a top-level Windows window."""
    require_windows_window_api()
    handle = None
    try:
        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
        handle = ctypes.windll.kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            return ''
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not ctypes.windll.kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            return ''
        return os.path.basename(buffer.value).lower()
    except Exception:
        return ''
    finally:
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)


def is_boss_edge_window(title, process_name):
    """Reject unrelated apps whose title merely contains the word BOSS."""
    return process_name == 'msedge.exe' and ('BOSS' in title or 'zhipin' in title.lower())


def bring_edge_foreground():
    """将 BOSS 直聘 Edge 窗口置顶"""
    if not IS_WINDOWS:
        logger.error('❌ 当前平台不支持 Windows Edge 窗口置顶')
        return False

    result = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        process_name = get_window_process_name(hwnd)
        if is_boss_edge_window(title, process_name):
            result.append((hwnd, title))
            return False
        return True

    win32gui.EnumWindows(cb, result)

    if not result:
        logger.error('❌ 找不到 BOSS 直聘窗口')
        return False

    hwnd, title = result[0]
    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.3)

    try:
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.5)
        logger.info(f'✅ Edge 已置顶: {title}')
        return True
    except Exception as e:
        logger.error(f'❌ 置顶失败: {e}')
        return False


# ─── 基础工具 ───────────────────────────────────────

def prepare_browser(platform_name=None, *, launch_safe_target=False):
    """Prepare the supported browser without leaking platform details to run()."""
    current_platform = sys.platform if platform_name is None else platform_name

    if current_platform == 'win32':
        ready = bring_edge_foreground()
        return BrowserPrepareResult(
            ready=ready,
            platform='windows',
            browser='edge',
            message='' if ready else '未能准备 Windows Edge 窗口',
            error_code='' if ready else 'EDGE_PREPARE_FAILED',
        )

    if current_platform == 'darwin':
        resolved = resolve_chrome_executable()
        if resolved.error_code:
            return resolved
        executable_path = resolved.executable_path
        launched = None
        if launch_safe_target:
            launched = launch_chrome_safe_target(Path(executable_path))
            if not launched.launched:
                return launched
        try:
            permissions = check_macos_permissions()
        except Exception as exc:
            return BrowserPrepareResult(
                ready=False,
                platform='macos',
                browser='chrome',
                launched=launch_safe_target,
                executable_path=(
                    launched.executable_path if launched is not None else executable_path
                ),
                message=f'macOS 权限诊断失败: {exc}。{MACOS_PERMISSION_GUIDANCE}',
                error_code='MACOS_PERMISSION_CHECK_FAILED',
            )

        focus = focus_chrome_window()
        if not focus.frontmost:
            return BrowserPrepareResult(
                ready=False,
                platform='macos',
                browser='chrome',
                launched=launch_safe_target,
                executable_path=(
                    launched.executable_path if launched is not None else executable_path
                ),
                message=f'{permissions.message} {focus.message}',
                error_code=focus.error_code,
                focus_frontmost=False,
            )

        tab = get_chrome_active_tab_identity()
        if tab.error_code:
            return BrowserPrepareResult(
                ready=False,
                platform='macos',
                browser='chrome',
                launched=launch_safe_target,
                executable_path=(
                    launched.executable_path if launched is not None else executable_path
                ),
                message=f'{permissions.message} {focus.message}。{tab.message}',
                error_code=tab.error_code,
                focus_frontmost=True,
                page_url=tab.url or None,
                page_title=tab.title or None,
                page_error_code=tab.error_code,
            )

        page_allowed = is_allowed_boss_page(tab.url, tab.title)
        if not page_allowed:
            return BrowserPrepareResult(
                ready=False,
                platform='macos',
                browser='chrome',
                launched=launch_safe_target,
                executable_path=(
                    launched.executable_path if launched is not None else executable_path
                ),
                message=(
                    f'{permissions.message} {focus.message}。active tab 页面不在 '
                    'BOSS 身份白名单中；不放行业务动作。'
                ),
                error_code='MACOS_PAGE_NOT_ALLOWED',
                focus_frontmost=True,
                page_url=tab.url,
                page_title=tab.title,
                page_allowed=False,
                page_error_code='MACOS_PAGE_NOT_ALLOWED',
            )

        return BrowserPrepareResult(
            ready=True,
            platform='macos',
            browser='chrome',
            launched=launch_safe_target,
            executable_path=(
                launched.executable_path if launched is not None else executable_path
            ),
            message=(
                f'{permissions.message} {focus.message}。active tab 页面身份允许，'
                '但 Retina 坐标、校准、OCR 与真实业务动作尚未完成；不放行业务动作。'
            ),
            error_code='MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY',
            focus_frontmost=True,
            page_url=tab.url,
            page_title=tab.title,
            page_allowed=True,
            page_error_code='MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY',
        )

    return BrowserPrepareResult(
        ready=False,
        platform=current_platform,
        browser='',
        message=f'不支持的运行平台: {current_platform}',
        error_code='UNSUPPORTED_PLATFORM',
    )


def _normalize_monitor_entry(monitor):
    """Keep only stable monitor fields for diagnostics and fingerprinting."""
    return {
        'left': int(monitor['left']),
        'top': int(monitor['top']),
        'width': int(monitor['width']),
        'height': int(monitor['height']),
        'is_primary': bool(monitor.get('is_primary', False)),
    }


def _select_primary_monitor(monitors):
    """Choose the primary physical monitor from an MSS monitor list."""
    physical_monitors = monitors[1:] if len(monitors) > 1 else monitors
    if not physical_monitors:
        return None
    for monitor in physical_monitors:
        if monitor.get('is_primary'):
            return _normalize_monitor_entry(monitor)
    return _normalize_monitor_entry(physical_monitors[0])


def _build_display_fingerprint(monitors):
    """Hash a stable monitor snapshot into a display fingerprint."""
    canonical = [_normalize_monitor_entry(monitor) for monitor in monitors]
    payload = json.dumps(canonical, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _valid_positive_integer_size(size):
    """Return a normalized positive integer size, or None when invalid."""
    if not isinstance(size, tuple) or len(size) != 2:
        return None
    if any(isinstance(value, bool) or not isinstance(value, int) for value in size):
        return None
    if any(value <= 0 for value in size):
        return None
    return size


def infer_retina_scale(request_size, image_size, *, tolerance=0.02):
    """Infer per-axis scale from request/image metadata without screen access."""
    normalized_request = _valid_positive_integer_size(request_size)
    if normalized_request is None:
        return RetinaScaleInference(
            request_size=None,
            image_size=_valid_positive_integer_size(image_size),
            scale_x=None,
            scale_y=None,
            passed=False,
            message='MSS request size 必须是两个正整数',
            error_code='RETINA_SCALE_REQUEST_SIZE_INVALID',
        )

    normalized_image = _valid_positive_integer_size(image_size)
    if normalized_image is None:
        return RetinaScaleInference(
            request_size=normalized_request,
            image_size=None,
            scale_x=None,
            scale_y=None,
            passed=False,
            message='captured image size 必须是两个正整数',
            error_code='RETINA_SCALE_IMAGE_SIZE_INVALID',
        )

    if (
        isinstance(tolerance, bool)
        or not isinstance(tolerance, (int, float))
        or not math.isfinite(tolerance)
        or tolerance < 0
    ):
        return RetinaScaleInference(
            request_size=normalized_request,
            image_size=normalized_image,
            scale_x=None,
            scale_y=None,
            passed=False,
            message='scale tolerance 必须是有限非负数',
            error_code='RETINA_SCALE_TOLERANCE_INVALID',
        )

    try:
        scale_x = normalized_image[0] / normalized_request[0]
        scale_y = normalized_image[1] / normalized_request[1]
    except OverflowError:
        scale_x = None
        scale_y = None

    if (
        scale_x is None
        or scale_y is None
        or not math.isfinite(scale_x)
        or not math.isfinite(scale_y)
        or scale_x <= 0
        or scale_y <= 0
    ):
        return RetinaScaleInference(
            request_size=normalized_request,
            image_size=normalized_image,
            scale_x=scale_x,
            scale_y=scale_y,
            passed=False,
            message='推断出的 Retina scale 不是有限正数',
            error_code='RETINA_SCALE_NON_FINITE',
        )

    if not (0.5 <= scale_x <= 4.0 and 0.5 <= scale_y <= 4.0):
        return RetinaScaleInference(
            request_size=normalized_request,
            image_size=normalized_image,
            scale_x=scale_x,
            scale_y=scale_y,
            passed=False,
            message='推断出的 Retina scale 超出允许范围 [0.5, 4.0]',
            error_code='RETINA_SCALE_OUT_OF_RANGE',
        )

    axis_difference = abs(scale_x - scale_y)
    tolerance_value = float(tolerance)
    if axis_difference > tolerance_value and not math.isclose(
        axis_difference,
        tolerance_value,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        return RetinaScaleInference(
            request_size=normalized_request,
            image_size=normalized_image,
            scale_x=scale_x,
            scale_y=scale_y,
            passed=False,
            message=(
                'Retina scale 两轴不一致：'
                f'scale_x={scale_x}, scale_y={scale_y}, tolerance={tolerance}'
            ),
            error_code='RETINA_SCALE_AXIS_MISMATCH',
        )

    return RetinaScaleInference(
        request_size=normalized_request,
        image_size=normalized_image,
        scale_x=scale_x,
        scale_y=scale_y,
        passed=True,
        message='MSS request/result scale metadata 推断通过；不代表真实屏幕已验证',
    )


def infer_monitor_capture_scale(monitor, image_size, *, tolerance=0.02):
    """Infer scale from an MSS monitor dict and supplied image metadata only."""
    if not isinstance(monitor, dict):
        monitor_size = None
    else:
        monitor_size = _valid_positive_integer_size(
            (monitor.get('width'), monitor.get('height'))
        )

    if monitor_size is None:
        return RetinaScaleInference(
            request_size=None,
            image_size=_valid_positive_integer_size(image_size),
            scale_x=None,
            scale_y=None,
            passed=False,
            message='MSS monitor 必须包含有效的正整数 width/height',
            error_code='RETINA_SCALE_MONITOR_INVALID',
        )

    return infer_retina_scale(monitor_size, image_size, tolerance=tolerance)


def _is_finite_number(value):
    """Return whether a value is numeric, finite, and not a bool."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    try:
        return math.isfinite(float(value))
    except (OverflowError, ValueError):
        return False


def _valid_finite_point(point):
    """Return a finite numeric point as floats, or None when invalid."""
    if not isinstance(point, tuple) or len(point) != 2:
        return None
    if any(not _is_finite_number(value) for value in point):
        return None
    try:
        return (float(point[0]), float(point[1]))
    except (OverflowError, ValueError):
        return None


def _valid_tk_selection(selection):
    """Return whether every selection field is finite numeric metadata."""
    if not isinstance(selection, TkSelectionRegion):
        return False
    values = (selection.left, selection.top, selection.width, selection.height)
    return all(_is_finite_number(value) for value in values)


def normalize_drag_selection(start, end, *, min_size=1.0):
    """Normalize any drag direction into a Tk overlay-local rectangle."""
    normalized_start = _valid_finite_point(start)
    normalized_end = _valid_finite_point(end)
    if (
        normalized_start is None
        or normalized_end is None
        or not _is_finite_number(min_size)
        or min_size <= 0
    ):
        return TkToScreenshotMapping(
            tk_selection=None,
            crop_region=None,
            passed=False,
            message='拖拽点和 min_size 必须是有限有效数值',
            error_code='TK_SELECTION_POINTS_INVALID',
        )

    left = min(normalized_start[0], normalized_end[0])
    top = min(normalized_start[1], normalized_end[1])
    width = abs(normalized_end[0] - normalized_start[0])
    height = abs(normalized_end[1] - normalized_start[1])
    selection = TkSelectionRegion(left, top, width, height)
    if width < min_size or height < min_size:
        return TkToScreenshotMapping(
            tk_selection=selection,
            crop_region=None,
            passed=False,
            message=f'Tk selection 小于最小尺寸 {min_size}',
            error_code='TK_SELECTION_TOO_SMALL',
        )

    return TkToScreenshotMapping(
        tk_selection=selection,
        crop_region=None,
        passed=True,
        message='Tk 拖拽区域已规范化；尚未映射到截图像素',
    )


def validate_screenshot_crop(crop_region, screenshot_size):
    """Validate a half-open screenshot crop without clamping it."""
    normalized_screenshot = _valid_positive_integer_size(screenshot_size)
    if normalized_screenshot is None:
        return TkToScreenshotMapping(
            tk_selection=None,
            crop_region=None,
            passed=False,
            message='screenshot size 必须是两个正整数',
            error_code='SCREENSHOT_SIZE_INVALID',
        )

    if not isinstance(crop_region, ScreenshotCropRegion):
        return TkToScreenshotMapping(
            tk_selection=None,
            crop_region=None,
            passed=False,
            message='screenshot crop 数据结构无效',
            error_code='SCREENSHOT_CROP_EMPTY',
        )

    crop_values = (
        crop_region.left,
        crop_region.top,
        crop_region.width,
        crop_region.height,
    )
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in crop_values
    ):
        return TkToScreenshotMapping(
            tk_selection=None,
            crop_region=crop_region,
            passed=False,
            message='screenshot crop 字段必须是整数',
            error_code='SCREENSHOT_CROP_EMPTY',
        )

    if crop_region.width <= 0 or crop_region.height <= 0:
        return TkToScreenshotMapping(
            tk_selection=None,
            crop_region=crop_region,
            passed=False,
            message='screenshot crop 必须非空',
            error_code='SCREENSHOT_CROP_EMPTY',
        )

    right = crop_region.left + crop_region.width
    bottom = crop_region.top + crop_region.height
    if (
        crop_region.left < 0
        or crop_region.top < 0
        or right > normalized_screenshot[0]
        or bottom > normalized_screenshot[1]
    ):
        return TkToScreenshotMapping(
            tk_selection=None,
            crop_region=crop_region,
            passed=False,
            message='screenshot crop 超出图像边界；未执行 clamp',
            error_code='SCREENSHOT_CROP_OUT_OF_BOUNDS',
        )

    return TkToScreenshotMapping(
        tk_selection=None,
        crop_region=crop_region,
        passed=True,
        message='screenshot crop 非空且位于图像边界内',
    )


def map_tk_selection_to_screenshot_crop(
    selection,
    overlay_size,
    screenshot_size,
):
    """Map one validated Tk-local selection to screenshot image pixels."""
    normalized_overlay = _valid_positive_integer_size(overlay_size)
    if normalized_overlay is None:
        return TkToScreenshotMapping(
            tk_selection=selection if isinstance(selection, TkSelectionRegion) else None,
            crop_region=None,
            passed=False,
            message='Tk overlay size 必须是两个正整数',
            error_code='TK_OVERLAY_SIZE_INVALID',
        )

    normalized_screenshot = _valid_positive_integer_size(screenshot_size)
    if normalized_screenshot is None:
        return TkToScreenshotMapping(
            tk_selection=selection if isinstance(selection, TkSelectionRegion) else None,
            crop_region=None,
            passed=False,
            message='screenshot size 必须是两个正整数',
            error_code='SCREENSHOT_SIZE_INVALID',
        )

    if not _valid_tk_selection(selection):
        return TkToScreenshotMapping(
            tk_selection=None,
            crop_region=None,
            passed=False,
            message='Tk selection 字段必须是有限数值',
            error_code='TK_SELECTION_POINTS_INVALID',
        )

    if selection.width <= 0 or selection.height <= 0:
        return TkToScreenshotMapping(
            tk_selection=selection,
            crop_region=None,
            passed=False,
            message='Tk selection 必须非空',
            error_code='TK_SELECTION_TOO_SMALL',
        )

    selection_right = selection.left + selection.width
    selection_bottom = selection.top + selection.height
    if (
        selection.left < 0
        or selection.top < 0
        or selection_right > normalized_overlay[0]
        or selection_bottom > normalized_overlay[1]
    ):
        return TkToScreenshotMapping(
            tk_selection=selection,
            crop_region=None,
            passed=False,
            message='Tk selection 必须完全位于 overlay 边界内',
            error_code='TK_SELECTION_OUT_OF_BOUNDS',
        )

    scale = infer_retina_scale(normalized_overlay, normalized_screenshot)
    if not scale.passed:
        return TkToScreenshotMapping(
            tk_selection=selection,
            crop_region=None,
            passed=False,
            message=f'无法安全映射 Tk selection：{scale.message}',
            error_code=scale.error_code,
        )

    left = math.floor(selection.left * scale.scale_x)
    top = math.floor(selection.top * scale.scale_y)
    right = math.ceil(selection_right * scale.scale_x)
    bottom = math.ceil(selection_bottom * scale.scale_y)
    crop = ScreenshotCropRegion(
        left=left,
        top=top,
        width=right - left,
        height=bottom - top,
    )
    crop_validation = validate_screenshot_crop(crop, normalized_screenshot)
    if not crop_validation.passed:
        return TkToScreenshotMapping(
            tk_selection=selection,
            crop_region=crop,
            passed=False,
            message=crop_validation.message,
            error_code=crop_validation.error_code,
        )

    return TkToScreenshotMapping(
        tk_selection=selection,
        crop_region=crop,
        passed=True,
        message=(
            'Tk selection 已映射为 screenshot pixel crop；'
            '仅表示纯坐标转换通过，不代表真实屏幕已验证'
        ),
    )


def crop_image_for_preview(image, crop):
    """Return a detached crop preview from one provided NumPy image array."""
    try:
        import numpy as np
    except ImportError:
        return (False, None, 'CROP_PREVIEW_IMAGE_INVALID')

    if not isinstance(image, np.ndarray):
        return (False, None, 'CROP_PREVIEW_IMAGE_INVALID')
    if image.ndim not in (2, 3):
        return (False, None, 'CROP_PREVIEW_IMAGE_INVALID')
    if image.ndim == 3 and image.shape[2] <= 0:
        return (False, None, 'CROP_PREVIEW_IMAGE_INVALID')

    if not isinstance(crop, ScreenshotCropRegion):
        return (False, None, 'CROP_PREVIEW_REGION_INVALID')
    if crop.width <= 0 or crop.height <= 0:
        return (False, None, 'CROP_PREVIEW_REGION_INVALID')
    if crop.left < 0 or crop.top < 0:
        return (False, None, 'CROP_PREVIEW_REGION_INVALID')

    image_height, image_width = image.shape[:2]
    if crop.left + crop.width > image_width or crop.top + crop.height > image_height:
        return (False, None, 'CROP_PREVIEW_REGION_OUT_OF_BOUNDS')

    cropped = image[
        crop.top:crop.top + crop.height,
        crop.left:crop.left + crop.width,
    ].copy()
    return (True, cropped, None)


def build_coordinate_diagnostics_dir(base_dir='logs/macos-coordinate-diagnostics'):
    """Return one timestamped diagnostics directory path without creating it."""
    return Path(base_dir) / time.strftime('%Y%m%d-%H%M%S')


def save_crop_preview_for_manual_check(
    image,
    crop,
    *,
    output_dir,
    filename='crop_preview.png',
):
    """Save only one local crop preview for manual verification."""
    if (
        not isinstance(filename, str)
        or not filename
        or Path(filename).name != filename
        or any(part == '..' for part in Path(filename).parts)
    ):
        return CropPreviewResult(
            saved=False,
            preview_path=None,
            crop_size=None,
            message='crop preview filename 非法，拒绝路径穿越',
            error_code='CROP_PREVIEW_PATH_INVALID',
        )

    cropped_ok, cropped, crop_error = crop_image_for_preview(image, crop)
    if not cropped_ok:
        error_messages = {
            'CROP_PREVIEW_IMAGE_INVALID': 'crop preview image 非法',
            'CROP_PREVIEW_REGION_INVALID': 'crop preview region 非法',
            'CROP_PREVIEW_REGION_OUT_OF_BOUNDS': (
                'crop preview region 超出 image bounds'
            ),
        }
        return CropPreviewResult(
            saved=False,
            preview_path=None,
            crop_size=None,
            message=error_messages.get(crop_error, 'crop preview 失败'),
            error_code=crop_error,
        )

    try:
        from PIL import Image

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        preview_path = output_path / filename
        Image.fromarray(cropped).save(preview_path)
    except Exception as exc:
        return CropPreviewResult(
            saved=False,
            preview_path=None,
            crop_size=None,
            message=f'crop preview 保存失败: {exc}',
            error_code='CROP_PREVIEW_SAVE_FAILED',
        )

    return CropPreviewResult(
        saved=True,
        preview_path=str(preview_path),
        crop_size=(cropped.shape[1], cropped.shape[0]),
        message='crop preview 已保存到本地诊断目录',
    )


def build_coordinate_calibration_metadata(
    *,
    display_fingerprint,
    scale_inference,
    tk_to_screenshot_mapping,
    crop_preview,
    preview_confirmed=False,
):
    """Build fail-closed coordinate evidence without touching screen APIs."""
    fingerprint_valid = (
        isinstance(display_fingerprint, str) and bool(display_fingerprint.strip())
    )
    scale_valid = (
        isinstance(scale_inference, RetinaScaleInference)
        and scale_inference.passed
    )
    mapping_valid = (
        isinstance(tk_to_screenshot_mapping, TkToScreenshotMapping)
        and tk_to_screenshot_mapping.passed
        and tk_to_screenshot_mapping.crop_region is not None
    )
    preview_saved = (
        isinstance(crop_preview, CropPreviewResult)
        and crop_preview.saved
        and bool(crop_preview.preview_path)
    )
    validated = fingerprint_valid and scale_valid and mapping_valid
    manually_confirmed = (
        validated and preview_saved and preview_confirmed is True
    )

    if not fingerprint_valid:
        message = '坐标校准 metadata 缺少 display fingerprint'
        error_code = 'COORDINATE_CALIBRATION_METADATA_MISSING'
    elif not scale_valid:
        message = '坐标校准 scale inference 未通过验证'
        error_code = 'COORDINATE_CALIBRATION_SCALE_NOT_VALIDATED'
    elif not mapping_valid:
        message = 'Tk selection 到 screenshot crop mapping 未通过验证'
        error_code = 'COORDINATE_CALIBRATION_MAPPING_NOT_VALIDATED'
    elif not manually_confirmed:
        message = 'crop preview 尚未保存并由人工确认'
        error_code = 'COORDINATE_CALIBRATION_PREVIEW_NOT_CONFIRMED'
    else:
        message = (
            '坐标校准 metadata 已验证并经人工确认；'
            '仍不代表 OCR 或真实业务可用'
        )
        error_code = 'COORDINATE_CALIBRATION_VALIDATED_NOT_BUSINESS_READY'

    return CoordinateCalibrationMetadata(
        display_fingerprint=(
            display_fingerprint.strip() if fingerprint_valid else None
        ),
        scale_inference=(
            scale_inference
            if isinstance(scale_inference, RetinaScaleInference)
            else None
        ),
        tk_to_screenshot_mapping=(
            tk_to_screenshot_mapping
            if isinstance(tk_to_screenshot_mapping, TkToScreenshotMapping)
            else None
        ),
        crop_preview=(
            crop_preview if isinstance(crop_preview, CropPreviewResult) else None
        ),
        validated=validated,
        manually_confirmed=manually_confirmed,
        message=message,
        error_code=error_code,
    )


def attach_coordinate_metadata_to_region(region, metadata=None):
    """Attach optional evidence while preserving the original ScreenRegion."""
    if not isinstance(region, ScreenRegion):
        raise TypeError('region 必须是 ScreenRegion')
    if metadata is not None and not isinstance(
        metadata, CoordinateCalibrationMetadata
    ):
        raise TypeError('metadata 必须是 CoordinateCalibrationMetadata 或 None')
    return CalibratedScreenRegion(
        region=region,
        coordinate_metadata=metadata,
    )


def capture_screen_coordinate_diagnostics():
    """Collect read-only coordinate metadata without screenshots or input."""
    platform_name = sys.platform

    if platform_name != 'darwin':
        return ScreenCoordinateDiagnostics(
            platform=platform_name,
            pyautogui_size=None,
            pyautogui_position=None,
            mss_monitors=(),
            primary_monitor=None,
            tk_version=None,
            tcl_version=None,
            display_fingerprint=None,
            passed=False,
            message=(
                'coordinate diagnostics are only implemented as a read-only '
                f'macOS probe; unsupported platform: {platform_name}'
            ),
            error_code='COORDINATE_DIAGNOSTICS_UNSUPPORTED_PLATFORM',
        )

    try:
        pyautogui_size = tuple(int(value) for value in pyautogui.size())
    except Exception as exc:
        return ScreenCoordinateDiagnostics(
            platform=platform_name,
            pyautogui_size=None,
            pyautogui_position=None,
            mss_monitors=(),
            primary_monitor=None,
            tk_version=None,
            tcl_version=None,
            display_fingerprint=None,
            passed=False,
            message=f'pyautogui.size() 读取失败: {exc}',
            error_code='COORDINATE_DIAGNOSTICS_PYAUTOGUI_FAILED',
        )

    try:
        pyautogui_position = tuple(int(value) for value in pyautogui.position())
    except Exception as exc:
        return ScreenCoordinateDiagnostics(
            platform=platform_name,
            pyautogui_size=pyautogui_size,
            pyautogui_position=None,
            mss_monitors=(),
            primary_monitor=None,
            tk_version=None,
            tcl_version=None,
            display_fingerprint=None,
            passed=False,
            message=f'pyautogui.position() 读取失败: {exc}',
            error_code='COORDINATE_DIAGNOSTICS_PYAUTOGUI_FAILED',
        )

    try:
        import mss
    except ImportError as exc:
        return ScreenCoordinateDiagnostics(
            platform=platform_name,
            pyautogui_size=pyautogui_size,
            pyautogui_position=pyautogui_position,
            mss_monitors=(),
            primary_monitor=None,
            tk_version=None,
            tcl_version=None,
            display_fingerprint=None,
            passed=False,
            message=f'mss 不可用: {exc}',
            error_code='COORDINATE_DIAGNOSTICS_MSS_FAILED',
        )

    try:
        with mss.MSS() as capture:
            raw_monitors = tuple(capture.monitors)
    except Exception as exc:
        return ScreenCoordinateDiagnostics(
            platform=platform_name,
            pyautogui_size=pyautogui_size,
            pyautogui_position=pyautogui_position,
            mss_monitors=(),
            primary_monitor=None,
            tk_version=None,
            tcl_version=None,
            display_fingerprint=None,
            passed=False,
            message=f'mss 监视器读取失败: {exc}',
            error_code='COORDINATE_DIAGNOSTICS_MSS_FAILED',
        )

    if not raw_monitors:
        return ScreenCoordinateDiagnostics(
            platform=platform_name,
            pyautogui_size=pyautogui_size,
            pyautogui_position=pyautogui_position,
            mss_monitors=(),
            primary_monitor=None,
            tk_version=None,
            tcl_version=None,
            display_fingerprint=None,
            passed=False,
            message='mss 监视器列表为空',
            error_code='COORDINATE_DIAGNOSTICS_MSS_FAILED',
        )

    try:
        mss_monitors = tuple(_normalize_monitor_entry(monitor) for monitor in raw_monitors)
        primary_monitor = _select_primary_monitor(raw_monitors)
        display_fingerprint = _build_display_fingerprint(raw_monitors)
    except Exception as exc:
        return ScreenCoordinateDiagnostics(
            platform=platform_name,
            pyautogui_size=pyautogui_size,
            pyautogui_position=pyautogui_position,
            mss_monitors=(),
            primary_monitor=None,
            tk_version=None,
            tcl_version=None,
            display_fingerprint=None,
            passed=False,
            message=f'display fingerprint 生成失败: {exc}',
            error_code='COORDINATE_DIAGNOSTICS_FAILED',
        )

    try:
        import tkinter as tk
        tk_version = str(tk.TkVersion)
        tcl_version = str(tk.TclVersion)
    except Exception as exc:
        return ScreenCoordinateDiagnostics(
            platform=platform_name,
            pyautogui_size=pyautogui_size,
            pyautogui_position=pyautogui_position,
            mss_monitors=mss_monitors,
            primary_monitor=primary_monitor,
            tk_version=None,
            tcl_version=None,
            display_fingerprint=display_fingerprint,
            passed=False,
            message=f'Tk/Tcl 版本读取失败: {exc}',
            error_code='COORDINATE_DIAGNOSTICS_TK_FAILED',
        )

    return ScreenCoordinateDiagnostics(
        platform=platform_name,
        pyautogui_size=pyautogui_size,
        pyautogui_position=pyautogui_position,
        mss_monitors=mss_monitors,
        primary_monitor=primary_monitor,
        tk_version=tk_version,
        tcl_version=tcl_version,
        display_fingerprint=display_fingerprint,
        passed=True,
        message='坐标系统基础信息只读采集成功',
    )


def resolve_chrome_executable(chrome_path=MACOS_CHROME_EXECUTABLE):
    """Resolve the fixed macOS Chrome executable without launching it."""
    path = Path(chrome_path)
    result_fields = {
        'ready': False,
        'platform': 'macos',
        'browser': 'chrome',
        'executable_path': str(path),
    }

    if not path.exists():
        return BrowserPrepareResult(
            **result_fields,
            message=f'未找到 macOS Chrome: {path}',
            error_code='CHROME_NOT_FOUND',
        )
    if not path.is_file():
        return BrowserPrepareResult(
            **result_fields,
            message=f'macOS Chrome 路径不是文件: {path}',
            error_code='CHROME_NOT_EXECUTABLE',
        )
    if not os.access(path, os.X_OK):
        return BrowserPrepareResult(
            **result_fields,
            message=f'macOS Chrome 文件不可执行: {path}',
            error_code='CHROME_NOT_EXECUTABLE',
        )

    return BrowserPrepareResult(**result_fields)


def launch_chrome_safe_target(chrome_path):
    """Launch only about:blank; a successful process start is not browser readiness."""
    path = Path(chrome_path)
    try:
        subprocess.Popen([str(path), CHROME_SAFE_TARGET])
    except Exception as exc:
        return BrowserPrepareResult(
            ready=False,
            platform='macos',
            browser='chrome',
            executable_path=str(path),
            message=f'macOS Chrome 启动失败: {exc}',
            error_code='CHROME_LAUNCH_FAILED',
        )

    return BrowserPrepareResult(
        ready=False,
        platform='macos',
        browser='chrome',
        launched=True,
        executable_path=str(path),
        message='macOS Chrome 已启动 about:blank，但窗口尚未验证为可操作',
        error_code='MACOS_BROWSER_STARTED_NOT_READY',
    )


def run_osascript(script, timeout=3.0):
    """Run one AppleScript via osascript without invoking a shell."""
    return subprocess.run(
        ['osascript', '-e', script],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def focus_chrome_window():
    """Activate Chrome and verify it is the frontmost macOS application."""
    activate_script = 'tell application "Google Chrome" to activate'
    frontmost_script = (
        'tell application "System Events" '
        'to get name of first application process whose frontmost is true'
    )

    try:
        activate_result = run_osascript(activate_script)
        if activate_result.returncode != 0:
            error_detail = (
                activate_result.stderr.strip()
                or activate_result.stdout.strip()
                or 'unknown osascript error'
            )
            return MacOSChromeFocusResult(
                platform='macos',
                browser='chrome',
                activated=False,
                frontmost=False,
                message=f'macOS Chrome activate 失败: {error_detail}',
                error_code='MACOS_CHROME_ACTIVATE_FAILED',
            )

        frontmost_result = run_osascript(frontmost_script)
        if frontmost_result.returncode != 0:
            error_detail = (
                frontmost_result.stderr.strip()
                or frontmost_result.stdout.strip()
                or 'unknown osascript error'
            )
            return MacOSChromeFocusResult(
                platform='macos',
                browser='chrome',
                activated=True,
                frontmost=False,
                message=f'macOS frontmost application 查询失败: {error_detail}',
                error_code='MACOS_CHROME_FRONTMOST_QUERY_FAILED',
            )

        frontmost_app = frontmost_result.stdout.strip()
        if frontmost_app != 'Google Chrome':
            return MacOSChromeFocusResult(
                platform='macos',
                browser='chrome',
                activated=True,
                frontmost=False,
                message=(
                    'macOS frontmost application 不是 Google Chrome: '
                    f'{frontmost_app or "unknown"}'
                ),
                error_code='MACOS_CHROME_NOT_FRONTMOST',
            )

        return MacOSChromeFocusResult(
            platform='macos',
            browser='chrome',
            activated=True,
            frontmost=True,
            message='macOS Chrome 已激活并确认位于前台',
        )
    except subprocess.TimeoutExpired as exc:
        return MacOSChromeFocusResult(
            platform='macos',
            browser='chrome',
            activated=False,
            frontmost=False,
            message=f'macOS osascript 调用超时: {exc}',
            error_code='MACOS_OSASCRIPT_TIMEOUT',
        )
    except FileNotFoundError as exc:
        return MacOSChromeFocusResult(
            platform='macos',
            browser='chrome',
            activated=False,
            frontmost=False,
            message=f'macOS osascript 不可用: {exc}',
            error_code='MACOS_OSASCRIPT_UNAVAILABLE',
        )
    except OSError as exc:
        return MacOSChromeFocusResult(
            platform='macos',
            browser='chrome',
            activated=False,
            frontmost=False,
            message=f'macOS osascript 调用失败: {exc}',
            error_code='MACOS_OSASCRIPT_ERROR',
        )


def get_chrome_active_tab_identity():
    """Read the URL/title of Chrome's current active tab without activating it."""
    tab_query_script = """
tell application "Google Chrome"
    if not (exists front window) then
        error "NO_FRONT_WINDOW"
    end if
    set frontWindow to front window
    try
        set activeTab to active tab of frontWindow
    on error
        error "NO_ACTIVE_TAB"
    end try
    set tabUrl to URL of activeTab
    set tabTitle to title of activeTab
    return tabUrl & linefeed & tabTitle
end tell
""".strip()

    try:
        query_result = run_osascript(tab_query_script)
        if query_result.returncode != 0:
            error_detail = (
                query_result.stderr.strip()
                or query_result.stdout.strip()
                or 'unknown osascript error'
            )
            if 'NO_FRONT_WINDOW' in error_detail:
                return MacOSChromeTabIdentity(
                    platform='macos',
                    browser='chrome',
                    message='macOS Chrome 当前没有 front window',
                    error_code='MACOS_CHROME_NO_FRONT_WINDOW',
                )
            if 'NO_ACTIVE_TAB' in error_detail:
                return MacOSChromeTabIdentity(
                    platform='macos',
                    browser='chrome',
                    message='macOS Chrome front window 没有 active tab',
                    error_code='MACOS_CHROME_NO_ACTIVE_TAB',
                )
            return MacOSChromeTabIdentity(
                platform='macos',
                browser='chrome',
                message=f'macOS Chrome active tab 查询失败: {error_detail}',
                error_code='MACOS_CHROME_TAB_QUERY_FAILED',
            )

        output = query_result.stdout.rstrip('\r\n')
        lines = output.splitlines()
        tab_url = lines[0].strip() if lines else ''
        tab_title = '\n'.join(lines[1:]).strip() if len(lines) > 1 else ''

        if not tab_url:
            return MacOSChromeTabIdentity(
                platform='macos',
                browser='chrome',
                title=tab_title,
                message='macOS Chrome active tab URL 缺失',
                error_code='MACOS_CHROME_ACTIVE_TAB_URL_MISSING',
            )

        return MacOSChromeTabIdentity(
            platform='macos',
            browser='chrome',
            url=tab_url,
            title=tab_title,
            message='macOS Chrome active tab URL/title 查询成功',
        )
    except subprocess.TimeoutExpired as exc:
        return MacOSChromeTabIdentity(
            platform='macos',
            browser='chrome',
            message=f'macOS osascript 调用超时: {exc}',
            error_code='MACOS_OSASCRIPT_TIMEOUT',
        )
    except FileNotFoundError as exc:
        return MacOSChromeTabIdentity(
            platform='macos',
            browser='chrome',
            message=f'macOS osascript 不可用: {exc}',
            error_code='MACOS_OSASCRIPT_UNAVAILABLE',
        )
    except OSError as exc:
        return MacOSChromeTabIdentity(
            platform='macos',
            browser='chrome',
            message=f'macOS osascript 调用失败: {exc}',
            error_code='MACOS_OSASCRIPT_ERROR',
        )


def check_macos_accessibility_capability():
    """Return unknown without generating any system input event."""
    return 'unknown'


def check_macos_screen_recording_capability():
    """Return unknown without capturing or saving any screen content."""
    return 'unknown'


def check_macos_keyboard_listener_capability():
    """Return unknown without starting a listener or waiting for input."""
    return 'unknown'


def check_macos_permissions():
    """Aggregate side-effect-free macOS capability diagnostics."""
    accessibility = check_macos_accessibility_capability()
    screen_recording = check_macos_screen_recording_capability()
    keyboard_listener = check_macos_keyboard_listener_capability()
    ready = all(
        status == 'ok'
        for status in (accessibility, screen_recording, keyboard_listener)
    )
    message = (
        'macOS 权限诊断：'
        f'accessibility={accessibility}, '
        f'screen_recording={screen_recording}, '
        f'keyboard_listener={keyboard_listener}。'
        f'{MACOS_PERMISSION_GUIDANCE}'
    )
    return MacOSPermissionStatus(
        accessibility=accessibility,
        screen_recording=screen_recording,
        keyboard_listener=keyboard_listener,
        ready=ready,
        message=message,
    )


def run_preflight_only(_cli_args=None):
    """Run browser and permission preparation diagnostics, then always exit."""
    result = prepare_browser(launch_safe_target=True)
    print('Browser preflight only (no business actions):')
    print(f'  platform: {result.platform}')
    print(f'  browser: {result.browser or "unsupported"}')
    print(f'  launched: {result.launched}')
    print(f'  ready: {result.ready}')
    print(f'  focus_frontmost: {result.focus_frontmost}')
    print(f'  page_url: {result.page_url or "none"}')
    print(f'  page_title: {result.page_title or "none"}')
    print(f'  page_allowed: {result.page_allowed}')
    print(f'  page_error_code: {result.page_error_code or "none"}')
    print(f'  error_code: {result.error_code or "none"}')
    print(f'  message: {result.message or "none"}')
    print(
        '  note: preflight diagnoses window focus and page identity, but does not '
        'validate Retina coordinates, calibration, OCR, forwarding, or real '
        'business safety.'
    )
    return 0


def run_coordinate_diagnostics_only(_cli_args=None):
    """Run coordinate diagnostics only, then always exit."""
    result = capture_screen_coordinate_diagnostics()
    print('Coordinate diagnostics only (no business actions):')
    print(f'  platform: {result.platform}')
    print(f'  pyautogui_size: {result.pyautogui_size}')
    print(f'  pyautogui_position: {result.pyautogui_position}')
    print(f'  mss_monitors: {result.mss_monitors}')
    print(f'  primary_monitor: {result.primary_monitor}')
    print(f'  tk_version: {result.tk_version or "none"}')
    print(f'  tcl_version: {result.tcl_version or "none"}')
    print(f'  display_fingerprint: {result.display_fingerprint or "none"}')
    print(f'  passed: {result.passed}')
    print(f'  error_code: {result.error_code or "none"}')
    print(f'  message: {result.message}')
    print(
        '  note: this helper only records read-only coordinate metadata; it '
        'does not screenshot, create a Tk overlay, calibrate OCR, or start '
        'business actions.'
    )
    return 0


def run_mac_forward_ui_smoke_only(
    cli_args,
    *,
    focus_fn=None,
    click_fn=None,
    typewrite_fn=None,
    position_fn=pyautogui.position,
    confirm_fn=input,
    submit_confirm_fn=input,
    sleep_fn=time.sleep,
    now_fn=time.time,
) -> int:
    """Run the manual macOS forward/filter UI smoke path fail closed."""
    try:
        config = build_mac_forward_ui_smoke_config(cli_args)
    except MacSafeBrowseArgumentError as exc:
        print('MAC FORWARD UI SMOKE ONLY — FAIL CLOSED')
        print(f'  error_code: {exc.error_code}')
        print(f'  message: {exc}')
        return 2

    print('MAC FORWARD UI SMOKE ONLY — NO FORWARDING ENABLED')
    print(f'  invalid_submit_enabled: {config.allow_invalid_submit}')
    budget = build_mac_forward_ui_smoke_budget(config)
    plan = build_mac_forward_ui_smoke_plan(config)
    action_fns, statuses, apply_count = build_mac_forward_ui_smoke_action_fns(
        config,
        focus_fn=focus_fn,
        click_fn=click_fn,
        typewrite_fn=typewrite_fn,
        position_fn=position_fn,
        confirm_fn=confirm_fn,
        submit_confirm_fn=submit_confirm_fn,
        sleep_fn=sleep_fn,
    )
    result = run_mac_forward_ui_smoke_pipeline(
        budget,
        plan,
        started_at=now_fn(),
        now_fn=now_fn,
        action_fns=action_fns,
        apply_count_fn=apply_count,
        statuses=statuses,
    )
    for action, status in result.statuses.items():
        print(f'  {action}_attempted: {status.attempted}')
        print(f'  {action}_verified: {status.verified}')
        print(f'  {action}_count: {status.count}')
        print(f'  {action}_error_code: {status.error_code}')
    print(f'  forwarding_enabled: {result.forwarding_enabled}')
    print(f'  invalid_submit_enabled: {result.invalid_submit_enabled}')
    if not result.completed:
        print(f'  error_code: {result.error_code}')
        print(f'  message: {result.message}')
        return 2

    print('  error_code: MAC_FORWARD_UI_SMOKE_STOPPED_AFTER_MANUAL_ACTIONS')
    print(
        '  message: 手工 smoke 动作已完成；未进入业务循环，'
        '未验证真实发送，也不代表业务 ready'
    )
    return 2


def run_mac_safe_browse_calibration_only(
    cli_args,
    *,
    display_fingerprint=None,
    scale_inference=None,
    tk_to_screenshot_mapping=None,
    preview_confirmed=False,
    select_region_fn=None,
    save_preview_fn=None,
    capture_fn=None,
    preview_path=None,
    diagnostics_fn=None,
    save_crop_preview_fn=None,
    confirmation_fn=None,
    preview_dir=None,
    overlay_cleanup_check_fn=None,
) -> int:
    """Prepare and atomically publish calibration metadata, then exit."""
    try:
        validate_mac_safe_browse_calibration_args(cli_args)
    except MacSafeBrowseArgumentError as exc:
        print('MAC SAFE BROWSE CALIBRATION ONLY — FAIL CLOSED')
        print(f'  error_code: {exc.error_code}')
        print(f'  message: {exc}')
        return 2

    print('MAC SAFE BROWSE CALIBRATION ONLY — NO FORWARDING ENABLED')
    result = publish_mac_safe_browse_calibration(
        display_fingerprint=display_fingerprint,
        scale_inference=scale_inference,
        tk_to_screenshot_mapping=tk_to_screenshot_mapping,
        preview_confirmed=preview_confirmed,
        select_region_fn=select_region_fn,
        save_preview_fn=save_preview_fn,
        capture_fn=capture_fn,
        preview_path=preview_path,
        diagnostics_fn=diagnostics_fn,
        save_crop_preview_fn=save_crop_preview_fn,
        confirmation_fn=confirmation_fn,
        preview_dir=preview_dir,
        overlay_cleanup_check_fn=overlay_cleanup_check_fn,
    )
    if not result.published or result.calibrated_region is None:
        print('  published: False')
        print(f'  error_code: {result.error_code}')
        print(f'  message: {result.message}')
        return 2

    region = result.calibrated_region.region
    metadata = result.calibrated_region.coordinate_metadata
    print('  published: True')
    print(
        f'  region: left={region.left} top={region.top} '
        f'width={region.width} height={region.height}'
    )
    print(f'  coordinate_validated: {metadata.validated}')
    print(f'  manually_confirmed: {metadata.manually_confirmed}')
    print(f'  business_ready: {metadata.business_ready}')
    print(f'  overlay_cleanup_completed: {result.overlay_cleanup_completed}')
    print(f'  display_fingerprint: {metadata.display_fingerprint}')
    print(
        '  preview_path: '
        f'{metadata.crop_preview.preview_path if metadata.crop_preview else "none"}'
    )
    print(f'  error_code: {result.error_code}')
    print(f'  message: {result.message}')
    return 0


def run_mac_safe_browse_calibrate_and_dry_run(
    cli_args,
    *,
    display_fingerprint=None,
    scale_inference=None,
    tk_to_screenshot_mapping=None,
    preview_confirmed=False,
    select_region_fn=None,
    save_preview_fn=None,
    capture_fn=None,
    preview_path=None,
    diagnostics_fn=None,
    save_crop_preview_fn=None,
    confirmation_fn=None,
    preview_dir=None,
    real_capture_focus_fn=None,
    real_capture_factory=None,
    candidate_open_fn=None,
    candidate_focus_fn=None,
    candidate_open_confirm_fn=input,
    candidate_open_position_fn=pyautogui.position,
    candidate_open_sleep_fn=time.sleep,
    candidate_open_countdown_seconds=5,
    overlay_cleanup_check_fn=None,
) -> int:
    """Run same-process calibration, then the bounded browse-only trial plan."""
    try:
        config = build_mac_safe_browse_calibrate_and_dry_run_config(cli_args)
    except MacSafeBrowseArgumentError as exc:
        print('MAC SAFE BROWSE CALIBRATE AND DRY RUN — FAIL CLOSED')
        print(f'  error_code: {exc.error_code}')
        print(f'  message: {exc}')
        return 2

    print('MAC SAFE BROWSE CALIBRATE AND DRY RUN — NO FORWARDING ENABLED')
    print(f'  max_candidates: {config.max_candidates}')
    print(f'  max_runtime_minutes: {config.max_runtime_minutes}')
    calibration_result = publish_mac_safe_browse_calibration(
        display_fingerprint=display_fingerprint,
        scale_inference=scale_inference,
        tk_to_screenshot_mapping=tk_to_screenshot_mapping,
        preview_confirmed=preview_confirmed,
        select_region_fn=select_region_fn,
        save_preview_fn=save_preview_fn,
        capture_fn=capture_fn,
        preview_path=preview_path,
        diagnostics_fn=diagnostics_fn,
        save_crop_preview_fn=save_crop_preview_fn,
        confirmation_fn=confirmation_fn,
        preview_dir=preview_dir,
        overlay_cleanup_check_fn=overlay_cleanup_check_fn,
    )
    print(f'  calibration_published: {calibration_result.published}')
    if (
        not calibration_result.published
        or calibration_result.calibrated_region is None
    ):
        print(f'  error_code: {calibration_result.error_code}')
        print(f'  message: {calibration_result.message}')
        return 2

    metadata = calibration_result.calibrated_region.coordinate_metadata
    print(f'  coordinate_validated: {metadata.validated}')
    print(f'  manually_confirmed: {metadata.manually_confirmed}')
    print(f'  business_ready: {metadata.business_ready}')
    print(
        f'  overlay_cleanup_completed: '
        f'{calibration_result.overlay_cleanup_completed}'
    )
    print(
        '  preview_path: '
        f'{metadata.crop_preview.preview_path if metadata.crop_preview else "none"}'
    )

    action_budget = build_default_mac_safe_browse_action_budget(config)
    real_capture_enabled = cli_args.get('mac_safe_browse_real_capture_once') is True
    open_candidate_enabled = (
        cli_args.get('mac_safe_browse_open_candidate_once') is True
    )
    dry_plan = build_mac_safe_browse_trial_plan(
        config,
        open_candidate_once=open_candidate_enabled,
    )
    action_fns = None
    build_real_capture_result = None
    if real_capture_enabled or open_candidate_enabled:
        action_fns, build_real_capture_result = (
            build_mac_safe_browse_real_action_fns(
                calibration_result.calibrated_region,
                focus_fn=real_capture_focus_fn,
                capture_factory=real_capture_factory,
                candidate_open_fn=candidate_open_fn,
                candidate_focus_fn=candidate_focus_fn,
                candidate_open_confirm_fn=candidate_open_confirm_fn,
                candidate_open_position_fn=candidate_open_position_fn,
                candidate_open_sleep_fn=candidate_open_sleep_fn,
                candidate_open_countdown_seconds=candidate_open_countdown_seconds,
                open_candidate_once=open_candidate_enabled,
                overlay_cleanup_completed=(
                    calibration_result.overlay_cleanup_completed
                ),
            )
        )
    dry_result = run_mac_safe_browse_dry_pipeline(
        action_budget,
        dry_plan,
        started_at=0.0,
        now=0.0,
        action_fns=action_fns,
    )
    real_capture_result = (
        build_real_capture_result()
        if callable(build_real_capture_result)
        else MacSafeBrowseRealCaptureResult(
            focus_restored=False,
            capture_completed=False,
            capture_size=None,
            candidate_open_attempted=False,
            candidate_open_verified=False,
            candidate_opened=False,
            message='real actions 未启用；保持 noop dry pipeline',
        )
    )
    print(f'  real_capture_enabled: {real_capture_enabled}')
    print(f'  candidate_open_enabled: {open_candidate_enabled}')
    print(f'  dry_pipeline_completed: {dry_result.completed}')
    print(f'  real_browsing_enabled: {dry_result.real_browsing_enabled}')
    print(f'  forwarding_enabled: {dry_result.forwarding_enabled}')
    print(f'  focus_restore_count: {dry_result.state.focus_restore}')
    print(f'  ocr_capture_count: {dry_result.state.ocr_capture}')
    print(f'  candidate_open_count: {dry_result.state.candidate_open}')
    print(f'  capture_completed: {real_capture_result.capture_completed}')
    print(f'  capture_size: {real_capture_result.capture_size}')
    print(
        f'  candidate_open_attempted: '
        f'{real_capture_result.candidate_open_attempted}'
    )
    print(
        f'  candidate_open_verified: '
        f'{real_capture_result.candidate_open_verified}'
    )
    print(f'  candidate_opened: {real_capture_result.candidate_opened}')
    print(f'  browse_loop_enabled: {real_capture_result.browse_loop_enabled}')
    if not dry_result.completed:
        error_code = real_capture_result.error_code or dry_result.error_code
        print(f'  error_code: {error_code}')
        print(f'  message: {real_capture_result.message or dry_result.message}')
        return 2

    print('  error_code: MAC_SAFE_BROWSE_BROWSE_LOOP_NOT_IMPLEMENTED')
    print(
        '  message: calibration 已在同进程发布，'
        '仅允许 focus_restore/ocr_capture'
        f'{" / candidate_open" if open_candidate_enabled else ""} '
        '的最小试点；browse loop remains disabled and is not implemented in 5F-6'
    )
    return 2


def run_mac_safe_browse_only(cli_args) -> int:
    """Validate CLI and existing OCR evidence, then stop before browsing."""
    try:
        config = build_mac_safe_browse_config(cli_args)
    except MacSafeBrowseArgumentError as exc:
        print('MAC SAFE BROWSE ONLY — FAIL CLOSED')
        print(f'  error_code: {exc.error_code}')
        print(f'  message: {exc}')
        return 2

    print('MAC SAFE BROWSE ONLY — NO FORWARDING ENABLED')
    print(f'  max_candidates: {config.max_candidates}')
    print(f'  max_runtime_minutes: {config.max_runtime_minutes}')
    print('  allow_scroll: False')
    print('  allow_next_candidate: False')
    print('  allow_refresh: False')
    print('  allow_filter: False')

    ocr_evidence = collect_mac_safe_browse_ocr_evidence(ocr_calibrated_region)
    print(f'  ocr_region_present: {ocr_evidence.has_calibrated_region}')
    print(f'  coordinate_metadata_present: {ocr_evidence.has_coordinate_metadata}')
    print(f'  coordinate_validated: {ocr_evidence.coordinate_validated}')
    print(f'  manually_confirmed: {ocr_evidence.manually_confirmed}')
    print(f'  business_ready: {ocr_evidence.business_ready}')
    print(
        '  display_fingerprint: '
        f'{ocr_evidence.display_fingerprint or "none"}'
    )
    if not ocr_evidence.passed:
        print(f'  error_code: {ocr_evidence.error_code}')
        print(f'  message: {ocr_evidence.message}')
        return 2

    action_budget = build_default_mac_safe_browse_action_budget(config)
    print('  action_budget_ready: True')
    print(f'  max_runtime_seconds: {action_budget.max_runtime_seconds}')
    print(f'  max_candidate_open: {action_budget.max_candidate_open}')
    print(f'  max_scroll: {action_budget.max_scroll}')
    print(f'  max_next_candidate: {action_budget.max_next_candidate}')
    print(f'  max_refresh: {action_budget.max_refresh}')
    print(f'  max_filter_click: {action_budget.max_filter_click}')
    print(f'  max_focus_restore: {action_budget.max_focus_restore}')
    print(f'  max_ocr_capture: {action_budget.max_ocr_capture}')
    print(f'  max_forward: {action_budget.max_forward}')
    dry_plan = build_mac_safe_browse_dry_run_plan(config)
    dry_result = run_mac_safe_browse_dry_pipeline(
        action_budget,
        dry_plan,
        started_at=0.0,
        now=0.0,
    )
    print(f'  dry_pipeline_completed: {dry_result.completed}')
    print(f'  real_browsing_enabled: {dry_result.real_browsing_enabled}')
    print(f'  forwarding_enabled: {dry_result.forwarding_enabled}')
    print(f'  focus_restore_count: {dry_result.state.focus_restore}')
    print(f'  ocr_capture_count: {dry_result.state.ocr_capture}')
    if not dry_result.completed:
        print(f'  error_code: {dry_result.error_code}')
        print(f'  message: {dry_result.message}')
        return 2

    print('  error_code: MAC_SAFE_BROWSE_REAL_BROWSING_NOT_IMPLEMENTED')
    print(
        '  message: noop dry pipeline completed; real browsing remains disabled '
        'and is not implemented in 5F-1'
    )
    return 2


def safe_wait(seconds):
    """等待指定秒数，期间响应暂停/停止"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        if stop_event:
            return False
        while paused and not stop_event:
            time.sleep(0.2)
        time.sleep(0.2)
    return True


def request_timed_stop():
    """Request a normal stop when the configured run duration expires."""
    global stop_event
    stop_event = True


def start_run_timer(duration_seconds):
    """Start the optional run timer and return it for later cancellation."""
    if duration_seconds <= 0:
        return None
    timer = threading.Timer(duration_seconds, request_timed_stop)
    timer.daemon = True
    timer.start()
    return timer


def human_delay(min_s=FORWARD_MIN_DELAY, max_s=FORWARD_MAX_DELAY):
    """随机延迟，模拟人类操作间隔"""
    delay = random.uniform(min_s, max_s)
    return safe_wait(delay)


def _bezier_human_move_to(target_x, target_y):
    """Existing observable path, retained as the WindMouse failure fallback."""
    start = pyautogui.position()
    start_x = float(start[0])
    start_y = float(start[1])
    delta_x = target_x - start_x
    delta_y = target_y - start_y
    distance = math.hypot(delta_x, delta_y)

    if distance == 0:
        pyautogui.moveTo(target_x, target_y, duration=0)
        return

    duration = min(
        MOUSE_MOVE_MAX_DURATION,
        max(
            MOUSE_MOVE_MIN_DURATION,
            MOUSE_MOVE_BASE_DURATION + distance / MOUSE_MOVE_DISTANCE_DIVISOR,
        ),
    )
    steps = min(
        MOUSE_MOVE_MAX_STEPS,
        max(MOUSE_MOVE_MIN_STEPS, round(duration * MOUSE_MOVE_SAMPLE_RATE)),
    )

    # Very short moves stay straight and stable. Moderate moves use a
    # degenerate straight Bezier without intermediate jitter.
    first_fraction = 1.0 / 3.0
    second_fraction = 2.0 / 3.0
    curve_offset = 0.0
    jitter_amplitude = 0.0
    if distance >= MOUSE_MOVE_CURVE_MIN_DISTANCE:
        first_fraction = random.uniform(0.25, 0.40)
        second_fraction = random.uniform(0.60, 0.75)
        curve_ratio = random.uniform(
            MOUSE_MOVE_CURVE_RATIO_MIN,
            MOUSE_MOVE_CURVE_RATIO_MAX,
        )
        curve_offset = min(
            MOUSE_MOVE_CURVE_OFFSET_MAX,
            max(MOUSE_MOVE_CURVE_OFFSET_MIN, distance * curve_ratio),
        )
        curve_offset *= random.choice((-1.0, 1.0))
        jitter_amplitude = random.uniform(
            MOUSE_MOVE_JITTER_MIN,
            MOUSE_MOVE_JITTER_MAX,
        )

    unit_x = delta_x / distance
    unit_y = delta_y / distance
    perpendicular_x = -unit_y
    perpendicular_y = unit_x
    control1_x = (
        start_x + delta_x * first_fraction + perpendicular_x * curve_offset
    )
    control1_y = (
        start_y + delta_y * first_fraction + perpendicular_y * curve_offset
    )
    control2_x = (
        start_x + delta_x * second_fraction + perpendicular_x * curve_offset
    )
    control2_y = (
        start_y + delta_y * second_fraction + perpendicular_y * curve_offset
    )
    step_interval = duration / steps

    for index in range(1, steps):
        progress = index / steps
        eased = 3.0 * progress ** 2 - 2.0 * progress ** 3
        inverse = 1.0 - eased
        point_x = (
            inverse ** 3 * start_x
            + 3.0 * inverse ** 2 * eased * control1_x
            + 3.0 * inverse * eased ** 2 * control2_x
            + eased ** 3 * target_x
        )
        point_y = (
            inverse ** 3 * start_y
            + 3.0 * inverse ** 2 * eased * control1_y
            + 3.0 * inverse * eased ** 2 * control2_y
            + eased ** 3 * target_y
        )

        if jitter_amplitude and distance >= MOUSE_MOVE_SHORT_DISTANCE:
            jitter_scale = math.sin(math.pi * progress)
            point_x += random.uniform(
                -jitter_amplitude,
                jitter_amplitude,
            ) * jitter_scale
            point_y += random.uniform(
                -jitter_amplitude,
                jitter_amplitude,
            ) * jitter_scale

        pyautogui.moveTo(int(round(point_x)), int(round(point_y)), duration=0)
        time.sleep(step_interval)

    # Never let curve rounding or intermediate jitter alter the click target.
    pyautogui.moveTo(target_x, target_y, duration=0)


def human_move_to(x, y, *, simple=None, region_size=None):
    """Move to an exact target using simple, WindMouse, or fallback movement."""
    target_x = int(round(x))
    target_y = int(round(y))
    if simple is None:
        simple = simple_mouse_enabled
    # This is intentionally before any WindMouse import or availability check.
    if simple:
        pyautogui.moveTo(target_x, target_y, duration=random.uniform(0.15, 0.35))
        return
    mouse_motion.move_to_target(
        pyautogui, target_x, target_y, region_size=region_size,
        fallback=lambda: _bezier_human_move_to(target_x, target_y), logger=logger,
    )


def human_click(x, y, offset=FORWARD_CLICK_OFFSET, *, region_size=None):
    """
    带随机偏移的人类化点击。
    点击位置在目标坐标的 ±offset 范围内随机抖动。
    按下时长随机 50-150ms，模拟人类手指停留。
    """
    tx = x + random.randint(-offset, offset)
    ty = y + random.randint(-offset, offset)
    target_x = int(round(tx))
    target_y = int(round(ty))
    human_move_to(target_x, target_y, region_size=region_size)
    time.sleep(random.uniform(0.03, 0.08))
    pyautogui.mouseDown(target_x, target_y)
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.mouseUp(target_x, target_y)


def random_point_in_region(region):
    """Return one point inside a screen region using half-open bounds."""
    if region.width <= 0 or region.height <= 0:
        raise ValueError('焦点恢复区域尺寸必须为正数')
    return (
        random.randint(region.left, region.left + region.width - 1),
        random.randint(region.top, region.top + region.height - 1),
    )


def random_point_in_inner_region(region, ratio=0.6):
    """Return a random point inside the centered inner portion of a region."""
    if not isinstance(region, ScreenRegion):
        return None
    if region.width <= 0 or region.height <= 0:
        return None
    if isinstance(ratio, bool) or not isinstance(ratio, (int, float)):
        return None
    if not math.isfinite(float(ratio)) or not 0 < ratio <= 1:
        return None

    margin = (1.0 - float(ratio)) / 2.0
    return (
        random.uniform(
            region.left + region.width * margin,
            region.left + region.width * (1.0 - margin),
        ),
        random.uniform(
            region.top + region.height * margin,
            region.top + region.height * (1.0 - margin),
        ),
    )


def _is_valid_screen_region(region):
    """Return whether a value is a usable positive screen region."""
    return (
        isinstance(region, ScreenRegion)
        and region.width > 0
        and region.height > 0
    )


def resolve_candidate_detail_safe_region():
    """Prefer the existing detail focus region, then the OCR body region."""
    if _is_valid_screen_region(focus_restore_region):
        return focus_restore_region

    if isinstance(ocr_calibrated_region, ScreenRegion):
        ocr_region = ocr_calibrated_region
    else:
        ocr_region = getattr(ocr_calibrated_region, 'region', None)
    if _is_valid_screen_region(ocr_region):
        return ocr_region
    return None


def restore_candidate_detail_focus_after_favorite():
    """Restore candidate detail focus twice after a favorite-button click."""
    region = resolve_candidate_detail_safe_region()
    if region is None:
        logger.warning('⚠ 候选人详情页安全区缺失或无效，跳过收藏后焦点恢复')
        return False

    try:
        for _ in range(2):
            point = random_point_in_inner_region(region, ratio=0.6)
            if point is None:
                logger.warning('⚠ 候选人详情页安全区取点失败，停止收藏后焦点恢复')
                return False
            human_click(
                point[0],
                point[1],
                offset=0,
                region_size=(region.width, region.height),
            )
            time.sleep(0.15)
        return True
    except Exception as exc:
        logger.exception('❌ 收藏后候选人详情页焦点恢复失败: %s', exc)
        return False


def perform_favorite_action():
    """Click the calibrated favorite button and wait for the UI to settle."""
    region = favorite_button_region
    point = random_point_in_inner_region(region, ratio=0.6)
    if point is None:
        logger.error('❌ 收藏按钮区域缺失或无效，跳过收藏点击')
        return False

    try:
        human_click(
            point[0],
            point[1],
            offset=0,
            region_size=(region.width, region.height),
        )
        time.sleep(0.5)
        return restore_candidate_detail_focus_after_favorite()
    except Exception as exc:
        logger.exception('❌ 收藏按钮点击失败: %s', exc)
        return False


def click_in_region(region):
    """Click one random point inside a region without adding a second offset."""
    x, y = random_point_in_region(region)
    human_click(x, y, offset=0, region_size=(region.width, region.height))


def get_clipboard_text():
    """读取剪贴板文本（CF_UNICODETEXT）。失败返回空字符串。"""
    if sys.platform == 'darwin':
        try:
            result = subprocess.run(
                ['pbpaste'],
                capture_output=True,
                text=True,
                timeout=1.0,
                check=False,
            )
            if result.returncode == 0:
                return result.stdout
        except Exception:
            return ''


def type_text_human(text):
    """
    人类化文本输入。
    使用 pyautogui.typewrite 输入，字符间隔随机 0.03-0.08 秒。
    """
    for char in text:
        if stop_event:
            return False
        pyautogui.typewrite(char, interval=random.uniform(0.03, 0.08))
    return True


# ─── 关键词检测 ─────────────────────────────────────

class OCRInterrupted(RuntimeError):
    """Raised when Esc stops the run during an OCR wait or scroll."""


def initialize_ocr():
    """Initialize one RapidOCR engine for the entire process."""
    global ocr_backend, ocr_capture, ocr_initialization_attempted

    if ocr_initialization_attempted:
        return ocr_backend is not None and ocr_capture is not None
    ocr_initialization_attempted = True
    try:
        dpi_mode = enable_windows_dpi_awareness()
        ocr_backend = RapidOCRBackend()
        ocr_capture = MSSScreenCapture()
        logger.info(f'✅ OCR 初始化成功 (RapidOCR + ONNX Runtime, DPI={dpi_mode})')
        return True
    except Exception as exc:
        ocr_backend = None
        ocr_capture = None
        logger.exception(f'❌ OCR 初始化失败，自动转发已安全禁用: {exc}')
        return False


def ocr_wait(seconds):
    """OCR wait hook that keeps Esc and Space responsive."""
    if not safe_wait(seconds):
        raise OCRInterrupted('OCR scan interrupted by stop request')


def ocr_scroll_down():
    """Scroll down by the configured OCR scan distance."""
    if stop_event:
        raise OCRInterrupted('OCR scan interrupted by stop request')
    while paused and not stop_event:
        time.sleep(0.2)
    if stop_event:
        raise OCRInterrupted('OCR scan interrupted by stop request')
    steps = random.randint(OCR_SCROLL_MIN_STEPS, OCR_SCROLL_MAX_STEPS)
    logger.info(f'  OCR 有序向下滚动 {steps} 格')
    pyautogui.scroll(-steps)


def remaining_stay_seconds(target_seconds, started_at, now=None):
    """Return only the unspent part of the original candidate stay budget."""
    current = time.monotonic() if now is None else now
    return max(0.0, target_seconds - (current - started_at))


def ensure_ocr_region_calibrated(coordinate_metadata=None):
    """Calibrate once after the first candidate detail is visible."""
    global ocr_detector, ocr_calibrated_region
    global ocr_calibration_attempted, ocr_calibration_in_progress

    if ocr_detector is not None:
        return True
    if ocr_calibration_attempted:
        return False
    ocr_calibration_attempted = True

    if not initialize_ocr():
        logger.warning('🛡 因 OCR 不可用跳过关键词检测和转发')
        return False

    logger.info('请框选主显示器上的候选人详情正文区域；按 Esc 取消校准。')
    ocr_calibration_in_progress = True
    try:
        region = select_screen_region()
        preview = save_region_preview(region, OCR_PREVIEW_PATH, ocr_capture.capture)
        calibrated_region = attach_coordinate_metadata_to_region(
            region,
            coordinate_metadata,
        )
        new_detector = OCRKeywordDetector(
            backend=ocr_backend,
            capture=ocr_capture,
            region=region,
            max_scans=OCR_MAX_SCANS,
            min_confidence=OCR_MIN_CONFIDENCE,
            scroll=ocr_scroll_down,
            wait=ocr_wait,
            settle_seconds=OCR_SETTLE_SECONDS,
            confirmation_seconds=OCR_CONFIRMATION_SECONDS,
        )
    except CalibrationCancelled:
        logger.warning('🛡 OCR 校准已取消，本次运行禁用自动转发并继续浏览')
        return False
    except Exception as exc:
        logger.exception(f'🛡 OCR 校准失败，本次运行禁用自动转发并继续浏览: {exc}')
        return False
    finally:
        ocr_calibration_in_progress = False

    # Publish detector and coordinate evidence together only after all
    # construction steps succeed. Existing OCR still receives ScreenRegion.
    ocr_detector = new_detector
    ocr_calibrated_region = calibrated_region
    logger.info(
        '✅ OCR 校准完成: left=%s top=%s width=%s height=%s',
        region.left,
        region.top,
        region.width,
        region.height,
    )
    logger.info(f'校准预览已保存: {preview}')
    return True


def reset_focus_restore_calibration():
    """Reset focus restore calibration to its per-run defaults."""
    global focus_restore_region
    global focus_restore_calibration_requested
    global focus_restore_calibration_attempted
    global focus_restore_calibration_in_progress

    focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
    focus_restore_calibration_requested = False
    focus_restore_calibration_attempted = False
    focus_restore_calibration_in_progress = False


def reset_forward_click_calibration():
    """Reset forwarding click regions to their per-run defaults."""
    global forward_click_regions
    global forward_click_calibration_requested
    global forward_click_calibration_attempted
    global forward_click_calibration_in_progress

    forward_click_regions = DEFAULT_FORWARD_CLICK_REGIONS
    forward_click_calibration_requested = False
    forward_click_calibration_attempted = False
    forward_click_calibration_in_progress = False


def reset_batch_filter_calibration():
    """Reset batch filter calibration to its per-run disabled state."""
    global batch_filter_regions
    global batch_filter_calibration_requested
    global batch_filter_calibration_attempted
    global batch_filter_calibration_in_progress
    global batch_filter_enabled

    batch_filter_regions = None
    batch_filter_calibration_requested = False
    batch_filter_calibration_attempted = False
    batch_filter_calibration_in_progress = False
    batch_filter_enabled = False


def reset_favorite_button_calibration():
    """Reset favorite button calibration to its per-run empty state."""
    global favorite_button_region
    global favorite_button_calibration_attempted
    global favorite_button_calibration_in_progress

    favorite_button_region = None
    favorite_button_calibration_attempted = False
    favorite_button_calibration_in_progress = False


def ensure_favorite_button_region_calibrated():
    """Calibrate the favorite button once and fail closed on any problem."""
    global favorite_button_region
    global favorite_button_calibration_attempted
    global favorite_button_calibration_in_progress

    if action_mode != ACTION_MODE_FAVORITE:
        return favorite_button_region
    if favorite_button_calibration_attempted:
        return favorite_button_region

    favorite_button_calibration_attempted = True
    favorite_button_calibration_in_progress = True
    try:
        logger.info(
            '请框选 Chrome BOSS 候选人详情页中的收藏按钮内部安全区域；'
            '保持 Chrome 窗口位置、大小和缩放状态稳定，按 Esc 取消。'
        )
        region = select_screen_region(
            min_size=12,
            instruction='框选收藏按钮内部安全区域 · Esc 取消本轮运行',
            subtitle='请保持 Chrome 窗口位置、大小和缩放状态稳定',
        )
        if not isinstance(region, ScreenRegion):
            logger.error('❌ 收藏按钮区域校准返回无效区域，本轮安全退出')
            return None
        if region.width <= 0 or region.height <= 0:
            logger.error('❌ 收藏按钮区域尺寸无效，本轮安全退出')
            return None

        favorite_button_region = region
        logger.info(
            '✅ 收藏按钮区域校准完成: left=%s top=%s width=%s height=%s',
            region.left,
            region.top,
            region.width,
            region.height,
        )
        return favorite_button_region
    except CalibrationCancelled:
        favorite_button_region = None
        logger.warning('⚠ 收藏按钮区域校准已取消，本轮安全退出')
        return None
    except Exception as exc:
        favorite_button_region = None
        logger.exception('❌ 收藏按钮区域校准失败，本轮安全退出: %s', exc)
        return None
    finally:
        favorite_button_calibration_in_progress = False


def close_batch_filter_panel_after_calibration():
    """Best-effort close of the filter panel without stopping the run."""
    global _programmatic_esc

    _programmatic_esc = True
    try:
        pyautogui.press('esc')
    finally:
        _programmatic_esc = False


def ensure_batch_filter_regions_calibrated():
    """Calibrate all batch-filter navigation regions atomically once per run."""
    global batch_filter_regions
    global batch_filter_calibration_attempted
    global batch_filter_calibration_in_progress
    global batch_filter_enabled

    if not batch_filter_calibration_requested:
        return batch_filter_regions
    if batch_filter_calibration_attempted:
        return batch_filter_regions

    batch_filter_calibration_attempted = True
    batch_filter_calibration_in_progress = True
    panel_may_be_open = False
    panel_close_attempted = False

    try:
        first_candidate = select_screen_region(
            min_size=20,
            instruction='框选首位候选人卡片内部安全区域 · Esc 使用旧流程',
            subtitle='校准 1/4 · 只框选，不会打开候选人详情',
        )
        open_filter = select_screen_region(
            min_size=12,
            instruction='框选“打开筛选”按钮内部安全区域 · Esc 使用旧流程',
            subtitle='校准 2/4 · 程序将用该区域打开筛选面板',
        )

        # 点击可能已经改变页面，即使调用抛错也需要最佳努力关闭面板。
        panel_may_be_open = True
        click_in_region(open_filter)
        if not human_delay(0.5, 1.0):
            raise RuntimeError('打开筛选面板的等待被中断')

        unseen_filter = select_screen_region(
            min_size=12,
            instruction='框选“最近没看过”选项内部安全区域 · Esc 使用旧流程',
            subtitle='校准 3/4 · 只框选，不会选择该筛选项',
        )
        confirm_filter = select_screen_region(
            min_size=12,
            instruction='框选“筛选确定”按钮内部安全区域 · Esc 使用旧流程',
            subtitle='校准 4/4 · 只框选，不会应用筛选',
        )

        panel_close_attempted = True
        close_batch_filter_panel_after_calibration()
        panel_may_be_open = False

        calibrated_regions = BatchFilterRegions(
            first_candidate=first_candidate,
            open_filter=open_filter,
            unseen_filter=unseen_filter,
            confirm_filter=confirm_filter,
        )
        batch_filter_regions = calibrated_regions
        batch_filter_enabled = True
        logger.info('✅ 自动筛选归位区域校准完成')
    except CalibrationCancelled:
        batch_filter_regions = None
        batch_filter_enabled = False
        logger.warning('自动筛选归位区域校准已取消，本次运行使用旧流程')
    except Exception as exc:
        batch_filter_regions = None
        batch_filter_enabled = False
        logger.exception(f'自动筛选归位区域校准失败，本次运行使用旧流程: {exc}')
    finally:
        if panel_may_be_open and not panel_close_attempted:
            try:
                close_batch_filter_panel_after_calibration()
            except Exception as exc:
                logger.warning(f'校准后关闭筛选面板失败，本次运行使用旧流程: {exc}')
        batch_filter_calibration_in_progress = False

    return batch_filter_regions


def close_forward_dialog_after_calibration():
    """Close a possibly open forwarding dialog without stopping the run."""
    global _programmatic_esc

    _programmatic_esc = True
    try:
        pyautogui.press('esc')
    finally:
        _programmatic_esc = False


def ensure_forward_click_regions_calibrated():
    """Calibrate all forwarding click regions atomically once per run."""
    global forward_click_regions
    global forward_click_calibration_attempted
    global forward_click_calibration_in_progress

    if not forward_click_calibration_requested:
        return forward_click_regions
    if forward_click_calibration_attempted:
        return forward_click_regions

    forward_click_calibration_attempted = True
    forward_click_calibration_in_progress = True
    try:
        forward_icon = select_screen_region(
            min_size=12,
            instruction='框选详情页右上角“转发牛人”图标内部安全区域 · Esc 使用全部默认区域',
            subtitle='校准 1/5 · 程序将用该区域打开转发弹窗',
        )
        click_in_region(forward_icon)
        if not human_delay(0.8, 1.2):
            raise RuntimeError('打开转发弹窗的等待被中断')

        email_tab = select_screen_region(
            min_size=12,
            instruction='框选弹窗左侧“邮件转发” Tab 内部安全区域 · Esc 使用全部默认区域',
            subtitle='校准 2/5 · 程序将用该区域进入邮件转发界面',
        )
        click_in_region(email_tab)
        if not human_delay(0.5, 0.8):
            raise RuntimeError('切换邮件转发 Tab 的等待被中断')

        input_box = select_screen_region(
            min_size=12,
            instruction='框选邮箱输入框内部安全点击区域 · Esc 使用全部默认区域',
            subtitle='校准 3/5 · 只框选，不会输入内容',
        )
        recent_email = select_screen_region(
            min_size=12,
            instruction='框选“最近联系”中第一个邮箱标签内部安全区域 · Esc 使用全部默认区域',
            subtitle='校准 4/5 · 只框选，不会触发转发',
        )
        forward_button = select_screen_region(
            min_size=12,
            instruction='框选右下角“转发”按钮内部安全区域 · Esc 使用全部默认区域',
            subtitle='校准 5/5 · 只框选，程序绝不点击此按钮',
        )

        forward_click_regions = ForwardClickRegions(
            forward_icon=forward_icon,
            email_tab=email_tab,
            input_box=input_box,
            recent_email=recent_email,
            forward_button=forward_button,
        )
        logger.info('✅ 完整转发点击区域校准完成')
    except CalibrationCancelled:
        forward_click_regions = DEFAULT_FORWARD_CLICK_REGIONS
        logger.warning('完整转发点击区域校准已取消，本次运行全部使用默认区域')
    except Exception as exc:
        forward_click_regions = DEFAULT_FORWARD_CLICK_REGIONS
        logger.exception(f'完整转发点击区域校准失败，本次运行全部使用默认区域: {exc}')
    finally:
        try:
            close_forward_dialog_after_calibration()
        except Exception as exc:
            logger.warning(f'校准后关闭转发弹窗失败，继续本次运行: {exc}')
        forward_click_calibration_in_progress = False

    return forward_click_regions


def ensure_focus_restore_region_calibrated():
    """Calibrate once when requested, falling back to the default region."""
    global focus_restore_region
    global focus_restore_calibration_attempted
    global focus_restore_calibration_in_progress

    if not focus_restore_calibration_requested:
        return focus_restore_region
    if focus_restore_calibration_attempted:
        return focus_restore_region

    focus_restore_calibration_attempted = True
    focus_restore_calibration_in_progress = True
    try:
        focus_restore_region = select_screen_region(
            min_size=20,
            instruction='拖动框选候选人详情页空白区域 · Esc 使用默认区域',
            subtitle='第一版仅支持主显示器',
        )
        logger.info(
            '✅ 焦点恢复区域校准完成: left=%s top=%s width=%s height=%s',
            focus_restore_region.left,
            focus_restore_region.top,
            focus_restore_region.width,
            focus_restore_region.height,
        )
    except CalibrationCancelled:
        focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
        logger.warning('焦点恢复区域校准已取消，本次运行使用默认区域')
    except Exception as exc:
        focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
        logger.exception(f'焦点恢复区域校准失败，本次运行使用默认区域: {exc}')
    finally:
        focus_restore_calibration_in_progress = False

    return focus_restore_region

def detect_keywords():
    """
    截取已校准的屏幕区域并执行最多 8 屏 OCR 精确匹配。
    OCR 失败、空结果、低置信度或二次确认失败均返回 False。
    """
    if not forward_enabled or not forward_keywords:
        return False

    if not ensure_ocr_region_calibrated():
        logger.warning('🛡 OCR 未就绪，因安全原因跳过转发')
        return False

    logger.info(f'🔍 OCR 关键词规则检测中... 目标: {keyword_rule_sources()}')
    result = ocr_detector.detect(forward_keywords)
    for sequence, observation in enumerate(result.observations, start=1):
        phase = '二次确认' if sequence > 1 and (
            observation.scan_number == result.observations[sequence - 2].scan_number
        ) else '扫描'
        logger.info(
            '  OCR %s: 屏=%s 耗时=%.3fs 文字框=%s 命中=%s 规则=%s',
            phase,
            observation.scan_number,
            observation.elapsed_seconds,
            observation.item_count,
            bool(observation.matched_keyword),
            observation.matched_keyword or '-',
        )

    if not result.success:
        logger.error(f'🛡 OCR 错误，因安全原因跳过转发: {result.error}')
        return False
    if result.error:
        logger.warning(f'🛡 OCR 二次确认失败，因安全原因跳过转发: {result.error}')
        return False
    if result.confirmed_match:
        logger.info(f'🔑 OCR 二次确认命中规则: {result.matched_keyword}')
        return True

    logger.info('  → OCR 最多 8 屏未确认命中，跳过转发')
    return False


# ─── 转发流程 ───────────────────────────────────────

def forward_one_candidate():
    """
    执行一次完整邮件转发流程。
    返回 True 表示转发成功，False 表示失败或跳过。
    """
    global forward_consecutive
    global _programmatic_esc

    try:
        # ── 检查连续转发上限 ──
        if forward_consecutive >= FORWARD_MAX_CONSEC:
            logger.warning(f'⚠ 连续转发已达上限 ({FORWARD_MAX_CONSEC} 次)，本次跳过')
            return False
        if stop_event:
            return False

        logger.info('📧 ────── 开始转发流程 ──────')

        # ── 步骤 1：点击"转发牛人"图标 ──
        logger.info(f'  [1/5] 点击"转发牛人"图标 →')
        click_in_region(forward_click_regions.forward_icon)
        if not human_delay(0.5, 1.5):
            return False

        # ── 步骤 2：点击"邮件转发" Tab ──
        logger.info(f'  [2/5] 点击"邮件转发"')
        click_in_region(forward_click_regions.email_tab)
        if not human_delay(0.5, 1.0):
            return False

        # ── 步骤 3：尝试填入邮箱 ──
        logger.info(f'  [3/5] 填入邮箱')
        # 先点"最近联系"中的邮箱标签
        click_in_region(forward_click_regions.recent_email)
        if not human_delay(0.3, 0.8):
            return False

        # 检测邮箱是否已填入
        click_in_region(forward_click_regions.input_box)
        time.sleep(0.1)
        if stop_event:
            return False
        pyautogui.hotkey('command', 'a')
        time.sleep(0.2)
        if stop_event:
            return False
        pyautogui.hotkey('command', 'c')
        time.sleep(0.28)
        if stop_event:
            return False
        box_text = ''
        for _ in range(5):
            box_text = get_clipboard_text().strip()
            if box_text:
                break
            time.sleep(0.15)

        if '@' in box_text and '.' in box_text:
            logger.info(f'  ✓ 邮箱已自动填入: {box_text}')
        else:
            logger.warning(f'  ⚠ "最近联系"未自动填入邮箱 (读到: "{box_text}")')
            if backup_email:
                # 手动输入备选邮箱
                logger.info(f'  ⌨ 正在手动输入备选邮箱: {backup_email}')
                click_in_region(forward_click_regions.input_box)
                time.sleep(0.1)
                if stop_event:
                    return False
                pyautogui.hotkey('command', 'a')
                time.sleep(0.05)
                if stop_event:
                    return False
                pyautogui.press('delete')
                time.sleep(0.05)
                if stop_event or not type_text_human(backup_email):
                    return False
                if not human_delay(0.3, 0.5):
                    return False
            else:
                logger.warning('  ✗ 无备选邮箱，放弃本次转发')
                # 关闭弹窗（程序触发 ESC，不停止主循环）
                _programmatic_esc = True
                pyautogui.press('esc')
                _programmatic_esc = False
                return False

        # ── 步骤 4：点击"转发"按钮 ──
        if stop_event:
            return False
        logger.info(f'  [4/5] 点击"转发"按钮')
        click_in_region(forward_click_regions.forward_button)
        if not human_delay(1.0, 2.0):
            return False

        forward_consecutive += 1
        logger.info(f'📧 ✓ 转发完成！(连续转发 {forward_consecutive}/{FORWARD_MAX_CONSEC})')
        return True
    finally:
        # 只要进入转发处理函数，所有退出路径都统一恢复详情页焦点两次。
        for attempt in range(1, 3):
            try:
                focus_x, focus_y = random_point_in_region(focus_restore_region)
                human_click(focus_x, focus_y, offset=0)
                human_delay(0.3, 0.5)
            except Exception as exc:
                logger.error(f'❌ 转发流程第 {attempt} 次焦点恢复点击失败: {exc}')


# ─── 刷简历核心 ─────────────────────────────────────

def click_first_candidate(x, y):
    """在鼠标当前位置点击一次，打开第一位候选人详情"""
    if stop_event:
        return False
    logger.info(f'🖱️ 点击第一位候选人: ({x}, {y})')
    pyautogui.click(x, y, duration=0)
    return safe_wait(CLICK_WAIT_SECONDS)


def apply_batch_filter_and_open_first_candidate():
    """Apply the calibrated unseen filter and open the first candidate."""
    if stop_event:
        return False
    if not batch_filter_enabled or batch_filter_regions is None:
        logger.error('自动筛选归位区域未就绪，停止本轮运行')
        return False

    try:
        logger.info('🔎 打开候选人筛选面板')
        click_in_region(batch_filter_regions.open_filter)
        if not human_delay(FILTER_OPEN_DELAY_MIN, FILTER_OPEN_DELAY_MAX):
            return False

        if stop_event:
            return False
        logger.info('🔎 选择“最近没看过”')
        click_in_region(batch_filter_regions.unseen_filter)
        if not human_delay(FILTER_OPTION_DELAY_MIN, FILTER_OPTION_DELAY_MAX):
            return False

        if stop_event:
            return False
        logger.info('🔎 应用候选人筛选')
        click_in_region(batch_filter_regions.confirm_filter)
        if not human_delay(FILTER_RESULTS_DELAY_MIN, FILTER_RESULTS_DELAY_MAX):
            return False

        if stop_event:
            return False
        logger.info('🖱️ 点击筛选后的首位候选人')
        click_in_region(batch_filter_regions.first_candidate)
        return safe_wait(CLICK_WAIT_SECONDS)
    except Exception as exc:
        logger.exception(f'自动筛选归位失败，停止本轮运行: {exc}')
        return False


def open_first_candidate_for_batch(legacy_point=None):
    """Open the first candidate through the calibrated or legacy path."""
    if batch_filter_enabled:
        return apply_batch_filter_and_open_first_candidate()
    if legacy_point is None:
        logger.error('旧首位候选人坐标未就绪，停止本轮运行')
        return False
    return click_first_candidate(*legacy_point)


def human_scroll_once():
    """严格鼠标不动，仅在当前位置触发小幅度滚轮。"""
    if stop_event:
        return
    if random.random() > SCROLL_PROBABILITY:
        return

    times = random.randint(1, SCROLL_MAX_TIMES)
    direction = random.choice([-1, 1])

    logger.info(f'🖱️ 滚动 {times} 次，方向 {"下" if direction == -1 else "上"}')

    for _ in range(times):
        if stop_event:
            return
        steps = random.randint(SCROLL_MIN_STEPS, SCROLL_MAX_STEPS)
        if random.random() < 0.3:
            direction *= -1
        pyautogui.scroll(steps * direction)
        time.sleep(random.uniform(0.3, 1.0))


def view_candidate(index_in_batch):
    """
    浏览当前候选人。
    流程：检测关键词 → 命中则按 action_mode 执行动作 → 停留 + 滚动。
    """
    global forward_consecutive

    # OCR 扫描耗时计入原有 12-18 秒停留时间。
    stay = random.uniform(MIN_STAY_SECONDS, MAX_STAY_SECONDS)
    stay_started = time.monotonic()

    # ── 关键词检测（在浏览开始前） ──
    keyword_hit = False
    if action_mode not in (ACTION_MODE_FAVORITE, ACTION_MODE_FORWARD):
        raise ValueError(f'未知 action_mode: {action_mode!r}')
    if forward_enabled and forward_keywords:
        keyword_hit = detect_keywords()

        if stop_event:
            return False

        if keyword_hit and action_mode == ACTION_MODE_FAVORITE:
            if not perform_favorite_action():
                logger.warning('⚠ 收藏动作未完成，继续当前候选人浏览流程')
        elif keyword_hit and action_mode == ACTION_MODE_FORWARD:
            if no_forward_mode:
                logger.info('🛡 --no-forward 已启用：保留 OCR 命中记录，禁止真实邮件转发')
            else:
                forward_one_candidate()
        else:
            # 未命中关键词，重置连续转发计数
            forward_consecutive = 0

    # ── 停留浏览 ──
    status = '🔑' if keyword_hit else '👤'
    now = time.monotonic()
    elapsed = now - stay_started
    remaining_stay = remaining_stay_seconds(stay, stay_started, now)
    logger.info(
        f'{status} 第 {index_in_batch + 1}/{BATCH_SIZE} 位，'
        f'目标停留 {stay:.1f} 秒，OCR/处理已用 {elapsed:.1f} 秒，'
        f'剩余 {remaining_stay:.1f} 秒...'
    )

    end_time = time.monotonic() + remaining_stay
    while time.monotonic() < end_time:
        segment = random.uniform(2, 5)
        remaining = end_time - time.monotonic()
        if segment > remaining:
            segment = remaining
        if segment <= 0:
            break

        if not safe_wait(segment):
            return False

        human_scroll_once()

    return True


def next_candidate():
    """按右方向键切换到下一位候选人"""
    if stop_event:
        return False
    pyautogui.press('right')
    return safe_wait(0.5)


def refresh_browser_shortcut():
    """使用当前平台浏览器的刷新快捷键。"""
    if sys.platform == 'darwin':
        pyautogui.hotkey('command', 'r')
    else:
        pyautogui.press('f5')


def refresh_page():
    """刷新页面并保留原有等待/返回语义。"""
    if stop_event:
        return False
    logger.info('🔄 已查看 100 位，刷新页面')
    refresh_browser_shortcut()
    return safe_wait(REFRESH_WAIT_SECONDS)


# ─── 主循环 ─────────────────────────────────────────

def run():
    global stop_event, forward_consecutive, no_forward_mode, simple_mouse_enabled
    global action_mode
    stop_event = False
    simple_mouse_enabled = False
    action_mode = ACTION_MODE_FORWARD
    reset_focus_restore_calibration()
    reset_forward_click_calibration()
    reset_batch_filter_calibration()
    reset_favorite_button_calibration()

    # ── 交互/参数输入 ──
    try:
        cli_args = parse_args()
        if cli_args.get('mac_single_candidate_forward_smoke', False):
            return run_mac_single_candidate_forward_smoke_only(cli_args)
        if cli_args.get('mac_forward_ui_smoke_only', False):
            return run_mac_forward_ui_smoke_only(cli_args)
        if cli_args.get('mac_safe_browse_calibrate_and_dry_run', False):
            return run_mac_safe_browse_calibrate_and_dry_run(cli_args)
        if cli_args.get('mac_safe_browse_calibrate_only', False):
            return run_mac_safe_browse_calibration_only(cli_args)
        if cli_args.get('mac_safe_browse_only', False):
            return run_mac_safe_browse_only(cli_args)
        if cli_args.get('coordinate_diagnostics_only', False):
            return run_coordinate_diagnostics_only(cli_args)
        if cli_args.get('preflight_only', False):
            return run_preflight_only(cli_args)
        no_forward_mode = cli_args['no_forward']
        simple_mouse_enabled = bool(cli_args.get('simple_mouse', False))
        get_user_input(
            keywords_str=cli_args['keywords'],
            email_str=cli_args['email'],
            duration_str=cli_args['duration_seconds'],
            auto=cli_args['auto'],
            no_forward=no_forward_mode,
            no_batch_filter=cli_args.get('no_batch_filter', False),
            action_mode_value=cli_args.get('action_mode', ACTION_MODE_FORWARD),
        )
    except MacSafeBrowseArgumentError as exc:
        print(f'[错误][{exc.error_code}] {exc}')
        return 2
    except ValueError as exc:
        print(f'[错误] {exc}')
        return 2

    # 提前初始化并复用 OCR 引擎；校准仍延迟到第一位详情打开之后。
    if forward_enabled and forward_keywords:
        initialize_ocr()

    # ── 启动键盘监听（必须在交互输入之后，避免 exe 中 input() 冲突） ──
    listener.start()

    logger.info('\n' + '=' * 50)
    logger.info('BOSS 直聘极简刷简历 v4 启动')
    logger.info(f'停留: {MIN_STAY_SECONDS}-{MAX_STAY_SECONDS}s | 每 {BATCH_SIZE} 人刷新')
    if forward_enabled:
        logger.info(f'转发关键词规则: {keyword_rule_sources()}')
        if no_forward_mode:
            logger.info('模式: 只执行 OCR 检测，真实邮件转发已禁用 (--no-forward)')
        else:
            logger.info(f'备选邮箱: {backup_email}')
            logger.info(f'连续转发上限: {FORWARD_MAX_CONSEC}')
    else:
        logger.info('转发: 已禁用')
    logger.info('=' * 50)

    browser_result = prepare_browser()
    if not browser_result.ready:
        logger.error(
            '❌ 浏览器准备失败 [%s]: %s',
            browser_result.error_code,
            browser_result.message,
        )
        return 0

    run_timer = None
    total_viewed = 0
    forward_consecutive = 0

    try:
        if batch_filter_calibration_requested:
            ensure_batch_filter_regions_calibrated()

        if batch_filter_enabled:
            legacy_point = None
            if not open_first_candidate_for_batch():
                return 0
        else:
            logger.info(
                f'\n请将鼠标移到第一位候选人卡片上，'
                f'{COUNTDOWN_SECONDS} 秒后开始...'
            )
            if not safe_wait(COUNTDOWN_SECONDS):
                return 0

            click_x, click_y = pyautogui.position()
            logger.info(f'📍 固定点击位置: ({click_x}, {click_y})')
            legacy_point = (click_x, click_y)
            if not open_first_candidate_for_batch(legacy_point):
                return 0

        # 首位详情稳定后完成既有运行期校准；这些启动准备不计入运行时间。
        if action_mode == ACTION_MODE_FAVORITE:
            if ensure_favorite_button_region_calibrated() is None:
                logger.error('❌ 收藏按钮区域未校准成功，本轮安全退出')
                return 0
        if focus_restore_calibration_requested:
            ensure_focus_restore_region_calibrated()
        if forward_click_calibration_requested:
            ensure_forward_click_regions_calibrated()
        if forward_enabled and forward_keywords:
            ensure_ocr_region_calibrated()

        if stop_event:
            return 0

        run_timer = start_run_timer(run_duration_seconds)
        first_candidate_opened = True

        while not stop_event:
            if not first_candidate_opened:
                if not open_first_candidate_for_batch(legacy_point):
                    break
            first_candidate_opened = False

            # 浏览本批次 100 位
            for i in range(BATCH_SIZE):
                if stop_event:
                    break

                total_viewed += 1
                if not view_candidate(i):
                    break

                if i < BATCH_SIZE - 1:
                    if not next_candidate():
                        break

            if stop_event:
                break

            # 每 100 位刷新
            forward_consecutive = 0  # 刷新后重置连续计数
            if not refresh_page():
                break

            logger.info(f'📊 累计已查看: {total_viewed} 位')

    except Exception as e:
        logger.exception(f'运行异常: {e}')
    finally:
        if run_timer is not None:
            run_timer.cancel()
        logger.info(f'\n🏁 停止运行。累计查看 {total_viewed} 位候选人。')
        logger.info(f'日志文件: logs/simple_brush.log\n')
    return 0


if __name__ == '__main__':
    exit_code = 0
    try:
        exit_code = run() or 0
    except KeyboardInterrupt:
        pass
    finally:
        stop_event = True
        listener.stop()
    if exit_code:
        sys.exit(exit_code)
