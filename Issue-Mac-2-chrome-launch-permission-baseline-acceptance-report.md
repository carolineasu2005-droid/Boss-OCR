# Mac Change 2：Chrome 启动与权限基线总体验收报告

## 1. 验收信息

- 验收分支：`mac-chrome-port`
- 验收范围：Mac Change 2A–2E
- 验收性质：macOS Chrome 启动、权限诊断与安全 preflight baseline
- 验收结论：**通过**
- 结论边界：仅确认 baseline / preflight 设计与安全边界达标，不代表 macOS 已可运行完整 BossOCR 业务。

## 2. 实施范围

### 2.1 Change 2A：平台无关浏览器准备边界

- 新增 `BrowserPrepareResult`，结构化表达 `ready`、平台、浏览器、是否启动、可执行路径、消息和错误码。
- 新增 `prepare_browser(platform_name=None)` 作为 `run()` 的平台无关浏览器准备入口。
- Windows 继续复用原有 `bring_edge_foreground()`；`is_boss_edge_window()`、`get_window_process_name()` 和 Win32 窗口匹配语义未改变。
- `run()` 只在 `BrowserPrepareResult.ready=True` 时进入后续业务流程；macOS 与未知平台 fail closed。
- 保留原有前置时序：参数处理 → OCR 初始化 → Listener 启动 → 启动日志 → 浏览器准备。

### 2.2 Change 2B：macOS Chrome 路径与安全启动

- 固化默认路径：

  ```text
  /Applications/Google Chrome.app/Contents/MacOS/Google Chrome
  ```

- 新增 `resolve_chrome_executable()`，使用 `Path` 检查路径存在性、文件类型和可执行位。
- 新增 `launch_chrome_safe_target()`，仅通过参数列表启动：

  ```text
  [chrome_path, "about:blank"]
  ```

- 未使用 `shell=True`，未传入 BOSS URL，未创建或修改 Chrome Profile，未关闭用户已有 Chrome。
- 区分“进程启动调用成功”与“窗口/页面可操作”；启动成功时 `launched=True`，但仍 `ready=False`。

### 2.3 Change 2C：macOS 权限诊断 baseline

- 新增 `MacOSPermissionStatus`，表达 Accessibility、Screen Recording、Keyboard Listener 三类能力状态和总体 `ready`。
- 新增 `check_macos_permissions()` 及三个单项检查函数。
- 默认诊断策略为三项均 `unknown`，不通过真实输入、截图或等待按键探测权限。
- 权限非全部明确 `ok` 时返回 `MACOS_PERMISSIONS_NOT_READY` 并 fail closed；检查异常时返回 `MACOS_PERMISSION_CHECK_FAILED`。
- 诊断文案覆盖 Terminal / iTerm / VS Code / Python / 打包 App 授权主体差异、系统设置路径和宿主进程重启要求。

### 2.4 Change 2D：`--preflight-only` 安全冒烟入口

- `parse_args()` 新增 `--preflight-only`。
- 新增 `run_preflight_only()`；在参数解析后、用户输入/OCR/Listener/业务逻辑之前提前分流。
- preflight 只调用 `prepare_browser()`，输出平台、浏览器、`launched`、`ready`、`error_code`、`message` 和安全边界说明，然后退出。
- 与 `--auto --no-forward --no-batch-filter --simple-mouse` 组合时仍只执行 preflight，其他参数的业务含义不会被执行。

### 2.5 Change 2E：文档与人工验收清单

- 新增 `docs/macos-chrome-preflight.md`，覆盖 Python 3.11 / venv / 依赖安装、Chrome 默认路径、preflight 边界、macOS 权限和人工验收步骤。
- README 增加 macOS Chrome preflight 指南链接，并明确完整业务流程仍仅支持 Windows + Microsoft Edge。

## 3. 非目标确认

本 Change 明确**没有实现或没有修改**：

- macOS 真实 BOSS 页面操作；
- Chrome 窗口置前；
- Chrome 页面身份识别；
- Retina 逻辑坐标/物理像素适配；
- macOS 区域校准迁移；
- macOS OCR 真实截图与扫描迁移；
- macOS 邮件转发迁移；
- Next-5 批次筛选业务逻辑；
- Next-6 鼠标轨迹逻辑；
- 关键词 parser / matcher；
- Windows 打包流程或 Windows 正式版 release；
- `main` 分支、tag 或 release。

## 4. 自动化测试与检查结果

Mac Change 2 实施期间已记录以下执行结果：

| 命令 | 结果 |
|---|---|
| `python -m unittest tests.test_browser_prepare -v` | **23/23 OK** |
| `python -m unittest tests.test_mouse_motion -v` | **18/18 OK** |
| `python -m unittest tests.test_simple_brush_ocr -v` | **85/85 OK** |
| `git diff --check` | **通过** |

Change 2E 最后仅修改 Markdown 文档与 `.gitignore` 的文档跟踪例外，未修改可执行代码或测试，因此文档收尾阶段未重复运行完整单测；已重新执行 `git diff --check`。

## 5. macOS 实机 preflight 记录

手工安全冒烟命令：

```bash
python simple_brush.py --preflight-only --auto --no-forward --no-batch-filter --simple-mouse
```

已记录的预期/实测结果：

```text
platform: macos
browser: chrome
launched: True
ready: False
error_code: MACOS_PERMISSIONS_NOT_READY
```

验收边界：

- Chrome 最多只打开 `about:blank`；
- 权限 baseline 默认为 `unknown`，因此返回 `ready=False`；
- 诊断后立即退出，不进入 BossOCR 业务循环；
- Chrome 未安装、路径不可用、启动失败或诊断异常时，应返回对应明确的 fail-closed 错误码。

> 本轮生成验收报告时未再次启动 GUI；上述内容是对 Mac Change 2 实施/手工验收记录的归档。

## 6. `--preflight-only` 安全边界

自动化负向断言与实施边界确认，`--preflight-only` **不调用**：

- 交互式用户输入流程；
- `initialize_ocr()`；
- keyboard Listener；
- Tk 区域框选；
- MSS 真实截图或截图保存；
- PyAutoGUI 鼠标、滚轮、按键或热键输入；
- 首位候选人点击；
- 批次筛选与归位；
- 滚动浏览；
- 右方向键翻页；
- F5 刷新；
- 邮件转发。

可调用范围仅为：命令行参数解析 → `prepare_browser()` → Chrome `about:blank` 安全启动（macOS）→ 无输入/无截图权限诊断（macOS）→ 输出结果 → 退出。

## 7. 当前限制

- macOS 仍不是完整业务可用版。
- macOS `prepare_browser()` 当前始终 `ready=False`，不会进入真实业务 GUI 流程。
- Accessibility、Screen Recording 和 Keyboard Listener 自动诊断默认均为 `unknown`。
- 尚未完成 Chrome 窗口置前、页面身份识别、Retina 坐标适配、macOS 区域校准、OCR 真实扫描与邮件转发迁移。
- preflight 结果不得解读为“可以安全运行真实业务”。
- 在上述工作完成之前，不得打开或操作真实 BOSS 页面。

## 8. 验收结论与下一步

Mac Change 2A–2E 已满足 Chrome 启动与权限基线 TID 的实施、自动化回归、安全边界和文档验收要求。未发现阻断本 baseline 通过的问题。

**验收结论：通过。**

建议下一步进入 **Mac Change 3：Chrome 窗口置前与页面身份识别 TID**。本报告仅提出下一步建议，**不实施 Change 3**。
