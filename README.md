# BossOCR

BossOCR 是一个面向 Windows 的 BOSS 直聘候选人简历辅助浏览工具。它使用鼠标和键盘模拟完成候选人切换，通过本地 RapidOCR 识别屏幕上当前候选人的可见简历内容；只有关键词经过两次 OCR 精确确认后，程序才允许进入已有的邮件转发流程。

项目不读取网页 DOM，不调用 BOSS 接口，也不使用 Selenium、Playwright、WebDriver、浏览器调试端口或 JavaScript 注入。OCR 和关键词匹配全部在本机完成。

> 使用前请确认你的操作符合 BOSS 直聘服务条款、招聘合规要求和个人信息保护规定。程序包含真实鼠标/键盘自动化，必须先在 `--no-forward` 安全模式下验证。

## 下载与运行

推荐从 [GitHub Releases](https://github.com/carolineasu2005-droid/Boss-OCR/releases/latest) 下载 `BossOCR-Windows-x64.zip`。

1. 解压整个 ZIP，不能只复制 `BossOCR.exe`。
2. 在 Microsoft Edge 登录 BOSS 直聘并打开“推荐牛人”页面。
3. 把 Edge 放在主显示器上，不要最小化。
4. 首次测试双击 `安全测试_只检测不转发.bat`。
5. 输入关键词，多个关键词用英文分号 `;` 分隔。
6. 将鼠标放到第一位候选人卡片上。
7. 第一位候选人详情打开后，在半透明界面中框选详情正文区域。
8. 观察日志和实际页面，确认 OCR 命中正确后，再考虑使用 `正式运行.bat`。

运行期间：

- `空格`：暂停或继续
- `Esc`：安全停止

Windows SmartScreen 可能提示“未知发布者”，因为当前 EXE 没有商业代码签名证书。请从本仓库 Release 下载并核对 SHA-256 后再运行。

## 工作原理

### 1. 打开当前候选人

程序启动后将标题包含 `BOSS` 或 `zhipin`、且进程名严格为 `msedge.exe` 的窗口置前。倒计时结束后，它只点击一次用户预先放置鼠标的位置，打开第一位候选人详情。

后续候选人使用键盘右方向键切换；每浏览 100 位候选人后按 `F5` 刷新。这些行为与 OCR 模块相互独立。

### 2. 首次检测时拖框校准

第一位候选人详情已经打开后，程序才显示 Tk 半透明拖框。用户框选当前候选人的详情正文区域，程序记录：

```text
left, top, width, height
```

校准区域只保存在本次运行的内存中，程序重启后需要重新框选。校准完成时会通过 MSS 对同一区域截图，并保存预览到：

```text
logs/ocr_calibration_preview.png
```

Windows 下程序启用 Per-Monitor V2 DPI 感知，并将 Tk 的界面坐标换算成 MSS 使用的物理像素坐标。当前第一版只支持主显示器；多显示器混合 DPI 环境应把 Edge 移到主显示器。

### 3. 局部屏幕截图

OCR 只截取拖框区域内当前真实可见的像素，不会截取浏览器整页，也不会读取被详情遮挡的底层候选人列表文本。这解决了旧方案通过 `Ctrl+A` / `Ctrl+C` 复制整个网页时，其他候选人的关键词可能误触发当前候选人的问题。

截图后端使用 `mss`，像素数据直接在内存中交给 RapidOCR。除校准预览外，不需要把每一屏保存到磁盘。

### 4. RapidOCR 本地识别

程序启动时创建一个 RapidOCR 实例，并在整个运行期间复用。推理由 ONNX Runtime CPU 后端执行，默认包含三个本地模型：

- 文字检测模型
- 文字方向分类模型
- 中文/英文文字识别模型

模型随 Windows Release 一起分发，不需要把候选人截图上传到外部 OCR 服务。

每个 OCR 文字框包含文字、位置和置信度。低于 `0.85` 的文字框不会参与关键词匹配。剩余文字框按自适应行高从上到下、同行从左到右排序。

### 5. 标准化后的精确匹配

OCR 文本与用户关键词执行相同的标准化：

- Unicode NFKC 全角/半角归一化
- 英文字母转小写
- 删除换行和布局空白

之后只执行标准化后的精确子串匹配：

```text
normalized_keyword in normalized_ocr_text
```

程序不做编辑距离、相似字替换、拼音匹配、同义词推断、语义匹配或大模型判断。例如关键词“短剧”不会因为 OCR 识别成相似但不同的字符而模糊命中。

### 6. 最多 8 屏有序扫描

每位候选人的第一屏直接截图识别。未命中时，程序始终向下滚动约 5–7 格，等待页面稳定约 `0.6` 秒后继续截图，最多扫描 8 屏。

```text
第一屏 OCR
    ↓ 未命中
向下滚动并等待稳定
    ↓
第二屏 OCR
    ↓
……最多第八屏
```

OCR 扫描耗时计入原有每位候选人 12–18 秒停留预算；扫描结束后不会再完整等待一轮 12–18 秒。OCR 等待和滚动期间仍响应空格暂停与 Esc 停止。

### 7. 同一关键词二次确认

首次识别到关键词后，程序不会立即转发。它保持当前滚动位置，等待约 `0.7` 秒，对同一区域再次截图和 OCR。两次都命中同一个关键词，才产生 `confirmed_match=True`。

以下情况全部禁止转发：

- OCR 引擎初始化失败
- 用户取消或未完成拖框
- MSS 截图失败
- OCR 调用异常
- OCR 返回空结果
- 只有低置信度文字命中
- 第二次 OCR 未确认同一关键词

失败时不会回退到网页全选复制方案。

### 8. 转发安全门

`--no-forward` 模式仍会完整执行拖框、OCR、滚动、二次确认和日志记录，但即使命中也不会调用邮件转发函数。这是首次部署和关键词验收必须使用的模式。

正式模式下，只有二次确认命中才会调用原有 `forward_one_candidate()`。邮件图标、标签页、邮箱输入框、最近联系人和转发按钮仍使用固定屏幕坐标；邮箱输入框内部保留剪贴板检查逻辑，但候选人关键词检测完全不使用剪贴板。

## 命令行用法

安全检测，不发送邮件：

```powershell
BossOCR.exe --keywords "Python;短剧" --no-forward --auto
```

源码环境：

```powershell
venv\Scripts\python.exe simple_brush.py --keywords "Python;短剧" --no-forward --auto
```

正式模式示例：

```powershell
BossOCR.exe --keywords "Python;短剧" --email "backup@example.com" --auto
```

| 参数 | 作用 |
| --- | --- |
| `--keywords` | 检测关键词；多个关键词用英文分号分隔 |
| `--email` | 最近联系人没有邮箱时使用的备用邮箱 |
| `--no-forward` | 完整执行 OCR，但禁止真实邮件转发 |
| `--auto` | 跳过交互输入，直接使用命令行参数 |

不提供关键词时，OCR 和自动转发均禁用，只执行候选人浏览。

## 从源码运行

### 环境要求

- Windows 10/11 x64
- Python 3.10 或更高版本（推荐 Python 3.11 x64）
- Microsoft Edge
- Edge 位于主显示器

### 安装

双击：

```text
setup.bat
```

或手动执行：

```powershell
py -3.11 -m venv venv
venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr.txt
```

启动：

```powershell
venv\Scripts\python.exe simple_brush.py --keywords "测试关键词" --no-forward --auto
```

运行测试：

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 代码结构

```text
simple_brush.py      主循环、窗口控制、候选人切换、暂停/停止和邮件转发安全门
ocr_calibration.py   Tk 拖框、Windows DPI 坐标换算、校准预览
ocr_detector.py      MSS 截图、RapidOCR 适配、8 屏扫描和二次确认
ocr_text.py          OCR 文字框排序、文本标准化和精确关键词匹配
tests/               校准、OCR、失败关闭、no-forward 和主流程测试
```

## 日志与隐私

运行数据统一保存在 `logs/`，该目录已被 Git 忽略：

```text
logs/simple_brush.log
logs/ocr_calibration_preview.png
logs/ocr_hits/
```

日志至少记录 OCR 初始化、校准区域、扫描序号、OCR 耗时、文字框数量、命中关键词、二次确认、错误和安全跳过原因。

校准预览和命中截图可能包含候选人个人信息。不要提交、上传、分享或长期保留 `logs/`，并按适用的数据保护规则定期清理。

## 当前限制

- 第一版只支持主显示器拖框；混合 DPI 多显示器尚未支持。
- OCR 只识别当前屏幕可见内容，遮挡、动画、加载状态和字体清晰度会影响结果。
- 每位候选人固定最多扫描 8 屏，不判断简历视觉底部。
- 邮件转发仍依赖固定屏幕坐标，分辨率、系统缩放、浏览器缩放和页面布局变化都可能造成误点。
- EXE 当前未进行商业代码签名。
- 自动化工具不能替代人工招聘判断；正式启用前应使用 `--no-forward` 人工核对足够样本。

## 安全建议

1. 新电脑、新分辨率或页面布局变化后，先使用 `--no-forward`。
2. 人工核对关键词在首屏、后续屏、无关键词和二次确认失败等场景。
3. 确认 `logs/` 中没有 OCR 或截图错误。
4. 仅在测试邮箱小规模验证后再启用正式转发。
5. 发现误点或异常时立即按 Esc。
