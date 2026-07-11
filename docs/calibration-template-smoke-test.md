# 通用校准模板冒烟验收说明

本文档用于验收 BossOCR 通用校准模板模块。Change 9 只补充测试与验收说明，不新增功能、不改变模板数据结构、不改变 CLI 行为。

## 自动化测试

运行全量测试：

```powershell
venv\Scripts\python.exe -m unittest discover -s tests -v
```

校准模板模块的自动化覆盖应包含：

1. 模板文件名安全化。
2. 模板保存与读取。
3. 多模板扫描。
4. JSON 损坏。
5. `schema_version` 不支持。
6. `areas` 缺失。
7. 必填字段缺失。
8. 区域 `width` / `height` 非法。
9. `ScreenRegion` 与模板区域转换。
10. 系统信息匹配与不匹配。
11. 模板注入 `ForwardClickRegions`。
12. 模板注入 `BatchFilterRegions`。
13. `focus_restore_region` 注入。
14. `favorite_button_region` 注入。
15. `--calibration-profile` 参数解析。
16. 非交互模式未指定模板时旧行为不变。
17. 非交互模式指定坏模板时失败。
18. `--no-batch-filter` 优先级高于模板筛选字段。

## 人工冒烟前置条件

1. Microsoft Edge 已登录 BOSS 直聘，并打开可测试的候选人页面。
2. 使用测试账号、测试关键词和安全参数，首次验证建议开启 `--no-forward`。
3. 校准与运行时保持同一台设备、同一主显示器、同一 Boss 页面窗口位置、窗口大小和浏览器缩放。
4. 调用校准模板前，确认程序出现以下提示：

```text
调用校准模板前，请确保 Boss 页面窗口位置、大小、缩放状态与校准时基本一致。
如果窗口位置、窗口大小或页面缩放发生变化，旧模板中的点击区域可能发生偏移，建议重新校准。
```

## 手工冒烟清单

1. 无模板时启动主程序，确认旧手动校准流程仍可用。
2. 运行独立校准入口并生成模板：

```powershell
venv\Scripts\python.exe calibration_template.py
```

3. 使用相同模板名称再次运行独立校准入口，确认同名模板覆盖需要用户确认。
4. 启动主程序交互模式，确认能看到已有模板列表。
5. 在模板选择界面选择不使用模板，确认继续进入旧手动校准流程。
6. 选择使用模板并进入收藏模式，确认收藏模式可读取收藏按钮、筛选、首位候选人和焦点恢复相关区域。
7. 选择使用模板并进入转发模式，确认转发模式可读取转发按钮、邮箱 Tab、最近转发、输入栏、确认转发、筛选、首位候选人和焦点恢复相关区域。
8. 故意破坏某个模板 JSON，确认程序提示错误并回退，不闪退、不盲跑。
9. 删除模板中的某个必填字段，确认程序提示字段缺失并回退，不继续执行不完整模板。
10. 在不同分辨率或 DPI 下加载模板，确认交互模式出现风险提示；非交互模式应明确失败。
11. 保持 Boss 页面窗口位置、大小、缩放状态与校准时一致，确认点击区域不发生明显偏移。
12. 使用模板前确认窗口位置、大小、缩放一致性提示已经出现。

## 非交互模式检查

未指定模板时，非交互模式不应扫描或猜测模板：

```powershell
venv\Scripts\python.exe simple_brush.py --keywords '"测试关键词"' --no-forward --auto
```

显式指定模板时，非交互模式应只加载指定模板；模板不存在、损坏、字段缺失或系统信息明显不匹配时应失败，不等待用户输入：

```powershell
venv\Scripts\python.exe simple_brush.py --keywords '"测试关键词"' --no-forward --auto --calibration-profile "模板名称"
```

`--no-batch-filter` 优先级高于模板中的筛选区域：

```powershell
venv\Scripts\python.exe simple_brush.py --keywords '"测试关键词"' --no-forward --auto --no-batch-filter --calibration-profile "模板名称"
```

## 打包说明

本 Change 不修改打包流程，也不新增第二个 EXE。当前源码运行入口为 `calibration_template.py`；如果后续发布包需要暴露独立校准入口，应在发布验收时确认 `calibration_profiles.py`、`calibration_steps.py`、`calibration_template.py` 已被收集，并单独评估是否需要更新 PyInstaller spec 或批处理入口。
