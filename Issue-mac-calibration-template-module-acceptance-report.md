# macOS 校准模板模块最终验收报告

## 结论

**通过，可作为 BossOCR 首个 macOS 正式版本从 `mac-chrome-port` 发布。** 本轮发布不合并 `main`，不创建 Windows release；正式产物只包含一个 onedir 和唯一入口 `BossOCR/BossOCR`。

## 基线与合并状态

- 分支：`mac-chrome-port`
- 验收基线 commit：`7616adc build: verify macOS calibration menu packaging`
- `origin/main`：已合并，`git merge-base --is-ancestor origin/main HEAD` 返回 0。
- 本分支相对 `origin/mac-chrome-port`：验收开始时 ahead 6；本报告与文档改动尚未提交。

## 模块与范围核对

| 项目 | 结果 |
| --- | --- |
| 模块文件 | `calibration_profiles.py`、`calibration_steps.py`、`calibration_template.py`；接入点 `simple_brush.py`、打包定义 `BossOCR-macos.spec`、构建脚本 `scripts/build_macos_beta.sh` |
| 功能范围 | 模板仅作为既有校准区域参数来源；未改 OCR、收藏/转发业务、筛选逻辑、鼠标参数或 Retina 自动缩放 |
| 正式启动入口 | 唯一入口：`dist/BossOCR/BossOCR`（源码为 `simple_brush.py`）；无参数主菜单为“开始运行 BossOCR / 创建/更新校准模板 / 退出” |
| 第二个 App | 无；构建验证 onedir 顶层只有一个可执行入口，且没有 `.app` |
| `calibration_template.py` | 仅开发、自动化测试和排障直接入口；正式用户从唯一 BossOCR 入口的菜单创建/更新模板 |
| 模板创建 | 菜单分支在同一进程执行；成功、取消、未确认覆盖或失败均回主菜单；取消/失败不保存不完整模板 |
| 模板选择与注入 | 交互模式可选模板或选择 0 走旧手动流程；注入 `ForwardClickRegions`、`BatchFilterRegions`、`focus_restore_region`、`favorite_button_region` |
| 非交互 | `--auto --calibration-profile "模板名称"` 仅显式加载指定模板；未指定不猜测、不扫描；坏模板/字段缺失/明显系统不匹配时失败且不等待输入 |
| 不调用模板 | 旧手动校准仍可使用 |

## macOS 坐标、路径与权限

- `dpi_scale`：macOS `get_system_info()` 保存 `dpi_scale: null`；仅 Windows 尝试读取 DPI。模板比较中双方均为 `null` 时记为不可用 warning，不伪造 DPI。
- 模板保存路径合同未变：`PROFILE_DIR = Path("calibration_profiles")`，相对启动时 CWD。仓库根目录源码为 `$PROJECT_ROOT/calibration_profiles`；在 `dist/BossOCR` 内启动 onedir 为 `$PROJECT_ROOT/dist/BossOCR/calibration_profiles`；其他 CWD 为 `$CWD/calibration_profiles`。
- Retina 坐标门禁：**通过（已完成目标 Mac 实机冒烟）**。门禁要求有效 display fingerprint、MSS request/result scale、Tk 框选至截图 crop mapping 与 crop preview 人工确认；无自动缩放、无跨缩放/跨显示器适配。调用模板前 Boss 页面窗口位置、大小与浏览器缩放必须和校准时一致。
- 权限：**通过（真实页面人工冒烟前置已满足）**。实际运行主体必须有辅助功能、屏幕录制和输入监控权限；Terminal/IDE/Python/onedir 可能是不同主体，授权变更后必须重启主体。权限缺失即停止，不盲点。

## 人工烟测

目标设备为 MacBook Air M1 内置 Retina 显示器，macOS Chrome 的真实 Boss 页面烟测已完成：

- MSS、Tk 与 PyAutoGUI 坐标空间一致，Retina 框选区域和实际鼠标落点一致；没有使用 Retina 自动倍率补偿。
- 唯一 BossOCR 入口可进入校准流程，11 个区域均可完成校准，每个校准步骤开始前提供 3 秒准备时间。
- 模板可保存、读取并在业务流程中调用；不使用模板时旧手动校准仍可用。
- 收藏模式、转发模式和“最近没看过”筛选通过。
- 首位候选人点击与焦点恢复通过。
- 辅助功能、屏幕录制和输入监控权限通过。
- 打包产物中没有第二个可执行入口或 `.app`。

该结果只适用于校准时相同的窗口位置、窗口大小、主显示器和浏览器缩放；页面布局、窗口、显示器或缩放变化后必须重新校准。

## 自动化回归与构建

本机没有 `python` 可执行命令，因此用户给定命令以等价的 `.venv/bin/python`（Python 3.11.9）执行；原 `python -m unittest tests.test_calibration_profiles -v` 因 `python: command not found` 未启动任何测试。

| 命令 | 结果 |
| --- | --- |
| `.venv/bin/python -m unittest tests.test_calibration_profiles -v` | 23 passed |
| `.venv/bin/python -m unittest tests.test_calibration_steps -v` | 7 passed |
| `.venv/bin/python -m unittest tests.test_calibration_template -v` | 7 passed |
| `.venv/bin/python -m unittest tests.test_ocr_calibration -v` | 6 passed |
| `.venv/bin/python -m unittest tests.test_simple_brush_ocr -v` | 174 passed |
| `.venv/bin/python -m unittest tests.test_browser_prepare -v` | 219 passed |
| `.venv/bin/python -m unittest tests.test_mouse_motion -v` | 14 passed |
| `.venv/bin/python -m unittest discover -s tests -v` | **506 passed** |
| `git diff --check` | 通过，无输出 |
| `bash scripts/build_macos_beta.sh` | 通过；生成 `dist/BossOCR/BossOCR`，验证三个模板模块、唯一入口、无 `.app`、无用户模板 JSON |

## 未解决风险

- 模板和运行期区域均为绝对屏幕坐标；窗口位置/尺寸、显示器、系统缩放、浏览器缩放或页面布局变化可能导致偏移，需重新校准。
- 路径相对 CWD 是既有合同；从不同目录启动会读写不同的 `calibration_profiles/`。
- onedir 未签名、未公证；新 Mac 还需处理 Gatekeeper 与针对实际运行主体的权限授权。
- 当前 onedir 必须完整解压并保留全部依赖文件，不能单独复制 `BossOCR` 二进制。

## 建议

- 建议 commit：是。
- 建议 commit message：`feat: complete first macOS release`
- 建议 push 到 `mac-chrome-port`：是，完成提交后推送。
- 建议合并 `main`：否；本轮只发布已经验收的 `mac-chrome-port`。
- 建议 release：是；专项与全量测试、干净构建、独立压缩包验证均通过后创建 `v1.2.0-macos` 正式 release。
