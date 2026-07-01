# -*- coding: utf-8 -*-
"""
BOSS 直聘推荐牛人自动刷简历 v4 —— 键盘翻页 + 智能邮件转发版

交互方案：
1. 启动时输入触发关键词（多个用 ; 分隔）和备选邮箱
2. 鼠标保持不动，脚本只执行一次左键点击打开第一位候选人
3. 后续全部用键盘右方向键（→）切换下一位候选人
4. 每位候选人详情页停留 12-18 秒（随机），期间随机滚动
5. 停留期间检测详情页内容，命中任意关键词则触发邮件转发
6. 转发完成后右键恢复键盘焦点，继续用右方向键翻页
7. 每 100 人自动 F5 刷新
8. ESC 停止 / 空格暂停
"""
import sys
import io
import os
import time
import random
import logging
from pathlib import Path
import win32gui
import win32con
import win32clipboard
import pyautogui
from pynput import keyboard

from ocr_calibration import (
    CalibrationCancelled,
    enable_windows_dpi_awareness,
    save_region_preview,
    select_screen_region,
)
from ocr_detector import MSSScreenCapture, OCRKeywordDetector, RapidOCRBackend

# ─── 命令行参数解析 ───────────────────────────────
def parse_args():
    """解析命令行参数"""
    args = {'keywords': '', 'email': '', 'no_forward': False, 'auto': False}
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == '--keywords' and i + 1 < len(sys.argv):
            args['keywords'] = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == '--email' and i + 1 < len(sys.argv):
            args['email'] = sys.argv[i + 1]
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
OCR_SCROLL_MIN_STEPS = 5
OCR_SCROLL_MAX_STEPS = 7
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
# 详情页中央（邮件转发完成后用于恢复键盘焦点）
# 注意：必须在右侧详情弹窗区域内（左列表区结束于 x≈800）
DETAIL_CENTER_X  = 1200
DETAIL_CENTER_Y  = 500

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

# 转发状态（全局）
forward_keywords = []       # 启动时输入的关键词列表
backup_email = ""           # 备选邮箱
forward_enabled = False     # 是否启用转发
forward_consecutive = 0     # 连续转发计数
no_forward_mode = False     # 只检测，不执行真实邮件转发

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
        if ocr_calibration_in_progress:
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
def get_user_input(keywords_str='', email_str='', auto=False, no_forward=False):
    """
    获取关键词和备选邮箱。
    auto=True 或 keywords 已传入时跳过交互。
    """
    global forward_keywords, backup_email, forward_enabled

    # ── 非交互模式（命令行传参或 --auto） ──
    if auto or keywords_str:
        if keywords_str:
            forward_keywords = [k.strip() for k in keywords_str.split(';') if k.strip()]
            forward_enabled = True
        else:
            forward_keywords = []
            forward_enabled = False
        backup_email = email_str
        print()
        print(f'  关键词: {forward_keywords if forward_keywords else "(无，转发已禁用)"}')
        print(f'  备选邮箱: {backup_email if backup_email else "(未设置)"}')
        print()
        return

    # ── 交互模式 ──
    print()
    raw = input('请输入触发转发的关键词（多个用 ; 分隔，留空跳过转发）:\n> ').strip()
    if raw:
        forward_keywords = [k.strip() for k in raw.split(';') if k.strip()]
        forward_enabled = True
        print(f'  已录入 {len(forward_keywords)} 个关键词: {forward_keywords}')
    else:
        forward_keywords = []
        forward_enabled = False
        print('  未设置关键词，转发功能已禁用')

    if forward_enabled and not no_forward:
        backup_email = input('\n请输入备选邮箱（最近联系中无邮箱时兜底）:\n> ').strip()
        print(f'  备选邮箱: {backup_email if backup_email else "(未设置)"}')
    else:
        backup_email = ""

    print()


# ─── 窗口操作 ───────────────────────────────────────
def bring_edge_foreground():
    """将 BOSS 直聘 Edge 窗口置顶"""
    result = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if 'BOSS' in title or 'zhipin' in title:
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
    """Scroll down roughly half to two-thirds of the visible detail region."""
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

    logger.info(f'🔍 OCR 关键词检测中... 目标: {forward_keywords}')
    result = ocr_detector.detect(forward_keywords)
    for sequence, observation in enumerate(result.observations, start=1):
        phase = '二次确认' if sequence > 1 and (
            observation.scan_number == result.observations[sequence - 2].scan_number
        ) else '扫描'
        logger.info(
            '  OCR %s: 屏=%s 耗时=%.3fs 文字框=%s 命中=%s 关键词=%s',
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
        logger.info(f'🔑 OCR 二次确认命中: "{result.matched_keyword}"')
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

    # ── 检查连续转发上限 ──
    if forward_consecutive >= FORWARD_MAX_CONSEC:
        logger.warning(f'⚠ 连续转发已达上限 ({FORWARD_MAX_CONSEC} 次)，本次跳过')
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
    pyautogui.hotkey('ctrl', 'a')
    time.sleep(0.05)
    pyautogui.hotkey('ctrl', 'c')
    time.sleep(0.08)
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
            pyautogui.hotkey('ctrl', 'a')
            time.sleep(0.05)
            pyautogui.press('delete')
            time.sleep(0.05)
            type_text_human(backup_email)
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
    logger.info(f'  [4/5] 点击"转发"按钮')
    human_click(FORWARD_BTN_X, FORWARD_BTN_Y)
    if not human_delay(1.0, 2.0):
        return False

    forward_consecutive += 1
    logger.info(f'📧 ✓ 转发完成！(连续转发 {forward_consecutive}/{FORWARD_MAX_CONSEC})')

    # 点击详情页中央，恢复焦点，确保右键翻页正常
    human_click(DETAIL_CENTER_X, DETAIL_CENTER_Y, offset=3)
    if not human_delay(0.3, 0.5):
        return False
    return True


# ─── 刷简历核心 ─────────────────────────────────────

def click_first_candidate(x, y):
    """在鼠标当前位置点击一次，打开第一位候选人详情"""
    logger.info(f'🖱️ 点击第一位候选人: ({x}, {y})')
    pyautogui.click(x, y, duration=0)
    return safe_wait(CLICK_WAIT_SECONDS)


def human_scroll_once():
    """严格鼠标不动，仅在当前位置触发小幅度滚轮。"""
    if random.random() > SCROLL_PROBABILITY:
        return

    times = random.randint(1, SCROLL_MAX_TIMES)
    direction = random.choice([-1, 1])

    logger.info(f'🖱️ 滚动 {times} 次，方向 {"下" if direction == -1 else "上"}')

    for _ in range(times):
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
    logger.info('🔄 已查看 100 位，按 F5 刷新页面')
    pyautogui.press('f5')
    return safe_wait(REFRESH_WAIT_SECONDS)


# ─── 主循环 ─────────────────────────────────────────

def run():
    global stop_event, forward_consecutive, no_forward_mode

    # ── 交互/参数输入 ──
    cli_args = parse_args()
    no_forward_mode = cli_args['no_forward']
    get_user_input(keywords_str=cli_args['keywords'], email_str=cli_args['email'],
                   auto=cli_args['auto'], no_forward=no_forward_mode)

    # 提前初始化并复用 OCR 引擎；校准仍延迟到第一位详情打开之后。
    if forward_enabled and forward_keywords:
        initialize_ocr()

    # ── 启动键盘监听（必须在交互输入之后，避免 exe 中 input() 冲突） ──
    listener.start()

    logger.info('\n' + '=' * 50)
    logger.info('BOSS 直聘极简刷简历 v4 启动')
    logger.info(f'停留: {MIN_STAY_SECONDS}-{MAX_STAY_SECONDS}s | 每 {BATCH_SIZE} 人刷新')
    if forward_enabled:
        logger.info(f'转发关键词: {forward_keywords}')
        if no_forward_mode:
            logger.info('模式: 只执行 OCR 检测，真实邮件转发已禁用 (--no-forward)')
        else:
            logger.info(f'备选邮箱: {backup_email}')
            logger.info(f'连续转发上限: {FORWARD_MAX_CONSEC}')
    else:
        logger.info('转发: 已禁用')
    logger.info('=' * 50)

    if not bring_edge_foreground():
        return

    logger.info(f'\n请将鼠标移到第一位候选人卡片上，{COUNTDOWN_SECONDS} 秒后开始...')
    if not safe_wait(COUNTDOWN_SECONDS):
        return

    click_x, click_y = pyautogui.position()
    logger.info(f'📍 固定点击位置: ({click_x}, {click_y})')

    total_viewed = 0
    forward_consecutive = 0

    try:
        while not stop_event:
            # 打开第一位候选人
            if not click_first_candidate(click_x, click_y):
                break

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
        logger.info(f'\n🏁 停止运行。累计查看 {total_viewed} 位候选人。')
        logger.info(f'日志文件: logs/simple_brush.log\n')


if __name__ == '__main__':
    try:
        run()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event = True
        listener.stop()
