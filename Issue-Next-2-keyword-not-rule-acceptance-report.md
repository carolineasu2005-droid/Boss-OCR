# [Next-2] 验收报告：关键词规则新增 not 排除逻辑

## 1. 验收结论

**验收结论：通过。**

`[Next-2] P2：关键词规则新增 not 排除逻辑` 已按 TID 完成实现、接入、文档和回归验收。4 个产生文件变更的 change 均为独立提交；Change 5 仅执行全量回归和范围验收，按 TID 未创建空 commit。

全量自动化测试 97 项全部通过，生成本报告前工作区干净。`not` 优先级、OR 分支正向关键词约束、旧规则兼容和 OCR 完整规则二次确认均有自动化测试覆盖。

建议进入 Next-3。正式使用前仍建议按第 9 节使用 `--no-forward` 完成真实 OCR 样本验证。

## 2. 实施摘要

- 新增 frozen `KeywordTerm`，区分正向关键词和排除关键词。
- 保留现有 OR-of-AND 规则模型，将 AND group 扩展为正负 term 列表。
- 支持大小写不敏感的 `not` token，优先级为 `not` > `and` > `or`。
- `not` 只能修饰一个英文双引号关键词。
- 每个 OR 分支都必须至少包含一个正向关键词。
- 纯 not 规则和纯 not OR 分支明确报错并包含位置。
- 保持现有 canonical source、分号规则和旧 AND/OR 行为。
- 匹配继续采用 NFKC、小写、去空白后的精确子串判断。
- OCR 二次确认继续重新判断首次命中的完整 `KeywordRule`，包括全部正向和排除条件。
- 普通交互和 `--auto` 均使用同一解析器；非法规则不会静默忽略。
- README 已补充语法、优先级、合法/非法示例、限制及安全建议。

## 3. 提交记录

| Change | Commit | Commit message | 主要内容 |
| --- | --- | --- | --- |
| Change 1 | `3642004` | `feat: add not keyword rule parsing and matching` | 新增 `KeywordTerm`、not 解析、OR 分支正向词验证、正负 term 匹配及 `ocr_text` 测试。 |
| Change 2 | `34797c9` | `test: verify not rules during OCR confirmation` | 增加完整 not 规则的 OCR 首次检测和二次确认测试；生产 detector 无需修改。 |
| Change 3 | `7e053fc` | `feat: expose not keyword rules in startup input` | 更新启动输入提示；验证交互重试、`--auto` 合法/非法规则和完整规则传递。 |
| Change 4 | `d09b734` | `docs: explain not keyword rule syntax` | 更新 README 的语法、优先级、示例、二次确认、限制和安全说明。 |
| Change 5 | 无文件变更 | 不创建空 commit | 执行全量测试、累计 diff、非目标和工作区验收。 |

上述提交连续位于 `origin/main` 的 `70e6a4a` 之后。生成报告前本地 `main` 相对 `origin/main` 为 ahead 4、behind 0。

## 4. 测试结果

### 4.1 全量测试

命令：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：

```text
Ran 97 tests in 0.037s
OK
```

- 通过：97
- 失败：0
- 错误：0
- 跳过：0

### 4.2 专项覆盖

`tests/test_ocr_text.py` 覆盖：

- `not` 排除匹配。
- `not > and > or` 优先级。
- `"A" or not "B" and "C"` 合法结构和语义。
- `"A" and not "B" or "C"` 语义。
- 连接符大小写和 canonical source。
- 引号内 `not` 作为普通关键词正文。
- 纯 not 规则和纯 not OR 分支拒绝。
- 缺少操作数、隐式连接、重复 not、组合取反及括号拒绝。
- 全部旧 AND/OR 规则回归。

`tests/test_ocr_detector.py` 覆盖：

- 两次均满足完整正负规则时确认成功。
- 二次 OCR 出现排除词时确认失败。
- 二次 OCR 缺少正向词时确认失败。
- 混合 OR/AND/NOT 规则按完整规则重新判断。
- 首次 OCR 已含排除词时不启动二次确认。

`tests/test_simple_brush_ocr.py` 覆盖：

- 完整 not 规则传给 detector。
- `--auto` 解析合法 not 规则。
- `--auto` 在纯 not 分支非法时于打开 Edge 前失败。
- 普通交互模式报错后重新输入。
- `--no-forward` 和 Next-1 相关回归测试继续通过。

### 4.3 其他检查

- `git diff --check`：通过。
- 工作区：生成报告前干净。
- `ocr_detector.py` 生产代码：无变更。
- `ocr_calibration.py`：无变更。
- `simple_brush.py` 仅修改输入提示和格式示例。

### 4.4 未执行测试

未执行真实 Windows Edge OCR 页面手工测试，也未执行真实邮件转发。原因是本次验收以自动化语义、parser、detector 和接入测试为主；该需求不需要真实邮件发送。建议按第 9 节使用 `--no-forward` 验证真实 OCR 样本。

## 5. 验收标准对照

| 验收标准 | 结果 | 证据 |
| --- | --- | --- |
| `not` 优先级高于 `and` 和 `or` | 通过 | parser 将 `not` 解析为 term 属性，AND group 先于 OR 分组；优先级专项测试通过。 |
| `not` 只能修饰一个英文双引号关键词 | 通过 | `parse_term()` 要求 `not` 后直接出现英文双引号关键词；重复 not、括号和缺少引号均报错。 |
| 每条规则至少有一个正向关键词 | 通过 | 更严格地在每个 OR 分支完成时验证至少一个 `negated=False` term。 |
| 每个 OR 分支至少有一个正向关键词 | 通过 | `finish_group()` 对每个分支执行验证；首个和末尾纯 not 分支测试均通过。 |
| 纯 `not` 规则被拒绝 | 通过 | `not "销售"` 抛出带位置的 `KeywordRuleSyntaxError`。 |
| `not "销售" or "短剧"` 被拒绝 | 通过 | 首个 OR 分支仅含排除 term，在进入下一分支前被拒绝。 |
| `"短剧" or not "销售"` 被拒绝 | 通过 | 末尾 OR 分支仅含排除 term，在规则结束时被拒绝。 |
| `"A" or not "B" and "C"` 合法 | 通过 | 第二分支解析为 `not "B"` 与正向 `"C"` 的 AND group；结构和匹配测试通过。 |
| `"短剧" and not "销售"` 正确匹配 | 通过 | 含“短剧”且不含“销售”时命中；同时包含两词时不命中。 |
| 旧规则 `"A" and "B" or "C"` 行为不变 | 通过 | 旧 AND、OR、优先级、分号、canonical source 和错误格式测试全部通过。 |
| 二次确认使用完整规则 | 通过 | detector 将 `first.matched_rule` 作为完整规则传入第二次 `_observe()`；排除词出现和正向词消失测试均导致确认失败。 |
| 错误格式明确报错 | 通过 | 非法 not 规则抛出 `KeywordRuleSyntaxError`，信息包含原因和一基位置；交互模式允许重新输入，自动模式阻止启动。 |
| 不支持括号 | 通过 | `not ("销售" or "运营")` 和普通括号表达式均被拒绝。 |
| 不支持数值比较 | 通过 | 未新增比较 token、数值 AST 或求值逻辑；README 明确不支持。 |
| 不支持 `not` 修饰组合表达式 | 通过 | `not` 后只能由 parser 接受一个英文双引号关键词。 |
| 不引入通用表达式引擎或 `eval` | 通过 | 继续使用局部顺序扫描器；代码范围检查未发现 `eval`。 |
| 不重构 OCR 或转发流程 | 通过 | detector 生产代码和转发流程未修改；simple_brush 仅更新提示。 |

## 6. 规则语义确认

| 规则 | 合法性 | 语义或结果 |
| --- | --- | --- |
| `"短剧" and not "销售"` | 合法 | 文本必须包含“短剧”且不能包含“销售”。 |
| `"A" or "B" and not "C"` | 合法 | 等价于 `"A" or ("B" and (not "C"))`。 |
| `"A" and not "B" or "C"` | 合法 | 等价于 `("A" and (not "B")) or "C"`。 |
| `"A" or not "B" and "C"` | 合法 | 等价于 `"A" or ((not "B") and "C")`；第二个 OR 分支包含正向关键词 `"C"`。 |
| `not "销售"` | 非法 | 整条规则为纯 not 分支，缺少正向关键词。 |
| `not "销售" or "短剧"` | 非法 | 第一个 OR 分支为纯 not 分支。 |
| `"短剧" or not "销售"` | 非法 | 第二个 OR 分支为纯 not 分支。 |

其他确认：

- `"A" AND NOT "B" Or "C"` 会规范化为 `"A" and not "B" or "C"`。
- 引号内的 `"not for sale"` 是普通正向关键词，不解析其中的 `not`。
- 多条分号规则仍按输入顺序独立匹配。

## 7. 非目标确认

对 `origin/main...HEAD` 的累计文件和代码差异进行了检查：

- 未实现 macOS Chrome。
- 未修改 Next-1 焦点恢复校准代码；`ocr_calibration.py` 无差异。
- 未实现 P3 日志或 P4 数值匹配。
- 未支持括号。
- 未支持数值比较。
- 未支持 `not` 修饰组合表达式。
- 未新增 DOM 读取。
- 未引入 Selenium、Playwright、WebDriver 或其他浏览器驱动。
- 未新增页面状态识别或转发成功检测。
- 未引入通用表达式引擎或 `eval`。
- 未重构 OCR detector 或邮件转发主流程。

累计变更文件仅为：

- `ocr_text.py`
- `simple_brush.py`
- `README.md`
- `tests/test_ocr_text.py`
- `tests/test_ocr_detector.py`
- `tests/test_simple_brush_ocr.py`

## 8. 风险与限制

- OCR 漏识别排除词时，原本应被排除的文本可能错误命中。
- OCR 误识别出排除词时，原本应命中的文本可能被错误排除。
- `not` 仍采用标准化后的精确子串匹配，不是分词、词边界或语义匹配。
- 过短排除词，例如 `"A"`，可能在大量英文内容中出现并造成误伤。
- 二次确认可降低偶发 OCR 误差，但不能消除两次都漏识别或误识别的情况。
- 不支持括号，复杂逻辑必须拆成符合固定优先级的规则或多条分号规则。
- 不支持数值比较、正则表达式、模糊匹配或组合取反。
- parser 的规则结构从字符串 term 升级为 `KeywordTerm`；当前仓库调用方已完成回归，但外部未纳入仓库的直接结构访问者需要同步适配。

## 9. 手工验证建议或结果

### 9.1 当前结果

本次验收未执行真实 Windows Edge OCR 手工测试，也未发送真实邮件。自动化测试结果为 97/97 通过。

### 9.2 建议步骤

1. 在 Windows Edge 打开受控测试页面或测试账号。
2. 使用普通交互模式和 `--no-forward`：

   ```powershell
   .\venv\Scripts\python.exe simple_brush.py --no-forward
   ```

3. 输入：

   ```text
   "短剧" and not "销售"
   ```

4. 验证只含“短剧”的样本能够命中。
5. 验证同时含“短剧”和“销售”的样本不命中。
6. 输入 `not "销售"`，确认明确报错并允许重新输入。
7. 输入 `not "销售" or "短剧"` 与 `"短剧" or not "销售"`，确认均被拒绝。
8. 输入 `"A" or not "B" and "C"`，确认可以启动且日志显示完整 canonical source。
9. 观察首次 OCR 和二次确认；第二次出现排除词时必须不确认。
10. 全程保持 `--no-forward`，本需求不需要真实邮件转发验证。

## 10. 是否可以进入 Next-3

**可以进入 Next-3。**

理由：Next-2 的语法、数据结构、匹配、完整规则二次确认、启动接入、错误处理和文档均符合 TID；全量测试和范围检查通过，未发现需要在本 Issue 内继续修复的阻塞问题。建议在正式启用 not 规则前完成第 9 节真实 OCR 样本安全验证。
