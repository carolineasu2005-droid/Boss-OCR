# BossOCR macOS beta 打包与运行

本方案生成可从终端运行的 PyInstaller `onedir` 产物：

```text
dist/BossOCR/BossOCR
```

第一版 beta 不把双击 `.app` 作为主入口。当前程序依赖终端中的
`input()` 交互；console onedir 能保留输入、日志和错误信息，也更适合小范围
beta 验收。本流程不生成 `.app`。

## 环境准备

打包必须在 macOS 上执行，建议使用 Python 3.11 和项目 `.venv`：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pip install -r requirements-ocr.txt
.venv/bin/python -m pip install -r requirements-build.txt
```

`requirements-ocr.txt` 包含 RapidOCR、ONNX Runtime、MSS、Pillow 和 NumPy
等 OCR/截图运行依赖。打包脚本只检查依赖，不会静默安装，也不会修改全局
Python 环境。

`requirements.txt` 固定包含 `windmouse==1.0.2`。Mac beta 仅使用其 PyAutoGUI
backend；不安装或显式收集 AutoHotkey backend。打包会保留
`windmouse-1.0.2.dist-info` 及 `licenses/LICENSE`（GPL-3.0-only）。WindMouse
项目为 <https://github.com/AsfhtgkDavid/windmouse>；本仓库仅通过 PyPI 引用，
不复制或修改其源码。正式分发前须确认发布方式满足 GPL-3.0-only 的义务。

## 构建 onedir beta

在仓库根目录运行：

```bash
bash scripts/build_macos_beta.sh
```

脚本将：

1. 拒绝在非 macOS 平台运行；
2. 使用已激活的 virtualenv，或显式使用 `.venv/bin/python`；
3. 检查 Python 版本、PyInstaller 和运行依赖；
4. 清理 `build/macos` 与 `dist/BossOCR`；
5. 使用 `BossOCR-macos.spec` 构建 console onedir 包；
6. 验证 `dist/BossOCR/BossOCR` 已生成且可执行。

现有通用 `BossOCR.spec` 不会被修改或调用，因此 Windows 打包流程保持不变。

## 运行

构建完成后，从仓库根目录运行：

```bash
dist/BossOCR/BossOCR
```

分发时必须保留整个 `dist/BossOCR` 目录，不能只复制同名可执行文件；onedir
目录中的 Python、OCR 模型、动态库和其他依赖都是运行所需内容。

## 另一台 Mac 的首次运行与权限

macOS 隐私权限不会随打包产物复制。另一台 Mac 必须给实际运行主体重新授予：

- 辅助功能；
- 屏幕录制；
- 输入监控。

“实际运行主体”可能显示为 Terminal、iTerm、其他终端宿主或 BossOCR 可执行
文件。权限变更后，应完全退出相关终端和 BossOCR 进程，再重新启动。不要假设
开发机上已经授权就代表目标 Mac 也已授权。

## 未签名、未公证限制

本 beta 产物暂时不做代码签名和 Apple notarization。通过 GitHub 下载后，
Gatekeeper 可能阻止首次运行。可以先尝试在 Finder 中右键选择“打开”。只有在
确认下载来源和文件内容可信后，才考虑对完整 onedir 目录解除 quarantine：

```bash
xattr -dr com.apple.quarantine dist/BossOCR
```

解除隔离会降低 Gatekeeper 提供的保护，不应对来源不明的文件执行。每次重新
下载的产物都可能需要重新处理。

## Beta 使用边界

该包仅用于受控 beta 验收，不表示 macOS 已获得无条件业务放行。首次在另一台
Mac 上运行时，应先检查权限和显示器环境，再执行单候选人或很小批量验收。
不要直接用于生产批量运行；如出现页面、坐标、截图、OCR 或权限状态异常，应
立即停止，而不是继续尝试输入动作。
