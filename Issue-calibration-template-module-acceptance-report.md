# 校准模板模块验收报告

## 1. 文档信息

- 模块名称：BossOCR 通用校准模板模块
- 关联 PRD：`PRD-calibration-template-module.md`
- 关联 TID：`TID-calibration-template-module.md`
- 验收范围：Change 1 至 Change 9
- 验收日期：2026-07-10
- 当前结论：自动化验收通过；真实 Boss 页面人工冒烟仍需在目标设备上执行

## 2. 验收结论摘要

当前实现符合 PRD/TID 的最小可行范围：校准模板作为新增参数来源接入，不改写收藏、转发、筛选、OCR、鼠标轨迹或人类化点击核心业务逻辑。

已实现独立模板生成入口、模板 JSON 读写校验、校准步骤注册表、交互模式模板选择、运行时字段注入、非交互 `--calibration-profile` 显式加载、异常回退与测试/冒烟说明。

## 3. 范围核对

| 核对项 | 结论 |
|---|---|
| 不改写收藏、转发、筛选、OCR、鼠标轨迹、人类化点击核心业务逻辑 | 通过 |
| 模板只是新增参数来源 | 通过 |
| 不使用模板时旧手动校准流程仍可用 | 通过 |
| 非交互模式未指定 `--calibration-profile` 时旧行为不变 | 通过 |
| 未新增复杂模板管理器 | 通过 |
| 未新增模板重命名、删除、复制、导入导出、健康评分、图形化管理器 | 通过 |
| 未做浏览器窗口识别、页面缩放识别、坐标缩放换算、跨设备自动适配 | 通过 |
| 未新增第二个发布 EXE | 通过 |

## 4. 字段与模板结构核对

模板 `areas` 字段复用当前代码已有字段名：

```text
first_candidate
open_filter
unseen_filter
confirm_filter
forward_icon
email_tab
recent_email
input_box
forward_button
focus_restore_region
favorite_button_region
```

模板结构符合 TID：

```json
{
  "schema_version": "1.0",
  "profile_name": "...",
  "created_at": "...",
  "system_info": {
    "os": "...",
    "screen_width": 1920,
    "screen_height": 1080,
    "dpi_scale": 1.0
  },
  "areas": {
    "first_candidate": {
      "left": 0,
      "top": 0,
      "width": 100,
      "height": 50
    }
  }
}
```

核对结论：

- 使用 `left/top/width/height`，未使用 `x/y`。
- 区域保存为矩形区域，不保存单点。
- 模板加载后还原为 `ScreenRegion`。
- 点击继续走现有区域随机取点与 `human_click()` 路径。

## 5. 主程序接入核对

| 核对项 | 结论 |
|---|---|
| 主程序启动时检测 `calibration_profiles/` | 通过 |
| 交互模式可以选择使用模板 | 通过 |
| 交互模式可以选择不使用模板并走旧手动校准 | 通过 |
| 无模板时旧流程不受影响 | 通过 |
| 模板损坏时不闪退 | 通过 |
| 模板字段缺失时不盲跑 | 通过 |
| 系统信息不匹配时有风险提示 | 通过 |
| 使用模板后可注入 `ForwardClickRegions` | 通过 |
| 使用模板后可注入 `BatchFilterRegions` | 通过 |
| 使用模板后可注入 `focus_restore_region` | 通过 |
| 使用模板后可注入 `favorite_button_region` | 通过 |
| `--no-batch-filter` 优先级高于模板筛选字段 | 通过 |
| `--no-forward` 不被模板加载破坏 | 通过 |

## 6. 非交互模式核对

| 核对项 | 结论 |
|---|---|
| 支持 `--calibration-profile <profile_name>` | 通过 |
| 未指定模板时不自动猜模板 | 通过 |
| 不弹出模板选择菜单 | 通过 |
| 不等待用户输入 | 通过 |
| 指定不存在模板时安全失败 | 通过 |
| 指定损坏模板时安全失败 | 通过 |
| 指定字段缺失模板时安全失败 | 通过 |
| 指定系统信息不匹配模板时安全失败 | 通过 |
| 不破坏 `--auto`、`--keywords`、`--no-batch-filter`、`--no-forward` | 通过 |

## 7. 异常回退核对

| 异常场景 | 结论 |
|---|---|
| `calibration_profiles/` 目录不存在 | 通过 |
| 模板列表为空 | 通过 |
| 模板 JSON 解析失败 | 通过 |
| `schema_version` 不支持 | 通过 |
| `system_info` 缺失 | 通过 |
| `areas` 缺失 | 通过 |
| 必填区域字段缺失 | 通过 |
| 区域字段类型错误 | 通过 |
| 区域 `width/height` 为 0 或负数 | 通过 |
| OS / 分辨率 / DPI 不匹配 | 通过 |
| 用户取消某一步校准 | 通过 |
| 同名模板覆盖确认 | 通过 |
| 模板加载成功但运行时注入失败 | 通过 |

交互模式异常处理结论：优先提示用户并回退旧手动校准流程。

非交互模式异常处理结论：不阻塞、不等待输入，模板不可安全使用时失败返回，不继续盲跑。

## 8. 自动化测试结果

已运行专项测试：

```text
.\venv\Scripts\python.exe -m unittest tests.test_calibration_profiles -v
Ran 18 tests
OK

.\venv\Scripts\python.exe -m unittest tests.test_calibration_steps -v
Ran 7 tests
OK

.\venv\Scripts\python.exe -m unittest tests.test_calibration_template -v
Ran 5 tests
OK
```

已运行全量测试：

```text
.\venv\Scripts\python.exe -m unittest discover -s tests -v
Ran 263 tests
OK
```

格式检查：

```text
git diff --check
无 whitespace error，仅有 CRLF/LF 换行提示
```

## 9. 人工冒烟状态

以下项目需要在真实 Boss 页面、目标设备、目标分辨率和 DPI 下人工执行：

1. 无模板时旧手动校准流程仍可用。
2. 独立校准入口可生成模板。
3. 同名模板覆盖提示正常。
4. 主程序启动后能看到模板列表。
5. 选择不使用模板时旧流程正常。
6. 选择模板后收藏模式可读取收藏相关区域。
7. 选择模板后转发模式可读取转发相关区域。
8. 破坏模板 JSON 后程序提示并回退。
9. 删除必填字段后程序提示并回退。
10. 不同分辨率或 DPI 下加载模板出现风险提示。
11. 保持 Boss 页面窗口位置、大小、缩放一致时点击区域无明显偏移。
12. 使用模板前出现窗口位置、大小、缩放一致性提示。

详细步骤见 `docs/calibration-template-smoke-test.md`。

## 10. 风险与边界

- 模板坐标仍是绝对屏幕坐标，窗口位置、窗口大小、系统 DPI 或浏览器缩放变化后可能误点击。
- 本阶段不做坐标缩放换算、不识别浏览器窗口、不判断页面布局变化。
- 多设备之间模板不保证通用，每台设备建议单独校准。
- 当前未新增第二个发布 EXE；源码入口为 `calibration_template.py`。

## 11. 最终建议

自动化验收已通过。建议完成真实页面人工冒烟后，再提交 Change 1 至 Change 9。

建议提交信息：

```text
feat: add reusable calibration profile workflow
```
