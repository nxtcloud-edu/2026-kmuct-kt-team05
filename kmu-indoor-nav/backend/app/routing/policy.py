"""
통행 정책과 시간 모델.

핵심 구분 (구현지시서 7절)
--------------------------
1. **필수 제약(hard constraint)** 은 탐색 전에 엣지를 제거한다.
   큰 벌점으로 대체하지 않는다.
2. **estimated_time_s** 와 **preference_cost** 는 다른 값이다.
   기존 거리 비용을 초로 이름만 바꾸지 않는다.
3. '계단 없이'(no_stairs) 와 '휠체어 접근성 확인'(wheelchair) 은 다르다.
   후자는 폭/문턱/방향별 경사 등 필수 속성에 **현장 근거**가 있어야 통과한다.
4. 속도·대기시간은 모두 **가정값**이며 policy_version 과 함께 보고한다.
"""

from __future__ import annotations

import dataclasses

from ..models.schema import (
    MIN_VERIFICATION_FOR_ACCESSIBILITY,
    Accessibility,
    Edge,
    EdgeKind,
    STAIR_EDGE_KINDS,
)

#: 정책 버전. 한계값/가정값을 바꾸면 반드시 올린다.
POLICY_VERSION = "policy-2026.09.20-01"


# ---------------------------------------------------------------- 시간 모델
@dataclasses.dataclass(frozen=True)
class TimeModel:
    """모든 값이 가정값이다. 대표 경로 실측으로 보정해야 한다."""

    walk_speed_mps: float
    door_pass_s: float = 4.0
    door_pass_s_auto: float = 2.0
    stair_s_per_step: float = 1.2
    #: 단수 근거가 없을 때 계단 1구간에 쓰는 대체 시간
    stair_s_per_edge_fallback: float = 20.0
    elevator_wait_s: float = 25.0
    elevator_board_alight_s: float = 10.0
    elevator_s_per_floor: float = 5.0
    assumptions_note: str = "모두 가정값. 현장 반복측정 전에는 확정 도착시간으로 표시 금지."


TIME_MODELS: dict[str, TimeModel] = {
    "normal": TimeModel(walk_speed_mps=1.30),
    "elderly": TimeModel(walk_speed_mps=0.90, door_pass_s=6.0,
                         stair_s_per_step=2.0, stair_s_per_edge_fallback=35.0),
    "wheelchair": TimeModel(walk_speed_mps=0.85, door_pass_s=8.0),
}


# ---------------------------------------------------------------- 제약
@dataclasses.dataclass
class Constraints:
    """사용자 요청에서 유도된 제약. 세션 병합은 호출부 책임."""

    no_stairs: bool = False
    wheelchair: bool = False
    #: 휠체어 조건에서 검증을 요구할 속성
    required_accessibility_fields: tuple[str, ...] = (
        "clear_width_m", "threshold_m", "slope_up_pct", "slope_down_pct",
    )
    #: 관측 기반 한계값. 프로젝트 정책이며 법적 기준이 아니다.
    max_slope_up_pct: float = 8.33
    max_slope_down_pct: float = 8.33
    min_clear_width_m: float = 0.90
    max_threshold_m: float = 0.02
    #: 실내 선호에서 허용할 추가 소요시간 비율
    indoor_detour_ratio: float = 0.35

    def signature(self) -> dict:
        return {
            "no_stairs": self.no_stairs,
            "wheelchair": self.wheelchair,
            "max_slope_up_pct": self.max_slope_up_pct if self.wheelchair else None,
            "max_slope_down_pct": self.max_slope_down_pct if self.wheelchair else None,
            "min_clear_width_m": self.min_clear_width_m if self.wheelchair else None,
            "max_threshold_m": self.max_threshold_m if self.wheelchair else None,
            "required_accessibility_fields":
                list(self.required_accessibility_fields) if self.wheelchair else [],
        }


class Block(str):
    """엣지 제거 사유."""


BLOCK_STAIRS = Block("stairs_excluded_by_constraint")
BLOCK_UNVERIFIED = Block("required_accessibility_unverified")
BLOCK_SLOPE = Block("observed_slope_exceeds_limit")
BLOCK_WIDTH = Block("observed_clear_width_below_limit")
BLOCK_THRESHOLD = Block("observed_threshold_above_limit")
BLOCK_CLOSED = Block("closed_or_restricted")
BLOCK_WHEELCHAIR_FLAG = Block("facility_marked_not_wheelchair_usable")


def edge_block_reason(edge: Edge, c: Constraints, closed: bool) -> Block | None:
    """이 엣지를 제거해야 하는 이유. None 이면 통행 허용.

    순서가 중요하다: 폐쇄 -> 계단 -> (휠체어) 미검증 -> 관측값 위반.
    """
    if closed:
        return BLOCK_CLOSED

    acc: Accessibility = edge.accessibility

    # --- 계단 ---
    is_stair = edge.kind in STAIR_EDGE_KINDS
    if acc.stairs.is_known and acc.stairs.value is True:
        is_stair = True
    if is_stair and (c.no_stairs or c.wheelchair):
        return BLOCK_STAIRS

    if not c.wheelchair:
        return None

    # --- 휠체어: 시설이 명시적으로 이용 불가 ---
    if acc.wheelchair_usable.is_known and acc.wheelchair_usable.value is False:
        return BLOCK_WHEELCHAIR_FLAG

    # --- 휠체어: 엘리베이터는 시설 속성으로 별도 판정 (engine 에서) ---
    if edge.kind == EdgeKind.ELEVATOR_RIDE:
        return None

    # --- 휠체어: 필수 속성 검증 여부 ---
    # unknown 을 통행 가능으로 간주하지 않는다.
    required = _required_fields_for(edge, c)
    if acc.unknown_fields(required):
        return BLOCK_UNVERIFIED

    # --- 휠체어: 관측값이 한계를 넘음 (비용으로 상쇄 불가) ---
    up = acc.slope_up_pct
    if up.known_at_least(MIN_VERIFICATION_FOR_ACCESSIBILITY) and \
            float(up.value) > c.max_slope_up_pct:
        return BLOCK_SLOPE
    dn = acc.slope_down_pct
    if dn.known_at_least(MIN_VERIFICATION_FOR_ACCESSIBILITY) and \
            float(dn.value) > c.max_slope_down_pct:
        return BLOCK_SLOPE
    w = acc.clear_width_m
    if w.known_at_least(MIN_VERIFICATION_FOR_ACCESSIBILITY) and \
            float(w.value) < c.min_clear_width_m:
        return BLOCK_WIDTH
    th = acc.threshold_m
    if th.known_at_least(MIN_VERIFICATION_FOR_ACCESSIBILITY) and \
            float(th.value) > c.max_threshold_m:
        return BLOCK_THRESHOLD

    return None


def _required_fields_for(edge: Edge, c: Constraints) -> tuple[str, ...]:
    """엣지 종류별로 검증이 필요한 접근성 속성."""
    if edge.kind == EdgeKind.DOOR:
        return ("clear_width_m", "threshold_m", "door_operability")
    if edge.kind == EdgeKind.ELEVATOR_RIDE:
        return ()
    if edge.kind in (EdgeKind.CORRIDOR, EdgeKind.OUTDOOR_WALK,
                     EdgeKind.RAMP, EdgeKind.ENTRANCE,
                     EdgeKind.BUILDING_CONNECTOR):
        return c.required_accessibility_fields
    return c.required_accessibility_fields


# ---------------------------------------------------------------- 비용
def edge_time_s(
    edge: Edge,
    tm: TimeModel,
    elevator_wait_s: float | None = None,
    elevator_floor_span: int | None = None,
    elevator_ride_s_per_floor: float | None = None,
    elevator_board_alight_s: float | None = None,
) -> float | None:
    """통행 소요시간(초). 계산 근거가 없으면 None.

    엘리베이터 승차 엣지는 **대기시간을 1회만** 포함한다.
    출발층->도착층을 하나의 직접 승차 엣지로 모델링하므로, 층을 연쇄로
    이어붙여 대기시간이 중복 부과되는 구조가 애초에 존재하지 않는다.
    갈아타기는 다른 facility_id 의 별도 승차 엣지 + 보행 연결로 표현된다.
    """
    if edge.kind == EdgeKind.ELEVATOR_RIDE:
        wait = tm.elevator_wait_s if elevator_wait_s is None else elevator_wait_s
        per_floor = (tm.elevator_s_per_floor if elevator_ride_s_per_floor is None
                     else elevator_ride_s_per_floor)
        board = (tm.elevator_board_alight_s if elevator_board_alight_s is None
                 else elevator_board_alight_s)
        span = max(1, int(elevator_floor_span or 1))
        return wait + board + per_floor * span

    if edge.kind == EdgeKind.DOOR:
        op = edge.accessibility.door_operability
        auto = op.is_known and str(op.value).lower() in ("automatic", "auto", "자동")
        return tm.door_pass_s_auto if auto else tm.door_pass_s

    if edge.kind == EdgeKind.STAIRS:
        steps = edge.accessibility.step_count
        if steps.is_known:
            return tm.stair_s_per_step * float(steps.value)
        return tm.stair_s_per_edge_fallback

    length = edge.traversal_length_m
    if not length.is_known:
        length = edge.horizontal_length_m
    if not length.is_known:
        return None          # 축척/거리 근거 없음 -> 시간 산출 불가
    return float(length.value) / tm.walk_speed_mps


def edge_preference_cost(edge: Edge, profile: str) -> float:
    """비음수 선호 비용. 시간과 **더하지 않고** 별도로 최적화/보고한다.

    경사 선호는 관측 경사가 있을 때만 반영한다. 추정 경사를 섞지 않는다.
    """
    cost = 0.0
    acc = edge.accessibility

    if edge.kind == EdgeKind.STAIRS:
        cost += {"normal": 1.0, "elderly": 30.0, "wheelchair": 1e6}.get(profile, 1.0)

    for attr in (acc.slope_up_pct, acc.slope_down_pct):
        if attr.known_at_least(MIN_VERIFICATION_FOR_ACCESSIBILITY):
            excess = max(0.0, abs(float(attr.value)) - 2.0)
            w = {"normal": 0.02, "elderly": 0.5, "wheelchair": 2.0}.get(profile, 0.1)
            cost += w * excess ** 2

    if edge.kind == EdgeKind.ELEVATOR_RIDE:
        cost += {"normal": 5.0, "elderly": 0.0, "wheelchair": 0.0}.get(profile, 0.0)

    return cost


def edge_outdoor_length_m(edge: Edge) -> float:
    """'실내 위주' 목적함수용 실외 이동거리."""
    if edge.kind not in (EdgeKind.OUTDOOR_WALK, EdgeKind.ENTRANCE):
        return 0.0
    length = edge.traversal_length_m if edge.traversal_length_m.is_known \
        else edge.horizontal_length_m
    return float(length.value) if length.is_known else 0.0
