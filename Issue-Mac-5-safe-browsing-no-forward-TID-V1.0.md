# Mac Change 5：macOS 安全浏览闭环：只浏览不转发 TID V1.0

## 0. 文档信息与核心安全口径

- 分支：`mac-chrome-port`
- 文档类型：Technical Implementation Design（TID）
- 本文性质：只做设计，不实施代码，不运行真实 BOSS 页面，不触发 GUI、截图、OCR 或转发
- 前置状态：Mac Change 1–4 已完成并 push；macOS 页面身份、坐标诊断和校准 metadata 已具备，但真实设备与真实页面链路尚未验收
- 核心口径：Change 5 只建立“受控浏览、不转发”的独立实验入口，不把普通 macOS 业务流程设为 ready

本文中的 `ready_for_browse=True` 只表示某一次受限人工验收可以开始，不等同于：

- `BrowserPrepareResult.ready=True`；
- `CoordinateCalibrationMetadata.business_ready=True`；
- 完整 BossOCR 业务可用；
- 可以发送邮件、自动打招呼或无限自动浏览。

任何门禁、页面、坐标、焦点、权限、计数器或中止能力不明确时，都必须 fail closed。

## 1. Change 5 目标

Change 5 只解决 macOS Chrome 上的“只浏览、不转发”安全闭环：

1. 由用户手工打开目标页面，程序只读确认当前 active tab 是受允许的 BOSS 页面；程序不主动打开 BOSS URL。
2. 在逐阶段、显式确认和严格限额下，允许进入真实 BOSS 页面的人工验收。
3. 校准浏览闭环必要的 OCR 区域，并绑定显示器 fingerprint、scale、Tk-to-screenshot mapping 和人工 preview 确认。
4. 在动作预算内打开并观察极少量候选人。
5. 使用 OCR 进行只读检测；OCR 结果只记录，不触发邮件转发或其他写操作。
6. 滚动、下一位和刷新仅能由独立开关逐项放行，并统一计数、限额和中止。
7. 在入口、配置、调度和转发函数边界多层强制禁用邮件转发。
8. 页面身份、焦点、权限、坐标、OCR、动作预算或运行时限任一失败时立即停止。
9. 为后续 Change 6 邮件转发迁移提供经过验收的浏览前置链路。

Change 5 不是完整业务版，不允许转发，不允许自动打招呼，不允许规避平台风控、验证码、访问频率限制或其他安全边界。

## 2. 非目标

本 Change 明确不做：

- 不发送邮件；
- 不点击“转发牛人”、邮件 Tab 或转发按钮；
- 不输入、粘贴或读取邮箱；
- 不打开或校准邮件转发弹窗；
- 不自动打招呼或发送聊天消息；
- 不修改关键词 parser / matcher；
- 不修改 Next-5 批次筛选业务；
- 不修改 Next-6 鼠标轨迹；
- 不实现反检测、验证码绕过或风控规避；
- 不打包，不 release，不合并 `main`，不创建 tag。

## 3. 当前代码调研

### 3.1 Windows 当前浏览与转发流程

`simple_brush.run()` 的普通流程为：

1. 解析参数并收集关键词、邮箱、运行时间和校准选择；
2. 有关键词时提前初始化 RapidOCR 和 MSS capture；
3. 启动全局 `keyboard.Listener`，以 Esc 停止、空格暂停；
4. 调用 `prepare_browser()`；Windows 路径将 Edge 置前，成功后返回 `ready=True`；
5. 可选校准和执行“最近没看过”批次筛选，或读取当前鼠标位置并点击首位候选人；
6. 在首位详情页完成焦点恢复、转发区域和 OCR 区域校准；
7. 每位候选人执行 OCR、停留和随机滚动，右方向键进入下一位；
8. 每批 `BATCH_SIZE=100` 人后按 F5 刷新，并继续下一批；
9. OCR 二次确认命中且未启用 no-forward 时调用 `forward_one_candidate()`。

Change 5 必须从这条 Windows 业务链路旁边建立 macOS 专用入口，不得改变 Windows 的 Edge 准备、校准、OCR、浏览、鼠标轨迹或转发行为。

### 3.2 `--no-forward` 的真实含义

当前 `--no-forward` 设置全局 `no_forward_mode=True`。当 OCR 命中时，`view_candidate()` 记录命中并跳过 `forward_one_candidate()`。它不是 dry-run：

- 仍可初始化 OCR 和 MSS capture；
- 仍可弹出 Tk 框选并保存校准 preview；
- 仍会打开首位候选人；
- OCR detector 从第二次扫描开始仍可调用 `ocr_scroll_down()`；
- 候选人停留期间仍可调用 `human_scroll_once()`；
- 仍会按右方向键进入下一位；
- 每 100 人仍会按 F5 刷新；
- 批次筛选未禁用时仍会点击筛选控件。

因此普通 `--auto --no-forward` 只是“自动运行但不调用真实转发”，不是 macOS 安全浏览入口。

### 3.3 当前真实输入与页面动作

当前会产生真实动作的主要函数包括：

| 类型 | 主要函数 | 当前动作 |
| --- | --- | --- |
| 首位打开 | `click_first_candidate()`、`open_first_candidate_for_batch()` | `pyautogui.click()` 或区域点击 |
| 批次筛选 | `apply_batch_filter_and_open_first_candidate()` | 多次区域点击 |
| 鼠标区域操作 | `human_click()`、`click_in_region()` | 移动、按下和释放鼠标 |
| 浏览滚动 | `human_scroll_once()` | `pyautogui.scroll()` |
| OCR 翻屏 | `ocr_scroll_down()` | `pyautogui.scroll()` |
| 下一位 | `next_candidate()` | `pyautogui.press('right')` |
| 刷新 | `refresh_page()` | `pyautogui.press('f5')` |
| 转发 | `forward_one_candidate()` | 点击、热键、读取剪贴板、输入邮箱和提交 |
| 校准收尾 | 转发/筛选校准 helper | 可能按 Esc 关闭弹窗 |

Change 5 的动作计数不能只包住主循环；OCR 内部滚动、焦点恢复和辅助关闭动作也必须纳入统一策略。safe browse 模式不得调用任何转发校准或转发 helper。

### 3.4 OCR 校准与 detector

`ensure_ocr_region_calibrated()` 当前会：

1. 调用 `initialize_ocr()` 创建 `RapidOCRBackend` 和 `MSSScreenCapture`；
2. 调用 `select_screen_region()` 弹出主显示器 Tk overlay；
3. 调用 `save_region_preview()` 抓取并保存校准区域；
4. 可选附加 `CoordinateCalibrationMetadata`；
5. 创建 `OCRKeywordDetector`，并注入 `ocr_scroll_down()` 和 `ocr_wait()`；
6. detector 与校准区域在构造全部成功后原子发布。

`OCRKeywordDetector.detect()` 每屏截图后执行识别；命中时再次截图确认。若首屏未命中且 `max_scans>1`，会先调用滚动回调再扫描下一屏。故 Change 5 的“只读 OCR”首阶段应使用单屏、无 scroll callback 的专用配置；不能把现有多屏 detector 直接称为无动作只读检测。

### 3.5 macOS `prepare_browser()` 仍 fail closed

macOS `prepare_browser()` 当前依次执行 Chrome 路径解析、`about:blank` 安全启动、权限 baseline、Chrome activate/frontmost、active tab URL/title 查询和 BOSS allowlist 判断。

- 页面不允许时返回 `MACOS_PAGE_NOT_ALLOWED`；
- 页面允许时返回 `MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY`；
- 两种情况均为 `ready=False`。

普通 `run()` 在 `ready=False` 时退出，所以 macOS 目前不会进入候选人业务循环。Change 5 不应把这一返回值改成 `True`，而应在独立 safe browse 入口中建立更严格的新 guard。

另一个实现风险是：当前 macOS prepare 会启动 `about:blank`，可能使用户手工准备的目标标签页不再是 active tab。后续实现应分成“安全 baseline”与“用户手工打开目标页后的再次只读核验”，不得由程序主动导航到真实 BOSS URL，也不得把 about:blank 启动结果误当目标页面状态。

### 3.6 coordinate metadata 边界

Change 4 已提供：

- `RetinaScaleInference`；
- `TkToScreenshotMapping`；
- `CropPreviewResult`；
- `CoordinateCalibrationMetadata`；
- `CalibratedScreenRegion`。

`validated=True` 只说明 display fingerprint、scale inference 和 crop mapping 结构有效；`manually_confirmed=True` 还要求 preview 已保存并由用户显式确认。`business_ready` 不可由调用方设置，恒为 `False`。

Change 4 验收报告同时明确：尚未完成真实 BOSS 页面、真实截图、真实 Tk overlay、真实 OCR 和真实设备矩阵验收。因此 Change 5 应要求 `validated=True` 且 `manually_confirmed=True`；仅 warning 不足以放行任何真实点击或 OCR。

### 3.7 现有独立诊断出口

- `--preflight-only` 只做浏览器、权限、焦点和页面身份诊断并退出；
- `--coordinate-diagnostics-only` 只读收集坐标元数据并退出；
- 两者都不应被 Change 5 参数组合改变，也不得落入 safe browse 或普通业务循环。

## 4. 风险边界

### 4.1 no-forward 不等于 dry-run

即使没有邮件发送，打开候选人、筛选、滚动、下一位和刷新仍是对真实页面的自动操作。safe browse 必须在日志和确认文案中避免使用“无副作用”或“dry-run”。

### 4.2 BOSS 页面与平台风控

自动浏览可能触发访问频率、行为模式、账号或企业侧限制。Change 5 必须采用极小候选人数、极短运行时间、默认关闭刷新和筛选，不实现任何隐藏自动化、伪装轨迹、验证码处理或重试轰炸。出现验证码、登录异常、访问限制或页面警告时立即停止并转人工处理。

### 4.3 坐标和 OCR 错位

结构化 scale/mapping 单测通过不等于真实设备正确。旧 metadata 若显示布局、缩放、主屏、Space、窗口位置或 Chrome UI 比例改变，必须作废。黑屏、空图、明显纯色图、越界 crop、preview 未确认或 fingerprint 不一致均不得继续 OCR 或点击。

### 4.4 页面身份不等于业务状态

allowlist 只验证 scheme、host 和路径前缀，不能证明：

- 用户已登录正确账号；
- 当前是预期候选人列表或详情布局；
- 没有弹窗、验证码、遮罩或风控页面；
- 当前 Profile、窗口和标签页归属正确；
- 控件坐标仍匹配。

safe browse guard 必须在动作前重新读取 active tab，并对目标页面类型、窗口/Profile 歧义和页面状态做额外 fail-closed 检查。

### 4.5 权限与焦点

屏幕录制权限不足可能产生异常、黑图或空图；辅助功能不足可能导致输入失败；输入监控不足可能使 Esc Listener 无法工作。任何按键前必须确认 Chrome frontmost。焦点恢复失败后禁止继续按右键或 F5，避免输入落到 IDE、终端或其他应用。

### 4.6 多显示器、多窗口和多 Profile

初始实现只允许校准、Chrome 目标窗口和 OCR 区域完整处于一个已确认显示器。检测到负坐标、跨屏、fingerprint 变化、多 Chrome 窗口或 Profile 归属不明时，不做猜测，直接停止。

### 4.7 页面状态变化

打开候选人、下一位和刷新可能改变 URL、active tab、选中候选人和列表位置。每次真实动作前后都要检查焦点；导航类动作完成后还要重新检查页面身份。刷新失败、URL 离开 allowlist、active tab 改变或页面未稳定时立即停止。

### 4.8 数量和时长

候选人数与运行时长必须同时存在，任何一个缺失都 fail closed。阶段 3 首次人工验收固定最多 1 位候选人、建议最多 5 分钟；不得以“持续运行”或 `0` 表示无限。后续即使扩大，也应保留审计过的硬上限，建议候选人数绝对上限 5、运行时间绝对上限 15 分钟。

## 5. 推荐安全开关设计

### 5.1 独立入口

新增 macOS 专用参数：

```text
--mac-safe-browse-only
--no-forward
--max-candidates N
--max-runtime-minutes N
```

推荐规则：

1. 仅 `sys.platform == 'darwin'` 接受该入口；其他平台拒绝，Windows 原流程不变。
2. 必须显式同时传入 `--no-forward`。入口内部还应把 forwarding capability 固定为 false；“强制”不能仅依赖用户参数。
3. `max_candidates` 和 `max_runtime_minutes` 必填、为正整数且不超过经测试的硬上限。
4. `--auto` 与该入口互斥，因为 safe browse 必须人工确认目标窗口、页面和动作预算。
5. `--preflight-only`、`--coordinate-diagnostics-only` 与该入口互斥，并保留原独立出口语义。
6. 初始默认：`allow_filter=False`、`allow_refresh=False`、`allow_next_candidate=False`、`allow_scroll=False`；每项按人工验收阶段显式放行。
7. 启动和结束时都输出醒目日志：`MAC SAFE BROWSE ONLY — NO FORWARDING ENABLED`，同时输出候选人数、时限和各动作预算。

不能复用普通 `--auto --no-forward`，因为它会跳过交互，可能使用默认/旧坐标，允许旧的 100 人循环、滚动、右键翻页、F5 刷新及批次筛选，而且没有 macOS 页面、coordinate metadata、动作预算和人工确认 guard。

### 5.2 前置 guard

safe browse 只有同时满足以下条件才可返回 `ready_for_browse=True`：

- macOS 专用模式已显式启用；
- no-forward 已由配置和运行态双重锁定；
- 用户未提供邮箱，转发区域未校准，转发能力对象未创建；
- 最大候选人数和最大时长有效；
- Chrome 已 frontmost，且窗口/Profile 唯一性可确认；
- active tab 当前 URL `page_allowed=True`，并且是本阶段预期路径；
- coordinate metadata 存在、`validated=True`；
- crop preview 对当前 display fingerprint 有效，且 `manually_confirmed=True`；
- 用户在终端中显式确认当前页面、候选人数、时长、允许动作和“绝不转发”；
- 中止机制可用；若 Listener 启动失败则不进入真实动作。

建议人工确认是强制条件，而不是 warning。确认只对本次运行、当前 display fingerprint、当前页面和当前预算有效，不能缓存到下次运行。

### 5.3 Listener 策略

`keyboard.Listener` 只能在纯 guard 通过后、首个真实动作前启动。启动异常必须停止。初始阶段同时保留终端 `Ctrl+C` 作为第二中止路径；不能把 Listener 未验证解释为可继续。Listener 不应在 preflight、coordinate diagnostics 或 guard 失败时启动。

### 5.4 转发硬禁用

建议至少四层防线：

1. CLI 要求 `--no-forward`；
2. safe config 中 `no_forward_required=True`，运行态 `forward_enabled=False`、邮箱为空；
3. safe browse 调度器没有到 `forward_one_candidate()`、转发校准和邮箱输入 helper 的引用路径；
4. 转发函数入口检测 safe browse 状态后抛出专用阻断错误并记录审计日志。

测试必须对所有转发相关函数做负向断言。仅在 `view_candidate()` 中检查 `no_forward_mode` 不足以形成硬隔离。

### 5.5 动作预算

动作计数器至少区分：

- `candidate_open`；
- `scroll`；
- `next_candidate`；
- `refresh`；
- `filter_click`；
- `focus_restore`；
- `ocr_capture`。

每次动作必须先预留预算，执行成功后提交计数；失败或结果不明时立即停止，不能自动重试。初次阶段 3 建议预算：打开 1 次、浏览滚动最多 2 次、下一位最多 1 次、刷新 0 次、筛选 0 次。若“下一位一次”会使第二位候选人实际显示，统计口径必须记录为一次导航动作，但不得继续扫描第二位。

## 6. 推荐实现边界

1. 新增 `run_mac_safe_browse_only()`，在普通 macOS `run()` 业务分支之前独立处理并退出。
2. 不修改 Windows 普通流程，不让普通 macOS `run()` 因 Change 5 自动进入业务。
3. 保持 macOS `prepare_browser().ready=False`；safe browse guard 读取诊断事实，但建立独立的 `ready_for_browse` 语义。
4. 程序不主动导航到 BOSS。用户手工打开页面后，guard 重新检查 Chrome focus、URL/title 和本阶段路径。
5. 首阶段不启用批次筛选，不使用旧默认坐标，不使用 `--auto`。
6. 只有 guard 通过后才初始化 OCR、启动 Listener 或创建 Tk overlay。
7. OCR 单屏、无滚动起步；其结果只输出观察记录，不触发转发或其他业务分支。
8. 真实点击、滚动和按键只能通过统一的受控 action executor；禁止 safe browse 直接调用未包裹的 PyAutoGUI 输入函数。
9. 每次导航动作前后复核 frontmost 和页面身份；显示 fingerprint 变化则使校准失效。
10. 所有异常均停止，不自动扩大预算、不降级使用旧坐标、不回退到普通业务流程。

## 7. 建议数据结构与 helper

以下仅为设计，不在本轮实现。

### 7.1 `MacSafeBrowseConfig`

```python
@dataclass(frozen=True)
class MacSafeBrowseConfig:
    enabled: bool
    no_forward_required: bool
    max_candidates: int | None
    max_runtime_minutes: int | None
    require_page_allowed: bool
    require_coordinate_validated: bool
    require_manual_confirmation: bool
    allow_scroll: bool
    allow_next_candidate: bool
    allow_refresh: bool
    allow_filter: bool
    message: str = ''
```

建议补充不可由 CLI 任意放大的内部硬上限和各动作预算；CLI 值只能在硬上限以内收紧。

### 7.2 `MacSafeBrowseGuard`

```python
@dataclass(frozen=True)
class MacSafeBrowseGuard:
    passed: bool
    ready_for_browse: bool
    no_forward_enforced: bool
    page_allowed: bool
    coordinate_validated: bool
    manual_confirmed: bool
    message: str
    error_code: str | None = None
```

`ready_for_browse` 仅用于 safe browse 调度器，不能写回 `BrowserPrepareResult.ready` 或 coordinate `business_ready`。

建议错误码包括：

- `MAC_SAFE_BROWSE_DISABLED`
- `MAC_SAFE_BROWSE_NO_FORWARD_REQUIRED`
- `MAC_SAFE_BROWSE_LIMIT_INVALID`
- `MAC_SAFE_BROWSE_PAGE_NOT_ALLOWED`
- `MAC_SAFE_BROWSE_PAGE_STATE_AMBIGUOUS`
- `MAC_SAFE_BROWSE_COORDINATE_NOT_VALIDATED`
- `MAC_SAFE_BROWSE_PREVIEW_NOT_CONFIRMED`
- `MAC_SAFE_BROWSE_MANUAL_CONFIRMATION_REQUIRED`
- `MAC_SAFE_BROWSE_LISTENER_UNAVAILABLE`
- `MAC_SAFE_BROWSE_ACTION_LIMIT_REACHED`
- `MAC_SAFE_BROWSE_RUNTIME_LIMIT_REACHED`
- `MAC_SAFE_BROWSE_FOCUS_LOST`
- `MAC_SAFE_BROWSE_PAGE_CHANGED`
- `MAC_SAFE_BROWSE_FORWARDING_BLOCKED`

### 7.3 helper 职责

- `validate_mac_safe_browse_guard()`：纯函数校验配置、页面与 coordinate evidence；不初始化 OCR、不启动 Listener、不产生输入。
- `run_mac_safe_browse_only()`：独立编排人工确认、guard、受限 OCR 和动作循环；始终不进入普通转发流程。
- `disable_forwarding_actions_in_safe_browse()`：建立运行态硬锁，并让转发入口显式拒绝调用。
- `count_and_limit_browser_actions()`：统一动作授权、计数、时限和停止原因。
- `revalidate_mac_safe_browse_context()`：动作前后复核 frontmost、active tab、页面类型和 display fingerprint。
- `run_read_only_ocr_probe()`：单屏、无滚动、结果不驱动业务动作的 OCR 探针。

## 8. 推荐实施拆分

- **5A：TID 与安全开关设计**——本文；只定义边界。
- **5B：macOS safe browse guard 纯函数与测试**——只做配置、页面、metadata、人工确认和错误码判断，不产生真实动作。
- **5C：CLI 参数与强制 no-forward / limit 校验**——新增独立入口和参数互斥，仍不执行真实浏览。
- **5D：只读 OCR 区域与 coordinate metadata 前置检查**——先使用合成图和 mock；真实验收固定单屏、无滚动。
- **5E：受控浏览动作计数器与硬停止**——所有输入动作统一经过预算和上下文复核，默认仍关闭。
- **5F：人工安全冒烟**——按第 10 节三阶段执行真实 BOSS 页面，只浏览、不转发。
- **5G：验收报告**——记录设备、权限、显示布局、Chrome/Profile、预算、动作计数、停止原因和未放行能力。

每一步单独验收；前一步失败时不得以“先试一下真实页面”绕过。

## 9. 测试计划

以下均为设计，本轮不新增测试。

1. Windows `prepare_browser()`、普通 `run()`、OCR、鼠标轨迹和转发行为保持不变。
2. 普通 macOS `run()` 仍因 `ready=False` 不进入业务。
3. `--mac-safe-browse-only` 只能在 macOS 使用，并必须强制 no-forward。
4. 未显式传入 `--no-forward` 时 fail closed，且不调用 OCR、Listener 或输入 API。
5. `max_candidates` 缺失、为 0、负数、非整数或超过硬上限时 fail closed。
6. `max_runtime_minutes` 缺失、为 0、负数、非整数或超过硬上限时 fail closed。
7. `page_allowed=False` 或页面路径不符合当前阶段时 fail closed。
8. coordinate metadata 缺失、fingerprint 不匹配或 `validated=False` 时 fail closed。
9. `manually_confirmed=False` 时必须 fail closed；本设计不采用 warning 放行。
10. `forward_one_candidate()`、转发区域校准、邮箱输入、剪贴板邮箱读取和提交函数在 safe browse 模式均禁止调用。
11. RapidOCR/MSS 初始化只在 guard 和人工确认全部通过后发生。
12. `keyboard.Listener` 只在 guard 通过后启动；启动失败立即停止，preflight/diagnostics/guard fail 均不启动。
13. 点击、滚动、右方向键、F5、筛选、焦点恢复和 OCR capture 分类型计数。
14. 超过动作、候选人数或运行时限时，在下一动作前硬停止。
15. 刷新默认禁止；显式允许后，执行失败或页面未稳定必须停止。
16. Chrome 非 frontmost、焦点恢复失败或前后应用不一致时停止，且不发送后续按键。
17. active tab URL 变为 about:blank、非 BOSS、未允许路径或查询失败时停止。
18. 多窗口、多 Profile、目标窗口归属或显示器归属不明时停止。
19. `--preflight-only` 行为与输出边界保持不变，不进入 safe browse。
20. `--coordinate-diagnostics-only` 行为与输出边界保持不变，不截图、不进入 safe browse。
21. 邮件转发路径所有函数做负向断言；即使 OCR 命中也只记录，不创建转发事件。
22. 现有 `tests.test_browser_prepare`、`tests.test_mouse_motion` 和 `tests.test_simple_brush_ocr` 全部通过。

补充建议测试：

- `--auto` 与 safe browse 互斥；
- 单屏 OCR 不注入 scroll callback；
- display fingerprint 在运行中改变会使 calibration 失效；
- 动作执行结果不明时计为失败并停止，而不是重试；
- 日志明确包含 no-forward、预算、动作计数和停止原因，但不记录截图内容或候选人敏感文本。

## 10. 人工验收计划

人工验收前必须确认：使用测试/获授权账号与环境，遵守平台规则；关闭不相关 Chrome 窗口和 Profile；准备独立日志目录；邮件转发入口在代码层和配置层均被禁用。任何阶段都禁止自动打招呼和转发。

### 10.1 阶段 1：无真实候选人动作

| 场景 | 允许动作 | 预期输出 | 停止条件 | 是否进入下一阶段 |
| --- | --- | --- | --- | --- |
| `about:blank` | 只读 focus/tab 查询 | `page_allowed=False`，guard fail | 出现任何截图或输入立即停止 | 不能 |
| 非 BOSS 页面 | 只读页面身份查询 | `MAC_SAFE_BROWSE_PAGE_NOT_ALLOWED` | 同上 | 不能 |
| BOSS 页面未登录 | 只读身份与页面状态观察 | 标记未登录，guard fail | 登录弹窗、验证码或歧义 | 不能；用户手工处理登录 |
| 已登录但非目标 path | 只读身份与阶段路径检查 | allowlist 可为 true，但阶段 guard fail | 页面状态不明确 | 不能 |

阶段 1 禁止 Tk overlay、截图、OCR、点击、滚动、按键、刷新和转发。只有四个场景都按预期 fail closed，且用户已手工准备目标页面，才可进入阶段 2。

### 10.2 阶段 2：真实目标页面只读观察

允许动作：

- 用户手工打开目标页面；
- 程序只读确认 frontmost、URL/title 和显示 fingerprint；
- 创建一次 Tk 校准 overlay；
- 对明确框选的小区域保存本地 crop preview；
- 用户确认 preview 后执行一次单屏 OCR；
- 不滚动。

禁止动作：打开候选人、下一位、刷新、筛选、转发、邮箱输入和自动重试。

预期输出：

- page allowed 与预期路径通过；
- coordinate metadata `validated=True`、`manually_confirmed=True`；
- `business_ready=False` 保持不变；
- OCR capture/识别次数可计数，scroll/点击/按键计数均为 0；
- 日志明确 `NO FORWARDING ENABLED`。

出现黑屏、空图、错位 preview、fingerprint 变化、OCR 异常、页面变化、权限提示或焦点丢失时立即停止。只有人工确认裁剪正确、单屏 OCR 可解释且所有禁止动作计数为 0，才可进入阶段 3。

### 10.3 阶段 3：极小浏览闭环

固定限制：

- `max_candidates=1`；
- `max_runtime_minutes<=5`；
- 允许打开候选人 1 次；
- 允许少量滚动，建议最多 2 次；
- 可在单独子场景允许下一位 1 次，用于验证导航后立即停止；
- 刷新和筛选仍保持关闭；
- 转发预算恒为 0。

每次动作前必须确认 Chrome frontmost、页面仍允许且预算充足；导航后重新读取页面身份。OCR 只记录，不驱动转发。达到一位候选人、一次下一位、任一动作上限、5 分钟或任何异常时立即停止。

预期输出包含：页面与 display fingerprint、人工确认状态、每类动作计数、候选人数、已用时、停止原因和 no-forward 硬锁状态。只有所有真实动作均在预算内、可中止、无转发路径调用，才可判定 Change 5 浏览闭环人工验收通过；这仍不能放行 Change 6。

## 11. 风险分析

### 11.1 BOSS 风控

真实自动浏览可能影响账号或触发限制。通过极小预算、默认禁用刷新/筛选、不重试、不规避验证码和人工分阶段验收降低风险，但不能消除平台侧风险。

### 11.2 真实点击与坐标错位

点击可能落在错误候选人、按钮、弹窗或其他应用。必须依赖当前 display fingerprint、人工 preview、单显示器限制、动作前焦点检查和最小动作预算；任何不确定性都停止。

### 11.3 OCR 误判

OCR 可能因错位、遮挡、缩放、低置信度或页面变化产生误判。Change 5 中识别结果不得触发写操作；即使“命中”也只能用于日志和人工观察。

### 11.4 页面状态变化

SPA 路由、弹窗、登录过期、候选人切换和刷新均可能改变布局。URL allowlist 不能替代页面状态检查，导航后必须重新验证。

### 11.5 焦点丢失

右方向键和 F5 若落入终端、IDE 或其他应用会产生意外输入。frontmost 查询失败、焦点恢复失败或窗口变化后禁止继续。

### 11.6 多窗口与多 Profile

AppleScript 返回的 active tab 不证明业务账号归属。初始验收应只保留一个 Chrome 窗口和明确 Profile；无法证明唯一性时 fail closed。

### 11.7 转发路径误触

单一 `no_forward_mode` 判断可能被未来重构绕过。必须采用 CLI、运行态能力、调度器无引用、函数入口阻断和测试负向断言的多层隔离。

### 11.8 长时间自动浏览

持续运行会扩大风控、误操作和数据暴露影响。候选人数与时间双硬限制都不可缺失，且 safe browse 禁止无限值。

### 11.9 用户误解

名称、日志和验收报告必须持续写明“实验性，只浏览、不转发，不是完整业务版”。Change 5 通过也不意味着邮件转发可用，更不应自动令普通 macOS `ready=True`。

### 11.10 隐私与本地诊断文件

真实页面 crop preview 和 OCR 文本可能包含个人信息。仅保存最小裁剪、本地存储、不上传、不提交 Git；验收后按明确保留策略清理。日志避免记录完整简历文本、邮箱和截图内容。

## 12. 验收结论格式

- **是否建议实施 Change 5**：有条件建议，必须按 5B–5G 小步实施并逐步人工放行，不建议一次性接入现有 100 人循环。
- **推荐模型**：GPT-5.5。
- **推荐复杂度**：High。
- **是否允许真实 BOSS 页面**：仅在 5F 分阶段人工验收中，由用户手工打开已授权目标页面；程序不得主动导航。
- **是否允许真实点击**：前两阶段禁止；阶段 3 在 guard 全通过后最多允许预算内的候选人打开动作。
- **是否允许滚动**：阶段 1/2 禁止；阶段 3 显式开关且少量计数。
- **是否允许 OCR**：阶段 2 起允许单屏、只读、人工确认区域的受控 OCR；不得驱动业务动作。
- **是否允许转发**：不允许，所有邮件转发能力必须硬禁用，预算恒为 0。
- **推荐下一步最小 Change**：Mac Change 5B——只实现 `MacSafeBrowseConfig`、`MacSafeBrowseGuard` 和 `validate_mac_safe_browse_guard()` 纯函数及 mock 单测，不接入 CLI、OCR、Listener 或真实 GUI 动作。

Change 5 验收通过后的最高结论只能是：macOS 在特定设备、显示配置、页面和严格预算下完成了“只浏览、不转发”的受控闭环。它不改变 `business_ready=False` 的历史证据，也不直接放行 Change 6 邮件转发。
