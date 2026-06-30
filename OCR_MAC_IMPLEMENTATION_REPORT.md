# RapidOCR Mac 阶段实施报告

实施日期：2026-06-30

实施分支：`feature/rapidocr-mac`

## 一、实施范围

本阶段只完成可在私人 Mac 上开发和验证的跨平台 OCR 关键词检测能力。

本阶段没有修改：

- `simple_brush.py`；
- 邮件转发流程；
- 邮箱填写和验证逻辑；
- 鼠标转发坐标；
- 候选人翻页逻辑；
- 停留和随机浏览逻辑；
- 每 100 人刷新逻辑；
- Windows 启动脚本。

OCR 核心尚未接入 Windows 主程序，避免在 Mac 无法验证 Windows 页面和操作流程的情况下扩大改动范围。

## 二、Git 基线与分支

实施前已在 `main` 保存调查与设计文档：

```text
37c5c70 docs: document RapidOCR migration plan
```

随后创建分支：

```text
feature/rapidocr-mac
```

## 三、已完成模块

### `ocr_text.py`

完成：

- OCR 文字框数据结构；
- 按屏幕位置恢复基本阅读顺序；
- Unicode NFKC 全半角标准化；
- 英文字母小写化；
- 去除换行和布局空白；
- 标准化后的精确子串匹配；
- 最低置信度过滤；
- 不包含任何模糊匹配。

### `ocr_calibration.py`

完成：

- `tkinter` 半透明全屏拖框；
- 支持任意拖动方向；
- 过小区域拒绝；
- `Esc` 取消；
- 输出 `left/top/width/height`；
- 使用 `mss` 截取校准预览；
- 使用 Pillow 保存预览图片。

### `ocr_detector.py`

完成：

- `mss` 局部屏幕截图后端；
- RapidOCR 延迟加载；
- RapidOCR 3.x 结果对象适配；
-旧版 `(lines, elapsed)` 返回格式适配；
- OCR 引擎单实例复用接口；
- 固定最大扫描次数；
- 扫描之间调用可注入滚动函数；
- 置信度过滤；
- 精确关键词检测；
- 命中后二次 OCR 确认；
- OCR 异常时失败关闭，不返回命中；
- 结构化扫描结果和观察记录。

### `ocr_mac_demo.py`

完成 Mac 屏幕校准演示入口：

```text
手动拖框
→ 保存校准预览
→ RapidOCR 识别当前屏幕区域
→ 二次确认关键词
```

预期使用方式：

```bash
python ocr_mac_demo.py --keywords "数字媒体;Python"
```

macOS 首次运行屏幕截图时，需要在“系统设置 → 隐私与安全性 → 屏幕录制”中允许所使用的终端或 IDE。

### `ocr_fixture_demo.py`

完成静态截图序列测试入口。它可以在 Mac 上用多张图片模拟候选人详情向下滚动：

```bash
python ocr_fixture_demo.py \
  screenshots/scan_01.png \
  screenshots/scan_02.png \
  screenshots/scan_03.png \
  --keywords "数字媒体;Python"
```

每张图片视为一屏；扫描次数由图片数量决定。命中后会在同一张图片上再识别一次完成二次确认。

### `requirements-ocr-mac.txt`

新增独立 Mac OCR 依赖清单：

- RapidOCR；
- ONNX Runtime；
- mss；
- Pillow；
- NumPy。

它与现有 Windows `requirements.txt` 分离，避免在 Mac 上安装 `pywin32`。

## 四、自动化测试

新增 13 个测试，覆盖：

- 正向和反向拖框；
- 过小区域拒绝；
- 全半角和空白标准化；
- 跨 OCR 行的精确关键词；
- 相似字不得模糊命中；
- 低置信度文字排除；
- 文字框阅读顺序；
- 命中必须二次确认；
- 二次确认失败不得触发；
- 固定扫描次数；
- 页面之间的滚动调用次数；
- OCR 后端异常时失败关闭；
- RapidOCR 新旧结果格式。

执行命令：

```bash
PYTHONPYCACHEPREFIX=/tmp/boss_resume_pycache \
python3 -m unittest discover -s tests -v
```

执行结果：

```text
Ran 13 tests
OK
```

同时已完成全部新增 Python 文件的语法编译检查，以及 `git diff --check`。

## 五、当前 Mac 环境限制

本机环境为：

```text
macOS Apple Silicon arm64
Python 3.9.6（系统自带）
tkinter 可用
Homebrew 未安装
```

已经建立隔离目录 `.venv-mac/` 并加入 `.gitignore`，但真实 RapidOCR、ONNX Runtime 和 `mss` 依赖未在本机成功完成安装。

具体原因：

- 沙箱内 pip 无法直接访问包索引；
- 受控联网安装没有完成包解析和下载；
- 系统 Python 3.9 与较新的 OCR 工具链相比偏旧；
- 本机没有可直接使用的 Homebrew Python 3.10+。

因此本报告不把以下事项标记为已验证：

- RapidOCR 模型在本机真实加载；
- 中文截图的真实模型识别率；
- 单屏实际推理耗时；
- macOS 屏幕录制权限下的真实区域截图；
- Retina 坐标与实际像素的端到端校准。

目前的验证基于可注入假 OCR 后端和假截图后端，核心状态机、匹配规则和安全行为已经自动化验证。

## 六、建议的 Mac 实机联调环境

后续在具备正常依赖下载条件的 Mac 终端中，建议使用 Python 3.10 或更高版本：

```bash
python3.11 -m venv .venv-mac
source .venv-mac/bin/activate
python -m pip install -r requirements-ocr-mac.txt
```

安装完成后依次执行：

```bash
python -m unittest discover -s tests -v
python ocr_fixture_demo.py <截图1> <截图2> --keywords "测试关键词"
python ocr_mac_demo.py --keywords "测试关键词"
```

候选人截图不得提交到 Git，应保存在已忽略的 `logs/` 或其他本地私密目录。

## 七、安全设计结果

本阶段实现遵循以下安全行为：

- OCR 无结果时不命中；
- OCR 抛出异常时不命中；
- 低置信度文字不参与匹配；
- 只允许标准化后的完整关键词命中；
- 不实施模糊匹配；
- 首次命中必须二次确认；
- 二次确认失败时不命中；
- 不回退到网页 `Ctrl+A` 全文检测；
- 不读取 DOM；
- 不接入浏览器自动化接口。

## 八、Windows 阶段仍需完成

以下工作有意留到公司 Windows 电脑：

1. 安装并验证 Windows OCR 依赖；
2. 验证拖框在 Windows DPI 缩放下的物理像素坐标；
3. 验证真实 BOSS 页面截图范围；
4. 确定单次向下滚动距离；
5. 确定最终最大扫描次数；
6. 将 `OCRKeywordDetector` 最小接入原 `detect_keywords()`；
7. 把原浏览滚动与 OCR 有序扫描的时间协调好；
8. 首先以“只检测、不转发”模式人工核对；
9. 使用测试邮箱小规模验证；
10. 确认邮件转发函数和其他流程没有行为变化。

## 九、最终状态

Mac 阶段已经完成可独立测试的跨平台 OCR 核心、手动拖框、局部截图适配、固定次数扫描、精准匹配和二次确认。

由于当前 Mac 缺少可用的现代 Python/OCR 安装环境，真实 RapidOCR 模型联调尚未完成；Windows 主程序也尚未接入。这两个边界均已通过模块隔离保留，不影响现有 `simple_brush.py` 和邮件转发代码。
