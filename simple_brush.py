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
import ctypes
from ctypes import wintypes
import time
import random
import logging
import threading
from pathlib import Path
import win32gui
import win32con
import win32clipboard
import win32process
import pyautogui
from pynput import keyboard

from ocr_calibration import (
    CalibrationCancelled,
    ScreenRegion,
    enable_windows_dpi_awareness,
    save_region_preview,
    select_screen_region,
)
from ocr_detector import MSSScreenCapture, OCRKeywordDetector, RapidOCRBackend
from ocr_text import parse_keyword_rules

# ─── 命令行参数解析 ───────────────────────────────
def parse_args():
    """解析命令行参数"""
    args = {
        'keywords': '',
        'email': '',
        'duration_seconds': '',
        'no_forward': False,
        'auto': False,
    }
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--keywords' and i + 1 < len(sys.argv):
            args['keywords'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--email' and i + 1 < len(sys.argv):
            args['email'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--duration-seconds':
            if i + 1 >= len(sys.argv):
                raise ValueError('--duration-seconds 缺少秒数')
            args['duration_seconds'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--no-forward':
            args['no_forward'] = True
            i += 1
        elif sys.argv[i] == '--auto':
            args['auto'] = True  # 跳过所有交互
            i += 1
        else:
            i += 1
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

# 转发反检测
FORWARD_CLICK_OFFSET = 5    # 点击位置随机偏移范围（像素）
FORWARD_MIN_DELAY   = 0.5   # 步骤间最短延迟（秒）
FORWARD_MAX_DELAY   = 1.5   # 步骤间最长延迟（秒）
FORWARD_MAX_CONSEC  = 5     # 连续转发上限（超出跳过）

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

# 转发状态（全局）
forward_keywords = []       # 启动时解析完成的关键词规则列表
backup_email = ""           # 备选邮箱
forward_enabled = False     # 是否启用转发
forward_consecutive = 0     # 连续转发计数
no_forward_mode = False     # 只检测，不执行真实邮件转发

# 焦点恢复区域状态（仅在当前运行期间有效）
focus_restore_region = DEFAULT_FOCUS_RESTORE_REGION
focus_restore_calibration_requested = False
focus_restore_calibration_attempted = False
focus_restore_calibration_in_progress = False

# OCR 状态（每次运行只初始化、校准一次）
ocr_backend = None
ocr_capture = None
ocr_detector = None
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
        if ocr_calibration_in_progress or focus_restore_calibration_in_progress:
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


def keyword_rule_sources():
    """Return stable display strings for the configured keyword rules."""
    return [rule.source for rule in forward_keywords]


def get_user_input(
    keywords_str='',
    email_str='',
    duration_str='',
    auto=False,
    no_forward=False,
):
    """
    获取关键词、备选邮箱和本次运行时间。
    auto=True 或 keywords 已传入时跳过交互。
    """
    global forward_keywords, backup_email, forward_enabled, run_duration_seconds
    global focus_restore_calibration_requested

    # ── 非交互模式（命令行传参或 --auto） ──
    if auto or keywords_str:
        focus_restore_calibration_requested = False
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

    if forward_enabled and not no_forward:
        backup_email = input('\n请输入备选邮箱（最近联系中无邮箱时兜底）:\n> ').strip()
        print(f'  备选邮箱: {backup_email if backup_email else "(未设置)"}')
    else:
        backup_email = ""

    if forward_enabled:
        calibrate_focus = input(
            '\n是否校准转发结束后的焦点恢复点击区域？[y/N]\n> '
        ).strip().lower()
        focus_restore_calibration_requested = calibrate_focus in ('y', 'yes')
        if focus_restore_calibration_requested:
            print('  将在第一位候选人详情页打开后进行焦点恢复区域校准')
        else:
            print('  焦点恢复点击将使用默认区域 X:400-500, Y:350-400')
    else:
        focus_restore_calibration_requested = False

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

def get_window_process_name(hwnd):
    """Return the executable name for a top-level Windows window."""
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


def human_click(x, y, offset=FORWARD_CLICK_OFFSET):
    """
    带随机偏移的人类化点击。
    点击位置在目标坐标的 ±offset 范围内随机抖动。
    按下时长随机 50-150ms，模拟人类手指停留。
    """
    tx = x + random.randint(-offset, offset)
    ty = y + random.randint(-offset, offset)
    pyautogui.moveTo(tx, ty, duration=random.uniform(0.15, 0.35))
    time.sleep(random.uniform(0.03, 0.08))
    pyautogui.mouseDown(tx, ty)
    time.sleep(random.uniform(0.05, 0.15))
    pyautogui.mouseUp(tx, ty)


def random_point_in_region(region):
    """Return one point inside a screen region using half-open bounds."""
    if region.width <= 0 or region.height <= 0:
        raise ValueError('焦点恢复区域尺寸必须为正数')
    return (
        random.randint(region.left, region.left + region.width - 1),
        random.randint(region.top, region.top + region.height - 1),
    )


def get_clipboard_text():
    """读取剪贴板文本（CF_UNICODETEXT）。失败返回空字符串。"""
    try:
        win32clipboard.OpenClipboard()
        if win32clipboard.IsClipboardFormatAvailable(win32clipboard.CF_UNICODETEXT):
            data = win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
        else:
            data = ""
        win32clipboard.CloseClipboard()
        return data
    except Exception:
        try:
            win32clipboard.CloseClipboard()
        except Exception:
            pass
        return ""


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


def ensure_ocr_region_calibrated():
    """Calibrate once after the first candidate detail is visible."""
    global ocr_detector, ocr_calibration_attempted, ocr_calibration_in_progress

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
    except CalibrationCancelled:
        logger.warning('🛡 OCR 校准已取消，本次运行禁用自动转发并继续浏览')
        return False
    except Exception as exc:
        logger.exception(f'🛡 OCR 校准失败，本次运行禁用自动转发并继续浏览: {exc}')
        return False
    finally:
        ocr_calibration_in_progress = False

    ocr_detector = OCRKeywordDetector(
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
        human_click(FORWARD_ICON_X, FORWARD_ICON_Y)
        if not human_delay(0.5, 1.5):
            return False

        # ── 步骤 2：点击"邮件转发" Tab ──
        logger.info(f'  [2/5] 点击"邮件转发"')
        human_click(EMAIL_TAB_X, EMAIL_TAB_Y)
        if not human_delay(0.5, 1.0):
            return False

        # ── 步骤 3：尝试填入邮箱 ──
        logger.info(f'  [3/5] 填入邮箱')
        # 先点"最近联系"中的邮箱标签
        human_click(RECENT_EMAIL_X, RECENT_EMAIL_Y)
        if not human_delay(0.3, 0.8):
            return False

        # 检测邮箱是否已填入
        human_click(INPUT_BOX_X, INPUT_BOX_Y, offset=3)
        time.sleep(0.1)
        if stop_event:
            return False
        pyautogui.hotkey('ctrl', 'a')
        time.sleep(0.05)
        if stop_event:
            return False
        pyautogui.hotkey('ctrl', 'c')
        time.sleep(0.08)
        if stop_event:
            return False
        box_text = get_clipboard_text().strip()

        if '@' in box_text and '.' in box_text:
            logger.info(f'  ✓ 邮箱已自动填入: {box_text}')
        else:
            logger.warning(f'  ⚠ "最近联系"未自动填入邮箱 (读到: "{box_text}")')
            if backup_email:
                # 手动输入备选邮箱
                logger.info(f'  ⌨ 正在手动输入备选邮箱: {backup_email}')
                human_click(INPUT_BOX_X, INPUT_BOX_Y, offset=3)
                time.sleep(0.1)
                if stop_event:
                    return False
                pyautogui.hotkey('ctrl', 'a')
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
        human_click(FORWARD_BTN_X, FORWARD_BTN_Y)
        if not human_delay(1.0, 2.0):
            return False

        forward_consecutive += 1
        logger.info(f'📧 ✓ 转发完成！(连续转发 {forward_consecutive}/{FORWARD_MAX_CONSEC})')
        return True
    finally:
        # 只要进入转发处理函数，所有退出路径都统一恢复详情页焦点。
        try:
            focus_x, focus_y = random_point_in_region(focus_restore_region)
            human_click(focus_x, focus_y, offset=0)
            human_delay(0.3, 0.5)
        except Exception as exc:
            logger.error(f'❌ 转发流程焦点恢复点击失败: {exc}')


# ─── 刷简历核心 ─────────────────────────────────────

def click_first_candidate(x, y):
    """在鼠标当前位置点击一次，打开第一位候选人详情"""
    if stop_event:
        return False
    logger.info(f'🖱️ 点击第一位候选人: ({x}, {y})')
    pyautogui.click(x, y, duration=0)
    return safe_wait(CLICK_WAIT_SECONDS)


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
    流程：检测关键词 → 命中则转发 → 停留 12-18 秒 + 滚动。
    """
    global forward_consecutive

    # OCR 扫描耗时计入原有 12-18 秒停留时间。
    stay = random.uniform(MIN_STAY_SECONDS, MAX_STAY_SECONDS)
    stay_started = time.monotonic()

    # ── 关键词检测（在浏览开始前） ──
    keyword_hit = False
    if forward_enabled and forward_keywords:
        keyword_hit = detect_keywords()

        if stop_event:
            return False

        if keyword_hit and no_forward_mode:
            logger.info('🛡 --no-forward 已启用：保留 OCR 命中记录，禁止真实邮件转发')
        elif keyword_hit:
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


def refresh_page():
    """按 F5 刷新页面"""
    if stop_event:
        return False
    logger.info('🔄 已查看 100 位，按 F5 刷新页面')
    pyautogui.press('f5')
    return safe_wait(REFRESH_WAIT_SECONDS)


# ─── 主循环 ─────────────────────────────────────────

def run():
    global stop_event, forward_consecutive, no_forward_mode
    stop_event = False
    reset_focus_restore_calibration()

    # ── 交互/参数输入 ──
    try:
        cli_args = parse_args()
        no_forward_mode = cli_args['no_forward']
        get_user_input(
            keywords_str=cli_args['keywords'],
            email_str=cli_args['email'],
            duration_str=cli_args['duration_seconds'],
            auto=cli_args['auto'],
            no_forward=no_forward_mode,
        )
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

    if not bring_edge_foreground():
        return 0

    run_timer = start_run_timer(run_duration_seconds)
    total_viewed = 0
    forward_consecutive = 0

    try:
        logger.info(f'\n请将鼠标移到第一位候选人卡片上，{COUNTDOWN_SECONDS} 秒后开始...')
        if not safe_wait(COUNTDOWN_SECONDS):
            return 0

        click_x, click_y = pyautogui.position()
        logger.info(f'📍 固定点击位置: ({click_x}, {click_y})')

        while not stop_event:
            # 打开第一位候选人
            if not click_first_candidate(click_x, click_y):
                break

            # 仅普通交互模式可请求；详情页可见后再显示框选层。
            if focus_restore_calibration_requested:
                ensure_focus_restore_region_calibrated()

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
