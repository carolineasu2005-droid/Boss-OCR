# Mac Change 3：Chrome 窗口置前与页面身份识别 TID V1.0

## 1. 文档信息

- 分支：`mac-chrome-port`
- 文档类型：Technical Implementation Design（TID）
- 本文范围：定义 macOS Chrome 窗口置前、前台应用确认、活动标签页只读身份识别与 fail-closed 安全边界
- 本文不实施代码，不启动真实 BOSS 导航，不进入真实业务流程
- 保持约束：不修改 `simple_brush.py`、不修改测试、不修改 `README.md`、不 commit、不 push

## 2. Change 3 目标

Mac Change 3 只解决以下问题：

1. macOS Chrome 是否可被安全找到。
2. Chrome 是否可被安全置前。
3. 当前前台窗口是否属于 Chrome。
4. 当前页面是否是允许继续的目标页面。
5. 页面身份无法确认时是否严格 fail closed。
6. 为后续 Retina 坐标迁移与真实浏览闭环提供前置安全边界。

边界说明：

- Change 3 的“允许继续”仅表示页面身份满足后续更深一层验证的前置条件。
- 即使识别到允许页面，也不代表已经允许真实点击、滚动、按键、刷新、OCR 扫描或邮件转发。

## 3. 非目标

本 Change 明确不做：

- 不点击真实 BOSS 页面。
- 不滚动。
- 不按方向键。
- 不刷新。
- 不做 OCR 真实扫描。
- 不做 Tk 区域校准迁移。
- 不做 Retina 坐标适配。
- 不做邮件转发。
- 不修改关键词 parser / matcher。
- 不修改 Next-5 批次筛选。
- 不修改 Next-6 鼠标轨迹。
- 不打包。
- 不 release。
- 不合并 `main`。

## 4. 当前代码调研

### 4.1 当前 `prepare_browser()` 行为

根据 `simple_brush.py` 当前实现，`prepare_browser()` 已经是平台无关入口：

1. Windows：
   - 调用现有 `bring_edge_foreground()`。
   - 成功时返回 `BrowserPrepareResult(ready=True, platform='windows', browser='edge')`。
   - 失败时返回结构化 fail-closed 结果，错误码为 `EDGE_PREPARE_FAILED`。
2. macOS：
   - 先调用 `resolve_chrome_executable()` 校验固定路径 `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`。
   - 再调用 `launch_chrome_safe_target()`，只允许参数数组启动 `about:blank`。
   - 然后调用 `check_macos_permissions()`，当前仅返回无副作用的 baseline 诊断。
   - 无论权限是 `unknown` 还是全部 `ok`，当前都不会把 macOS 标记为可进入业务；最终仍返回 `ready=False`。
3. 其他平台：
   - 返回 `UNSUPPORTED_PLATFORM`，严格 fail closed。

### 4.2 当前 `BrowserPrepareResult` 字段

当前 `BrowserPrepareResult` 已包含：

- `ready`
- `platform`
- `browser`
- `launched`
- `executable_path`
- `message`
- `error_code`

这个结构已经足够表达“浏览器准备层”的结果，但它还没有承载“页面身份层”的专门字段。

### 4.3 当前 macOS 为什么 `ready=False`

当前 macOS `ready=False` 是有意设计，不是缺陷：

1. Chrome 只被允许启动到 `about:blank`。
2. 当前未实现 Chrome 窗口置前。
3. 当前未确认前台应用是否真的是 Chrome。
4. 当前未确认当前页面是否属于允许继续的目标页面。
5. 当前未完成 Retina 坐标迁移。
6. 当前未完成真实 OCR、真实浏览与真实业务动作的安全闭环。

因此，即使 Chrome 启动成功、权限全为 `ok`，代码仍返回 `MACOS_BROWSER_STARTED_NOT_READY`，并明确提示“窗口和页面尚未验证为可操作”。

### 4.4 当前 `--preflight-only` 的独立出口

`parse_args()` 已支持 `--preflight-only`。`run()` 在解析参数后若发现该标志，会直接走 `run_preflight_only()` 并退出。

当前 `run_preflight_only()` 的契约是：

- 调用 `prepare_browser()`；
- 打印结构化结果；
- 输出一条明确 note，说明 preflight 不验证窗口置前、页面身份、Retina 坐标、校准和真实业务安全；
- 直接返回，不启动 OCR、校准、点击、滚动、按键、刷新、转发或业务主循环。

这条独立出口已经被 `tests/test_browser_prepare.py` 通过负向断言保护。

### 4.5 Windows Edge 行为必须保持不变

当前 Windows 路径依旧依赖：

- `bring_edge_foreground()`
- Edge 既有窗口识别
- 既有执行顺序：OCR 初始化、键盘监听、浏览器准备、后续业务动作

`tests/test_browser_prepare.py` 已明确覆盖：

- Windows 成功分支仍应 `ready=True`
- Windows 失败分支仍应 fail closed
- Windows 不得调用 macOS Chrome 路径解析、`subprocess.Popen()` 或 macOS 权限检查
- 既有运行顺序不得回归

因此 Change 3 只能在 macOS 分支新增能力，不得改变 Windows Edge 逻辑、返回语义或调用顺序。

## 5. 技术方案候选

### 5.1 方案 A：AppleScript / `osascript`

能力设想：

- `tell application "Google Chrome" to activate`
- 读取 `frontmost` 应用
- 读取 Chrome 当前活动窗口的活动 tab URL
- 读取当前 tab title

优点：

- 系统自带，无需新增 Python 重依赖。
- 与“激活应用 + 读取活动 tab 元数据”目标天然贴近。
- 更容易做到“只读查询”，不必引入窗口遍历与坐标层复杂性。
- 适合做最小实现，便于严格 fail closed。

风险：

- 依赖 Automation / Apple Events 权限，首次调用可能被系统拦截或弹授权。
- Chrome 未启动、多窗口、多 Profile、无活动窗口时，返回行为需要小心规范。
- `osascript` 错误字符串需要做稳定映射，便于测试和错误码设计。

### 5.2 方案 B：PyObjC / Quartz / AppKit

能力设想：

- 通过 Quartz 查询窗口列表。
- 识别 Google Chrome 窗口。
- 判断 frontmost app。
- 用 AppKit / NSWorkspace 获取当前前台应用。

优点：

- 可以更细粒度处理窗口枚举、窗口层级和 frontmost app。
- 对后续 Retina / 窗口几何信息可能更有帮助。

风险：

- 需要新增 PyObjC / Quartz / AppKit 相关依赖或更重的平台耦合。
- 仅凭窗口 API 不一定能稳定拿到“活动标签页 URL / title”，仍可能回到 AppleScript 或其他桥接。
- 权限、依赖、打包与单测复杂度明显更高。
- 对当前“只做安全前置边界”的目标而言过重。

### 5.3 方案 C：保守混合方案

思路：

- 用 AppleScript / `osascript` 完成 Chrome `activate`、frontmost 判断、active tab URL/title 读取。
- 用现有 Python 结构封装结果、错误码与 fail-closed 语义。
- 不引入 PyObjC 重依赖。
- 所有读取失败、权限失败、状态不明都返回不可继续。

优点：

- 最贴近当前 Change 3 的最小边界。
- 代码接入点清晰，可直接挂到现有 `prepare_browser()` 或其后续辅助层。
- 与 Change 2 的结构化结果、mock 测试风格一致。
- 后续若 Change 4/5 需要 Retina / 窗口几何，再单独评估 PyObjC，不会过早绑定复杂方案。

风险：

- 仍然依赖 AppleScript 权限与 Chrome 脚本字典行为。
- 多窗口 / 多 Profile 语义要在 TID 中先收紧，不可乐观假设。

### 5.4 推荐方案

推荐方案：**方案 C，保守混合方案**。

原因：

1. Change 3 的核心不是做完整 macOS GUI 自动化，而是建立“窗口与页面身份已确认，否则不继续”的安全边界。
2. AppleScript 已足够覆盖 activate、frontmost、URL/title 读取这几个最小能力点。
3. 现阶段引入 PyObjC 的收益主要落在未来 Retina / 窗口几何，但这不属于本 Change 目标。
4. 方案 C 可以最小化对仓库依赖、测试面和 Windows 行为的冲击。
5. 当 AppleScript 失败时，方案 C 可以非常自然地 fail closed，而不是为了“尽量继续”引入不稳定降级。

## 6. 推荐实现边界

推荐按最小步原则约束 Change 3：

- 新增 macOS 专用 helper。
- 不影响 Windows。
- 不打开 BOSS URL。
- 不主动导航。
- 不触发点击、滚动、按键。
- 页面身份只读检测。
- 检测失败返回明确错误码。
- `--preflight-only` 仍只做 preflight，不进入业务动作。

进一步边界：

- Change 3 可允许“读取当前已经打开的页面身份”，但不得把“读取成功”解释为“允许业务点击”。
- Change 3 只建立页面安全门，不建立业务动作放行门。

## 7. 建议的数据结构 / 函数

### 7.1 新增 `ChromePageIdentity`

建议新增独立数据结构，而不是直接扩展 `BrowserPrepareResult`：

- `platform`
- `browser`
- `frontmost`
- `url`
- `title`
- `is_allowed`
- `error_code`
- `message`

建议保持只读、结构化、可 mock。

### 7.2 建议函数

建议但本轮不实现：

- `focus_chrome_window()`
  - 负责激活 Chrome。
  - 只负责“请求置前 + 验证 frontmost”。
  - 不读取页面身份，不做导航。
- `get_chrome_active_tab_identity()`
  - 只读获取 active tab 的 `url` 与 `title`。
  - 失败时返回结构化错误。
- `is_allowed_boss_page(url, title)`
  - 只做白名单判断。
  - 不做点击，不做 OCR，不做业务动作。
- 可选内部 helper：
  - `get_frontmost_application()`
  - `run_osascript(script_text)`
  - `normalize_page_identity(url, title)`

### 7.3 是否应直接修改 `BrowserPrepareResult`

本 TID **不建议在 Change 3 直接扩展 `BrowserPrepareResult` 承载页面身份明细**。

原因：

1. `BrowserPrepareResult` 当前语义是“浏览器准备层”。
2. 页面身份属于更细一层的“页面安全门”。
3. 若把 URL/title/frontmost 全部塞进 `BrowserPrepareResult`，会让 Windows Edge 路径也被迫承担不必要字段。
4. 这会模糊“浏览器已找到”和“页面已允许”的两个边界。

替代方案：

- 保持 `BrowserPrepareResult` 只表达浏览器准备结果。
- 新增 `ChromePageIdentity` 专门表达 macOS Chrome 页面身份结果。
- 在 macOS 后续接入时，由 `prepare_browser()` 内部或其后置辅助层组合两个结果，最终仍以 fail-closed 方式决定是否继续。

如果后续确实需要单一返回对象，可考虑新增更高层聚合结构，例如 `MacOSBrowserReadiness`，而不是污染现有跨平台基础结果。

## 8. 页面身份识别规则

BOSS 域名白名单必须在实施阶段明确列出具体 host / path 规则，禁止使用包含式宽匹配，例如仅凭字符串包含 `boss`、`zhipin` 或页面标题判断。

### 8.1 保守允许规则

建议仅在以下条件都满足时把页面标记为 `is_allowed=True`：

1. 当前前台应用确认是 Chrome。
2. 成功读取 active tab `url`。
3. `url` 命中严格的 BOSS 目标域名白名单。
4. `title` 或 `url` 至少有一个可以进一步支持“这是 BOSS 相关页面”的判断。

建议初版采用“URL 为主、title 为辅”的保守规则：

- 允许：明确属于 BOSS 直聘目标域名的 URL。
- 允许：URL 已明确命中白名单，且 title 显示为 BOSS 相关。
- 禁止：URL 缺失。
- 禁止：title 缺失且 URL 不足以确认。
- 禁止：任何无法确认的情况。

### 8.2 明确禁止规则

必须明确禁止：

- `about:blank` 被视为业务 `ready`。
- 任意 Chrome 页面被视为业务 `ready`。
- 仅凭 Chrome 启动成功进入业务流程。
- 仅凭窗口置前成功进入业务流程。

### 8.3 关键口径

Change 3 可以识别页面，但**仍不代表可以进行真实业务点击**。

推荐把状态分成三层理解：

1. Chrome 已启动。
2. Chrome 已置前且页面身份允许。
3. 真实业务可执行。

Change 3 只尝试把 macOS 从第 1 层推进到第 2 层，绝不直接推进到第 3 层。

## 9. 错误码设计

建议错误码如下，可在实现评审时微调名称，但语义应保持清晰稳定：

- `MACOS_CHROME_NOT_FOUND`
- `MACOS_CHROME_ACTIVATE_FAILED`
- `MACOS_CHROME_NOT_FRONTMOST`
- `MACOS_CHROME_TAB_QUERY_FAILED`
- `MACOS_PAGE_IDENTITY_UNKNOWN`
- `MACOS_PAGE_NOT_ALLOWED`
- `MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY`
- `MACOS_AUTOMATION_PERMISSION_DENIED`
- `MACOS_CHROME_NO_ACTIVE_WINDOW`
- `MACOS_CHROME_NO_ACTIVE_TAB`

建议映射原则：

- 激活失败与脚本执行失败分开。
- frontmost 不符单独成码。
- URL/title 读取失败单独成码。
- “允许页面已识别，但仍不可进入真实业务”单独成码，避免误读。

## 10. 测试计划

本轮只设计，不实施。

至少覆盖以下单测：

1. Windows 行为保持不变。
2. macOS Chrome activate 成功。
3. macOS Chrome activate 失败。
4. macOS 当前 frontmost 是 Chrome。
5. macOS 当前 frontmost 不是 Chrome。
6. macOS active tab URL/title 读取成功。
7. URL 是 BOSS 允许页面。
8. URL 不是 BOSS 允许页面。
9. URL/title 缺失时 fail closed。
10. AppleScript / `osascript` 报错时 fail closed。
11. `about:blank` 不被视为业务 ready。
12. 多窗口 / 多 tab 情况下只读取 active tab。
13. `--preflight-only` 不进入页面身份后的业务流程。
14. 不调用 OCR。
15. 不启动 keyboard.Listener，不新增任何键盘监听动作。
16. 不调用 PyAutoGUI 输入。
17. 不调用点击、滚动、刷新、转发。

测试设计建议：

- 延续 `tests/test_browser_prepare.py` 的纯 mock 风格。
- 对 `subprocess.run(["osascript", ...])` 或封装 helper 做 patch，不依赖真实 macOS GUI。
- 对“失败即不继续”的负向断言要继续覆盖业务入口函数。
- Windows 路径必须继续断言不会触发任何 macOS helper。

## 11. 人工验收计划

本轮只设计，不实施。

### 11.1 Chrome 未启动

预期：

- 若只做 activate/query，结果应 fail closed。
- `ready=True`：否。
- 是否允许进入后续业务：否。
- 是否禁止真实点击：是。

### 11.2 Chrome 已启动但不是前台

预期：

- 系统尝试 activate Chrome。
- 若 activate 后仍不是 frontmost，则 fail closed。
- `ready=True`：否。
- 是否允许进入后续业务：否。
- 是否禁止真实点击：是。

### 11.3 Chrome 前台但打开 `about:blank`

预期：

- 能识别 active tab。
- 页面身份不允许。
- `ready=True`：否。
- 是否 fail closed：是。
- 是否允许进入后续业务：否。
- 是否禁止真实点击：是。

### 11.4 Chrome 前台但打开非 BOSS 页面

预期：

- URL/title 可读。
- 命中非白名单，fail closed。
- `ready=True`：否。
- 是否允许进入后续业务：否。
- 是否禁止真实点击：是。

### 11.5 Chrome 前台并打开 BOSS 页面

预期：

- 页面可被识别为 allowed。
- 仍应返回“allowed but not business ready”语义。
- `ready=True`：建议仍为否，或仅在更高层聚合状态中标记 `is_allowed=True`。
- 是否允许进入后续业务：否。
- 是否禁止真实点击：是。

### 11.6 多窗口场景

预期：

- 只认 frontmost Chrome 窗口的 active tab。
- 不猜测后台 Chrome 窗口。
- 任何歧义都 fail closed。
- `ready=True`：否，除非当前 frontmost active tab 明确允许，且即便如此也不进入真实业务。
- 是否禁止真实点击：是。

### 11.7 多 Profile 场景

预期：

- 不主动切换 Profile。
- 只读取当前前台 Chrome 会话的 active tab。
- Profile 无法确认时不做乐观放行。
- `ready=True`：默认否。
- 是否允许进入后续业务：否。
- 是否禁止真实点击：是。

### 11.8 权限不足场景

预期：

- Apple Events / Automation 权限不足时，返回明确错误码。
- fail closed。
- `ready=True`：否。
- 是否允许进入后续业务：否。
- 是否禁止真实点击：是。

## 12. 风险分析

### 12.1 macOS AppleScript 权限风险

- `osascript` 依赖 Automation / Apple Events 权限。
- 首次授权弹窗、IDE 宿主变化、Terminal 与 Python 主体差异，都可能导致脚本失败。
- 这类失败必须映射为明确错误码，不能静默忽略。

### 12.2 Chrome 多窗口 / 多 Profile 风险

- 用户可能同时打开多个 Chrome 窗口或多个 Profile。
- 如果实现错误地读取后台窗口或错误 Profile，会把身份判断建立在错误上下文上。
- 初版必须只认 frontmost active tab，不做猜测。

### 12.3 URL/title 获取失败

- Chrome 可能没有活动窗口、没有活动 tab，或 AppleScript 调用异常。
- URL/title 任一关键字段缺失时应 fail closed。

### 12.4 BOSS 页面标题变化

- 仅凭 title 判断不稳定。
- 标题文案变化、登录态变化、页面 A/B 实验都可能让 title 失真。
- 因此应以 URL 白名单为主，title 只做辅助确认。

### 12.5 域名白名单过宽风险

- 如果白名单写得过宽，可能把无关页面或非目标页面误判为允许页面。
- 建议优先精确到受控域名与关键路径模式，宁可保守拒绝，也不要宽松放行。

### 12.6 把页面识别误认为业务安全的风险

- 页面身份允许，只说明“页面看起来像目标页面”。
- 它不等于坐标准确、页面布局稳定、OCR 可用、点击安全、业务合规。
- 文档、日志和错误码都必须明确这一边界。

### 12.7 与 Retina 坐标尚未完成之间的边界风险

- 即使 Change 3 完成，macOS 仍未解决逻辑坐标与物理像素映射。
- 因此不能因为页面已识别就启用点击、滚动或区域校准。
- Retina 问题应在后续 Change 中独立解决。

## 13. 推荐实施拆分

建议把 Change 3 再拆成最小可实施步骤：

### 3A：macOS Chrome frontmost / activate helper

- 增加 `focus_chrome_window()`
- 封装 AppleScript activate 与 frontmost 校验
- 失败即 fail closed

### 3B：active tab URL/title 只读查询

- 增加 `get_chrome_active_tab_identity()`
- 只读取当前 active tab 的 URL/title
- 不做导航，不做点击

### 3C：BOSS 页面身份白名单与 fail-closed

- 增加 `is_allowed_boss_page(url, title)`
- 建立严格白名单
- 身份不明一律拒绝

### 3D：接入 `prepare_browser()`，但仍不进入真实业务

- macOS 路径在 Chrome 已启动、权限满足后，继续做 activate + page identity 检查
- 即使页面 allowed，也返回“not business ready”语义
- `--preflight-only` 仍只输出诊断，不进入业务动作

### 3E：测试与人工验收报告

- 补充纯 mock 单测
- 设计并执行人工验收
- 输出独立验收报告

## 14. 验收结论格式

TID 结束时建议使用以下结论模板：

- 是否建议实施 Change 3：建议实施
- 推荐方案：方案 C，保守混合方案
- 推荐复杂度：Medium / High
- 是否允许真实 BOSS 页面：允许只读识别，不允许真实业务操作
- 是否允许点击/滚动/按键：不允许
- 是否允许转发：不允许

## 15. 总结结论

建议实施 Change 3，但必须坚持“小步、只读、fail closed”原则。

最推荐的路线是：

1. 用 AppleScript / `osascript` 完成 Chrome activate、frontmost 确认与 active tab URL/title 读取。
2. 用新的 `ChromePageIdentity` 表达页面身份层结果。
3. 保持 `BrowserPrepareResult` 作为浏览器准备层基础结构，不直接承载页面明细。
4. 即使识别到允许页面，也不要把 macOS 放行为真实业务可执行。

因此，Change 3 的正确定位不是“让 macOS 可以操作 BOSS 页面”，而是“在后续真实 GUI 自动化之前，先补齐窗口与页面身份的安全门”。
