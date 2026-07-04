# Mac Change 4：Retina 坐标、截图、Tk 框选一致性验证 TID V1.0

## 0. 文档信息与安全口径

- 分支：`mac-chrome-port`
- 文档类型：Technical Implementation Design（TID）
- 本文范围：设计 macOS 屏幕坐标诊断、Retina 缩放推断、Tk 框选到 MSS 截图裁剪的映射与验证边界
- 本文性质：只做设计，不实施代码，不运行真实探针，不创建或保存截图
- 前置状态：Mac Change 1 / 2 / 3 已完成；macOS Chrome 可进行窗口和页面身份只读诊断，但始终 `ready=False`
- 核心口径：坐标一致性通过，只能证明“测试区域可被可信定位和裁剪”，不能证明真实 BOSS 页面可安全操作

本文把坐标空间明确分为四类，避免继续用一个含义模糊的 `ScreenRegion` 同时代表所有坐标：

1. Tk overlay 局部坐标；
2. macOS / Core Graphics 全局显示坐标；
3. PyAutoGUI 指针输入坐标；
4. MSS 返回图像内的像素坐标。

任何实现都不得在未验证时假设四者恒等，也不得把一个全局固定的 `2.0` 当作所有显示器的通用 Retina 比例。

## 1. Change 4 目标

Change 4 只解决以下问题：

1. 明确 macOS Retina 下逻辑点、全局屏幕坐标和 backing-store 物理像素之间的关系。
2. 验证 `pyautogui.size()`、`pyautogui.position()` 和未来输入坐标所处的坐标空间。
3. 验证 `mss.monitors` 的矩形与 `mss.grab()` 实际返回像素尺寸之间的关系。
4. 明确 Tk window、canvas、鼠标事件与目标显示器全局坐标之间的映射。
5. 建立 Tk 框选区域到 MSS 抓取请求、再到返回图像像素区域的可验证转换。
6. 验证 OCR 区域裁剪是否准确落在用户框选的本地测试图区域，但不运行真实 OCR 识别。
7. 明确多显示器、外接屏、混合缩放、负坐标、主屏切换和显示模式变化的风险边界。
8. 为后续 macOS 只浏览闭环提供坐标可信前提；本 Change 不建立业务动作放行门。

Change 4 的完成状态最多应表达为“coordinate diagnostics passed”或“crop mapping validated”。它不得把 `BrowserPrepareResult.ready` 改为 `True`。

## 2. 非目标

本 Change 明确不做：

- 不打开真实 BOSS 页面；
- 不点击真实页面或任何业务控件；
- 不滚动；
- 不按方向键或其他业务按键；
- 不刷新；
- 不做真实 OCR 文本识别、关键词判定或二次确认；
- 不做邮件转发；
- 不实现候选人浏览业务循环；
- 不修改关键词 parser / matcher；
- 不修改 Next-5 批次筛选；
- 不修改 Next-6 鼠标轨迹；
- 不合并或修改 `main`；
- 不创建 tag / release；
- 不以真实招聘页面、聊天页面或候选人数据作为诊断截图材料。

## 3. 当前代码调研

### 3.1 当前区域模型

`ocr_calibration.py` 定义不可变 `ScreenRegion(left, top, width, height)`，其 `as_mss_monitor()` 直接把四个整数原样转换为 MSS 抓取字典。当前没有字段记录：

- 坐标属于哪个显示器；
- 单位是 Tk unit、逻辑点还是图像像素；
- 对应的 scale factor；
- 显示器布局或缩放配置指纹；
- 区域是在何时、由哪个坐标源产生。

因此当前 `ScreenRegion` 的安全性依赖一个隐含前提：Tk、MSS 和 PyAutoGUI 使用同一套坐标。这个前提在 Windows 通过 `enable_windows_dpi_awareness()` 尝试建立，在 macOS 尚未被证明。

### 3.2 当前 Tk 框选流程

`select_screen_region()` 当前流程为：

1. 调用 `enable_windows_dpi_awareness()`；macOS 返回 `not-windows`，不做任何适配。
2. `primary_monitor_region()` 从 `mss.MSS().monitors[1:]` 中优先找 `is_primary`，否则取第一项。
3. 以该 monitor 的 `left/top/width/height` 创建无边框、置顶、半透明 Tk overlay。
4. Canvas 填满 overlay；鼠标事件记录 `event.x/event.y` 局部坐标。
5. 鼠标释放时读取已实现的 `canvas.winfo_width()/height()`。
6. `physical_point_from_overlay()` 按 `monitor.width / overlay_width` 和 `monitor.height / overlay_height` 分别缩放起止点，并加 monitor origin。
7. `region_from_points()` 用 `min/abs` 支持正向和反向拖拽，并以 `min_size` 拒绝过小区域。
8. overlay 销毁后返回一个 `ScreenRegion`。

现有实现已经意识到 Tk overlay 尺寸可能与 MSS monitor 尺寸不同，但函数名 `physical_point_from_overlay()` 和注释“physical MSS coordinates”尚未经过 macOS Retina 实测证明。尤其要验证：MSS monitor 字典是抓取请求坐标，未必等于抓取结果数组的物理像素网格。

当前 overlay 文案多处写着“第一版仅支持主显示器”，与多显示器业务使用仍有明确缺口。

### 3.3 当前 MSS 截图与 OCR 裁剪

`MSSScreenCapture.capture(region)` 将 `ScreenRegion.as_mss_monitor()` 直接交给 `mss.grab()`，再把返回 BGRA 数组裁为 BGR。它没有：

- 验证请求区域属于哪台显示器；
- 验证返回数组的宽高是否等于请求宽高；
- 记录请求矩形与返回图像尺寸的比例；
- 检查空图、黑屏、透明图、越界或跨屏区域；
- 在显示配置变化后使旧校准失效。

`save_region_preview()` 使用同一 capture 获取图像，检查三维颜色数组，去除 alpha、从 BGR 转为 RGB，然后保存到 `logs/ocr_calibration_preview.png`。预览能帮助人工发现错位，但当前没有在保存前做隐私来源限制，也没有自动核对目标标记、尺寸或边界。

`OCRKeywordDetector._observe()` 每次把相同 `ScreenRegion` 交给 capture，再将整幅裁剪图交给 OCR backend。换言之，坐标一旦偏移，OCR 可能稳定识别错误区域；识别成功本身不能反证裁剪正确。

### 3.4 当前区域如何用于 PyAutoGUI

`random_point_in_region()` 从 `ScreenRegion` 半开区间内选择整数点，`click_in_region()` 再把该点交给 `human_click()`，最终调用 `pyautogui.moveTo()`、`mouseDown()` 和 `mouseUp()`。批次筛选、转发校准和焦点恢复区域都复用这条路径。

因此当前同一个 `ScreenRegion` 既可作为 MSS 截图请求，又可作为 PyAutoGUI 点击区域。Retina 下即使截图预览正确，也不能自动推出点击坐标正确；两条路径必须分别验证。Change 4 不允许用真实点击来做验证，只能记录鼠标位置或使用人工移动后的非注入式观察。

### 3.5 当前测试保护

`tests/test_simple_brush_ocr.py` 已覆盖：

- 框选取消、失败和单次尝试语义；
- 多区域校准的原子发布与回退；
- 反向区域归一化相关基础行为；
- 区域内随机点的半开边界；
- OCR 校准预览与 detector 的 mock 接线；
- 点击、滚动、转发等业务路径的 mock 行为。

`tests/test_browser_prepare.py` 已保护：

- Windows Edge 成功/失败语义；
- macOS focus、tab identity、allowlist 和 `prepare_browser()` 的 fail-closed 链路；
- `--preflight-only` 不启动 OCR、Listener、校准、点击、滚动、按键、刷新或转发。

现有测试尚未建立 macOS 显示器元数据、Tk realized size、MSS 返回图像尺寸和 scale 推断之间的契约。

### 3.6 Windows 与 macOS 当前边界

- Windows 已通过 DPI awareness helper 和既有测试形成当前行为，Change 4 不得改变其坐标、OCR、Edge 或鼠标轨迹语义。
- Mac Change 3 只证明 Chrome frontmost 与 active tab 页面身份可诊断；即使 `page_allowed=True`，仍返回 `MACOS_PAGE_ALLOWED_NOT_BUSINESS_READY`。
- macOS 当前不得进入真实业务。Change 4 也不得改变这一点。

## 4. 技术问题拆解

### 4.1 Retina 逻辑点与物理像素

macOS UI 几何通常以 point 表达，backing store 以 pixel 表达。`backingScaleFactor` 表示每个线性屏幕单位对应的 backing pixel 数，但 Apple 明确建议优先使用 backing conversion API，而非把 scale 当作永远固定的硬件常数；显示模式、镜像和窗口所在屏幕都可能影响结果。

因此设计必须满足：

- scale 按显示器记录，而非全局单值；
- `scale_x` 与 `scale_y` 分开计算并验证；
- 只接受有限、稳定、正数且两轴合理一致的结果；
- 显示模式或布局变化后旧诊断立即失效；
- 不把 Retina 简化为“永远 2 倍”。

### 4.2 `pyautogui.size()` 是逻辑尺寸还是物理尺寸

PyAutoGUI 文档把 `size()` 描述为主屏分辨率，并说明其多显示器支持不可靠，但没有为 macOS Retina 给出可依赖的 point/pixel 契约。当前项目虚拟环境中的 PyAutoGUI 0.9.54 macOS 后端用 `CGDisplayPixelsWide/High` 实现 `_size()`，而指针位置和事件走 AppKit / Quartz 的另一组 API。

结论：不得因为 `pyautogui.size()` 看起来等于某个像素尺寸，就推断 `moveTo(x, y)` 接受同一物理像素坐标。Change 4 诊断只能读取 `size()` 与 `position()`，不得注入点击；未来要单独验证输入坐标空间。

### 4.3 `mss.monitors` 是物理像素还是逻辑坐标

当前 MSS macOS 后端通过 `CGDisplayBounds` 枚举全局 display rectangle，并把该 rectangle 交给 `CGWindowListCreateImage`；抓取完成后，又通过 `CGImageGetWidth/Height` 获取实际图像像素尺寸。这意味着“请求矩形尺寸”和“返回图像像素尺寸”是两个必须分别记录的量。

因此 TID 不把 `mss.monitors` 笼统定义为物理像素。正确诊断是：

```text
mss_request_bounds = monitor dict width/height
mss_image_size     = actual grabbed array width/height
scale_x            = image_width  / request_width
scale_y            = image_height / request_height
```

只有请求成功、边界有效且返回图像可验证时，比例才是候选 scale。跨屏矩形不能用单个比例处理。

### 4.4 Tk window / canvas / selection 映射

Tk 的 `event.x/event.y` 是 widget 局部坐标；`winfo_width/height` 是 widget 实现后的尺寸；`winfo_rootx/rooty` 和 virtual-root 信息可能参与全局定位。现有代码仅使用局部点、realized canvas size 和 MSS monitor origin。

Change 4 需要记录：

- overlay 请求 geometry；
- overlay 和 canvas 的 realized width/height；
- `winfo_rootx/rooty`；
- `winfo_vrootx/y/width/height`；
- Tk scaling 值；
- 框选起止点及归一化后的局部矩形；
- 目标 display id / monitor index。

若引入 AppKit 的 `NSScreen` 辅助数据，必须显式处理 AppKit 常见的左下原点与现有 Tk/Core Graphics 顶部方向差异，禁止只乘 scale 不做原点和 Y 轴转换。

### 4.5 截图裁剪是否需要 scale factor

要区分两个动作：

1. 向 MSS 提交抓取矩形；
2. 在 MSS 返回图像数组中定位像素。

前者应使用经诊断确认的 MSS request coordinate；后者使用图像局部 pixel coordinate。若整屏 request 为 `(L, T, W, H)`，实际图像为 `(Pw, Ph)`，局部选择 `(x, y, w, h)` 的候选像素转换是：

```text
pixel_left   = floor(x * Pw / W)
pixel_top    = floor(y * Ph / H)
pixel_right  = ceil((x + w) * Pw / W)
pixel_bottom = ceil((y + h) * Ph / H)
```

使用 floor/ceil 是为了不因舍入漏掉边界；最终仍必须 clamp 前验证并拒绝越界。不能把全局 `left/top` 直接乘 scale，因为负坐标、多屏原点与每屏 scale 会使结果错误。

### 4.6 主屏、外接屏与负坐标

- Core Graphics 全局 display bounds 相对主显示器左上角；显示器在主屏左侧或上方时可出现负坐标。
- 每台显示器可能有不同 scale；跨屏选择不存在唯一 affine scale。
- 主屏切换会改变全局原点，即使物理排列不变，旧区域也应失效。
- 初始实现应限制“一次诊断和一次框选必须完整落在单一显示器内”。跨屏区域直接 fail closed。
- 不应依赖 `mss.monitors` 顺序永久稳定；需生成 display fingerprint，并显式识别 primary。

### 4.7 菜单栏、Dock 与多 Space

- full screen bounds 与可用工作区并不相同；菜单栏、Dock 会影响可用窗口区域，但不应被偷偷扣减出截图坐标。
- Dock 自动隐藏、菜单栏显示策略变化时，可见内容可能变化，但 display bounds 不一定变化。
- 多 Space 只应诊断当前可见 Space；不得尝试切换 Space。
- overlay 建立后若 Space、主屏、分辨率、缩放或排列改变，本次结果作废。
- 诊断截图不得以菜单栏或 Dock 是否出现作为唯一几何校验，应该使用受控测试图边框和角标。

### 4.8 截图权限失败模式

屏幕录制权限不足可能表现为：

- MSS / Core Graphics 抛异常；
- 返回空引用、零尺寸或尺寸异常；
- 返回黑图、透明图或缺少目标窗口内容；
- 权限刚修改但宿主未重启，状态仍旧。

诊断需把异常、空图、维度不符和测试标记缺失分别映射为错误码。纯色黑图检测只能作为信号，不能单独作为权限结论，因为受控测试页也可能是纯色；建议测试图包含四角不同颜色、网格和中心十字。

### 4.9 用可视化验证 OCR 区域偏移

只允许使用本地生成的非敏感测试图或 `about:blank` 上明确放置的人工测试窗口。推荐测试图包含：

- 1 px / 1 logical-unit 对照边框；
- 四角不同颜色和编号；
- 固定间距网格；
- 中心十字；
- 已知尺寸的小矩形。

预览应在 overlay 销毁后生成，避免截到半透明遮罩。人工比较框选目标与 crop preview 的四边、角标和中心线；不得运行 RapidOCR，也不得把“识别到了测试字样”作为几何正确性的证明。

## 5. 推荐方案候选

### 5.1 方案 A：保持现有坐标直接复用

做法：继续让一个 `ScreenRegion` 同时供 Tk、MSS 与 PyAutoGUI 使用，仅依赖现有 `physical_point_from_overlay()`。

优点：

- 改动最小；
- Windows 现有结构无需调整；
- 单显示器、scale 1.0 环境可能表面可用。

风险：

- Retina 下 MSS request 尺寸与返回 pixel 尺寸可能不同；
- PyAutoGUI `size()` 与事件坐标未必同空间；
- 混合缩放和负坐标下会发生系统性偏移；
- 错位可能仍得到有效图像，难以及时发现；
- 不具备安全放行依据。

结论：不推荐。

### 5.2 方案 B：引入统一坐标映射层

做法：显式定义 Tk local、display global、PyAutoGUI input、MSS request 和 image pixel 坐标；所有转换携带 display identity、origin、scale 与边界。

优点：

- 坐标语义清晰；
- 可对转换函数做纯单测；
- 能按显示器处理不同 scale；
- 能让截图区域与未来输入区域分开验证。

风险：

- 实现复杂；
- 如果缺少真实设备观测，模型可能“数学正确、API 假设错误”；
- 需要迁移现有 `ScreenRegion` 调用方并严防 Windows 回归。

结论：作为最终结构推荐，但不应成为第一步。

### 5.3 方案 C：先做诊断工具，不改业务逻辑

做法：新增 macOS 专用 dry probe，只读取并输出 PyAutoGUI size/position、MSS monitor/request/image size、Tk realized geometry 和候选 scale；只对本地测试图生成显式路径的 crop preview。

优点：

- 不触发真实业务动作；
- 可以在实际硬件、缩放与多屏布局上收集证据；
- 先验证 API 坐标语义，再决定映射层；
- 失败可自然 fail closed。

风险：

- 需要人工验收矩阵；
- 屏幕截图权限会成为前置条件；
- 若诊断输出缺少显示器指纹，结果不可复现。

结论：推荐作为 Change 4 第一步。

### 5.4 推荐方案

推荐 **方案 C → 方案 B 的分阶段组合**：

1. 先通过 4A / 4B 建立只读诊断数据和受控测试图证据；
2. 再通过 4C 建立按显示器的统一坐标映射层；
3. 通过 4D 的本地 crop preview 和人工矩阵验证映射；
4. 最后才允许 4E 把已验证的截图区域接到 OCR 校准对象，但仍不运行真实 OCR、不进入业务。

方案 A 不具备足够的可验证性，不应作为 macOS 放行基础。

## 6. 推荐实现边界

Change 4 实施时应遵守：

- 先做独立诊断工具，再改业务坐标数据流；
- 诊断入口必须与业务运行入口分离，不复用 `--auto` 等业务参数伪装 dry-run；
- 不接入真实业务点击，不调用 `mouseDown/mouseUp/click/press/hotkey/scroll/typewrite`；
- 可以只读调用 `pyautogui.size()` 和 `position()`，但不得移动指针；
- 不打开 BOSS URL；
- 不保存敏感页面截图；
- 如需保存，只允许本地生成测试图、空白页或专用无敏感数据窗口；
- 建议诊断根目录为 `logs/macos-coordinate-diagnostics/<timestamp>/`；该目录默认不上传、不提交，并应由 `.gitignore` 保护；
- 每次保存前打印绝对路径、来源类型和隐私提示；默认应要求显式 `--save-preview`；
- 默认只保留 crop preview 和 JSON 元数据，不保留全屏原图；若调试必须保存全屏测试图，应单独显式授权并在验收后删除；
- 每个区域必须绑定 display fingerprint；显示配置变化后 fail closed；
- 第一阶段只支持完整落在单一显示器内的区域；跨屏区域拒绝；
- Windows 继续走现有实现，不得改变 Windows DPI、OCR、Edge 或鼠标轨迹行为；
- `--preflight-only` 保持 Change 3 语义，不自动截图、不弹 Tk 框选；
- macOS `ready=False` 保持不变。

## 7. 建议数据结构 / helper

### 7.1 坐标和显示器结构

建议设计但本轮不实现：

```python
@dataclass(frozen=True)
class CoordinatePoint:
    x: float
    y: float
    space: str
    display_id: str | None = None

@dataclass(frozen=True)
class CoordinateRegion:
    left: float
    top: float
    width: float
    height: float
    space: str
    display_id: str | None = None

@dataclass(frozen=True)
class DisplayCoordinateProfile:
    display_id: str
    is_primary: bool
    request_bounds: CoordinateRegion
    captured_pixel_size: tuple[int, int]
    scale_x: float
    scale_y: float
    fingerprint: str
```

`space` 至少区分：`tk_local`、`display_global`、`pyautogui_input`、`mss_request`、`image_pixel`。不建议只靠变量名暗示单位。

### 7.2 `ScreenCoordinateDiagnostics`

建议结构：

```python
@dataclass(frozen=True)
class ScreenCoordinateDiagnostics:
    platform: str
    pyautogui_size: tuple[int, int] | None
    pyautogui_position: tuple[int, int] | None
    mss_monitors: tuple[dict, ...]
    primary_monitor: dict | None
    target_display_id: str | None
    tk_selection: CoordinateRegion | None
    tk_overlay_size: tuple[int, int] | None
    tk_root_origin: tuple[int, int] | None
    mss_request_region: CoordinateRegion | None
    screenshot_size: tuple[int, int] | None
    scale_x: float | None
    scale_y: float | None
    crop_region: CoordinateRegion | None
    preview_path: str | None
    passed: bool
    message: str
    error_code: str | None
```

建议错误码：

- `MACOS_COORDINATE_MONITOR_UNAVAILABLE`
- `MACOS_COORDINATE_DISPLAY_CHANGED`
- `MACOS_COORDINATE_SCALE_INVALID`
- `MACOS_COORDINATE_SCALE_AMBIGUOUS`
- `MACOS_COORDINATE_CROSS_DISPLAY_UNSUPPORTED`
- `MACOS_TK_OVERLAY_GEOMETRY_INVALID`
- `MACOS_TK_SELECTION_EMPTY`
- `MACOS_TK_SELECTION_OUT_OF_BOUNDS`
- `MACOS_SCREEN_CAPTURE_PERMISSION_DENIED`
- `MACOS_SCREEN_CAPTURE_FAILED`
- `MACOS_SCREEN_CAPTURE_SIZE_MISMATCH`
- `MACOS_CROP_EMPTY`
- `MACOS_CROP_OUT_OF_BOUNDS`
- `MACOS_CROP_PREVIEW_NOT_CONFIRMED`
- `MACOS_COORDINATES_VALIDATED_NOT_BUSINESS_READY`

### 7.3 helper 分类

诊断专用 helper：

- `capture_screen_diagnostics()`：收集元数据，不做输入；第一阶段不进入业务链。
- `probe_mss_monitor_capture_size()`：对受控测试屏抓取并记录 request/result 尺寸。
- `collect_tk_overlay_diagnostics()`：记录 overlay realized geometry 和局部 selection。
- `save_crop_preview_for_manual_check()`：仅在显式允许时保存本地 crop preview。
- `build_display_fingerprint()`：绑定显示器排列、尺寸、scale 与主屏状态。

可作为纯函数、未来可能进入校准链路的 helper：

- `infer_retina_scale(request_size, screenshot_size)`：推断并验证两轴比例。
- `normalize_tk_selection_to_screenshot_region()`：把单屏 Tk 局部矩形映射为图像 pixel 矩形。
- `validate_crop_region()`：检查非空、单屏、边界、比例和舍入。
- `normalize_drag_points()`：统一正向/反向拖拽。
- `is_display_profile_current()`：运行前判断旧校准是否失效。

未来可能进入业务链路、但 Change 4 不得调用输入的 helper：

- `screen_region_to_pyautogui_region()`：只有经过独立输入坐标验收后才可启用。
- `screen_region_to_mss_request()`：只有单显示器 request-space 契约验证后才可替换现有直传逻辑。

## 8. 测试计划

本轮只设计，不实施测试。

### 8.1 纯函数与结构测试

1. Windows 既有 `ScreenRegion`、OCR、Edge 与鼠标行为保持不变。
2. macOS request size 与 screenshot size 相同，推断 `scale_x=scale_y=1.0`。
3. macOS screenshot 两轴均为 request 的两倍，推断 `scale_x=scale_y=2.0`。
4. 正常 Tk selection 映射到预期 pixel crop。
5. 反向拖拽得到与正向拖拽相同的规范化区域。
6. selection 超出目标 display / overlay 边界时 fail closed。
7. MSS monitor request 尺寸与 PyAutoGUI size 不一致时，不直接报错；结合实际 screenshot size 和 display identity 推断候选 scale。
8. scale 为零、负数、NaN、无限、两轴严重不一致或无法归属显示器时 fail closed。
9. 多显示器含负坐标时，以 display-local offset 转换，不对全局 origin 盲目乘 scale。
10. 跨显示器 selection fail closed。
11. 主屏或 display fingerprint 改变后旧 profile 失效。
12. selection 恰好贴边时使用明确的半开矩形和 floor/ceil 规则，不越界。

### 8.2 截图与错误映射测试

13. MSS 抛权限相关异常时映射为明确错误码。
14. MSS 返回空引用、零尺寸、二维数组或异常 channel 数时 fail closed。
15. 裁剪区域为空时 `MACOS_CROP_EMPTY`。
16. 裁剪区域越界时 `MACOS_CROP_OUT_OF_BOUNDS`，不得静默 clamp 后继续。
17. preview 保存失败时不发布校准结果。
18. preview 路径必须位于允许的本地诊断目录。

### 8.3 副作用负向测试

19. 诊断 helper 不构造 RapidOCR backend，不调用 `OCRKeywordDetector.detect()`。
20. 不调用 PyAutoGUI 点击、移动、按键、滚动或输入 API。
21. 不启动 `keyboard.Listener`。
22. 不调用邮件转发、批次筛选、候选人打开或业务循环。
23. `--preflight-only` 行为保持不变，不自动进入 Change 4 probe。
24. macOS 诊断通过也不使 `prepare_browser().ready=True`。
25. Windows OCR、浏览器准备与鼠标轨迹既有测试全部继续通过。

测试应使用注入的 monitor 字典、Tk geometry 和合成 NumPy 图像，不依赖真实显示器或系统截图。真实设备矩阵只属于人工验收。

## 9. 人工验收计划

所有场景只允许显示本地无敏感测试图；不得登录或打开真实 BOSS 页面。每次验收都记录 macOS、Python、Tk、PyAutoGUI、MSS 版本，显示器型号/排列/缩放、宿主应用和诊断目录。

| 场景 | 需要观察 | 预期输出 | 是否允许进入下一阶段 | 真实业务动作 |
|---|---|---|---|---|
| MacBook 内置 Retina 屏 | PyAutoGUI size、MSS request/result、Tk realized size、四角 crop | 单屏 profile 唯一；两轴 scale 稳定；预览边界吻合 | 全部一致才允许进入 4C/4D | 禁止 |
| 外接普通显示器 | 外屏 scale、显示器 identity、crop 尺寸 | 通常可能为 1.0，但必须实测；预览吻合 | 通过该显示器 profile 后允许下一诊断阶段 | 禁止 |
| 外接 Retina / 高分屏 | 每屏独立 scale 与返回像素 | 不复用内屏 scale；两轴比例合理 | 仅该屏通过后允许下一诊断阶段 | 禁止 |
| 主屏为外接屏 | 全局 origin、primary 标识、display fingerprint | primary 切换被检测；旧 profile 失效 | 重新校准通过后才允许 | 禁止 |
| 左/上方显示器产生负坐标 | monitor `left/top`、局部 offset、crop | 负全局 origin 被保留；局部 crop 非负且在图像内 | 单屏映射通过才允许 | 禁止 |
| 测试窗口在主屏 | 框选标记与 preview 四边 | 完整包含预期角标，无固定偏移 | 可进入该屏更大区域测试 | 禁止 |
| 测试窗口在副屏 | 目标 display 归属、scale 与 preview | 不错误套用主屏 profile | 该副屏独立通过才允许 | 禁止 |
| Tk 框选小区域 | 最小区域、舍入、边界像素 | 非空且尺寸符合 floor/ceil 契约 | 预览人工确认后允许 | 禁止 |
| Tk 框选大区域 | 边缘累计误差、截图尺寸、内存 | 四角和中心均吻合，无随距离增长的偏移 | 通过后才允许 4D 完成 | 禁止 |
| 反向拖拽 | 起止顺序与归一化结果 | 与相同矩形正向拖拽结果一致 | 一致才允许 | 禁止 |
| 截图权限关闭 | 异常、空图或测试标记缺失 | 明确 fail closed；不发布 profile/preview | 不允许 | 禁止 |
| 截图权限开启并重启宿主 | capture 成功、测试标记、保存路径 | 尺寸和标记正确，文件仅在本地诊断目录 | 人工确认后允许下一阶段 | 禁止 |

补充判定：

- 任一场景出现无法解释的偏移、scale 不稳定、跨屏歧义、黑图或权限不确定，都不允许进入下一阶段。
- “允许进入下一阶段”仅指继续 Change 4 的诊断/映射工作，不指进入候选人浏览、OCR 识别或转发。
- 人工验收结束后应删除不再需要的全屏测试截图；crop preview 是否保留由验收记录明确说明。

## 10. 风险分析

### 10.1 Retina scale 推断错误

单纯用 `screenshot_width / pyautogui.size().width` 可能混淆主屏、显示模式和不同 API 坐标空间。缓解方式是按 display identity 比较 MSS request/result，并用受控图像人工确认；不接受全局固定比例。

### 10.2 Tk 与 MSS 坐标不一致

Tk geometry 和事件是 widget-local，MSS request 是全局 display rectangle。overlay 未实现、窗口管理器修正 geometry 或 Y 轴处理错误都会产生偏移。必须记录 realized geometry、root origin，并用单屏局部 offset 转换。

### 10.3 PyAutoGUI 输入与截图坐标不一致

PyAutoGUI 0.9.54 的 macOS size、position、event 路径不应被视为同一物理 pixel API。截图映射通过后仍不能直接复用 image pixel 点击。Change 4 禁止注入输入；未来必须单独设计安全输入验收。

### 10.4 多显示器原点和混合缩放

负坐标、主屏切换、旋转、镜像和不同 scale 会破坏全局线性比例。只允许单显示器区域；profile 绑定完整布局指纹；配置变化即失效。

### 10.5 菜单栏、Dock 和 Space

可见工作区与 full display bounds 不同，Space 切换会改变截图内容。诊断不主动切换 Space，不根据 Dock/菜单栏猜测 offset，并在 overlay 到 capture 之间检测配置变化。

### 10.6 截图权限导致黑屏或空图

只捕获到黑图不一定有异常。必须同时检查 API 错误、尺寸、channel、测试图标记和宿主重启状态；任何不确定情况 fail closed。

### 10.7 截图隐私风险

全屏截图可能包含姓名、聊天、邮件、通知或其他敏感信息。只能使用本地合成测试图/空白页；默认不保存全屏；路径固定在被忽略的本地目录；不上传、不提交。

### 10.8 把坐标验证误认为业务安全

几何一致不代表页面身份、控件语义、登录状态、业务规则、OCR 准确率或点击后果安全。Change 4 完成后 macOS 仍不得直接浏览真实候选人或转发。

### 10.9 旧区域继续使用

若显示配置变化后仍复用旧 `ScreenRegion`，可能截错屏或点错位置。所有未来校准结果必须携带 fingerprint，运行前重新验证；不匹配即拒绝。

## 11. 推荐实施拆分

### 4A：坐标系统调研与诊断输出 helper

- 新增纯诊断结构和显示器指纹；
- 只读输出 PyAutoGUI、MSS、Tk 版本与尺寸；
- 不截图、不弹业务校准、不接入 `prepare_browser()` ready。

### 4B：MSS / PyAutoGUI / Tk scale 推断

- 对本地测试图执行单显示器 MSS probe；
- 记录 request bounds 和实际 image size；
- 建立纯函数 scale 推断与 fail-closed 错误码；
- PyAutoGUI 仅只读，不注入输入。

### 4C：Tk 框选到截图裁剪区域转换

- 引入显式坐标空间和 display-local 转换；
- 支持正向/反向拖拽；
- 拒绝越界、跨屏、display 改变和 scale 不明；
- 暂不替换业务点击区域。

### 4D：本地裁剪预览与人工验收

- 仅对合成测试图或空白测试窗口保存 crop preview；
- 明确本地路径、忽略规则、删除策略；
- 执行第 9 节设备矩阵并归档结果。

### 4E：接入 OCR 区域校准，但仍不进入真实业务

- 让 OCR 校准对象持有已验证 display profile 与 crop mapping；
- 只验证截图区域，不启动 RapidOCR 识别和滚动；
- macOS 仍 `ready=False`。

### 4F：Change 4 验收报告

- 汇总单测、设备矩阵、preview 人工确认、失败模式和遗留限制；
- 明确能否建议进入后续“只浏览、不转发”TID；
- 不在验收报告阶段扩大业务权限。

推荐下一步最小 Change 是 **4A**，而不是直接迁移 OCR 或点击。

### 11.1 设计依据

- Apple 的 [High Resolution OS X API 指南](https://developer.apple.com/library/archive/documentation/GraphicsAnimation/Conceptual/HighResolutionOSX/APIs/APIs.html) 区分屏幕 point 与 backing pixel，并建议优先使用 backing conversion API。
- Apple 的 [`CGDisplayBounds`](https://developer.apple.com/documentation/coregraphics/cgdisplaybounds%28_%3A%29) 定义全局 display coordinate space，相对主显示器左上角。
- Python 官方 [`tkinter` 文档](https://docs.python.org/3/library/tkinter.html) 区分 widget/root/virtual-root 坐标，并说明 realized width 初始可能为 1。
- PyAutoGUI [鼠标文档](https://pyautogui.readthedocs.io/en/latest/mouse.html) 定义 `size()` / `position()` 基础语义；其[上游仓库](https://github.com/asweigart/pyautogui)同时明确多显示器支持不可靠。
- MSS [上游仓库与文档](https://github.com/BoboTiG/python-mss)说明 monitor 枚举和区域抓取能力；具体 request/result 尺寸仍须在目标版本和硬件上验证。

这些资料用于建立风险假设，不能替代本项目在实际 Mac、实际 Tk/MSS/PyAutoGUI 版本上的诊断数据。

## 12. 验收结论格式

- 是否建议实施 Change 4：**建议实施**
- 推荐方案：**方案 C 先诊断，证据充分后进入方案 B 的统一映射层**
- 推荐复杂度：**High**
- 是否允许真实 BOSS 页面：**不允许；仅允许本地合成测试图或无敏感空白测试窗口**
- 是否允许截图：**仅允许显式授权的本地非敏感测试截图；默认不保存全屏，不上传、不提交**
- 是否允许点击 / 滚动 / 按键：**不允许**
- 是否允许 OCR：**不允许真实 OCR 识别；只允许验证截图/crop 几何与像素尺寸**
- 是否允许转发：**不允许**
- macOS 是否可设为业务 `ready=True`：**不允许，必须保持 `False`**
- 推荐下一步最小 Change：**4A：坐标系统调研与诊断输出 helper**

最终结论：Change 4 值得实施，但必须从无业务动作的诊断探针开始。只有单显示器坐标空间、MSS request/result 尺寸、Tk realized geometry 和本地 crop preview 在设备矩阵中均可复现地一致，才可进入 OCR 区域接线；即使 Change 4 全部通过，也仍不能直接启用真实浏览、OCR 判定或邮件转发。
