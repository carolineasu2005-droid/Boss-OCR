# TID-Action-Mode-Favorite-Forward

Change name: Add candidate `action_mode` with favorite / forward dispatch.

## 1. 背景

同事测试后发现，在部分 BossOCR 工作流中，点击 BOSS 页面内的“收藏”比执行邮件转发更简洁：收藏只需要一次区域点击；现有转发流程需要点击转发入口、切换邮件 Tab、选择或输入邮箱、检查输入框内容、点击确认转发，并处理弹窗和焦点恢复。

因此新增“收藏模式”作为轻量筛选模式；原有“转发模式”仍保留，适合作为重留存模式。两个模式必须互斥，避免同一候选人既收藏又转发，或两个动作都没有执行。

## 2. 目标

本次只设计以下能力：

- 在启动后、筛选规则输入前新增 `action_mode` 输入。
- 将用户输入 `1/2` 统一转换为 `"favorite"` / `"forward"`。
- 两种模式互斥：favorite 只收藏，forward 只转发。
- 新增收藏按钮区域字段和校准接入方案。
- 收藏模式在收藏按钮区域中间 60% 内随机落点点击。
- 收藏点击后等待 `0.5` 秒。
- 保留现有转发流程、邮箱输入/检测/确认流程和相关测试。

## 3. 非目标

本 Change 明确不做：

- 删除转发模式。
- 重构 `forward_one_candidate()` 或转发核心流程。
- OCR 自动识别“收藏”文字。
- 识别收藏按钮状态。
- 收藏 / 转发自动决策。
- 修改关键词筛选规则语法或输入逻辑本身。
- 修改“近 14 天没看过”自动筛选归位逻辑。
- 修改 WindMouse / HumanMouseMotion 参数。
- 修改 OCR 主流程、8 屏扫描或二次确认逻辑。
- 使用 DOM、JavaScript、浏览器注入、浏览器调试端口或接口请求。
- 新增网页反爬相关逻辑。
- 大规模重构或格式化全仓库。

## 4. 当前代码调查

主程序入口在 `simple_brush.py`：

- `run()` 是主入口，负责解析 CLI、调用交互输入、初始化 OCR、启动键盘监听、置前 Edge、打开首位候选人、运行批次循环和刷新。
- `parse_args()` 手写解析 `--keywords`、`--email`、`--duration-seconds`、`--no-forward`、`--no-batch-filter`、`--simple-mouse`、`--auto`。

筛选规则输入逻辑在 `simple_brush.py`：

- `get_user_input()` 的交互分支先提示“请输入触发转发的关键词规则...”，用 `parse_keyword_rules()` 解析规则。
- 当前需求的 action_mode 输入应插入到该交互分支的关键词规则输入之前。
- `--auto` 或传入 `--keywords` 时进入非交互分支，当前不会询问任何校准。

转发逻辑入口在 `simple_brush.py`：

- `view_candidate(index_in_batch)` 在每位候选人浏览开始时调用 `detect_keywords()`。
- 命中后如果 `no_forward_mode` 为 True，只记录 `--no-forward` 安全跳过；否则直接调用 `forward_one_candidate()`。
- `forward_one_candidate()` 是完整邮件转发函数，依次点击 `forward_click_regions.forward_icon`、`email_tab`、`recent_email`、`input_box`、`forward_button`，并在 `finally` 中通过 `focus_restore_region` 恢复焦点。

当前已有 `no-forward` 开关：

- CLI 参数名为 `--no-forward`，内部状态为 `no_forward_mode`。
- 该开关不是业务模式选择，只是“关键词命中后禁止真实转发”的安全门。
- 后续实现应保留 `--no-forward` 用于转发模式安全验证；不应把它扩展成 favorite/forward 的双负向控制。

坐标校准逻辑在 `simple_brush.py` 和 `ocr_calibration.py`：

- `ocr_calibration.ScreenRegion` 使用 `left/top/width/height`，并提供 `as_mss_monitor()`。
- `select_screen_region()` 用 Tk 半透明层拖框，返回 MSS 物理像素坐标。
- `enable_windows_dpi_awareness()` 在 Windows 下启用 DPI 感知，使 Tk 与 MSS 坐标一致。
- `ensure_ocr_region_calibrated()` 校准 OCR 正文区域并保存预览到 `logs/ocr_calibration_preview.png`。
- `ensure_batch_filter_regions_calibrated()` 运行期校准首位候选人、打开筛选、最近没看过、筛选确定四个区域。
- `ensure_forward_click_regions_calibrated()` 运行期校准转发入口、邮件 Tab、邮箱输入框、最近联系、转发按钮五个区域。
- `ensure_focus_restore_region_calibrated()` 运行期校准详情页焦点恢复区域。

MSS 截图逻辑在 `ocr_detector.py` 和 `ocr_calibration.py`：

- `ocr_detector.MSSScreenCapture.capture(region)` 使用 `mss.MSS().grab(region.as_mss_monitor())` 抓取屏幕区域，并转换为 NumPy BGR 数组。
- `ocr_calibration.save_region_preview()` 可复用 MSS 截图保存校准预览。

鼠标移动 / 点击封装在 `simple_brush.py` 和 `mouse_motion.py`：

- `click_in_region(region)` 从区域内随机选点，并调用 `human_click(..., offset=0, region_width=..., region_height=...)`。
- `human_click()` 调用 `human_move_to()`，再 `mouseDown` / `mouseUp`。
- `human_move_to()` 默认走 `mouse_motion.move_to_observable()`，WindMouse 不可用或异常时回退 `move_to_bezier_fallback()`。
- `mouse_motion.py` 保存 WindMouse 参数：`WINDMOUSE_SHORT_STABLE`、`WINDMOUSE_FAST_APPROACH`、`WINDMOUSE_STABLE_FINISH`。本 Change 不应修改这些参数。

配置文件保存 / 读取现状：

- 当前仓库没有独立配置文件读写模块，也未发现 JSON/TOML/YAML/INI 持久化配置。
- `README.md` 明确说明 OCR 区域、自动筛选归位区域、完整转发点击区域均为运行期校准，不写入配置文件或重启后需要重新框选。
- 因 PRD 提到收藏区域保存 `x/y/width/height`，实施阶段应优先按运行期校准 MVP 落地；如果确实需要跨重启复用，再新增最小 JSON 配置边界，具体文件名待实施阶段确认。

当前测试覆盖：

- `tests/test_simple_brush_ocr.py` 覆盖 `detect_keywords()` 不使用剪贴板、`--no-forward` 不调用真实转发、OCR 失败不转发、`forward_one_candidate()` 焦点恢复、转发区域校准顺序与失败回退、批量筛选校准、运行准备顺序、刷新后重新应用筛选、CLI 参数解析和交互关键词输入。
- `tests/test_mouse_motion.py` 覆盖贝塞尔 fallback、WindMouse 分支、WindMouse 异常回退、`human_click()` 目标点一致、`click_in_region()` 只选一次点并禁用二次偏移、批量筛选点击路径走 `human_click()`。
- `tests/test_ocr_calibration.py` 覆盖 `ScreenRegion` 反向拖框、最小尺寸、默认提示、Tk overlay 坐标到物理像素转换和主显示器偏移。
- `tests/test_ocr_detector.py` 覆盖 MSS/OCR 检测抽象、最多 8 屏扫描、二次确认、低置信度失败、组合规则和 not/any 规则确认。
- `tests/test_ocr_text.py` 覆盖关键词规则解析、标准化和匹配。

## 5. 设计方案

### 5.1 action_mode 输入设计

交互模式启动后，在关键词规则输入前提示：

```text
请选择候选人处理模式：
1 = 收藏模式：点击收藏，不转发邮箱
2 = 转发模式：执行原邮箱转发流程
请输入 1 或 2：
```

规则：

- 输入 `1` -> `action_mode = "favorite"`。
- 输入 `2` -> `action_mode = "forward"`。
- 非法输入重新提示，不进入候选人处理流程。
- 不允许静默默认进入某个模式。
- 模式选择发生在 `get_user_input()` 交互分支的关键词规则输入前。

建议新增纯函数和交互函数：

- `parse_action_mode_choice(raw)`：便于单元测试，返回 `"favorite"` 或 `"forward"`，非法值抛 `ValueError`。
- `prompt_action_mode()`：循环读取 `input()`，直到得到合法模式。

非交互路径明确如下：

- 新增 CLI 参数 `--action-mode favorite|forward`。
- 交互模式下必须提示用户输入 `1/2`，不允许默认。
- 非交互模式下，也就是 `--auto` 或传入 `--keywords` 的场景，如果显式传入 `--action-mode`，则按参数设置模式。
- 为兼容旧脚本，非交互模式未显式传 `--action-mode` 时默认 `forward`。
- 后续 README 需要说明：交互模式无默认；非交互旧脚本兼容默认 `forward`。

### 5.2 主流程分发设计

使用单一正向模式变量：

```python
if action_mode == "favorite":
    perform_favorite_action(...)
elif action_mode == "forward":
    perform_forward_action(...)
else:
    raise ValueError(...)
```

最小接入点在 `view_candidate()` 内的 `keyword_hit` 分支。当前逻辑是：

```python
if keyword_hit and no_forward_mode:
    ...
elif keyword_hit:
    forward_one_candidate()
```

建议调整为：

```python
if keyword_hit:
    if action_mode == ACTION_MODE_FAVORITE:
        perform_favorite_action()
    elif action_mode == ACTION_MODE_FORWARD:
        if no_forward_mode:
            logger.info(...)
        else:
            forward_one_candidate()
    else:
        raise ValueError(...)
```

不建议使用：

```python
no_forward = True
no_favorite = True
```

双负向开关有四种组合，容易出现两个都执行或两个都不执行。`action_mode` 只有两个合法值，状态空间更小，也更适合测试互斥性。

### 5.3 收藏区域配置设计

建议新增字段：

```json
{
  "favorite_button_region": {
    "x": 0,
    "y": 0,
    "width": 0,
    "height": 0
  },
  "favorite_sleep_seconds": 0.5
}
```

与当前代码的 `ScreenRegion(left, top, width, height)` 对齐时，代码内部建议转换为：

```python
ScreenRegion(
    left=config["favorite_button_region"]["x"],
    top=config["favorite_button_region"]["y"],
    width=config["favorite_button_region"]["width"],
    height=config["favorite_button_region"]["height"],
)
```

当前仓库没有持久化配置系统。本 Change 不设计复杂配置系统，优先复用现有运行期校准状态体系。第一阶段可以接受运行期校准 MVP：每次选择收藏模式且没有 `favorite_button_region` 时，通过 `select_screen_region()` 校准并保存在当前进程内存中。

如果实施阶段决定做持久化，只允许新增最小 JSON 配置边界，例如 `bossocr_config.json` 或 `config/bossocr.json`，提供少量读写函数保存 `favorite_button_region`。不要引入复杂配置管理、模板解析、迁移框架或平行配置体系。该最小 JSON 边界未来应可迁移到后续“校准模板”体系，避免和校准模板需求冲突。

### 5.4 收藏点击设计

收藏点击应：

- 读取 `favorite_button_region`。
- 在中间 60% 区域随机落点。
- 使用现有 `human_click()` / WindMouse 路径。
- 点击后 `time.sleep(0.5)`。

伪代码：

```python
inner_x_min = region.left + region.width * 0.2
inner_x_max = region.left + region.width * 0.8
inner_y_min = region.top + region.height * 0.2
inner_y_max = region.top + region.height * 0.8

click_x = random.uniform(inner_x_min, inner_x_max)
click_y = random.uniform(inner_y_min, inner_y_max)

human_click(
    click_x,
    click_y,
    offset=0,
    region_width=region.width,
    region_height=region.height,
)
time.sleep(0.5)
```

不要直接复用 `click_in_region()`，因为它当前在全区域半开区间内随机，不满足“中间 60%”要求。可以新增 `random_point_in_inner_region(region, ratio=0.6)`，并让收藏动作专用。

### 5.5 收藏按钮校准设计

要求：

- 复用 `select_screen_region()`，不新造截图坐标体系。
- 校准结果保存到新增配置。
- 选择收藏模式且没有有效 `favorite_button_region` 时，提示并引导校准，不能静默失败。
- 校准说明应提示：调用校准模板前，请确保 Boss 页面窗口位置、大小、缩放状态与校准时基本一致。

最小必须新增：

- `favorite_button_region`
- `ensure_favorite_button_region_calibrated()`
- `perform_favorite_action()`

`reset_favorite_button_calibration()` 可选，仅当实现中确实需要和 `run()` 的启动状态重置保持一致时再新增。不要无必要新增 `requested`、`attempted`、`in_progress` 等多个全局状态；以现有代码风格和最小可用状态为准，避免继续扩大 `simple_brush.py` 的全局状态复杂度。

如果采用运行期 MVP，校准取消或失败时应安全停止收藏动作或禁用本次收藏模式，不应继续盲点收藏。如果采用最小 JSON 持久化，保存失败也应安全失败并提示用户。

### 5.6 转发模式兼容设计

- 转发模式仍调用现有 `forward_one_candidate()`。
- 不修改邮箱检测、剪贴板读取、备选邮箱输入、确认转发、焦点恢复流程。
- `--no-forward` 保留为转发模式安全门：`action_mode == "forward"` 且命中关键词时，如果 `no_forward_mode` 为 True，不调用 `forward_one_candidate()`。
- favorite 模式不应触发 `ensure_forward_click_regions_calibrated()`，不应要求备选邮箱，不应调用 `forward_one_candidate()`。
- 原有测试应继续通过；新增测试只覆盖模式输入、收藏动作和互斥分发。

## 6. 实施步骤

### Change 1：代码调查与字段确认

- 文件：`simple_brush.py`、`ocr_calibration.py`、`README.md`、`tests/`。
- 内容：确认现有区域字段是 `ScreenRegion.left/top/width/height`，确认当前无持久化配置读写，确认主流程插入点是 `get_user_input()` 和 `view_candidate()`。
- 预期行为：不改代码。
- 测试方式：无。

### Change 2：新增 action_mode 输入与校验

- 文件：`simple_brush.py`、`tests/test_simple_brush_ocr.py`。
- 内容：新增 `ACTION_MODE_FAVORITE`、`ACTION_MODE_FORWARD`、`action_mode` 状态、`parse_action_mode_choice()`、`prompt_action_mode()`；`parse_args()` 新增 `--action-mode favorite|forward`；在 `get_user_input()` 交互关键词输入前调用。
- 预期行为：交互模式必须先选择模式；非法输入重试。非交互模式显式 `--action-mode` 生效；非交互未传时为兼容旧脚本默认 `forward`。
- 测试：`parse_action_mode_choice("1") == "favorite"`、`parse_action_mode_choice("2") == "forward"`、非法值抛错或重试；CLI `--action-mode favorite|forward` 解析；`--auto` / `--keywords` 未传 `--action-mode` 默认 `forward`。

### Change 3：新增收藏按钮区域配置和校准接入

- 文件：`simple_brush.py`，可选新增极小 JSON 配置边界；测试放在 `tests/test_simple_brush_ocr.py`，如新增配置文件再加对应配置测试。
- 内容：最小新增 `favorite_button_region` 和 `ensure_favorite_button_region_calibrated()`，复用 `select_screen_region()`。第一阶段优先运行期校准 MVP；如做持久化，仅保存 `favorite_button_region` 到最小 JSON 配置。
- 预期行为：favorite 模式启动准备阶段能获得有效收藏按钮区域；无区域且校准取消时安全停止或禁用收藏动作；不新增复杂配置系统。
- 测试：缺失区域触发校准；校准结果转换为 `ScreenRegion`；取消校准不会静默点击；如有 JSON 持久化，测试保存后读取。

### Change 4：新增收藏动作函数

- 文件：`simple_brush.py`、`tests/test_mouse_motion.py` 或 `tests/test_simple_brush_ocr.py`。
- 内容：新增 `random_point_in_inner_region()` 和 `perform_favorite_action()`；落点在中间 60%；调用 `human_click(..., offset=0, region_width=..., region_height=...)`；点击后 `time.sleep(0.5)`。
- 预期行为：收藏动作只点击收藏按钮区域，不进入转发弹窗。
- 测试：随机点边界；`human_click` 参数；sleep 参数。

### Change 5：主流程 action_mode 分发

- 文件：`simple_brush.py`、`tests/test_simple_brush_ocr.py`。
- 内容：在 `view_candidate()` 的关键词命中分支中按 `action_mode` 分发；favorite 调 `perform_favorite_action()`；forward 保留原 `--no-forward` 和 `forward_one_candidate()` 行为。
- 预期行为：favorite 不调用转发；forward 不调用收藏；候选人遍历、停留、滚动、刷新逻辑不变。
- 测试：favorite 模式不会调用 `forward_one_candidate()`；forward 模式不会调用 `perform_favorite_action()`；`--no-forward` 在 forward 模式仍拦截真实转发。

### Change 6：回归测试与验收

- 文件：`README.md` 可在实现后补充使用说明；本 Change 的 TID 阶段不修改。
- 内容：运行全量 unittest；人工验证 Windows 收藏/转发流程。macOS 目前 README 标注尚未完成，Mac 验收需待适配环境确认。
- 预期行为：原有转发、筛选、OCR、鼠标测试不回归。
- 测试：`venv\Scripts\python.exe -m unittest discover -s tests -v`。

## 7. 测试计划

单元测试：

- `parse_action_mode_choice("1") == "favorite"`。
- `parse_action_mode_choice("2") == "forward"`。
- 非法输入会重新提示或抛出可控错误。
- 收藏随机点击点位于区域中间 60%。
- 缺失收藏区域配置时不会静默点击。
- favorite 模式不会调用 `forward_one_candidate()`。
- forward 模式不会调用 `perform_favorite_action()`。
- forward + `--no-forward` 命中关键词时仍不会调用 `forward_one_candidate()`。
- `perform_favorite_action()` 调用现有 `human_click()`，并 `sleep(0.5)`。

集成 / 手动测试：

- Windows 收藏模式跑 3-5 位候选人，确认只点击收藏。
- Windows 转发模式保持原行为。
- Mac 收藏模式跑 3-5 位候选人：待实施阶段确认，因为 README 当前限制写明 macOS Chrome 适配尚未完成。
- Mac 转发模式保持原行为：同上，待实施阶段确认。
- 移动浏览器窗口或改变缩放后，说明需要重新校准。
- 校准后重启程序仍能读取收藏区域。
- 使用 `--no-forward` 验证 forward 模式不真实转发。

## 8. 验收标准

1. 程序启动后，先选择 `action_mode`，再输入筛选规则。
2. 输入 `1` 进入收藏模式。
3. 输入 `2` 进入转发模式。
4. 非法输入不会进入候选人处理流程。
5. 收藏模式下只点击收藏，不转发。
6. 转发模式下只转发，不收藏。
7. 收藏点击落点在收藏按钮区域中间 60%。
8. 收藏后等待 `0.5` 秒。
9. 未校准收藏按钮区域时，收藏模式会提示校准。
10. 原有转发流程不回归。
11. 原有近 14 天没看过筛选不回归。
12. 原有鼠标轨迹参数不变化。

## 9. 风险与缓解

坐标体系风险：MSS 截图坐标与鼠标点击坐标不一致。

- 缓解：复用 `ScreenRegion`、`select_screen_region()`、`enable_windows_dpi_awareness()`、`human_click()` 的现有路径，不另建坐标换算。

浏览器窗口 / 缩放变化风险：

- 缓解：配置保存的是绝对屏幕区域；提示用户窗口位置、大小、系统缩放、浏览器缩放变化后需要重新校准。

配置字段命名混乱风险：

- 缓解：外部配置使用 `favorite_button_region.x/y/width/height`，内部统一转换为 `ScreenRegion.left/top/width/height`；配置读写集中在一个边界函数中。

双模式误执行风险：

- 缓解：只使用单一 `action_mode`；为 favorite/forward 互斥分发补测试。

转发模式回归风险：

- 缓解：不重构 `forward_one_candidate()`；只在 `view_candidate()` 命中后的调用点外层加分发；保留现有 `--no-forward` 测试并补 forward 模式回归测试。

持久化配置新增风险：

- 缓解：配置模块保持小而独立；读取失败不静默使用空区域；写入失败不继续盲点收藏。

## 10. 回滚方案

- 如收藏模式异常，可临时只选择转发模式。
- `action_mode` 分支应允许禁用 favorite，例如隐藏交互选项或让 favorite 校准失败时安全退出。
- 不删除旧转发逻辑，因此回滚成本低。
- 可以通过移除或跳过 favorite 分支恢复旧行为。
- 如果配置持久化引发问题，可先回滚为运行期校准，不影响 `forward_one_candidate()`。

## 11. 建议修改文件清单

`simple_brush.py`

- 为什么改：主入口、交互输入、模式分发、收藏动作和运行期校准状态都集中在此。
- 改哪些函数：`parse_args()` 新增 `--action-mode favorite|forward`、`get_user_input()`、`run()`、`view_candidate()`；新增 `parse_action_mode_choice()`、`prompt_action_mode()`、`perform_favorite_action()`、`ensure_favorite_button_region_calibrated()`；`reset_favorite_button_calibration()` 仅在确有需要时可选新增。
- 是否需要新增测试：需要。
- 风险：中。该文件是主流程核心，但改动可局限在输入和命中后分发。

`ocr_calibration.py`

- 为什么改：原则上不需要改；收藏校准可直接复用 `select_screen_region()`。
- 改哪些函数：无。
- 是否需要新增测试：如不改文件，无需新增。
- 风险：低。避免改动坐标核心。

`mouse_motion.py`

- 为什么改：不应修改。
- 改哪些函数：无。
- 是否需要新增测试：无需修改现有 WindMouse 参数测试。
- 风险：高风险区域，明确禁止改动参数。

可选新增最小 JSON 配置边界，例如 `app_config.py` 或 `bossocr_config.py`

- 为什么改：仅当实施阶段决定做持久化时使用；当前仓库无配置读写模块，第一阶段也可接受运行期校准 MVP。
- 改哪些函数：最多新增 `load_app_config()`、`save_app_config()`、`get_favorite_button_region()`、`set_favorite_button_region()`。
- 是否需要新增测试：需要，覆盖缺失文件、字段缺失、无效尺寸、保存后读取。
- 风险：中。新增持久化边界必须保持最小，未来可迁移到“校准模板”体系，不能扩展成复杂配置系统。

`tests/test_simple_brush_ocr.py`

- 为什么改：已有主流程、交互、转发、校准测试集中在此。
- 改哪些测试：新增 action_mode 输入、favorite/forward 互斥分发、缺失收藏区域安全失败、forward + `--no-forward` 保持原行为。
- 风险：低。

`tests/test_mouse_motion.py`

- 为什么改：已有 `click_in_region()` 和 `human_click()` 路径测试。
- 改哪些测试：可新增收藏内 60% 随机点和 `perform_favorite_action()` 走 `human_click()` 的测试；也可放在 `test_simple_brush_ocr.py`。
- 风险：低。

`README.md`

- 为什么改：实现完成后需要更新用户流程、action_mode 提示、收藏校准说明，以及非交互模式兼容行为。
- 改哪些内容：运行步骤、命令行用法、`--action-mode favorite|forward`、交互模式无默认、非交互旧脚本默认 `forward`、工作原理、当前限制。
- 是否需要新增测试：文档无需单测。
- 风险：低。本轮 TID 不修改。

## 12. Codex 执行边界

- 本轮只生成 TID。
- 不直接修改代码。
- 不运行破坏性命令。
- 不 commit。
- 不格式化全仓库。
- 不做无关重构。
- 对不确定点标记“待实施阶段确认”，不在 TID 阶段强行决定。

推荐实施顺序：

1. 先加 `action_mode` 解析和交互输入测试。
2. 再加非交互 `--action-mode` 与旧脚本默认 `forward` 兼容测试。
3. 再加收藏区域运行期校准 MVP，必要时才加最小 JSON 读写边界。
4. 再加收藏动作函数和中间 60% 落点测试。
5. 最后在 `view_candidate()` 接入 favorite/forward 互斥分发。
6. 跑全量测试，并做 Windows 小样本手动验收。
