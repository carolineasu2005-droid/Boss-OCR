"""Standalone calibration profile generator."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Callable, Dict, Iterable, Optional, TextIO

from calibration_profiles import (
    PROFILE_DIR,
    ProfileExistsError,
    build_profile,
    get_system_info,
    profile_path,
    safe_profile_filename,
    save_profile,
)
from calibration_steps import CalibrationStep, calibration_stages, calibration_steps
from ocr_calibration import CalibrationCancelled, ScreenRegion, select_screen_region


EXIT_SUCCESS = 0
EXIT_CANCELLED = 2
EXIT_NOT_OVERWRITTEN = 3
EXIT_ERROR = 1

CALIBRATION_PROFILE_USAGE_NOTICE = (
    "调用校准模板前，请确保 Boss 页面窗口位置、大小、缩放状态与校准时基本一致。"
)
CALIBRATION_PROFILE_OFFSET_RISK_NOTICE = (
    "如果窗口位置、窗口大小或页面缩放发生变化，旧模板中的点击区域可能发生偏移，建议重新校准。"
)
CALIBRATION_STEP_WAIT_SECONDS = 3

STAGE_TITLES = {
    "A": "阶段 A：候选人基础区域",
    "C": "阶段 C：转发弹窗区域",
    "B": "阶段 B：筛选面板区域",
}

STAGE_NOTES = {
    "A": (
        "请从候选人列表页开始。先框选首位候选人卡片，随后按提示手动"
        "打开候选人详情页，再框选详情页焦点恢复区域和收藏按钮。"
    ),
    "C": (
        "请保持在候选人详情页。按提示手动打开转发菜单或弹窗，并手动"
        "切换到邮件转发页面；校准阶段不会点击确认转发按钮。"
    ),
    "B": (
        "请手动返回候选人列表页。按提示手动打开筛选面板，再框选"
        "最近没看过和筛选确认按钮；校准阶段不会应用筛选。"
    ),
}


def prompt_profile_name(
    input_func: Callable[[str], str] = input,
    output: TextIO = sys.stdout,
) -> str:
    while True:
        profile_name = input_func("请输入校准模板名称：\n> ").strip()
        if profile_name:
            return profile_name
        print("模板名称不能为空，请重新输入。", file=output)


def confirm_overwrite(
    profile_name: str,
    *,
    base_dir: Path = PROFILE_DIR,
    input_func: Callable[[str], str] = input,
    output: TextIO = sys.stdout,
) -> bool:
    path = profile_path(profile_name, base_dir)
    if not path.exists():
        return True

    print(
        f'模板 "{profile_name}" 已存在：{path}',
        file=output,
    )
    answer = input_func("是否覆盖同名模板？[y/N]\n> ").strip().lower()
    return answer in ("y", "yes")


def _steps_by_stage(steps: Iterable[CalibrationStep]):
    grouped = {stage: [] for stage in calibration_stages()}
    for step in steps:
        grouped.setdefault(step.stage, []).append(step)
    return grouped


def wait_before_region_selection(
    seconds: int = CALIBRATION_STEP_WAIT_SECONDS,
    output: TextIO = sys.stdout,
) -> None:
    """Give the user time to read a template-step prompt before selection."""
    print(f"{seconds} 秒后开始框选……", file=output)
    for remaining in range(seconds, 0, -1):
        print(remaining, file=output)
        time.sleep(1)


def collect_calibration_areas(
    *,
    steps: Iterable[CalibrationStep] = calibration_steps(),
    select_region: Callable[..., ScreenRegion] = select_screen_region,
    wait_before_selection: Callable[..., None] = wait_before_region_selection,
    output: TextIO = sys.stdout,
) -> Dict[str, ScreenRegion]:
    areas: Dict[str, ScreenRegion] = {}
    grouped = _steps_by_stage(steps)

    for stage in calibration_stages():
        stage_steps = grouped.get(stage, [])
        if not stage_steps:
            continue

        print("", file=output)
        print(STAGE_TITLES.get(stage, f"阶段 {stage}"), file=output)
        note = STAGE_NOTES.get(stage)
        if note:
            print(note, file=output)

        for index, step in enumerate(stage_steps, start=1):
            print("", file=output)
            print(f"[{stage}-{index}] {step.display_name}", file=output)
            print(step.precondition, file=output)
            print(step.instruction, file=output)
            wait_before_selection(CALIBRATION_STEP_WAIT_SECONDS, output=output)

            region = select_region(
                min_size=step.min_size,
                instruction=step.instruction,
                subtitle=(
                    "调用校准模板前，请确保 Boss 页面窗口位置、大小、缩放状态"
                    "与校准时基本一致"
                ),
            )
            areas[step.field_name] = region

            if step.manual_transition:
                print(step.manual_transition, file=output)

    return areas


def create_calibration_profile_interactive(
    *,
    base_dir: Path = PROFILE_DIR,
    input_func: Callable[[str], str] = input,
    output: TextIO = sys.stdout,
    select_region: Callable[..., ScreenRegion] = select_screen_region,
    system_info_func: Callable[[], dict] = get_system_info,
) -> int:
    print("BossOCR 通用校准模板生成", file=output)
    print(CALIBRATION_PROFILE_USAGE_NOTICE, file=output)
    print(CALIBRATION_PROFILE_OFFSET_RISK_NOTICE, file=output)

    profile_name = prompt_profile_name(input_func, output)
    safe_name = safe_profile_filename(profile_name)
    print(f"模板文件名：{safe_name}", file=output)

    if not confirm_overwrite(
        profile_name,
        base_dir=base_dir,
        input_func=input_func,
        output=output,
    ):
        print("已取消覆盖，未保存模板。", file=output)
        return EXIT_NOT_OVERWRITTEN

    try:
        system_info = system_info_func()
        print(f"系统信息：{system_info}", file=output)
        areas = collect_calibration_areas(
            select_region=select_region,
            output=output,
        )
        profile = build_profile(
            profile_name,
            areas,
            system_info=system_info,
        )
        path = save_profile(
            profile,
            base_dir=base_dir,
            overwrite=True,
        )
    except CalibrationCancelled:
        print("校准已取消，未保存不完整模板。", file=output)
        return EXIT_CANCELLED
    except ProfileExistsError:
        print("模板已存在且未允许覆盖，未保存模板。", file=output)
        return EXIT_NOT_OVERWRITTEN
    except Exception as exc:
        print(f"校准模板生成失败：{exc}", file=output)
        return EXIT_ERROR

    print(f"校准模板已保存：{path}", file=output)
    return EXIT_SUCCESS


def main(argv: Optional[list[str]] = None) -> int:
    _ = argv
    return create_calibration_profile_interactive()


if __name__ == "__main__":
    raise SystemExit(main())
