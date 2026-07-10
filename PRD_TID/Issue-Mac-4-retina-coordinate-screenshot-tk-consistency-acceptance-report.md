# Mac Change 4F：Retina 坐标、截图、Tk 框选一致性验证验收报告

## 1. 验收信息

- 验收分支：`mac-chrome-port`
- 验收范围：Mac Change 4A–4E
- 验收性质：macOS 坐标元数据、缩放推断、框选到截图裁剪映射、本地 preview、OCR 校准元数据的安全验收归档
- 验收结论：**通过**
- 结论边界：仅确认 Change 4 的诊断、映射与 metadata 结构按 TID 落地，不代表 macOS 已可运行完整 BossOCR 业务。

## 2. 实施范围

### 2.1 坐标系统元数据诊断

- 覆盖 `ScreenCoordinateDiagnostics`
- 覆盖 `capture_screen_coordinate_diagnostics()`
- 覆盖 `--coordinate-diagnostics-only`
- 只读采集 `pyautogui.size()`、`pyautogui.position()`、`mss.monitors`、primary monitor、Tk/Tcl version
- 不截图、不 `mss.grab()`、不弹 Tk overlay、不 OCR、不业务动作

### 2.2 display fingerprint

- `display_fingerprint` 基于 monitor 稳定字段生成
- 使用 `left/top/width/height/is_primary`
- 通过 `json.dumps(..., sort_keys=True, separators=(',', ':'))` 后再做 `sha256`
- 不包含时间戳、用户路径、页面信息或敏感数据

### 2.3 scale inference

- 覆盖 `RetinaScaleInference`
- 覆盖 `infer_retina_scale()`
- 覆盖 `infer_monitor_capture_scale()`
- 规则：
  - request/image 尺寸必须为正整数
  - `scale_x = image_width / request_width`
  - `scale_y = image_height / request_height`
  - scale 必须有限且位于 `[0.5, 4.0]`
  - 双轴差不得超过 tolerance，默认 `0.02`
  - 支持非整数缩放
  - 不 clamp
  - 不使用全局固定 scale

### 2.4 Tk selection normalize

- 覆盖 `TkSelectionRegion`
- 覆盖 `normalize_drag_selection()`
- 支持四方向拖拽归一化
- 点和 selection 字段必须为有限值
- selection 必须非空

### 2.5 Tk selection -> screenshot crop mapping

- 覆盖 `ScreenshotCropRegion`
- 覆盖 `TkToScreenshotMapping`
- 覆盖 `map_tk_selection_to_screenshot_crop()`
- 覆盖 `validate_screenshot_crop()`
- 左/上使用 `floor`
- 右/下使用 `ceil`
- crop 必须非空并位于截图边界内
- 越界 fail closed，不 clamp

### 2.6 crop preview helper

- 覆盖 `CropPreviewResult`
- 覆盖 `crop_image_for_preview()`
- 覆盖 `build_coordinate_diagnostics_dir()`
- 覆盖 `save_crop_preview_for_manual_check()`
- 只处理给定 image array
- 只保存 crop，不保存全屏原图
- output_dir 自动创建
- filename 路径穿越 fail closed
- crop 返回 `.copy()`
- 不修改原图

### 2.7 OCR calibration metadata

- 覆盖 `CoordinateCalibrationMetadata`
- 覆盖 `CalibratedScreenRegion`
- 覆盖 `build_coordinate_calibration_metadata()`
- 覆盖 `attach_coordinate_metadata_to_region()`
- 覆盖 `ocr_calibrated_region`
- `ensure_ocr_region_calibrated()` 可选接收 metadata
- Detector 仍使用原始 `ScreenRegion`
- Detector 与 metadata 包装原子发布
- metadata 为 `None` 时保持旧行为兼容

### 2.8 Windows 行为与 macOS ready

- Windows 行为保持不变
- macOS `ready=False` 保持不变

## 3. 关键安全结论

- Change 4 没有让 macOS 成为完整业务可用版。
- Change 4 没有打开真实 BOSS 页面。
- Change 4 没有真实截图验收。
- Change 4 没有真实 Tk overlay / 框选验收。
- Change 4 没有运行真实 OCR。
- Change 4 没有点击、移动鼠标、滚动、按键、刷新或转发。
- Change 4 没有把 macOS `ready` 改为 `True`。
- 坐标 metadata validated 不等于 business ready。
- crop preview saved 不等于 business ready。
- `business_ready` 恒为 `False`。

## 4. 4A 详情

- `ScreenCoordinateDiagnostics` 已新增，用于结构化表达只读坐标诊断信息。
- `capture_screen_coordinate_diagnostics()` 已新增，作为只读探针入口。
- `--coordinate-diagnostics-only` 已新增，作为独立安全出口。
- display fingerprint 规则为：
  - 基于 `left/top/width/height/is_primary`
  - 使用 `json.dumps(..., sort_keys=True, separators=(',', ':'))`
  - 再做 `sha256`
  - 不包含时间戳、用户路径、页面信息或敏感数据
- 只读收集内容为：
  - `pyautogui.size()`
  - `pyautogui.position()`
  - `mss.monitors`
  - `primary monitor`
  - `Tk/Tcl version`

## 5. 4B 详情

- `RetinaScaleInference` 已新增。
- `infer_retina_scale()` 已新增。
- `infer_monitor_capture_scale()` 已新增。
- 规则确认：
  - request/image 尺寸必须为正整数
  - `scale_x = image_width / request_width`
  - `scale_y = image_height / request_height`
  - scale 必须有限且位于 `[0.5, 4.0]`
  - 双轴差不得超过 tolerance，默认 `0.02`
  - 支持非整数缩放
  - 不 clamp
  - 不使用全局固定 scale

## 6. 4C 详情

- `TkSelectionRegion` 已新增。
- `ScreenshotCropRegion` 已新增。
- `TkToScreenshotMapping` 已新增。
- `normalize_drag_selection()` 已新增。
- `map_tk_selection_to_screenshot_crop()` 已新增。
- `validate_screenshot_crop()` 已新增。
- 规则确认：
  - 四方向拖拽归一化
  - 点和 selection 字段必须为有限值
  - selection 必须非空并完整位于 overlay 内
  - 左/上使用 `floor`
  - 右/下使用 `ceil`
  - crop 必须非空并位于截图边界内
  - 越界 fail closed，不 clamp
  - scale 校验失败时保留 4B 错误码

## 7. 4D 详情

- `CropPreviewResult` 已新增。
- `crop_image_for_preview()` 已新增。
- `build_coordinate_diagnostics_dir()` 已新增。
- `save_crop_preview_for_manual_check()` 已新增。
- 规则确认：
  - 只处理给定 image array
  - 只保存 crop，不保存全屏原图
  - output_dir 自动创建
  - filename 路径穿越 fail closed
  - crop 返回 `.copy()`
  - 不修改原图
  - 当前仓库已有 `logs/` 忽略规则，可覆盖 `logs/macos-coordinate-diagnostics/`

## 8. 4E 详情

- `CoordinateCalibrationMetadata` 已新增。
- `CalibratedScreenRegion` 已新增。
- `build_coordinate_calibration_metadata()` 已新增。
- `attach_coordinate_metadata_to_region()` 已新增。
- `ocr_calibrated_region` 已新增。
- `ensure_ocr_region_calibrated()` 可选接收 metadata。
- Detector 仍使用原始 `ScreenRegion`。
- Detector 与 metadata 包装原子发布。
- metadata 为 `None` 时保持旧行为兼容。
- 状态关系：
  - `validated`：fingerprint、scale、mapping 均有效
  - `manually_confirmed`：还需要 preview 已保存并显式确认
  - `business_ready`：不可由调用方设置，恒为 `False`
  - validated / manual confirmation 均不代表 OCR 或业务可用

## 9. 测试结果

### 9.1 4A + 4B 合并提交前

- `tests.test_browser_prepare`：75 passed
- `tests.test_mouse_motion`：18 passed
- `tests.test_simple_brush_ocr`：85 passed
- `git diff --check`：通过

### 9.2 4C 后

- `tests.test_browser_prepare`：87 passed
- `tests.test_mouse_motion`：18 passed
- `tests.test_simple_brush_ocr`：85 passed
- `git diff --check`：通过

### 9.3 4D 后

- `tests.test_browser_prepare`：101 tests OK
- `tests.test_mouse_motion`：18 tests OK
- `tests.test_simple_brush_ocr`：85 tests OK
- `git diff --check`：通过

### 9.4 4E 后

- `tests.test_browser_prepare`：101 passed
- `tests.test_mouse_motion`：18 passed
- `tests.test_simple_brush_ocr`：93 passed
- `git diff --check`：通过

### 9.5 运行说明

- 使用 `.venv/bin/python`
- 系统无 `python` 命令
- 4A 与 4B 因 4A 未及时提交，最终合并为同一 commit
- 测试均未执行真实 BOSS 页面操作

## 10. 非目标确认

明确没有做：

- 真实 BOSS 页面操作
- 真实截图验收
- 真实 Tk overlay / 框选验收
- 真实 OCR 识别
- RapidOCR 初始化
- `mss.grab()` 默认调用
- 全屏截图保存
- 点击、移动鼠标、滚动、按键、刷新
- 邮件转发
- Next-5
- Next-6
- 关键词 parser / matcher
- main 合并
- tag/release

## 11. 当前限制

- macOS 仍不能运行真实业务流程。
- 坐标 metadata、scale inference 和 crop mapping 只是安全与一致性验证层，不是业务放行层。
- Retina 坐标、截图链路与 Tk 框选一致性仍需人工设备级确认。
- OCR 区域元数据已接入，但未将系统变成完整业务可用版。
- 真实 BOSS 页面仍未做人工验收。

## 12. 验收结论

- 验收结论：通过
- 建议下一步：Mac Change 5 TID：macOS 安全浏览闭环，只浏览不转发
- 不要直接实施 Change 5
- Change 5 TID 必须继续明确：不转发、不真实 OCR 放行业务、不绕过 `business_ready=False`
- 本报告不实施后续业务变更
