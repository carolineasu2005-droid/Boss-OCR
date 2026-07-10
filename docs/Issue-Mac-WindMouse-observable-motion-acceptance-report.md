# Mac WindMouse 可观察鼠标移动验收报告

## 验收结论

自动化验收通过，Mac 实机观感验证待执行。

该结论限定为 WindMouse 定向测试、依赖/API 探针、语法/依赖检查、全量测试和
Mac onedir 打包均通过；未执行真实鼠标、浏览器或邮件转发。因此不可作为正式
发布验收完成的声明。

## 实施范围

| 文件 | 变更 |
| --- | --- |
| `mouse_motion.py` | 新增 WindMouse PyAutoGUI 单段/两段封装及异常 fallback。 |
| `simple_brush.py` | `human_move_to()` 接入封装；`human_click()`/区域点击传递区域宽高。 |
| `tests/test_mouse_motion.py` | 覆盖参数、两段规则、fallback、简单模式、最终坐标和直接点击边界。 |
| `requirements.txt` | 固定 `windmouse==1.0.2`。 |
| `BossOCR-macos.spec` | 仅加入 `windmouse.core`、`windmouse.pyautogui_controller` hidden imports，并复制 metadata。 |
| `scripts/build_macos_beta.sh` | 将 `windmouse` 加入构建前模块检查。 |
| `README.md`、`docs/macos-beta-packaging.md` | 说明行为、Mac 权限、PyPI 来源与 GPL-3.0-only。 |

未修改 OCR、关键词、筛选、转发、刷新、Chrome、键盘切换或区域校准业务逻辑。
未引入或显式收集 `windmouse.ahk_controller`，也不要求 AutoHotkey。

## 行为验收

| 项目 | 自动化结果 |
| --- | --- |
| 小于 300 像素 | 单段，`10/0/16/12`，`tick_delay=0`、`step_duration=0`。 |
| 大于等于 300 像素 | 两段：第一段 `20/3/45/24`，第二段 `10/0/18/18`。 |
| 普通/小区域收尾 | 分别验证 `clamp(distance*.10,60,120)` 与 `clamp(distance*.12,80,140)`。 |
| 最终坐标 | 成功路径强制 `moveTo(target_x, target_y, duration=0)`；按下/抬起复用整数目标。 |
| 异常回退 | 缺失/导入失败、第一段失败、第二段失败均 warning 后调用原贝塞尔路径。 |
| `--simple-mouse` | 在 WindMouse 之前短路，保留旧单次直线移动。 |
| 区域取点与直接点击边界 | 随机点不变；仅传递宽高；旧 `click_first_candidate()` 仍直接点击。 |

## 上游 API 探针

安装并检查 `windmouse==1.0.2`：

- `PyautoguiMouseController`：`windmouse.pyautogui_controller`；
- `Coordinate`：此环境由 `windmouse.core` 提供，代码兼容包根导出失败时的 fallback；
- controller 构造参数包含 gravity/wind/max-step/damped-distance；
- `move_to_target(tick_delay=0, step_duration=0)` 可调用；
- 未引用 `windmouse.ahk_controller`。

## 自动化命令与结果

| 命令 | 结果 |
| --- | --- |
| `.venv/bin/python -m unittest tests.test_mouse_motion -v` | 14 passed。 |
| `.venv/bin/python -m compileall -q simple_brush.py mouse_motion.py tests` | passed。 |
| `.venv/bin/python -m pip check` | passed。 |
| `git diff --check` | passed。 |
| `.venv/bin/python -m unittest discover -s tests -v` | 387 passed。 |

## Mac 打包与许可证

执行 `bash scripts/build_macos_beta.sh` 成功，生成：

```text
dist/BossOCR/BossOCR
```

产物检查确认存在：

```text
dist/BossOCR/_internal/windmouse-1.0.2.dist-info/
dist/BossOCR/_internal/windmouse-1.0.2.dist-info/licenses/LICENSE
```

产物中未发现名称包含 `ahk` 的文件；spec 也没有显式收集 AHK backend。
正式分发前仍须确认 GPL-3.0-only 义务。

## Mac 实机与简单模式对照

未执行。发布前请在已授权辅助功能、屏幕录制和输入监控的 Mac 上，用 beta
安全模式（`--no-forward`）校准筛选及首位候选人区域，观察“打开筛选 -> 最近
没看过 -> 确定 -> 首位候选人”。确认轨迹可见、小区域远距离无明显回拉、落点
在安全区域且日志没有 fallback warning；随后加 `--simple-mouse` 对照旧直线
移动。不得执行真实邮件转发。

## 回退

1. 运行时加入 `--simple-mouse`，立即使用旧直线移动。
2. 卸载或缺失 WindMouse 时，程序记录 warning 并自动使用原贝塞尔路径。
3. 使用 Git 回退本次变更即可恢复原默认路径；未触及 Chrome、OCR、筛选、刷新或转发流程。

## 未完成项 / 发布前阻塞

1. 必须完成上述 Mac 实机安全模式观感验证。
