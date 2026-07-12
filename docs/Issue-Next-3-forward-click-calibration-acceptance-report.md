# [Next-3] 验收报告：转发流程全部关键点击点启动前校准

## 1. 验收结论

**验收结论：通过。**

Next-3 规定的五个转发关键点击对象已全部支持运行期区域校准，默认区域与旧中心点及 offset 范围等价。校准采用五项原子提交，取消或失败时整组回退默认区域。`--auto`、`--no-forward`、无关键词和焦点恢复等安全路径均有自动化测试覆盖。

全量测试 109 项全部通过，无失败、无错误。当前工作区无未提交业务变更。

**建议进入 macOS Chrome 移植的技术规划与实施阶段。** 由于本次验收未执行真实浏览器手工测试，建议在进入跨平台实作前，先在当前 Windows Edge 基线上完成一次受控的 `--no-forward` 校准冒烟验证。

## 2. 实施摘要

- 新增不可变 `ForwardClickRegions`，统一管理转发入口、邮件 Tab、邮箱输入框、最近联系和转发按钮五个运行期区域。
- 通过 `region_around()` 从旧中心点和旧 offset 严格推导五个默认区域。
- 新增 `click_in_region()`，每次仅在区域内取点一次，并以 `offset=0` 执行点击，避免二次偏移越界。
- 普通交互模式在有关键词时提供完整校准入口，在第一位候选人详情页打开后按 UI 顺序引导框选。
- 校准导航仅点击 `FORWARD_ICON` 和 `EMAIL_TAB`；`INPUT_BOX`、`RECENT_EMAIL` 和 `FORWARD_BTN` 只框选，校准期间不点击最终转发按钮。
- 五项区域全部成功后才一次性更新运行期配置；任意一项取消或异常时全部回退默认配置。
- `forward_one_candidate()` 的五类点击已接入运行期区域，两处 `INPUT_BOX` 点击共用同一区域。
- 继续复用 Next-1 的 `DEFAULT_FOCUS_RESTORE_REGION` 与单一 `finally` 焦点恢复机制。
- README 已补充完整校准方式、模式差异、回退逻辑、风险和真实转发安全要求。

## 3. 提交记录

| Change | Commit | Commit message | 主要内容 |
| --- | --- | --- | --- |
| Change 1 | `b1e9ec6` | `feat: add runtime regions for forwarding clicks` | 新增五区域数据结构、等价默认区域、运行期配置、重置函数和区域点击助手。 |
| Change 2 | `421c1eb` | `feat: calibrate forwarding click regions before browsing` | 新增普通模式询问、五步引导校准、原子提交/回退、Esc 隔离以及 `--auto`/`--no-forward`/无关键词分支。 |
| Change 3 | `acfc0b7` | `feat: use calibrated regions in forwarding workflow` | 将 `forward_one_candidate()` 六处调用（五类区域）接入运行期区域，并扩展早退、异常和焦点恢复测试。 |
| Change 4 | `f39cea8` | `docs: explain full forwarding click calibration` | 补充 README 使用方式、默认回退、模式限制、风险和安全验证要求。 |
| Change 5 | 无提交 | 不创建空 commit | 执行全量回归、累计 diff 与非目标范围审计；无文件变更。 |

以上四个有文件变更的 change 均已独立提交。当前 `main` 比 `origin/main` ahead 4，报告生成时上述提交尚未 push。

## 4. 测试结果

执行命令：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：

- 共运行 **109** 项测试。
- **109 通过，0 失败，0 错误。**
- 测试命令退出码为 `0`。
- 没有未运行的项目自动化测试。
- 未执行真实浏览器框选和真实邮件转发手工测试；原因是本次任务为报告生成，不应在未明确安排测试账号、测试邮箱和人工监控的情况下触发 GUI 自动化。

主要相关自动化测试：

- `test_default_forward_click_regions_preserve_existing_click_ranges`
- `test_click_in_region_chooses_once_and_disables_second_offset`
- `test_forward_click_calibration_selects_in_order_and_publishes_atomically`
- `test_cancelled_forward_click_calibration_falls_back_atomically_and_once`
- `test_failed_forward_click_calibration_falls_back_without_stopping`
- `test_forward_click_calibration_is_skipped_when_not_requested`
- `test_auto_mode_never_prompts_for_focus_restore_calibration`
- `test_interactive_mode_without_keywords_does_not_offer_forward_calibration`
- `test_no_forward_mode_never_calls_real_forward`
- `test_forward_uses_calibrated_regions_and_reuses_input_box_region`
- `test_forward_restores_focus_after_success` 及其早退/异常分支测试

## 5. 坐标校准覆盖对照

`ScreenRegion` 使用半开区间存储，下表的“实际覆盖”以可取到的闭区间表示。

| 原坐标或区域 | 是否支持校准 | 默认区域 / 实际覆盖 | 是否参与运行期点击 | 证据 |
| --- | --- | --- | --- | --- |
| `FORWARD_ICON_X/Y` (`1670,260`) | 是 | `ScreenRegion(1665,255,11,11)`；X `1665-1675`，Y `255-265` | 是 | `DEFAULT_FORWARD_CLICK_REGIONS.forward_icon`；`forward_one_candidate()` 调用 `click_in_region(forward_click_regions.forward_icon)`。 |
| `EMAIL_TAB_X/Y` (`700,600`) | 是 | `ScreenRegion(695,595,11,11)`；X `695-705`，Y `595-605` | 是 | `DEFAULT_FORWARD_CLICK_REGIONS.email_tab`；校准导航和真实转发均使用该运行期区域。 |
| `INPUT_BOX_X/Y` (`900,390`) | 是 | `ScreenRegion(897,387,7,7)`；X `897-903`，Y `387-393` | 是，两处点击共用同一区域 | `forward_one_candidate()` 两处均调用 `click_in_region(forward_click_regions.input_box)`；专项测试验证调用两次。 |
| `RECENT_EMAIL_X/Y` (`1000,440`) | 是 | `ScreenRegion(995,435,11,11)`；X `995-1005`，Y `435-445` | 是 | `DEFAULT_FORWARD_CLICK_REGIONS.recent_email`；真实转发流程使用 `forward_click_regions.recent_email`。 |
| `FORWARD_BTN_X/Y` (`1210,740`) | 是 | `ScreenRegion(1205,735,11,11)`；X `1205-1215`，Y `735-745` | 是，仅正常转发流程点击 | 校准协调函数只调用 selector 保存 `forward_button`；仅 `forward_one_candidate()` 通过 `click_in_region()` 使用它。 |
| `DEFAULT_FOCUS_RESTORE_REGION` | 是，复用 Next-1 | `ScreenRegion(400,350,101,51)`；X `400-500`，Y `350-400` | 是 | Next-1 的 `focus_restore_region` 独立保留；`forward_one_candidate()` 的单一 `finally` 仍从该区域取点并以 `offset=0` 点击。 |
| `RIGHT_CLICK_X/Y` (`960,500`) | 否，本 issue 不纳入 | 不适用（仅保留旧常量） | 否 | 全仓检索仅有定义，无调用；本 issue 未删除、未接入。 |

## 6. 验收标准对照

| TID 验收点 | 结果 | 证据 |
| --- | --- | --- |
| 五个默认区域与旧中心点及 offset 范围严格等价 | 通过 | `region_around(x, y, radius)` 使用 `2 * radius + 1` 生成区域；专项测试逐项断言五个边界。 |
| 区域点击只随机取点一次并使用 `offset=0` | 通过 | `click_in_region()` 只调用一次 `random_point_in_region()`，随后调用 `human_click(..., offset=0)`；有专项 mock 测试。 |
| 每次运行重置为默认配置 | 通过 | `run()` 开始调用 `reset_forward_click_calibration()`，相关状态与五区域被重置；有运行重置测试。 |
| 框选与导航顺序正确 | 通过 | 依次处理 `forward_icon` → 打开弹窗 → `email_tab` → 切换 Tab → `input_box` → `recent_email` → `forward_button`；顺序测试验证 1/5 至 5/5。 |
| `FORWARD_BTN` 校准期间只框选、不点击 | 通过 | 校准函数只对前两个区域调用 `click_in_region()`；测试断言点击列表不包含 `forward_button`。 |
| 五项成功时原子提交 | 通过 | 五个 selector 结果先保存为局部变量，全部成功后才构造并赋值全局 `ForwardClickRegions`。 |
| 取消或异常时全部五项回退默认配置 | 通过 | `CalibrationCancelled` 和通用异常分支均整体赋值 `DEFAULT_FORWARD_CLICK_REGIONS`；取消、失败和只尝试一次均有测试。 |
| 取消和异常不设置 `stop_event` | 通过 | 两类分支测试均断言 `stop_event=False`；校准期间 Esc 交给 Tk 处理。 |
| 同一运行只尝试一次 | 通过 | `forward_click_calibration_attempted` 在首次尝试前设置，后续调用直接返回；取消测试验证 selector 不重复执行。 |
| 第一位详情打开失败时不校准 | 通过 | `run()` 仅在 `click_first_candidate()` 成功后调用校准函数；有失败时两类校准均不调用的测试。 |
| `--auto` 不询问、不弹 selector、不执行校准导航 | 通过 | 非交互分支强制清除两类校准请求；测试断言 `input()` 不调用，未请求时 selector/导航/关闭弹窗都不调用。 |
| 普通 `--no-forward` 有关键词时允许完整校准 | 通过 | 交互询问只受 `forward_enabled` 控制，不被 `no_forward` 禁止；同时 `view_candidate()` 在 `no_forward_mode` 下不调用真实转发函数。 |
| 无关键词时不询问完整转发校准 | 通过 | `forward_enabled=False` 分支直接清除校准请求；测试验证仅执行关键词和运行时间两次输入。 |
| 五类转发点击全部使用运行期区域 | 通过 | `forward_one_candidate()` 六处点击全部使用 `forward_click_regions`，其中 `input_box` 两次。 |
| 两处 `INPUT_BOX` 使用同一运行期区域 | 通过 | 两处均引用 `forward_click_regions.input_box`；备选邮箱路径测试断言相同区域调用两次。 |
| 早退和异常路径仍只恢复一次焦点 | 通过 | 成功、连续上限、无备选邮箱、等待中断、转发点击异常、校准焦点区域等测试均断言恢复调用恰好一次且为最后一次点击。 |
| Next-1 焦点恢复机制未被破坏 | 通过 | `DEFAULT_FOCUS_RESTORE_REGION` 仍为 `ScreenRegion(400,350,101,51)`；运行期校准、回退及 `finally` 路径均保留，相关旧测试全部通过。 |
| README 包含使用方式和风险限制 | 通过 | README 已说明六个区域顺序、运行期内存、默认回退、两类模式、窗口/缩放风险和小规模真实转发限制。 |
| 全量回归和非目标范围审计 | 通过 | 109 项测试通过；累计 diff 仅涉及 `README.md`、`simple_brush.py` 和 `tests/test_simple_brush_ocr.py`。 |

## 7. 安全行为确认

- **校准期间不点击最终转发按钮。** 校准导航仅使用刚框选的 `forward_icon` 和 `email_tab`；`forward_button` 只被 selector 记录。
- **`--no-forward` 可安全验证校准。** 有关键词的普通交互模式仍会询问完整校准，但 OCR 命中后不调用 `forward_one_candidate()`。
- **`--auto` 不弹新增交互。** 它不调用 `input()`、不弹框选层、不点击导航对象，并使用默认区域。
- **取消或失败整组回退。** 五个新区域不会部分发布；回退后本次运行不再重复询问。
- **焦点恢复保持单一。** 只要进入 `forward_one_candidate()`，无论成功、早退或异常，都由原有单一 `finally` 尝试恰好一次恢复。
- **不检测页面状态或转发结果。** 引导流程仅按既定顺序框选、点击和等待，界面不符时由用户按 Esc 取消。
- **不读取 DOM，不引入浏览器驱动。** 没有 Selenium、Playwright、WebDriver 或其他浏览器自动化驱动依赖变更。

## 8. 非目标确认

| 非目标 | 确认结果 |
| --- | --- |
| macOS Chrome | 未实现。README 仍明确当前仅支持 Windows + Microsoft Edge。 |
| 关键词规则 | Next-3 累计 diff 未修改 `ocr_text.py`、`ocr_detector.py` 或关键词规则测试。 |
| P3 日志 | 未实现新的候选人日志功能。 |
| P4 数值匹配 | 未实现。 |
| DOM 读取 | 未新增。 |
| Selenium / Playwright / WebDriver / 其他浏览器驱动 | 未引入。 |
| 页面状态识别 | 未新增。 |
| 转发成功或失败检测 | 未新增；保留原有固定顺序和等待。 |
| 持久化配置 | 未实现；校准区域只存在于当前 Python 进程内存，`run()` 开始时重置。 |
| 整体 OCR 或转发流程重构 | 未执行；仅替换点击坐标来源并在现有启动时机接入校准。 |

## 9. 风险与限制

- 校准结果是绝对屏幕坐标。校准后移动 Edge 窗口、改变窗口大小、系统缩放、浏览器缩放、分辨率或页面布局，都可能使区域失效。
- 当前 Tk 框选机制第一版仅明确支持主显示器；混合 DPI 多显示器环境必须将 Edge 置于主显示器。
- 程序不识别弹窗或 Tab 是否真正打开。如果 UI 状态不符预期，后续框选提示可能对应错误页面。
- 用户可能框选到按钮边缘、邻近交互元素或不可点击空白；实现仅提供提示和最小尺寸，不做视觉校验。
- 任意一项取消或失败都会使五个新区域整组回退。这避免部分配置，但意味着必须从头重新启动才能再校准。
- 默认区域基于现有 1920×1080 Windows Edge 布局，在其他分辨率或页面布局下不保证安全。
- 校准完成后程序化 Esc 关闭弹窗如果失败，浏览会继续，用户必须人工确认弹窗已关闭。
- 其余非转发流程的屏幕/鼠标定位仍可能依赖当前 Windows Edge 布局；本 issue 没有对整个项目的坐标系统做重构。
- 本次未进行真实页面手工验证，自动化 mock 不能完全替代当前 BOSS UI 布局下的实际点击验证。

## 10. 手工验证建议或结果

**本次未执行手工 GUI 验证或真实邮件转发。**

建议先执行不会真实转发的安全验证：

1. 在 Windows 主显示器上打开 Microsoft Edge，使用测试账号进入推荐牛人页面。
2. 以普通交互方式运行 `.\venv\Scripts\python.exe simple_brush.py --no-forward`，输入一条无害测试关键词，并在完整校准询问中选择 `y`。
3. 打开第一位候选人详情后，确认框选顺序为：焦点恢复 → 转发入口 → 邮件 Tab → 邮箱输入框 → 最近联系 → 转发按钮。
4. 确认校准导航只点击转发入口和邮件 Tab，框选转发按钮时没有触发发送。
5. 确认校准完成后弹窗关闭，随后 OCR 可继续浏览；即使关键词命中，`--no-forward` 也不得调用真实转发。
6. 重启后测试中途 Esc 取消，确认程序使用默认区域继续；再以 `--auto` 运行，确认不出现任何新增询问、框选层或校准导航点击。

如需验证真实转发路径，必须同时满足：

- 只使用**测试账号**和**测试邮箱**。
- 首次只允许验证**一位候选人**，不得批量。
- 全程由人工监控页面和鼠标落点，不得无人值守。
- 完成一次后立即按 Esc 停止，检查邮箱、页面和日志。
- 任何弹窗、Tab 或点击位置异常时立即停止，不允许通过重试扩大风险。

## 11. 是否可以进入 macOS Chrome 移植

**可以进入。**

Next-3 的代码、自动化测试和文档验收标准已满足，转发流程中五个原固定坐标点已统一转换为可校准运行期区域，且 Next-1 焦点恢复机制未被破坏。这已满足 macOS Chrome 移植前的坐标稳定性前置条件。

建议执行顺序：

1. 先在 Windows Edge 上完成上述 `--no-forward` 受控手工冒烟。
2. 冒烟通过后开始 macOS Chrome 移植实施。
3. 跨平台实施期间保持当前 Windows Edge 全量测试为回归基线。
