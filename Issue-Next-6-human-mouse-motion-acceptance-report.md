# [Next-6][P2] 验收报告：优化鼠标移动轨迹——贝塞尔路径、途中抖动与慢-快-慢三段变速

## 1. 验收结论

**结论：通过。**

Next-6 已按 `Issue-Next-6-human-mouse-motion-TID-V1.0.md` 完成实施。核心鼠标移动、`human_click()` 接入、`--simple-mouse` 回退、业务路径兼容测试和 README 均已完成；指定测试与全量测试全部通过，未发现阻断问题。

本次验收建议下一步：

1. 将本报告全文评论到 Next-6 对应 GitHub issue。
2. 保持 issue open，等待人工评审或实机观察结论。
3. 完成评审后，再准备 macOS Chrome 移植前置工作。

## 2. 实施与提交摘要

| Change | Commit | 内容 |
| --- | --- | --- |
| Change 1 | `5a4df35 feat: add observable bezier mouse movement` | 新增 `human_move_to()`、路径参数和隔离单元测试 |
| Change 2 | `8df66d0 feat: use human mouse paths for region clicks` | `human_click()` 接入新移动封装，新增 `--simple-mouse` 和运行期状态 |
| Change 3 | `fc80c7b test: cover human mouse integration paths` | 补充区域点击、Next-5、旧首位点击及 CLI 兼容回归 |
| Change 4 | `6d1cafa docs: explain human mouse movement option` | README 补充移动行为、覆盖边界、回退方式和合规说明 |

相对验收基线 `origin/main`，Next-6 只修改：

- `simple_brush.py`
- `tests/test_mouse_motion.py`
- `README.md`

## 3. 实施范围核对

| 验收项 | 结果 | 证据 |
| --- | --- | --- |
| 新增 `human_move_to()` | 通过 | `simple_brush.py` 中新增 `human_move_to(x, y, *, simple=None)` |
| 三次贝塞尔路径 | 通过 | 使用起点、两个控制点和目标点计算三次贝塞尔中间坐标 |
| 单次移动慢—快—慢 | 通过 | 采用 `3u² - 2u³` smoothstep easing；专项测试比较首尾与中段步长 |
| 距离决定总时长和步数 | 通过 | 时长按基础值加距离换算后裁剪到 `0.20~0.75s`；步数裁剪到 `12~45` |
| 抖动只在中间路径点 | 通过 | 抖动只出现在中间采样循环，并用 `sin(πu)` 在两端衰减 |
| 最终一步强制目标坐标 | 通过 | 循环后独立执行 `pyautogui.moveTo(target_x, target_y, duration=0)` |
| `human_click()` 接入 | 通过 | 原直接 `pyautogui.moveTo()` 已替换为 `human_move_to(tx, ty)` |
| `--simple-mouse` 回退 | 通过 | CLI 解析、运行期状态和单次旧版直线 `moveTo` 分支均存在 |
| `offset=0` 稳定语义 | 通过 | 最终目标只计算一次；`human_move_to`、`mouseDown`、`mouseUp` 使用同一坐标 |
| 保留旧首位直接点击 | 通过 | `click_first_candidate()` 仍调用 `pyautogui.click(x, y, duration=0)`，未迁移到新封装 |

## 4. 核心验收用例

| 场景 | 结果 | 自动化证据 |
| --- | --- | --- |
| `human_move_to()` 最终落点等于目标点 | 通过 | `test_bezier_move_uses_intermediate_points_and_exact_integer_target` |
| 起点等于终点时稳定处理 | 通过 | `test_zero_distance_moves_exactly_once_without_sleep_or_randomness` |
| 短距离曲率和抖动收敛 | 通过 | `test_very_short_distance_stays_stable_without_curve_randomness` |
| 不同距离产生受限的不同总时长或步数 | 通过 | `test_distance_calculation_respects_step_bounds` |
| 相邻移动距离呈慢—快—慢 | 通过 | `test_easing_has_shorter_endpoint_steps_than_middle_steps` |
| 中途抖动不影响最终落点 | 通过 | `test_intermediate_jitter_never_changes_forced_target` |
| `human_click()` 先移动再按下/抬起 | 通过 | `test_human_click_reuses_move_target_for_press_and_release` |
| 移动异常后不继续 `mouseDown` / `mouseUp` | 通过 | `test_human_click_does_not_press_when_movement_fails` |
| `offset=0` 不偏移 | 通过 | `test_human_click_with_zero_offset_keeps_exact_target` |
| `click_in_region()` 只取点一次并传 `offset=0` | 通过 | `test_region_click_routes_one_exact_point_through_human_click` 及既有同类测试 |
| `--simple-mouse` 绕过新轨迹并使用旧版简单移动 | 通过 | `test_simple_argument_keeps_single_legacy_move_available`、`test_default_mode_reads_simple_mouse_runtime_state` |
| `--simple-mouse` 与现有 CLI 参数兼容 | 通过 | `test_simple_mouse_is_compatible_with_existing_cli_flags` |
| `click_first_candidate()` 旧直接点击保持不变 | 通过 | `test_legacy_first_candidate_keeps_direct_click_boundary` |
| P0 焦点恢复仍执行两次 | 通过 | 成功、上限、无备用邮箱、中断、异常和第一次点击失败等既有测试全部通过 |
| Next-5 点击顺序保持 open、unseen、confirm、first | 通过 | `test_batch_filter_region_path_reaches_human_click_in_order`、`test_apply_batch_filter_clicks_regions_in_order` |

## 5. 测试结果

验收环境：Windows，PowerShell，项目本地 `venv`。

| 命令 | 结果 |
| --- | --- |
| `.\venv\Scripts\python.exe -m unittest tests.test_mouse_motion -v` | 通过，18/18 |
| `.\venv\Scripts\python.exe -m unittest tests.test_simple_brush_ocr -v` | 通过，85/85 |
| `.\venv\Scripts\python.exe -m unittest discover -s tests -v` | 通过，165/165 |
| `git diff --check` | 通过，无空白错误 |

没有失败、跳过或未执行的自动化测试。测试输出中的预期异常日志来自异常分支测试，不是测试失败。

## 6. 测试隔离确认

鼠标专项测试对以下真实副作用进行了 mock：

- `pyautogui.position`
- `pyautogui.moveTo`
- `pyautogui.mouseDown`
- `pyautogui.mouseUp`
- `pyautogui.click`
- `time.sleep`
- `random.uniform`、`random.choice`、`random.randint`

本次验收测试确认：

| 隔离项 | 结果 |
| --- | --- |
| 未触发真实鼠标移动或点击 | 是 |
| 未触发真实键盘输入 | 是 |
| 未触发真实 OCR | 是 |
| 未打开或操作真实浏览器 | 是 |
| 未执行真实邮件转发 | 是 |
| 未访问真实剪贴板 | 是 |

本报告记录的是自动化验收结果；本轮没有强行执行真实 GUI 或真实页面测试。

## 7. 非目标确认

通过提交范围和 diff 审查，确认 Next-6 没有修改下列业务或平台能力：

- OCR 截图、识别、滚动和二次确认逻辑。
- 关键词 `and` / `or` / `not` / `any(...)` parser 与 matcher。
- 邮件转发步骤、备用邮箱、连续转发上限和成功/失败处理逻辑。
- Next-5 区域校准、自动筛选、首位归位和批次边界逻辑。
- 右方向键切换下一位候选人的既有逻辑。
- Windows `.spec`、批处理或其他打包脚本。
- macOS Chrome 逻辑。
- DOM 读取、Selenium、Playwright、WebDriver。
- 页面状态、按钮文字、图像或转发结果识别。
- 全局 `fast` / `normal` / `slow` 鼠标速度 profile。

代码、注释和日志中没有承诺或暗示本功能可规避验证码、风控或平台检测。README 仅包含明确的否定性合规说明：该功能用于本地 GUI 操作可观察性和统一封装，不用于规避上述机制，也不保证对其产生影响。

## 8. 风险与限制

- 新轨迹会为每次区域点击增加约 `0.20~0.75s` 移动时间，长流程总耗时会增加。
- 增强路径只覆盖经 `human_click()` 执行的区域点击；旧首位直接点击、滚轮和键盘保持原行为。
- 曲线路径增加中间 `moveTo` 次数；当前通过 `12~45` 步上限控制调用成本。
- 最终落点虽然强制稳定，但调用方校准区域本身错误、窗口移动、缩放或页面布局变化仍可能导致误点。
- PyAutoGUI fail-safe 保持有效；移动异常会向上传播，不会被静默吞掉。
- 自动化测试验证数学路径和调用契约，但不能完全替代 Windows Edge 实机对移动观感和耗时的观察。

## 9. 回退与发布状态

`--simple-mouse` 可作为运行期快速回退：如果增强轨迹在实机上表现不适配，使用该参数即可让 `human_click()` 恢复旧版单次简单直线移动，无需修改配置、重新校准或回滚提交。

本次验收没有：

- 创建或移动 tag。
- 创建 GitHub Release。
- 打包或上传发布附件。
- 修改稳定分支。

## 10. 最终建议

Next-6 满足 TID 与 issue 的自动化验收要求，**建议通过验收**。下一步可将本报告评论到 Next-6 issue；在人工评审后，再准备 macOS Chrome 移植前置工作。
