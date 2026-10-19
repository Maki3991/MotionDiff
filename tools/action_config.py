"""Per-action configuration: segmentation driver, phases, joints and prompts.

New actions join the catalog by adding an ActionConfig here and marking the
matching frontend card; no algorithm code changes are required as long as the
action shares the shoulder/hip/knee/ankle landmark chain used by the metrics.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionConfig:
    id: str
    name: str                 # 中文动作名（进度消息与界面展示）
    noun: str                 # 用于提示语，如“一次完整的深蹲”
    category: str             # 前端动作类别 id
    primary_metric: str       # 分段驱动指标
    active_direction: str     # "decrease"：指标在动作中段变小；"increase"：变大
    standing_limit: float     # decrease：起始指标需 ≥ 该值；increase：需 ≤ 该值
    min_excursion: float      # 起始到底部的最小行程
    flow: str                 # 完整动作流程描述，用于失败原因提示
    edge_label: str           # 两端起始姿态名称（站立/直立）
    phases: tuple[tuple[str, str], ...]  # (phase_id, 中文阶段标签)
    capture_hint: str         # 输入区短提示
    capture_protocol: str     # 拍摄条件长提示
    calibrated: bool = False  # 是否有带标签素材校准过阈值；False 时界面标「校准中」


PHASE_IDS = ("standing", "descent", "bottom", "ascent", "finish")

SQUAT = ActionConfig(
    id="squat", name="深蹲", noun="深蹲", category="strength",
    primary_metric="knee_angle_deg", active_direction="decrease",
    standing_limit=150.0, min_excursion=10.0,
    flow="站立→下蹲→起身", edge_label="站立",
    phases=(("standing", "开始站立"), ("descent", "下蹲中段"), ("bottom", "最低位"),
            ("ascent", "起身中段"), ("finish", "结束站立")),
    capture_hint="站立→下蹲→起身 · 每段一次完整深蹲",
    capture_protocol="相近侧面机位与距离；一人完整出镜；每段一次完整深蹲",
)

LUNGE = ActionConfig(
    id="lunge", name="弓步蹲", noun="弓步蹲", category="strength",
    primary_metric="knee_angle_deg", active_direction="decrease",
    standing_limit=150.0, min_excursion=10.0,
    flow="站立→下沉→起身", edge_label="站立",
    phases=(("standing", "站立准备"), ("descent", "下沉中段"), ("bottom", "最低位"),
            ("ascent", "起身中段"), ("finish", "结束站立")),
    capture_hint="站立→下沉→起身 · 每段一次完整弓步蹲",
    capture_protocol="相近侧面机位与距离；一人完整出镜；每段一次完整弓步蹲",
)

DEADLIFT = ActionConfig(
    id="deadlift", name="硬拉", noun="硬拉", category="strength",
    primary_metric="trunk_inclination_deg", active_direction="increase",
    standing_limit=25.0, min_excursion=10.0,
    flow="直立→下放→拉起", edge_label="直立",
    phases=(("standing", "直立准备"), ("descent", "下放中段"), ("bottom", "最低位"),
            ("ascent", "拉起中段"), ("finish", "直立锁定")),
    capture_hint="直立→下放→拉起 · 每段一次完整硬拉",
    capture_protocol="相近侧面机位与距离；一人完整出镜；每段一次完整硬拉，杠铃/负重全程入镜",
)


ROMANIAN_DEADLIFT = ActionConfig(
    id="romanian-deadlift", name="罗马尼亚硬拉", noun="罗马尼亚硬拉", category="strength",
    primary_metric="trunk_inclination_deg", active_direction="increase",
    standing_limit=25.0, min_excursion=10.0,
    flow="直立→下放→拉起", edge_label="直立",
    phases=(("standing", "直立准备"), ("descent", "下放中段"), ("bottom", "最低位"),
            ("ascent", "拉起中段"), ("finish", "直立锁定")),
    capture_hint="直立→下放→拉起 · 每段一次完整罗马尼亚硬拉",
    capture_protocol="相近侧面机位与距离；一人完整出镜；每段一次完整罗马尼亚硬拉，负重全程入镜",
)

BULGARIAN_SPLIT_SQUAT = ActionConfig(
    id="bulgarian-split-squat", name="保加利亚分腿蹲", noun="保加利亚分腿蹲", category="strength",
    primary_metric="knee_angle_deg", active_direction="decrease",
    standing_limit=150.0, min_excursion=10.0,
    flow="站立→下蹲→起身", edge_label="站立",
    phases=(("standing", "站立准备"), ("descent", "下沉中段"), ("bottom", "最低位"),
            ("ascent", "起身中段"), ("finish", "结束站立")),
    capture_hint="站立→下蹲→起身 · 每段一次完整保加利亚分腿蹲",
    capture_protocol="相近侧面机位与距离；一人完整出镜；每段一次完整保加利亚分腿蹲，后脚支撑位置入镜",
)


ACTIONS: dict[str, ActionConfig] = {config.id: config for config in
                                    (SQUAT, LUNGE, DEADLIFT, ROMANIAN_DEADLIFT, BULGARIAN_SPLIT_SQUAT)}


def get_action(action_id: str) -> ActionConfig | None:
    return ACTIONS.get(action_id)


def catalog_payload() -> list[dict]:
    """Implemented actions as consumed by the frontend catalog and /api/actions."""
    return [{"id": config.id, "name": config.name, "category": config.category,
             "capture_hint": config.capture_hint, "capture_protocol": config.capture_protocol,
             "calibrated": config.calibrated}
            for config in ACTIONS.values()]
