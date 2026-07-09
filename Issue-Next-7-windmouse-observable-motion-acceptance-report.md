# [Next-7] WindMouse 可观察鼠标移动验收报告

## 1. 验收结论

自动化验收通过，Windows Edge 实机观感验证待发布前人工执行。

本次以最小范围把两段式 WindMouse PyAutoGUI backend 接入 `human_click()` 的统一移动入口。近距离使用稳定单段，远距离使用快速接近加稳定收尾，以减轻小区域远距离点击的终点弹簧效应；依赖不可用或任一段移动异常时记录 warning 并回退原贝塞尔轨迹；`--simple-mouse` 继续使用旧版简单直线移动。OCR、关键词、筛选、转发、刷新、键盘切换和 Mac 分支逻辑均未改动。

## 2. 实施范围

| 文件 | 变更 |
| --- | --- |
| `docs/TID-Windows-WindMouse-Observable-Motion.md` | 新增设计、范围、API 探针结论、验收和回退方案 |
| `mouse_motion.py` | 新增 WindMouse 可用性检查、单段/两段 controller 封装和精确终点校准 |
| `simple_brush.py` | 传递区域尺寸，保留异常/缺失 fallback、原区域取点和最终整数点击坐标 |
| `tests/test_mouse_motion.py` | 覆盖两段参数、收尾距离、两段异常、简单模式和最终坐标 |
| `requirements.txt` | 固定 `windmouse==1.0.2` |
| `BossOCR.spec` | 精确加入 PyAutoGUI backend hidden imports，并复制 windmouse metadata/许可证 |
| `README.md` | 更新行为、参数、合规边界、代码结构和第三方许可证说明 |
| `.gitignore` | 只放行本 TID 与本验收报告 |

`requirements-build.txt` 和 `build-windows.bat` 无需修改：Windows 构建脚本本来就会安装 `requirements.txt`，而 `requirements-build.txt` 只保存 PyInstaller 构建工具依赖。

## 3. 行为验收

| 场景 | 结果 |
| --- | --- |
| 近距离 | `<300` 使用稳定参数 `10/0/16/12`，单段到目标 |
| 普通远距离 | `>=300`，快速参数 `20/3/70/8` 到预接近点，收尾距离夹在 60~120 像素 |
| 小区域远距离 | 区域宽 `<=80` 或高 `<=40`，收尾距离夹在 80~140 像素 |
| 稳定收尾 | 第二段使用 `10/0/18/18`，其中 `wind_magnitude=0` |
| 移动调用参数 | 所有分段均使用 `tick_delay=0`、`step_duration=0` |
| 最终坐标 | WindMouse 后强制 `moveTo` 到目标整数坐标；移动、按下、抬起复用同一坐标 |
| WindMouse 缺失/导入失败 | 不阻止程序导入或运行；首次区域移动明确 warning，随后使用原贝塞尔实现 |
| WindMouse 移动异常 | 当前移动记录 warning 并立即使用原贝塞尔实现完成移动 |
| `--simple-mouse` | 在 WindMouse 判断之前走旧版单次直线 `moveTo`，不调用 WindMouse |
| 区域覆盖 | 筛选、转发和焦点恢复等既有 `human_click()` 调用点自动覆盖 |
| 旧首位点击边界 | 未启用筛选区域时的旧直接点击保持不变 |

## 4. 上游 API 探针

本地安装并检查了 PyPI `windmouse==1.0.2`。controller 和 `move_to_target()` 签名与参数建议一致，但 wheel 没有按 README 示例从 `windmouse` 包根导出 `Coordinate`。实现优先尝试文档路径，并兼容实际可用的 `windmouse.core.Coordinate`。

探针结果：

```text
available True
coordinate_module windmouse.core
controller_module windmouse.pyautogui_controller
```

## 5. 测试结果

| 命令 | 结果 |
| --- | --- |
| `.\venv\Scripts\python.exe -m unittest tests.test_mouse_motion -v` | 通过，28/28 |
| `.\venv\Scripts\python.exe -m unittest discover -s tests -v` | 通过，175/175 |
| `.\venv\Scripts\python.exe -m compileall -q simple_brush.py mouse_motion.py tests` | 通过 |
| `.\venv\Scripts\python.exe -m pip check` | 通过，无依赖冲突 |
| PyInstaller `copy_metadata("windmouse")` 探针 | 通过，包含 `windmouse-1.0.2.dist-info` 及许可证目录 |
| `.\venv\Scripts\python.exe -m PyInstaller --noconfirm BossOCR.spec` | 通过，one-dir 构建成功 |
| `git diff --check` | 通过 |

项目虚拟环境未安装 pytest；仓库 README 和 `build-windows.bat` 的既定全量测试命令均为 unittest，因此未为本 change 额外引入 pytest 开发依赖。

测试全部使用 mock/stub，没有移动或点击真实鼠标，没有访问真实浏览器、OCR 或邮件转发流程。

## 6. 打包与许可证

- `requirements.txt` 已加入 `windmouse==1.0.2`，构建脚本会自动安装。
- `BossOCR.spec` 只显式包含 `windmouse.core` 与 `windmouse.pyautogui_controller`，未显式收集 `windmouse.ahk_controller`。
- windmouse 的包 metadata 和许可证会进入 one-dir 构建。
- WindMouse 项目地址：https://github.com/AsfhtgkDavid/windmouse
- WindMouse 许可证：GPL-3.0-only。
- 本仓库未复制或修改 WindMouse 源码。

本轮只生成了本地 one-dir 打包验证产物，没有压缩 ZIP、创建 release 或运行真实 GUI 冒烟流程。构建分析确认包含 `windmouse.core`、`windmouse.pyautogui_controller` 和 `windmouse-1.0.2.dist-info\licenses\LICENSE`，且不包含 `windmouse.ahk_controller`。发布前仍需运行完整 `build-windows.bat`；正式分发方应确认发布方式满足 GPL-3.0-only 的许可证义务。

## 7. Windows 手动验证步骤

1. 重新安装依赖：`.\venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-ocr.txt`。
2. 运行 `安全测试_只检测不转发.bat`，保持 `--no-forward` 安全模式，不执行真实邮件转发。
3. 按提示校准筛选区域和首位候选人区域。
4. 观察“打开筛选 → 最近没看过 → 确定 → 首位候选人”四次区域点击，确认鼠标轨迹明显可见，且最终落点仍在所选安全区域内。
5. 若同时校准转发和焦点恢复区域，只观察校准导航与安全模式行为，不执行真实转发。
6. 查看 `logs/simple_brush.log`，正常安装时不应出现 WindMouse fallback warning。
7. 再在安全测试批处理的 Python/EXE 命令后加入 `--simple-mouse` 运行，对比确认旧版单次直线模式仍可用，并确认筛选、OCR、刷新与键盘切换行为未改变。
8. 发布构建前运行 `build-windows.bat`，检查 `dist\BossOCR` 与 ZIP 中存在 `windmouse-1.0.2.dist-info\licenses\LICENSE`，再执行一次上述安全模式实机观察。

## 8. 回退

- 运行期加 `--simple-mouse` 可立即回到旧版直线移动。
- 缺失或卸载 windmouse 会自动回退到贝塞尔实现并记录 warning。
- 如需完全撤销，可用 Git 回退本 change；本次未创建 commit、tag 或 release。
