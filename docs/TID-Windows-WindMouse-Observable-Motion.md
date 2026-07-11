# Windows WindMouse 可观察鼠标移动 TID

## 1. 背景与问题

BossOCR 当前通过自研三次贝塞尔轨迹执行 `human_click()` 的区域点击。该轨迹能够保证最终落点，但实际移动过程不够利于人工观察。

WindMouse 初版单段移动在小区域远距离点击中可能于终点附近反复过冲、回拉。本次后续优化继续使用 WindMouse，通过快速接近与稳定收尾分离来减轻这一弹簧效应。

本次目标是在 Windows 正式版中引入 WindMouse 的 PyAutoGUI backend，提升本地 GUI 区域点击的鼠标移动可观察性。该功能只服务于人工观察和操作确认，不用于规避验证码、平台风控或自动化检测，也不保证产生相关效果。

## 2. 范围

- 只影响 `human_click()` 或其统一鼠标移动封装。
- 覆盖筛选区域、邮件转发区域、焦点恢复区域等通过 `human_click()` 发起的区域点击。
- 保持区域内目标点选择、点击区域、点击等待和按压时长不变。
- 不改变 OCR、关键词规则、筛选逻辑、邮件转发业务流程、刷新逻辑和键盘切换逻辑。
- 保留未经过 `human_click()` 的既有直接点击边界；本次不扩大业务改造范围。

## 3. 非目标

- 不做或暗示任何反检测、绕过风控或验证码规避承诺。
- 不引入 AutoHotkey backend，不要求安装 AutoHotkey 或其他系统软件。
- 不改变 Mac 分支或 Mac 打包方案。
- 不重写筛选、转发、刷新、OCR 或候选人浏览业务流程。
- 不新增复杂鼠标速度参数或配置界面。

## 4. 技术方案

新增轻量 `mouse_motion.py` 封装 WindMouse 依赖和参数，`simple_brush.py` 继续保留统一的 `human_move_to()` / `human_click()` 业务入口：

1. 默认模式把已选定目标坐标交给两段式 WindMouse PyAutoGUI 封装，并在区域点击时附带区域宽高；宽高不参与随机取点。
2. 封装计算当前鼠标位置到目标整数坐标的欧氏距离。小于 300 像素时使用稳定参数 `10/0/16/12` 单段到达目标；大于等于 300 像素时先使用快速参数 `20/3/70/8` 到预接近点，再使用稳定收尾参数 `10/0/18/18` 到达目标（依次为 gravity、wind、max step、damped distance，且 `tick_delay=0`、`step_duration=0`）。
3. 普通远距离的收尾距离为 `clamp(distance * 0.10, 60, 120)`；宽度不大于 80 或高度不大于 40 的小区域使用 `clamp(distance * 0.12, 80, 140)`，用于减轻终点过冲和回拉的弹簧效应。
4. WindMouse 完成后，额外用一次 `pyautogui.moveTo(target_x, target_y, duration=0)` 强制校准到目标整数坐标。
5. `human_click()` 的 `mouseDown` / `mouseUp` 继续在同一最终整数坐标执行。
6. `--simple-mouse` 保留为旧版简单直线兼容模式，完全绕过 WindMouse。
7. 第一段或第二段 WindMouse 导入失败或移动抛出异常时记录 warning，并回退到现有贝塞尔实现，不改变上层业务流程。

本次不新增 `--no-windmouse`。运行模式保持为：默认 WindMouse、不可用时自动回退贝塞尔、`--simple-mouse` 使用简单直线。

### 4.1 已确认的上游 API 差异

WindMouse 1.0.2 文档示例使用：

```python
from windmouse import Coordinate
```

但本地安装 `windmouse==1.0.2` 后的实际 wheel 没有从包根导出 `Coordinate`；真实可用位置为：

```python
from windmouse.core import Coordinate
```

封装先尝试文档路径，再兼容 1.0.2 的实际路径。controller 与移动方法的实测签名支持上述三组分段物理参数，以及 `move_to_target(tick_delay=0, step_duration=0)`。

## 5. 依赖与许可证

- `requirements.txt` 加入 `windmouse==1.0.2`；现有 `pyautogui` 依赖已满足其 PyAutoGUI backend，因此不安装 AHK extras。
- Windows 构建脚本同时安装 `requirements.txt`，无需在只存放 PyInstaller 的 `requirements-build.txt` 重复声明运行依赖。
- `BossOCR.spec` 只显式收集 `windmouse.core` 和 `windmouse.pyautogui_controller`，不收集 AHK backend；同时复制包 metadata，使许可证随 one-dir 发布物保留。
- WindMouse 采用 GPL-3.0-only。README 和验收报告应说明依赖名称、版本、项目地址和许可证；正式分发前应确认发布方式满足其许可证义务。
- 本仓库不复制或修改 WindMouse 源码，只通过 PyPI 依赖引用。

## 6. 验收标准

- `--simple-mouse` 行为保持，仍为一次旧版简单直线移动。
- 默认 `human_click()` 区域点击使用单段或两段式 WindMouse 轨迹，并保持原区域取点不变。
- WindMouse 缺失、导入失败或移动异常时程序继续运行，并明确记录回退 warning。
- WindMouse 路径结束后强制落到目标整数坐标，`mouseDown` / `mouseUp` 使用同一坐标。
- 现有单元测试通过，新增测试覆盖可用、不可用、运行异常、简单模式和最终坐标。
- Windows 打包配置包含 PyAutoGUI backend 所需模块与依赖 metadata，不包含 AHK backend 的显式收集。
- README 的鼠标移动章节和参数表同步更新，并保留合规边界说明。

## 7. 回退方案

- 使用 Git 回退本次 change，恢复原默认贝塞尔实现。
- 运行时使用 `--simple-mouse` 立即切回旧版简单直线移动。
- 卸载或缺失 windmouse 时，程序会记录 warning 并自动使用现有贝塞尔 fallback，不会因导入失败直接崩溃。
