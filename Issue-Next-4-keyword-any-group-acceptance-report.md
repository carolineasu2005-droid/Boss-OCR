# [Next-4] 关键词规则支持 `any(...)` 分组表达式验收报告

## 验收结论

结论：通过。

本次验收确认 Next-4 已完成 `any(...)` 分组表达式的 parser、matcher、detector 回归和文档范围变更。核心验收范围测试通过，`any(...)` 保持为独立 atom，未被展开为顶层 OR，未破坏既有 `not > and > or` 优先级和纯 `not` 分支安全约束。

全量 `unittest discover` 在非 Next-4 路径的 `test_simple_brush_ocr` 中出现环境性 `KeyboardInterrupt`，中断点位于 `setUp()` 调用 `reset_focus_restore_calibration()` 附近；该测试单独复跑通过。因此本次不判定为 Next-4 阻断，但记录为全量测试未完整跑完的残余风险。

## 实施范围核对

- 新增 `KeywordAnyGroup` 或等价独立 any atom 结构。
- 普通关键词规则继续使用原有 `KeywordTerm`。
- `any(...)` 作为 atom 参与外层 `and` / `or` / `not`。
- 未将 `any(...)` 展开为顶层 OR group。
- 修改范围聚焦于关键词 parser、matcher、OCR detector 回归测试和 README/规则文档。
- 未修改 GUI、真实键鼠、剪贴板、转发流程、打包脚本或 macOS Chrome 相关逻辑。

## 核心语义验收

已确认：

- `any("A","B")` 表示 A 或 B 任意命中。
- `any(...)` 在规则结构中是一个 atom。
- `not any("A","B")` 等价于 `not (A or B)`，不是 `not A or not B`。
- 优先级仍为 `not > and > or`。
- 外层 `or` 仍用于连接完整筛选分支。
- 每个 OR 分支仍必须至少包含一个正向 atom。
- 纯 `not any(...)` 分支仍非法。

## 关键用例

### 防止错误展开

规则：

```text
any("魔方","九州") and any("短剧","漫剧")
```

验收结果：

- 文本 `魔方`：不命中。
- 文本 `短剧`：不命中。
- 文本 `魔方 短剧`：命中。

该用例确认 `any(...)` 未被错误提升为顶层 OR。

### 排除组

规则：

```text
"魔方" and not any("投放","消耗")
```

验收结果：

- 文本 `魔方 投放`：不命中。
- 文本 `魔方 消耗`：不命中。
- 文本 `魔方 剪辑`：命中。
- 文本 `剪辑`：不命中。

### 公司组 + 能力组 + 排除组

规则形态：

```text
any("公司A","公司B")
and any("能力A","能力B")
and not any("排除A","排除B")
```

验收结果：

- 公司组命中 + 能力组命中 + 排除组未命中：命中。
- 公司组未命中：不命中。
- 能力组未命中：不命中。
- 排除组命中：不命中。
- 多个正向组命中但排除组命中：不命中。

### 兼容性

已确认：

- `any("A")` 合法，匹配结果等价于 `"A"`，并保留为 any atom。
- `any("A","B") or "C"` 外层 OR 正常。
- `"A" and any("B","C") or "D" and any("E","F")` 保持既有优先级。
- 旧的 `"A" and "B" or "C"`、`not` 规则、多规则分号语法继续通过。
- NFKC、大小写折叠、去空白等规范化行为与普通关键词一致。

## 非法语法验收

以下非法输入已被测试覆盖并拒绝，错误包含可定位位置：

- `any()`
- `any("")`
- `any("A",)`
- `any(,"A")`
- `any("A" "B")`
- `any("A", not "B")`
- `any("A" and "B")`
- `any(any("A","B"))`
- `any(A,B,C)`
- `any('A','B')`
- `any("A","A")`
- `not any("A","B")`
- `not any("A","B") or "C"`
- `"C" or not any("A","B")`

## 测试结果

### 关键词 parser / matcher 单测

命令：

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ocr_text -v
```

结果：

```text
Ran 36 tests in 0.005s
OK
```

### 核心范围回归

命令：

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_ocr_text tests.test_ocr_detector tests.test_ocr_calibration -v
```

结果：

```text
Ran 62 tests in 0.011s
OK
```

说明：`test_backend_failure_is_fail_closed` 中出现的 `OCR unavailable` traceback 是测试用例主动模拟 OCR 后端异常，最终结果为 `ok`，不属于失败。

### 疑似中断单测复核

命令：

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_simple_brush_ocr.SimpleBrushOCRTests.test_forward_restores_focus_when_forwarding_raises -v
```

结果：

```text
Ran 1 test in 0.001s
OK
```

### 全量测试状态

命令：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：未完整完成。测试执行到非 Next-4 路径 `test_simple_brush_ocr.SimpleBrushOCRTests.test_forward_restores_focus_when_forwarding_raises` 附近时收到 `KeyboardInterrupt`。

判断：

- 该中断不是断言失败。
- 该中断不是 Next-4 parser / matcher / detector 逻辑失败。
- 疑似中断测试单独复跑通过。
- 本次验收将其记录为全量测试残余风险，不作为 Next-4 阻断。

### diff 格式检查

命令：

```powershell
git diff --check
```

结果：无输出，表示通过。

## 风险核对

已确认：

- 不存在 parser 接受 `any(...)` 但 matcher 不支持的状态。
- 未将 `any(...)` 当普通关键词静默处理。
- 未将 `any(...)` 展开为顶层 OR。
- 未新增完整括号表达式。
- 未支持嵌套 `any(...)`。
- 未新增关键词权重、模糊匹配、分词或词边界逻辑。
- 未触发真实键鼠、剪贴板、GUI 或转发操作。

残余风险：

- 全量测试在 `test_simple_brush_ocr` 路径出现非稳定 `KeyboardInterrupt`，虽然疑似中断测试单独复跑通过，但本次没有取得完整全量 `discover` 的最终 `OK`。

## 建议下一步

1. 将本验收报告评论到 Next-4 issue。
2. 提交 Next-4 代码和文档变更。
3. 在 Codex 额度恢复后，可补充排查全量测试中偶发 `KeyboardInterrupt` 的环境原因，但不阻断 Next-4 关键词规则验收。
