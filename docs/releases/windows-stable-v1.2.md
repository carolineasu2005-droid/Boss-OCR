# BossOCR Windows Stable v1.2

## 新增

- 新增通用校准模板模块，支持保存并复用全部 11 个点击区域。
- Windows `BossOCR.exe` 新增“创建或更新校准模板”入口。
- 主程序启动时支持选择已有模板，也可以选择不使用模板并继续原有手动校准流程。
- 新增 `--calibration-profile <模板名称>` 参数。
- 支持多个模板 JSON 并存，保存位置为 `calibration_profiles/<模板名称>.json`。
- 每个模板校准步骤开始前增加约 3 秒等待，便于阅读提示和准备鼠标。

## 兼容性

- 保留原有手动校准流程。
- 不改变收藏、转发、筛选、OCR 和鼠标轨迹逻辑。
- `--no-batch-filter`、`--no-forward` 等既有参数继续有效。
- Windows 正式包仍为包含 `BossOCR.exe` 和 `_internal` 资源的 one-dir 目录，不新增第二个 EXE。
- 本版本不修改 macOS 功能。

## 安全与稳定性

- 模板损坏或字段缺失时不会盲跑。
- 系统信息不匹配时会提示并安全失败或回退到手动流程。
- 非交互模式不会弹出启动菜单或等待输入。
- 模板使用绝对屏幕坐标；调用前必须确保 Boss 页面窗口位置、大小、屏幕分辨率、系统 DPI 和页面缩放与校准时基本一致。

## 验证

- 自动化专项测试和全量测试通过后生成 Windows 正式 one-dir 包。
- 真实 GUI 校准模板创建、模板选择和每步 3 秒等待已通过人工 Windows 冒烟测试。

## 发布文件

- `BossOCR-Windows-x64.zip`
- `BossOCR-Windows-x64.sha256.txt`
