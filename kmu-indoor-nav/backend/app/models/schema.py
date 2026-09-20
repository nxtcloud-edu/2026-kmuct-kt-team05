"""
미래관 실내·실외 통합 내비게이션 데이터 스키마.

설계 원칙 (구현지시서 6절)
-------------------------
1. 안정적 ID. 파일명/탭이름에서 층을 자동 확정하지 않는다.
2. 단위를 필드명에 명시한다 (`_m`, `_s`, `_px`).
3. **unknown 을 0 / false / 이용가능 으로 바꾸지 않는다.**
   모든 접근성 관련 속성은 `Attr` 로 감싸 값과 근거·검증수준을 함께 갖는다.
4. 도면 픽셀 좌표(`plan:<floor_id>`)와 지리 좌표(`geo`)를 분리한다.
   층마다 원점·회전·축척이 다를 수 있으므로 층간 좌표를 복사하지 않는다.
5. 경사는 방향별 부호값으로 저장한다. 계단/엘리베이터의 수직이동은
   보행 경사 지표에서 제외한다.
6. 하나의 verified=true 가 모든 속성의 검증을 대신하지 못한다.
"""

from __future__ import annotations

import dataclasses
import enum
import json
import pathlib
from typing import Any, Iterable

SCHEMA_VERSION = "1.0.0"


# ---------------------------------------------------------------- 검증 수준
class Verification(str, enum.Enum):
    """속성 값의 근거 수준. 낮은 쪽부터."""

    UNKNOWN = "unknown"                  # 값 없음. 절대 0/false 로 치환하지 않는다.
    DRAWING_INFERRED = "drawing_inferred"  # 도면에서 추정 (기호 미확정 등)
    DRAWING_READ = "drawing_read"        # 도면에서 직접 판독
    DOCUMENT = "official_document"       # 공식 문서/대장
    FIELD_MEASURED = "field_measured"    # 현장 실측

    @property
    def rank(self) -> int:
        return _VERIF_RANK[self]


_VERIF_RANK = {
    Verification.UNKNOWN: 0,
    Verification.DRAWING_INFERRED: 1,
    Verification.DRAWING_READ: 2,
    Verification.DOCUMENT: 3,
    Verification.FIELD_MEASURED: 4,
}

# 휠체어 접근성 판정에 쓸 수 있는 최소 검증 수준.
# 도면 판독만으로는 폭/문턱/경사를 확정하지 않는다.
MIN_VERIFICATION_FOR_ACCESSIBILITY = Verification.FIELD_MEASURED


@dataclasses.dataclass
class Attr:
    """근거를 동반한 단일 속성값.

    value=None 은 '모름'이다. 호출부는 `.is_known` 으로 확인해야 하며
    None 을 0/False 로 해석해서는 안 된다.
    """

    value: Any = None
    unit: str | None = None
    verification: Verification = Verification.UNKNOWN
    source_refs: list[str] = dataclasses.field(default_factory=list)
    observed_at: str | None = None
    method: str | None = None
    note: str | None = None

    @property
    def is_known(self) -> bool:
        return self.value is not None and self.verification != Verification.UNKNOWN

    def known_at_least(self, level: Verification) -> bool:
        return self.is_known and self.verification.rank >= level.rank

    def to_json(self) -> dict:
        d = {"value": self.value, "verification": self.verification.value}
        for k in ("unit", "source_refs", "observed_at", "method", "note"):
            v = getattr(self, k)
            if v:
                d[k] = v
        return d

    @classmethod
    def from_json(cls, d: Any) -> "Attr":
        if d is None:
            return cls()
        if not isinstance(d, dict):
            # 원시값이 그냥 들어온 경우: 근거 없음으로 처리하고 경고 대상
            return cls(value=d, verification=Verification.UNKNOWN,
                       note="raw value without evidence")
        return cls(
            value=d.get("value"),
            unit=d.get("unit"),
            verification=Verification(d.get("verification", "unknown")),
            source_refs=list(d.get("source_refs", [])),
            observed_at=d.get("observed_at"),
            method=d.get("method"),
            note=d.get("note"),
        )


UNKNOWN = Attr()


# ---------------------------------------------------------------- 열거형
class NodeKind(str, enum.Enum):
    OUTDOOR_JUNCTION = "outdoor_junction"
    ENTRANCE_OUTSIDE = "entrance_outside"
    ENTRANCE_INSIDE = "entrance_inside"
    CORRIDOR_JUNCTION = "corridor_junction"
    ROOM_DOOR = "room_door"
    ELEVATOR_LOBBY = "elevator_lobby"
    STAIR_LANDING = "stair_landing"


class EdgeKind(str, enum.Enum):
    OUTDOOR_WALK = "outdoor_walk"
    CORRIDOR = "corridor"
    DOOR = "door"
    ENTRANCE = "entrance"
    RAMP = "ramp"
    STAIRS = "stairs"
    ELEVATOR_RIDE = "elevator_ride"
    BUILDING_CONNECTOR = "building_connector"


#: 수직 이동 엣지. 보행 경사 지표 집계에서 제외한다.
VERTICAL_EDGE_KINDS = {EdgeKind.STAIRS, EdgeKind.ELEVATOR_RIDE}

#: 계단으로 간주하는 엣지 (no_stairs 제약에서 제거 대상)
STAIR_EDGE_KINDS = {EdgeKind.STAIRS}


class MappingStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    SOURCE_LABEL_CONFLICT = "source_label_conflict"
    RESOLVED_DRAFT = "resolved_draft"       # 도면 내부표기 기준 초안
    FIELD_CONFIRMED = "field_confirmed"


class PlaceStatus(str, enum.Enum):
    DRAWING_CANDIDATE = "drawing_candidate"  # 도면에서만 확인. 현장 미확인
    FIELD_CONFIRMED = "field_confirmed"
    RETIRED = "retired"


# ---------------------------------------------------------------- 좌표
@dataclasses.dataclass
class PlanPoint:
    """도면 픽셀 좌표. coordinate_space 는 반드시 층을 포함한다."""

    coordinate_space: str   # 예: "plan:mirae/F3"
    x_px: float
    y_px: float

    def to_json(self) -> dict:
        return {"coordinate_space": self.coordinate_space,
                "x_px": round(self.x_px, 2), "y_px": round(self.y_px, 2)}


@dataclasses.dataclass
class GeoPoint:
    lon: float
    lat: float

    def to_json(self) -> dict:
        return {"lon": self.lon, "lat": self.lat}


# ---------------------------------------------------------------- 핵심 객체
@dataclasses.dataclass
class FloorPlan:
    """도면 원본 1장. 층 표기를 4종류로 분리 보관한다."""

    id: str
    image_ref: str
    width_px: int | None = None
    height_px: int | None = None
    # --- 층 표기 분리 (합치지 않는다) ---
    source_tab_label: str | None = None      # 웹페이지 탭 이름
    source_filename: str | None = None
    drawing_floor_label: str | None = None   # 도면 내부 인쇄 표기
    page_tab_id: str | None = None
    mapping_status: MappingStatus = MappingStatus.PENDING_REVIEW
    # --- 축척/정합 ---
    #: 도면 1픽셀당 미터. 근거 없으면 unknown -> 거리/ETA 를 숫자로 제공 금지
    scale_m_per_px: Attr = dataclasses.field(default_factory=Attr)
    control_points: list[dict] = dataclasses.field(default_factory=list)
    geo_transform: dict | None = None        # 지리 정합 결과. 미정합이면 None
    geo_error_estimate_m: Attr = dataclasses.field(default_factory=Attr)
    revision_date: str | None = None         # 도면 개정일. 불명 -> None
    #: 이 도면의 픽셀을 재서 엣지 길이를 만들었는가.
    #: True  = 길이가 도면 유래. 축척이 unknown 이면 길이도 있을 수 없다.
    #: False = 길이가 다른 출처(실측, OSM 등)에서 온다. 도면은 표시용이며
    #:         축척이 없어도 길이를 가질 수 있다. 캠퍼스 배치도가 이 경우다.
    lengths_from_plan: bool = True
    source_refs: list[str] = dataclasses.field(default_factory=list)
    usage_terms: str = "unknown"
    notes: list[str] = dataclasses.field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "id": self.id, "image_ref": self.image_ref,
            "width_px": self.width_px, "height_px": self.height_px,
            "source_tab_label": self.source_tab_label,
            "source_filename": self.source_filename,
            "drawing_floor_label": self.drawing_floor_label,
            "page_tab_id": self.page_tab_id,
            "mapping_status": self.mapping_status.value,
            "scale_m_per_px": self.scale_m_per_px.to_json(),
            "control_points": self.control_points,
            "geo_transform": self.geo_transform,
            "geo_error_estimate_m": self.geo_error_estimate_m.to_json(),
            "revision_date": self.revision_date,
            "source_refs": self.source_refs,
            "usage_terms": self.usage_terms,
            "notes": self.notes,
        }


@dataclasses.dataclass
class Floor:
    """서비스 층. label 은 표시용, sort_order 는 정렬용, elevation 은 별도."""

    id: str                  # 예: "mirae/F3"  (안정 ID)
    building_id: str
    label: str               # 표시 문자열 (예: "3층")
    sort_order: int          # 낮은 층 -> 높은 층 순서
    wing_id: str | None = None
    plan_id: str | None = None
    elevation_m: Attr = dataclasses.field(default_factory=Attr)
    #: 다른 건물의 같은 층 번호가 같은 높이라는 가정을 하지 않는다.
    notes: list[str] = dataclasses.field(default_factory=list)

    def to_json(self) -> dict:
        return {"id": self.id, "building_id": self.building_id,
                "label": self.label, "sort_order": self.sort_order,
                "wing_id": self.wing_id, "plan_id": self.plan_id,
                "elevation_m": self.elevation_m.to_json(), "notes": self.notes}


@dataclasses.dataclass
class Building:
    id: str
    official_name: str
    campus_code: str | None = None
    aliases: list[str] = dataclasses.field(default_factory=list)
    wings: list[str] = dataclasses.field(default_factory=list)
    footprint: dict | None = None
    source_refs: list[str] = dataclasses.field(default_factory=list)

    def to_json(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Place:
    """검색 가능한 목적지. 미등록 호실을 만들지 않는다."""

    id: str                  # 예: "mirae/F3/338"
    name: str
    building_id: str
    floor_id: str
    room_label: str | None = None
    aliases: list[str] = dataclasses.field(default_factory=list)
    wing_id: str | None = None
    door_node_ids: list[str] = dataclasses.field(default_factory=list)
    status: PlaceStatus = PlaceStatus.DRAWING_CANDIDATE
    label_plan_point: PlanPoint | None = None
    source_refs: list[str] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "id": self.id, "name": self.name, "building_id": self.building_id,
            "floor_id": self.floor_id, "room_label": self.room_label,
            "aliases": self.aliases, "wing_id": self.wing_id,
            "door_node_ids": self.door_node_ids, "status": self.status.value,
            "label_plan_point": self.label_plan_point.to_json() if self.label_plan_point else None,
            "source_refs": self.source_refs, "notes": self.notes,
        }


@dataclasses.dataclass
class Node:
    id: str
    kind: NodeKind
    building_id: str | None = None
    floor_id: str | None = None
    plan_point: PlanPoint | None = None
    geo_point: GeoPoint | None = None
    name: str | None = None
    facility_id: str | None = None     # 계단/승강기 시설 ID
    source_refs: list[str] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "id": self.id, "kind": self.kind.value,
            "building_id": self.building_id, "floor_id": self.floor_id,
            "plan_point": self.plan_point.to_json() if self.plan_point else None,
            "geo_point": self.geo_point.to_json() if self.geo_point else None,
            "name": self.name, "facility_id": self.facility_id,
            "source_refs": self.source_refs, "notes": self.notes,
        }


@dataclasses.dataclass
class Accessibility:
    """엣지의 접근성 속성. 모든 항목이 Attr 이므로 unknown 이 보존된다.

    경사는 방향별로 나눈다. from->to 진행 방향 기준:
      slope_up_pct   : 진행 방향 오르막 경사(%)
      slope_down_pct : 진행 방향 내리막 경사(%)
    둘 중 해당하지 않는 쪽은 unknown 이 아니라 0 이 될 수 있으나,
    근거 없이 0 을 넣지 않는다.
    """

    stairs: Attr = dataclasses.field(default_factory=Attr)
    step_count: Attr = dataclasses.field(default_factory=Attr)
    slope_up_pct: Attr = dataclasses.field(default_factory=Attr)
    slope_down_pct: Attr = dataclasses.field(default_factory=Attr)
    cross_slope_pct: Attr = dataclasses.field(default_factory=Attr)
    clear_width_m: Attr = dataclasses.field(default_factory=Attr)
    threshold_m: Attr = dataclasses.field(default_factory=Attr)
    surface: Attr = dataclasses.field(default_factory=Attr)
    door_operability: Attr = dataclasses.field(default_factory=Attr)
    wheelchair_usable: Attr = dataclasses.field(default_factory=Attr)

    FIELDS = ("stairs", "step_count", "slope_up_pct", "slope_down_pct",
              "cross_slope_pct", "clear_width_m", "threshold_m", "surface",
              "door_operability", "wheelchair_usable")

    def to_json(self) -> dict:
        return {f: getattr(self, f).to_json() for f in self.FIELDS}

    @classmethod
    def from_json(cls, d: dict | None) -> "Accessibility":
        d = d or {}
        return cls(**{f: Attr.from_json(d.get(f)) for f in cls.FIELDS})

    def unknown_fields(self, required: Iterable[str],
                       level: Verification = MIN_VERIFICATION_FOR_ACCESSIBILITY,
                       ) -> list[str]:
        return [f for f in required if not getattr(self, f).known_at_least(level)]


@dataclasses.dataclass
class Edge:
    """방향 엣지. 양방향 통행이면 두 개를 만든다 (역방향 경사 부호가 다르다)."""

    id: str
    from_node: str
    to_node: str
    kind: EdgeKind
    #: 수평 이동거리. 축척 미확정이면 unknown -> 거리/ETA 숫자 제공 금지
    horizontal_length_m: Attr = dataclasses.field(default_factory=Attr)
    #: 실제 통행거리(계단 사면 등 포함)
    traversal_length_m: Attr = dataclasses.field(default_factory=Attr)
    vertical_rise_m: Attr = dataclasses.field(default_factory=Attr)
    accessibility: Accessibility = dataclasses.field(default_factory=Accessibility)
    facility_id: str | None = None        # 계단/승강기/문 시설 ID
    schedule_id: str | None = None        # 운영시간
    geometry: list[list[float]] = dataclasses.field(default_factory=list)  # 도면 좌표 polyline
    #: 엘리베이터 승차 엣지 전용
    elevator_from_floor: str | None = None
    elevator_to_floor: str | None = None
    source_refs: list[str] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)
    #: 이 엣지의 접근성 판정에 요구하는 최소 검증 수준.
    #: 파트(데이터 출처)별로 다르게 선언할 수 있다. 실내 도면 기반 데이터는
    #: 현장 실측을 요구하지만, 실외 OSM 기반 데이터는 그 수준의 근거를 얻을 수
    #: 없으므로 낮춰 선언한다.
    #: None 이면 전역 기본값(MIN_VERIFICATION_FOR_ACCESSIBILITY)을 쓴다.
    #: 정책이 절대 하한으로 다시 제한하므로, 데이터가 이 값을 낮춰도
    #: unknown 을 통행 가능으로 만들 수는 없다.
    min_accessibility_verification: "Verification | None" = None
    #: 이 엣지의 길이가 '가정 상수'인가.
    #: 팀원 그래프의 assumptions(층고 4m, 연결 35m, 계단 20m 등)처럼
    #: 실측도 OSM 도 아닌 값이면 True 다.
    #: 시간 계산에는 그대로 쓰지만(다른 근거가 없다), 경로 선택에서는
    #: 실측 기반 구간보다 후순위로 둔다. 근거 없는 상수를 여러 개 더해
    #: 만든 지름길이 실측 경로를 이기면 존재하지 않는 길을 안내하게 된다.
    length_is_assumed: bool = False
    #: 이 엣지의 접근성 속성(폭/문턱/경사)이 '전제값'인가.
    #: 현장 실측이 아니라 '여기는 통행 가능하다'는 판단을 근거로 기록한 값이면
    #: True 다. 휠체어 경로가 이런 구간을 지나면 경로 응답의
    #: assumed_accessibility_segments 에 집계되어 사용자에게 보고된다.
    #: '확인된 접근성'과 '전제된 접근성'을 섞어 보고하지 않기 위한 장치다.
    accessibility_is_assumed: bool = False

    def accessibility_threshold(self, absolute_floor: "Verification") -> "Verification":
        """실제로 적용할 최소 검증 수준.

        데이터가 선언한 값과 정책의 절대 하한 중 **높은** 쪽을 쓴다.
        데이터 파일이 정책을 임의로 무력화하지 못하게 하는 장치다.
        """
        declared = self.min_accessibility_verification \
            or MIN_VERIFICATION_FOR_ACCESSIBILITY
        return declared if declared.rank >= absolute_floor.rank else absolute_floor

    @property
    def evidence_is_relaxed(self) -> bool:
        """전역 기본값보다 낮은 근거 수준으로 판정되는 엣지인가."""
        d = self.min_accessibility_verification
        return d is not None and d.rank < MIN_VERIFICATION_FOR_ACCESSIBILITY.rank

    def to_json(self) -> dict:
        return {
            "id": self.id, "from_node": self.from_node, "to_node": self.to_node,
            "kind": self.kind.value,
            "horizontal_length_m": self.horizontal_length_m.to_json(),
            "traversal_length_m": self.traversal_length_m.to_json(),
            "vertical_rise_m": self.vertical_rise_m.to_json(),
            "accessibility": self.accessibility.to_json(),
            "facility_id": self.facility_id, "schedule_id": self.schedule_id,
            "geometry": self.geometry,
            "elevator_from_floor": self.elevator_from_floor,
            "elevator_to_floor": self.elevator_to_floor,
            "source_refs": self.source_refs, "notes": self.notes,
            "min_accessibility_verification":
                self.min_accessibility_verification.value
                if self.min_accessibility_verification else None,
            "length_is_assumed": self.length_is_assumed,
            "accessibility_is_assumed": self.accessibility_is_assumed,
        }



@dataclasses.dataclass
class Elevator:
    """승강기. served_floor_ids 는 '실제 정차층'이며 근거가 있어야 한다."""

    id: str
    building_id: str
    shaft_group: str | None = None
    served_floor_ids: list[str] = dataclasses.field(default_factory=list)
    served_floors_evidence: Attr = dataclasses.field(default_factory=Attr)
    door_node_ids: dict[str, str] = dataclasses.field(default_factory=dict)  # floor_id -> node_id
    car_width_m: Attr = dataclasses.field(default_factory=Attr)
    car_depth_m: Attr = dataclasses.field(default_factory=Attr)
    door_width_m: Attr = dataclasses.field(default_factory=Attr)
    wheelchair_usable: Attr = dataclasses.field(default_factory=Attr)
    status: str = "unknown"            # unknown | in_service | out_of_service
    status_checked_at: str | None = None
    wait_s_assumed: float | None = None
    ride_s_per_floor_assumed: float | None = None
    board_alight_s_assumed: float | None = None
    source_refs: list[str] = dataclasses.field(default_factory=list)
    notes: list[str] = dataclasses.field(default_factory=list)

    def to_json(self) -> dict:
        d = dataclasses.asdict(self)
        for k in ("served_floors_evidence", "car_width_m", "car_depth_m",
                  "door_width_m", "wheelchair_usable"):
            d[k] = getattr(self, k).to_json()
        return d


@dataclasses.dataclass
class Closure:
    """일시 통행 제한. 시설 ID 단위로 관리해 관련 엣지 전부에 반영한다."""

    id: str
    target_kind: str          # "edge" | "facility"
    target_id: str
    status: str               # "closed" | "restricted"
    starts_at: str | None = None
    ends_at: str | None = None
    reason: str | None = None
    source_ref: str | None = None
    updated_at: str | None = None

    def to_json(self) -> dict:
        return dataclasses.asdict(self)


@dataclasses.dataclass
class Observation:
    """현장/문서 관측 1건. data/survey/observations.csv 와 대응."""

    target_id: str
    field: str
    value: Any
    unit: str | None
    method: str
    observed_at: str
    source_ref: str | None = None
    reviewer: str | None = None
    expires_at: str | None = None
    note: str | None = None


# ---------------------------------------------------------------- 검증
class SchemaError(Exception):
    pass


def validate_dataset(
    buildings: dict[str, Building],
    floors: dict[str, Floor],
    plans: dict[str, FloorPlan],
    places: dict[str, Place],
    nodes: dict[str, Node],
    edges: list[Edge],
    elevators: dict[str, Elevator],
) -> list[str]:
    """구조 검증. 치명적 문제는 예외, 경고는 문자열 목록으로 돌려준다."""
    problems: list[str] = []

    for f in floors.values():
        if f.building_id not in buildings:
            raise SchemaError(f"floor {f.id}: 알 수 없는 building_id {f.building_id}")
        if f.plan_id and f.plan_id not in plans:
            raise SchemaError(f"floor {f.id}: 알 수 없는 plan_id {f.plan_id}")

    for n in nodes.values():
        if n.floor_id and n.floor_id not in floors:
            raise SchemaError(f"node {n.id}: 알 수 없는 floor_id {n.floor_id}")
        if n.plan_point:
            # 좌표 공간은 '층' 또는 그 층이 쓰는 '도면' 으로 식별한다.
            # 두 형태를 모두 허용한다:
            #   plan:<floor_id>   층마다 도면이 따로인 경우 (미래관)
            #   plan:<plan_id>    여러 층이 한 장을 공유하는 경우 (캠퍼스 배치도.
            #                     건물 발자국은 층이 달라도 같은 위치다)
            # 어느 쪽이든 다른 층/도면의 값을 복사하면 불일치로 걸린다.
            fl = floors.get(n.floor_id) if n.floor_id else None
            allowed = {f"plan:{n.floor_id}"}
            if fl and fl.plan_id:
                allowed.add(f"plan:{fl.plan_id}")
            if n.plan_point.coordinate_space not in allowed:
                raise SchemaError(
                    f"node {n.id}: plan 좌표공간 불일치 "
                    f"({n.plan_point.coordinate_space} not in "
                    f"{sorted(allowed)}). "
                    "다른 층/도면의 좌표를 복사했을 가능성이 있다."
                )
        if n.plan_point is None and n.geo_point is None:
            problems.append(f"node {n.id}: 좌표 없음")

    seen_edge_ids: set[str] = set()
    for e in edges:
        if e.id in seen_edge_ids:
            raise SchemaError(f"edge id 중복: {e.id}")
        seen_edge_ids.add(e.id)
        for ref in (e.from_node, e.to_node):
            if ref not in nodes:
                raise SchemaError(f"edge {e.id}: 알 수 없는 노드 {ref}")
        a, b = nodes[e.from_node], nodes[e.to_node]
        # 층을 넘어도 되는 엣지: 수직 이동 시설, 출입구,
        # 건물 간 연결통로, 그리고 경사로.
        # 경사로는 층을 넘을 수 있다 (지하로 내려가는 램프, 경사 지형의
        # 완만한 연결). 다만 수직 시설이 아니므로 보행 경사 집계에는
        # 그대로 포함된다 — 경사로는 실제로 사람이 걷는 면이다.
        if e.kind not in VERTICAL_EDGE_KINDS and e.kind not in (
                EdgeKind.ENTRANCE, EdgeKind.BUILDING_CONNECTOR, EdgeKind.RAMP):
            if a.floor_id != b.floor_id:
                raise SchemaError(
                    f"edge {e.id}({e.kind.value}): 서로 다른 층을 직접 연결 "
                    f"({a.floor_id} -> {b.floor_id}). 층간 시설 엣지만 허용."
                )
        if e.kind == EdgeKind.ELEVATOR_RIDE:
            if not e.facility_id or e.facility_id not in elevators:
                raise SchemaError(f"edge {e.id}: elevator_ride 인데 facility_id 없음/미등록")
            ev = elevators[e.facility_id]
            for fid in (e.elevator_from_floor, e.elevator_to_floor):
                if fid not in ev.served_floor_ids:
                    raise SchemaError(
                        f"edge {e.id}: {fid} 는 승강기 {ev.id} 의 정차층 목록에 없다."
                    )

    for p in places.values():
        if p.floor_id not in floors:
            raise SchemaError(f"place {p.id}: 알 수 없는 floor_id {p.floor_id}")
        if not p.door_node_ids:
            problems.append(f"place {p.id}: 문 노드가 없어 경로 목적지로 쓸 수 없음")
        for nid in p.door_node_ids:
            if nid not in nodes:
                raise SchemaError(f"place {p.id}: 알 수 없는 door 노드 {nid}")

    for ev in elevators.values():
        for fid in ev.served_floor_ids:
            if fid not in floors:
                raise SchemaError(f"elevator {ev.id}: 알 수 없는 정차층 {fid}")
        if not ev.served_floors_evidence.is_known:
            problems.append(
                f"elevator {ev.id}: 정차층 근거가 unknown -> 층간 경로에 사용 금지"
            )

    for pl in plans.values():
        if not pl.scale_m_per_px.is_known:
            problems.append(
                f"plan {pl.id}: 축척 unknown -> 이 층의 거리/ETA 를 숫자로 제공하지 말 것"
            )
        if pl.mapping_status in (MappingStatus.PENDING_REVIEW,
                                 MappingStatus.SOURCE_LABEL_CONFLICT):
            problems.append(
                f"plan {pl.id}: 층 매핑 미확정({pl.mapping_status.value}) "
                f"web='{pl.source_tab_label}' drawing='{pl.drawing_floor_label}'"
            )

    return problems


def dump_json(path: pathlib.Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
