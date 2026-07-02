# BossOCR Windows Stable v1.0

BossOCR Windows Stable v1.0 是面向 Windows 10/11 x64 + Microsoft Edge 的稳定发布版。本版将 Issue #1 的最小可行改动、OCR 本地识别以及后续 Next-1 至 Next-3 稳定性工作整合为一个可直接解压运行的 Windows 发布包。

## 包含功能

- Issue #1 最小可行改动：
  - 转发后恢复候选人详情页键盘焦点。
  - 增加 OCR 滚动幅度。
  - 支持本次运行自动停止时间。
  - 支持英文双引号关键词以及 `and` / `or` 规则。
- Next-1：转发处理退出前的焦点恢复区域支持启动前校准，未校准时使用 X `400-500`、Y `350-400` 的默认区域。
- Next-2：关键词规则支持 `not` 排除逻辑，优先级为 `not > and > or`，并拒绝纯 `not` OR 分支。
- Next-3：完整邮件转发流程的五个关键点击对象支持运行期区域校准：
  - 转发入口。
  - 邮件转发 Tab。
  - 邮箱输入框。
  - 最近联系邮箱。
  - 最终转发按钮。
- 五个转发区域校准全部成功后才原子提交；取消或失败时整组回退到现有默认区域。
- `--no-forward` 模式可在不触发真实邮件转发的情况下验证 OCR 和完整区域校准流程。

## 不包含

- macOS + Chrome 运行支持。
- P3 候选人日志。
- P4 数值匹配。
- DOM 读取。
- Selenium、Playwright、WebDriver 或其他浏览器自动化驱动。
- 页面状态识别或转发成功/失败检测。

## Windows 使用说明

1. 下载 `BossOCR-Windows-x64.zip`。
2. 解压完整 ZIP，不要只复制 `BossOCR.exe`；one-dir 包内的 `_internal` 资源和 DLL 必须与 exe 保持在一起。
3. 在 Microsoft Edge 登录 BOSS 直聘，打开“推荐牛人”页面，并将 Edge 放在主显示器上。
4. 首次使用必须在命令行以 `--no-forward` 模式安全验证：

   ```powershell
   .\BossOCR.exe --no-forward
   ```

5. 输入用英文双引号包裹的关键词规则。普通交互模式下可选择完整转发点击区域校准。
6. 将鼠标放在第一位候选人卡片上，等待倒计时开始。
7. 运行期间按空格暂停/继续，按 Esc 安全停止。
8. 只有在测试账号、测试邮箱、一位候选人和全程人工监控下，才可以做真实转发验证。

## 测试与打包验证

源码全量测试：

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：**109/109 通过，0 失败，0 错误。**

稳定版使用仓库现有 `BossOCR.spec` 和 `build-windows.bat` 重新构建。PyInstaller 成功生成控制台 one-dir 应用，并由构建脚本压缩为 ZIP。

### exe 低风险冒烟

构建脚本执行：

```powershell
dist\BossOCR\BossOCR.exe --no-forward --auto --duration-seconds 0
```

在无关键词、无真实转发的条件下启动成功，未出现缺少模块、DLL 或资源文件错误。

额外参数验证：

```powershell
dist\BossOCR\BossOCR.exe --no-forward --auto --duration-seconds invalid
```

程序完成 frozen 模块加载后，在接触浏览器前正确返回参数错误和预期退出码 `2`。

### Windows GUI `--no-forward` 交互冒烟

**未执行。** 发布构建环境中没有可见 Edge 窗口、受控 BOSS 测试页面或可确认的测试账号。为避免对真实候选人页面产生鼠标操作，本次没有伪造或强行执行 GUI 结果。

发布后首次 GUI 验证必须使用测试账号和 `--no-forward`，并确认框选顺序为：焦点恢复 → 转发入口 → 邮件 Tab → 邮箱输入框 → 最近联系 → 转发按钮；框选最终转发按钮时不得发送邮件。

## 发布产物

- 应用：`dist\BossOCR\BossOCR.exe`
- 主发布附件：`release\BossOCR-Windows-x64.zip`
- ZIP SHA-256：`43CE29001A34989536C030EECA19A80BADB4248FBC864FBDCD15DE56FD28DFE7`

`dist/`、`build/`、`release/`、exe、ZIP、虚拟环境和缓存均不提交到 Git，仅将 ZIP 作为 GitHub Release 附件。

## 已知限制

- 校准区域仍是仅当前运行期有效的绝对屏幕坐标，不持久化。
- 校准后移动或缩放 Edge 窗口、改变分辨率或浏览器缩放会使区域失效，必须重启并重新校准。
- `--auto` 不询问、不弹框选层、不执行校准导航，始终使用默认区域。
- OCR 仍可能受字体清晰度、动画、遮挡、加载状态和识别误差影响。
- 框选第一版仅支持主显示器。
- 程序不识别页面状态，用户必须在界面与提示不符时按 Esc 停止或取消。
