# macOS Chrome preflight 与人工验收指南

## 当前状态

macOS Chrome 移植目前只完成了 baseline / preflight 阶段，**不是可运行完整 BossOCR 业务的版本**。

当前能力仅包括：

- 隔离 Windows-only `win32*` 导入；
- 检查 macOS Chrome 默认可执行文件；
- 最多启动 Chrome `about:blank`；
- 输出辅助功能、屏幕录制和键盘监听的权限诊断 baseline；
- 默认 fail closed，`ready=False`，不进入真实业务 GUI 流程。

> 本阶段不要打开或操作真实 BOSS 页面。手工验收时关闭所有 BOSS 标签页，只允许 preflight 打开 `about:blank`。

## 环境准备

建议使用 Python 3.11 和项目内虚拟环境：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

`requirements.txt` 中的 `pywin32`/`ppywin32` 依赖带有 Windows 平台条件，macOS 不会安装它。

macOS Chrome 默认路径必须为：

```text
/Applications/Google Chrome.app/Contents/MacOS/Google Chrome
```

当前 baseline 不搜索自定义安装路径，也不回退到 Safari。

## `--preflight-only` 安全冒烟入口

运行：

```bash
python simple_brush.py \
  --preflight-only \
  --auto \
  --no-forward \
  --no-batch-filter \
  --simple-mouse
```

`--preflight-only` 是独立诊断入口。它只会：

1. 解析命令行参数；
2. 检查默认 Chrome 路径；
3. 最多以参数列表启动 Chrome `about:blank`；
4. 执行无输入、无截图的 macOS 权限诊断；
5. 输出结构化结果并退出。

它不启动键盘 Listener，不初始化 OCR，不框选区域，不点击、滚动、按键、刷新或转发，也不进入 BossOCR 业务循环。与其他参数组合时，其他参数的业务执行含义会被忽略。

### preflight 不验证的内容

`--preflight-only` 不验证：

- 真实 BOSS 页面或页面身份；
- Chrome 窗口置前或多窗口选择；
- Retina 逻辑坐标与物理像素映射；
- 筛选、首位候选人、转发或焦点恢复的校准区域；
- OCR 真实截图、扫描、关键词命中或二次确认；
- 邮件转发流程；
- 真实业务自动化的安全性。

preflight 输出不得解读为“可以安全运行真实业务”。

## 现有参数都不是 dry-run

- `--no-forward` 只禁止真实邮件转发；普通业务模式仍可点击、滚动、翻页和刷新。
- `--auto` 会跳过交互和校准并使用默认/旧坐标，不是安全冒烟开关。
- `--no-batch-filter` 只禁用批次筛选归位，仍可进入旧首位点击流程。
- `--simple-mouse` 只将区域点击的鼠标轨迹改为旧版简单直线移动，不会减少操作。

除 `--preflight-only` 外，不要用上述参数组合作为 macOS 安全冒烟方案。

## macOS 权限 baseline

preflight 当前只能将以下能力标记为 `unknown`，不会为了探测权限而生成真实输入或截图：

- 辅助功能：**系统设置 → 隐私与安全性 → 辅助功能**；
- 屏幕录制：**系统设置 → 隐私与安全性 → 屏幕录制**；
- 键盘监听 / 输入监控：**系统设置 → 隐私与安全性 → 输入监控**，并同时检查辅助功能授权。

Terminal、iTerm、VS Code、Python 可执行文件和将来的打包 App 可能被 macOS 视为不同授权主体。必须检查本次实际启动程序的宿主。权限变更后，可能需要完全退出并重启 Terminal / IDE / Python / App 才能生效。

## macOS 人工验收清单

验收前关闭所有真实 BOSS 页面，不要登录或打开候选人页面。

1. 确认 Python：

   ```bash
   python --version
   ```

   期望 Python 3.11.x。

2. 在已激活的虚拟环境中安装依赖：

   ```bash
   python -m pip install -r requirements.txt
   ```

3. 运行纯 mock 回归测试：

   ```bash
   python -m unittest tests.test_browser_prepare -v
   python -m unittest tests.test_mouse_motion -v
   python -m unittest tests.test_simple_brush_ocr -v
   ```

   所有测试必须通过，且不得出现真实 GUI 输入、截图或浏览器业务操作。

4. 确认真实 BOSS 页面均已关闭，然后运行唯一允许的手工冒烟入口：

   ```bash
   python simple_brush.py --preflight-only --auto --no-forward --no-batch-filter --simple-mouse
   ```

5. 确认 Chrome 最多只打开 `about:blank`，终端输出至少包含：

   ```text
   platform: macos
   browser: chrome
   launched: True
   ready: False
   error_code: MACOS_PERMISSIONS_NOT_READY
   ```

   如果 Chrome 未安装、路径异常、不可执行或启动失败，可以出现 `CHROME_NOT_FOUND`、`CHROME_NOT_EXECUTABLE`、`CHROME_LAUNCH_FAILED` 或其他明确的 fail-closed 错误码。

6. 确认输出没有业务启动、候选人浏览、OCR 扫描、校准、筛选、翻页、刷新或邮件转发记录。

7. 记录实际运行宿主、macOS 版本、Python 版本、Chrome 版本和诊断错误码。

## 验收结论边界

本清单通过只能证明 Chrome 安全启动与权限诊断边界正常。在 Chrome 窗口置前、页面身份识别、Retina 坐标、校准和真实页面安全验证完成前，macOS 不得进入 BossOCR 业务模式。
