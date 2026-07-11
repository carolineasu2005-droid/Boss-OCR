"""Calibration step registry for reusable BossOCR profile creation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


STAGE_CANDIDATE_BASE = "A"
STAGE_FORWARD_DIALOG = "C"
STAGE_FILTER_PANEL = "B"

FEATURE_CANDIDATE_CARD = "候选人卡片"
FEATURE_FOCUS_RESTORE = "恢复焦点"
FEATURE_FAVORITE = "收藏"
FEATURE_FORWARD = "转发"
FEATURE_FILTER = "筛选"


@dataclass(frozen=True)
class CalibrationStep:
    field_name: str
    display_name: str
    instruction: str
    required: bool
    feature: str
    stage: str
    precondition: str
    min_size: int
    manual_transition: str


CALIBRATION_STEPS: Tuple[CalibrationStep, ...] = (
    CalibrationStep(
        field_name="first_candidate",
        display_name="首位候选人卡片",
        instruction="框选首位候选人卡片内部安全点击区域",
        required=True,
        feature=FEATURE_CANDIDATE_CARD,
        stage=STAGE_CANDIDATE_BASE,
        precondition="请确保当前页面处于候选人列表页，首位候选人卡片可见。",
        min_size=20,
        manual_transition="框选完成后，请手动打开首位候选人详情页，再继续后续区域校准。",
    ),
    CalibrationStep(
        field_name="focus_restore_region",
        display_name="详情页空白恢复焦点区域",
        instruction="框选候选人详情页空白区域，用于恢复键盘焦点",
        required=True,
        feature=FEATURE_FOCUS_RESTORE,
        stage=STAGE_CANDIDATE_BASE,
        precondition="请确保当前页面处于候选人详情页，正文或空白区域可见。",
        min_size=20,
        manual_transition="保持详情页不变，继续框选收藏按钮区域。",
    ),
    CalibrationStep(
        field_name="favorite_button_region",
        display_name="收藏按钮",
        instruction="框选收藏按钮内部安全点击区域",
        required=True,
        feature=FEATURE_FAVORITE,
        stage=STAGE_CANDIDATE_BASE,
        precondition="请确保当前页面处于候选人详情页，收藏按钮可见。",
        min_size=12,
        manual_transition="收藏按钮只框选，不会点击；完成后继续转发弹窗区域校准。",
    ),
    CalibrationStep(
        field_name="forward_icon",
        display_name="转发入口按钮",
        instruction="框选详情页右上角“转发牛人”入口内部安全区域",
        required=True,
        feature=FEATURE_FORWARD,
        stage=STAGE_FORWARD_DIALOG,
        precondition="请确保当前页面处于候选人详情页，转发入口可见。",
        min_size=12,
        manual_transition="框选完成后，请手动打开转发菜单或转发弹窗。",
    ),
    CalibrationStep(
        field_name="email_tab",
        display_name="邮件转发 Tab",
        instruction="框选弹窗左侧“邮件转发”Tab 内部安全区域",
        required=True,
        feature=FEATURE_FORWARD,
        stage=STAGE_FORWARD_DIALOG,
        precondition="请确保转发弹窗已打开，邮件转发 Tab 可见。",
        min_size=12,
        manual_transition="如尚未进入邮件转发页，请手动切换到邮件转发 Tab。",
    ),
    CalibrationStep(
        field_name="recent_email",
        display_name="最近联系邮箱标签",
        instruction="框选“最近联系”中第一个邮箱标签内部安全区域",
        required=True,
        feature=FEATURE_FORWARD,
        stage=STAGE_FORWARD_DIALOG,
        precondition="请确保邮件转发页面已打开，最近联系邮箱标签可见。",
        min_size=12,
        manual_transition="只框选，不会点击或发送邮件；继续框选邮箱输入栏。",
    ),
    CalibrationStep(
        field_name="input_box",
        display_name="转发邮箱输入栏",
        instruction="框选邮箱输入框内部安全点击区域",
        required=True,
        feature=FEATURE_FORWARD,
        stage=STAGE_FORWARD_DIALOG,
        precondition="请确保邮件转发页面已打开，邮箱输入框可见。",
        min_size=12,
        manual_transition="只框选，不会输入内容；继续框选确认转发按钮。",
    ),
    CalibrationStep(
        field_name="forward_button",
        display_name="确认转发按钮",
        instruction="框选右下角“转发”确认按钮内部安全区域",
        required=True,
        feature=FEATURE_FORWARD,
        stage=STAGE_FORWARD_DIALOG,
        precondition="请确保邮件转发页面已打开，确认转发按钮可见。",
        min_size=12,
        manual_transition="只框选，校准阶段不会点击确认转发按钮；完成后请手动返回候选人列表页。",
    ),
    CalibrationStep(
        field_name="open_filter",
        display_name="筛选按钮",
        instruction="框选打开筛选面板按钮内部安全区域",
        required=True,
        feature=FEATURE_FILTER,
        stage=STAGE_FILTER_PANEL,
        precondition="请确保当前页面处于候选人列表页，筛选按钮可见。",
        min_size=12,
        manual_transition="框选完成后，请手动打开筛选面板。",
    ),
    CalibrationStep(
        field_name="unseen_filter",
        display_name="最近没看过按钮",
        instruction="框选“最近没看过”选项内部安全区域",
        required=True,
        feature=FEATURE_FILTER,
        stage=STAGE_FILTER_PANEL,
        precondition="请确保筛选面板已打开，“最近没看过”选项可见。",
        min_size=12,
        manual_transition="只框选，不会选择该筛选项；继续框选筛选确认按钮。",
    ),
    CalibrationStep(
        field_name="confirm_filter",
        display_name="筛选确认按钮",
        instruction="框选筛选确认按钮内部安全区域",
        required=True,
        feature=FEATURE_FILTER,
        stage=STAGE_FILTER_PANEL,
        precondition="请确保筛选面板已打开，确认按钮可见。",
        min_size=12,
        manual_transition="只框选，不会应用筛选；该阶段完成后即可保存模板。",
    ),
)


def calibration_steps() -> Tuple[CalibrationStep, ...]:
    return CALIBRATION_STEPS


def calibration_steps_by_field() -> Dict[str, CalibrationStep]:
    return {step.field_name: step for step in CALIBRATION_STEPS}


def calibration_field_names() -> Tuple[str, ...]:
    return tuple(step.field_name for step in CALIBRATION_STEPS)


def calibration_stages() -> Tuple[str, ...]:
    stages: List[str] = []
    for step in CALIBRATION_STEPS:
        if step.stage not in stages:
            stages.append(step.stage)
    return tuple(stages)
