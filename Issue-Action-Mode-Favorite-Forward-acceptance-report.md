# Issue-Action-Mode-Favorite-Forward Acceptance Report

## 1. 验收结论

结论：通过。

建议：可以进入人工冒烟测试。

- action_mode 的 CLI、交互启动、非交互默认 forward、favorite / forward 主流程分发均已接入。
- 单元测试和全量回归测试通过。
- 未发现阻塞问题。
- 建议 commit，但建议将 action_mode 相关文件与当前工作区内 WindMouse / 构建配置等其它改动拆分确认，避免混入无关变更。

## 2. 实施范围回顾

本次实际实现了以下内容：

- 新增 `action_mode = favorite / forward`。
- 交互模式启动后先选择 `1 = 收藏模式` 或 `2 = 转发模式`。
- 非交互模式新增 `--action-mode favorite|forward`。
- 非交互旧脚本未传 `--action-mode` 时默认 `forward`，兼容旧脚本。
- 收藏模式使用运行期校准的收藏按钮区域。
- 收藏点击点落在区域中间 60%。
- 收藏点击后等待 `0.5` 秒。
- 转发模式保持原有流程。
- `--no-forward` 在 forward 模式下继续作为安全门。
- 本轮不做 JSON 持久化，重启后允许重新校准收藏按钮区域。
- Change 7 补齐了入口接入：`parse_args()`、`get_user_input()`、`run()` 已贯通 action_mode。

## 3. 非目标确认

- 没有删除转发模式。
- 没有重构 `forward_one_candidate()`。
- 没有修改 WindMouse / HumanMouseMotion 参数。
- 没有修改近 14 天没看过筛选逻辑。
- 没有修改 OCR 主流程。
- 没有使用 DOM / JS / 浏览器注入。
- 没有新增复杂配置系统。
- 没有实现收藏按钮 OCR 自动识别。
- 没有实现收藏按钮状态识别。
- 没有实现跨重启持久化收藏区域。
- 没有新增 JSON 配置边界。

注意：当前工作区同时存在 WindMouse 相关改动，包括 `mouse_motion.py`、`tests/test_mouse_motion.py`、`requirements.txt`、`BossOCR.spec` 等。这些不是本 action_mode Issue 的核心验收对象，提交前建议单独确认归属。

## 4. 修改文件清单

- `simple_brush.py`
  - 新增 action_mode 常量、解析、交互输入、CLI 参数、非交互默认 forward、收藏校准、收藏动作、`view_candidate()` 分发，以及 `run()` 入口贯通。
  - 风险：中。原因：涉及主流程入口和关键词命中后的分发，但未重构转发核心逻辑。

- `tests/test_simple_brush_ocr.py`
  - 新增 action_mode 解析、交互输入、CLI 参数、非交互默认 forward、run 贯通、收藏校准、收藏点击、favorite/forward 分发、`--no-forward` 回归相关测试。
  - 风险：低。原因：测试覆盖增加，原有相关测试继续通过。

- `README.md`
  - 新增 action_mode、交互模式选择、非交互 `--action-mode`、旧脚本默认 forward、收藏运行期校准、无跨重启持久化、收藏模式不触发邮箱流程、转发模式保持原行为等说明。
  - 风险：低。原因：当前代码入口已与 README 描述匹配。

- `TID-Action-Mode-Favorite-Forward.md`
  - 记录实施设计、范围、运行期校准 MVP、风险和验收标准。
  - 风险：低。文档文件。

当前工作区另有非本 Issue 核心文件改动或未跟踪文件，提交前应单独确认：`.gitignore`、`BossOCR.spec`、`requirements.txt`、`tests/test_mouse_motion.py`、`Issue-Next-7-windmouse-observable-motion-acceptance-report.md`、`docs/`、`mouse_motion.py`。

## 5. 关键实现核对

### 5.1 action_mode 输入

- `parse_action_mode_choice("1") == "favorite"`：已实现并有测试。
- `parse_action_mode_choice("2") == "forward"`：已实现并有测试。
- 非法输入会被拒绝：已实现；纯解析抛 `ValueError`，交互提示会要求重新输入。
- 交互模式不允许默认：已实现；`prompt_action_mode()` 必须输入 `1` 或 `2`。
- action_mode 输入发生在关键词规则输入之前：已实现并有测试覆盖。

### 5.2 CLI 行为

- `--action-mode favorite` 生效：已实现并有测试。
- `--action-mode forward` 生效：已实现并有测试。
- 非交互模式未传 `--action-mode` 时默认 `forward`：已实现并有测试。
- 旧脚本兼容：已保持；`--auto` 或 `--keywords` 未传 action_mode 时继续走 forward。
- 非法 `--action-mode` 会被拒绝或安全失败：已实现；非法值抛 `ValueError`，`run()` 返回错误码 `2`。

### 5.3 收藏按钮校准

- 收藏模式下需要收藏按钮区域：已实现；缺失时不会盲点。
- 缺失区域时触发运行期校准：`ensure_favorite_button_region_calibrated()` 已实现并有测试。
- 校准复用现有 `select_screen_region()` / `ScreenRegion`：已实现。
- 用户取消校准时不会继续盲点：已实现，返回 `None` 并清空 `favorite_button_region`。
- 本轮不要求重启后复用收藏区域：已满足，没有 JSON 或其它持久化。

### 5.4 收藏动作

- 收藏点击点位于区域中间 60%：已实现并有测试。
- 使用现有 `human_click()` / 鼠标轨迹能力：已实现。
- `offset=0`：已实现并有测试。
- 点击后 `sleep(0.5)`：已实现并有测试。
- 收藏模式不会调用转发函数：已实现并有测试。

### 5.5 转发兼容

- forward 模式仍走原有 `forward_one_candidate()`：已实现并有测试。
- `--no-forward` 在 forward 模式下仍然阻止真实转发：已实现并有测试。
- favorite 模式不触发邮箱输入、邮箱检测、转发确认：已实现；交互 favorite 模式不询问邮箱，分发层不调用转发函数。
- favorite 模式不要求转发区域校准：已实现；交互 favorite 模式不触发转发区域校准。
- 原有转发测试通过：全量测试通过。

### 5.6 主流程分发

- 关键词命中 + favorite：只调用 `perform_favorite_action()`。
- 关键词命中 + forward：调用 `forward_one_candidate()`，或在 `no_forward_mode=True` 时只记录跳过。
- 关键词未命中：不收藏、不转发，原有重置连续转发计数行为保留。
- 候选人遍历、滚动、刷新、近 14 天没看过筛选不受影响；相关测试通过。

## 6. 测试结果

测试命令：

- `.\venv\Scripts\python.exe -m unittest tests.test_simple_brush_ocr -v`
- `.\venv\Scripts\python.exe -m unittest discover -s tests -v`
- `git diff --check -- simple_brush.py tests\test_simple_brush_ocr.py`

结果：

- `tests.test_simple_brush_ocr`：通过
- 总测试数：112
- 失败数：0
- 错误数：0
- 跳过数：0

- 全量回归：通过
- 总测试数：202
- 失败数：0
- 错误数：0
- 跳过数：0

- `git diff --check`：未报告空白错误；仅出现 Windows 工作区 LF/CRLF 转换 warning。

## 7. 新增 / 修改测试覆盖

已覆盖：

- action_mode 解析。
- action_mode 交互输入。
- CLI `--action-mode favorite`。
- CLI `--action-mode forward`。
- CLI 非法 `--action-mode` 不会被静默忽略。
- 非交互默认 forward。
- `run()` 将 CLI action_mode 传入输入配置层。
- 交互模式先调用 `prompt_action_mode()`，再输入关键词规则。
- 交互选择 `1` 后最终 action_mode 为 favorite。
- 交互选择 `2` 后最终 action_mode 为 forward。
- favorite 交互模式不询问邮箱、不触发转发区域校准。
- 收藏区域校准。
- 收藏点击中间 60%。
- 收藏后 `sleep(0.5)`。
- favorite 不调用 forward。
- forward 不调用 favorite。
- forward + `--no-forward` 行为。
- 原有转发回归。

## 8. 人工冒烟测试建议

### 8.1 收藏模式冒烟

1. 启动程序：`.\venv\Scripts\python.exe simple_brush.py`。
2. 选择 `1 = 收藏模式`。
3. 输入关键词规则，例如 `"Python"`。
4. 校准收藏按钮区域；框选按钮内部安全区域。
5. 运行 3-5 位候选人。
6. 确认命中关键词时只点击收藏。
7. 确认不打开转发弹窗。
8. 确认不会要求邮箱。
9. 确认收藏后继续下一位候选人。

### 8.2 转发模式冒烟

1. 启动程序：`.\venv\Scripts\python.exe simple_brush.py`。
2. 选择 `2 = 转发模式`。
3. 输入关键词规则和邮箱。
4. 校准转发相关区域。
5. 使用安全邮箱或 `--no-forward` 测试。
6. 确认原有转发流程不回归。

### 8.3 非交互模式冒烟

至少覆盖：

- `.\venv\Scripts\python.exe simple_brush.py --keywords '"Python"' --action-mode favorite --auto`
- `.\venv\Scripts\python.exe simple_brush.py --keywords '"Python"' --action-mode forward --no-forward --auto`
- `.\venv\Scripts\python.exe simple_brush.py --keywords '"Python"' --no-forward --auto`

第三条不传 `--action-mode`，应默认 forward 并兼容旧脚本。

## 9. 风险与残留问题

- 风险：收藏区域是运行期校准，重启后需要重新校准。
  - 等级：低。
  - 当前缓解方式：README 和实现均按运行期 MVP 处理，不写持久化配置。
  - 是否阻塞本次验收：不阻塞。

- 风险：浏览器窗口位置、大小、缩放变化后需要重新校准。
  - 等级：中。
  - 当前缓解方式：校准说明提示保持 Boss 页面窗口位置、大小、缩放状态基本一致。
  - 是否阻塞本次验收：不阻塞，但需要人工冒烟确认。

- 风险：MSS 坐标与点击坐标仍需人工冒烟确认。
  - 等级：中。
  - 当前缓解方式：复用现有 `select_screen_region()` / `ScreenRegion` / `human_click()` 坐标体系。
  - 是否阻塞本次验收：不阻塞自动测试，发布前建议实机验证。

- 风险：favorite 模式需要确认不会误点相邻按钮。
  - 等级：中。
  - 当前缓解方式：点击点限制在用户框选区域中间 60%，缺失区域时不点击。
  - 是否阻塞本次验收：不阻塞代码验收，需要人工冒烟。

- 风险：Mac 行为未实测。
  - 等级：中。
  - 当前缓解方式：当前验收以 Windows 为主；Mac 标记待验证。
  - 是否阻塞本次验收：不阻塞 Windows 验收。

- 风险：当前工作区混有 WindMouse / 构建配置等其它改动。
  - 等级：中。
  - 当前缓解方式：提交前拆分或人工确认文件归属。
  - 是否阻塞本次验收：不阻塞 action_mode 功能验收，但影响 commit 范围判断。

## 10. 回滚方案

- 如果收藏模式异常，临时选择 forward 模式。
- 非交互脚本不传 `--action-mode` 默认 forward。
- 可隐藏 favorite 入口或暂不选择 favorite 模式。
- 因未删除转发逻辑，回滚成本低。
- 如需代码回滚，涉及文件：
  - `simple_brush.py`
  - `tests/test_simple_brush_ocr.py`
  - `README.md`
  - `TID-Action-Mode-Favorite-Forward.md`
  - `Issue-Action-Mode-Favorite-Forward-acceptance-report.md`

## 11. Git 状态

当前分支：

```text
main
```

`git status --short`：

```text
 M .gitignore
 M BossOCR.spec
 M README.md
 M requirements.txt
 M simple_brush.py
 M tests/test_mouse_motion.py
 M tests/test_simple_brush_ocr.py
?? Issue-Next-7-windmouse-observable-motion-acceptance-report.md
?? docs/
?? mouse_motion.py
```

是否有未跟踪文件：

- 有：`Issue-Next-7-windmouse-observable-motion-acceptance-report.md`、`docs/`、`mouse_motion.py`。

是否有不应提交的文件：

- 需要人工确认。`docs/`、`Issue-Next-7-windmouse-observable-motion-acceptance-report.md`、`mouse_motion.py`、`BossOCR.spec`、`requirements.txt`、`tests/test_mouse_motion.py` 看起来与 WindMouse / 其它事项相关，不应默认混入 action_mode 单独提交。

建议 commit 的文件清单：

- action_mode 相关建议提交：
  - `simple_brush.py`
  - `tests/test_simple_brush_ocr.py`
  - `README.md`
  - `TID-Action-Mode-Favorite-Forward.md`
  - `Issue-Action-Mode-Favorite-Forward-acceptance-report.md`

建议 commit message：

```text
Add favorite/forward action mode dispatch
```

## 12. 最终建议

- 是否建议人工冒烟：建议，当前已可进入 Windows 人工冒烟测试。
- 是否建议 commit：建议，但先确认是否要把 WindMouse / 构建配置改动拆成独立提交。
- 是否建议先修复某些问题：action_mode 范围内没有阻塞修复项。
- 下一步最小行动：按第 8 节执行 Windows 收藏模式、转发模式和非交互模式冒烟；冒烟通过后提交 action_mode 相关文件。
