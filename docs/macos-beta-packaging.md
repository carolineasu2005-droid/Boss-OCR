# BossOCR macOS beta 打包与运行

本方案生成唯一、可从终端运行的 PyInstaller `onedir` 正式产物：

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
6. 验证 `dist/BossOCR/BossOCR` 已生成且可执行；
7. 从临时 CWD 使用绝对路径运行只选择“退出”的安全冒烟，随后删除临时目录；
8. 拒绝包含 `logs/`、`calibration_profiles/`、日志、`.DS_Store` 或 Python 运行时缓存的 onedir。

现有通用 `BossOCR.spec` 不会被修改或调用，因此 Windows 打包流程保持不变。

## 运行

构建完成后，从仓库根目录运行：

```bash
dist/BossOCR/BossOCR
```

分发时必须保留整个 `dist/BossOCR` 目录，不能只复制同名可执行文件；onedir
目录中的 Python、OCR 模型、动态库和其他依赖都是运行所需内容。

正式用户只启动这一个 BossOCR 产物；不提供第二个 App、第二个可执行文件或独立模板工具。无参数启动唯一入口后会显示：

```text
1. 开始运行 BossOCR
2. 创建/更新校准模板
3. 退出
```

模板创建继续复用主程序静态导入的 `calibration_template.py`，在同一进程中完成，成功、取消或失败后均回到主菜单；取消或失败不保存不完整模板。`calibration_template.py` 只作为开发、自动化测试和排障时的直接调用入口，不是正式用户入口。构建脚本会在 PyInstaller 完成后验证：

- `calibration_profiles`、`calibration_steps`、`calibration_template` 均已进入
  PYZ 模块清单；
- onedir 顶层只有 `dist/BossOCR/BossOCR` 一个可执行入口；
- 没有生成 `.app`；
- 没有把 `calibration_profiles/*.json` 用户模板打入产物；
- 安全冒烟产生的日志和其他运行时文件只写入临时 CWD，不污染 `dist/BossOCR`；
- 压缩前 `dist/BossOCR` 不包含日志、模板目录、`.DS_Store` 或 Python 缓存。

## 校准模板路径验证

当前模板目录合同仍是：

```python
PROFILE_DIR = Path("calibration_profiles")
```

因此模板目录相对于进程启动时的当前工作目录，而不是相对于源码或可执行文件。
本次 onedir 验证得到：

| 启动方式 | 实际模板目录 |
| --- | --- |
| 仓库根目录启动源码 | `$PROJECT_ROOT/calibration_profiles` |
| 其他 CWD 启动源码 | `$OTHER_CWD/calibration_profiles` |
| 在 onedir 目录内启动 | `$PROJECT_ROOT/dist/BossOCR/calibration_profiles` |
| 从其他 CWD 启动 onedir | `$OTHER_CWD/calibration_profiles` |

这证明移动 CWD 会改变模板读写位置。本次不切换到 Application Support，不添加双路径搜索或迁移层，也不改变 Windows 当前相对路径合同。调用模板前必须保持 Boss 页面窗口位置、大小和浏览器缩放状态与校准时一致；坐标是绝对屏幕坐标，macOS Retina 门禁已完成实机验证，但不提供自动缩放或跨显示器适配。

非交互运行不会猜测模板。显式加载时传入：

```bash
dist/BossOCR/BossOCR --keywords '"测试关键词"' --auto --calibration-profile "模板名称"
```

不传 `--calibration-profile` 时继续旧手动校准；指定模板不存在、损坏、字段缺失或系统信息不匹配时，非交互流程明确失败且不等待输入。

## 另一台 Mac 的首次运行与权限

macOS 隐私权限不会随打包产物复制。另一台 Mac 必须给实际运行主体重新授予：

- 辅助功能；
- 屏幕录制；
- 输入监控。

“实际运行主体”可能显示为 Terminal、iTerm、其他终端宿主或 BossOCR 可执行
文件。权限变更后，应完全退出相关终端和 BossOCR 进程，再重新启动。不要假设开发机上已经授权就代表目标 Mac 也已授权。权限缺失、坐标门禁不通过、校准取消或校准失败时，应停止当前动作或回到主菜单/旧手动流程，绝不继续盲点。

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
