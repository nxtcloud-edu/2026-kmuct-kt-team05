"""
방향 다중그래프 + 데이터셋 로더.

- 방향 엣지를 그대로 보관한다 (양방향은 데이터에 두 개로 존재).
- 같은 노드쌍에 여러 엣지(병렬 통로)가 있을 수 있다 -> 다중그래프.
- Closure 는 시설 ID 단위로 관리해 관련 엣지 전부에 반영한다.
"""

from __future__ import annotations

import json
import pathlib
from collections import defaultdict

from ..models.schema import (
    Accessibility,
    Attr,
    Building,
    Closure,
    Edge,
    EdgeKind,
    Elevator,
    Floor,
    FloorPlan,
    GeoPoint,
    MappingStatus,
    Node,
    NodeKind,
    Place,
    PlaceStatus,
    PlanPoint,
    validate_dataset,
)


class Dataset:
    """발행된 그래프 1개 버전."""

    def __init__(self, doc: dict, source: str = "<memory>"):
        self.source = source
        self.graph_version: str = doc.get("graph_version", "unversioned")
        self.schema_version: str = doc.get("schema_version", "unknown")
        self.generated_at: str | None = doc.get("generated_at")
        self.verification_scope: dict = doc.get("verification_scope", {})
        self.notes: list[str] = list(doc.get("notes", []))

        self.buildings = {b["id"]: Building(**b) for b in doc.get("buildings", [])}
        self.plans = {p["id"]: _plan_from_json(p) for p in doc.get("floorplans", [])}
        self.floors = {f["id"]: _floor_from_json(f) for f in doc.get("floors", [])}
        self.places = {p["id"]: _place_from_json(p) for p in doc.get("places", [])}
        self.nodes = {n["id"]: _node_from_json(n) for n in doc.get("nodes", [])}
        self.edges = [_edge_from_json(e) for e in doc.get("edges", [])]
        self.elevators = {e["id"]: _elevator_from_json(e) for e in doc.get("elevators", [])}
        self.closures = [Closure(**c) for c in doc.get("closures", [])]

        self.warnings = validate_dataset(
            self.buildings, self.floors, self.plans, self.places,
            self.nodes, self.edges, self.elevators,
        )

        # 인접 리스트 (방향)
        self.out: dict[str, list[Edge]] = defaultdict(list)
        for e in self.edges:
            self.out[e.from_node].append(e)

        self._closed_edge_ids: set[str] = set()
        self._closed_facility_ids: set[str] = set()
        for c in self.closures:
            if c.status not in ("closed", "restricted"):
                continue
            if c.target_kind == "edge":
                self._closed_edge_ids.add(c.target_id)
            elif c.target_kind == "facility":
                self._closed_facility_ids.add(c.target_id)

    # ------------------------------------------------------------ 조회
    def is_closed(self, edge: Edge) -> bool:
        if edge.id in self._closed_edge_ids:
            return True
        if edge.facility_id and edge.facility_id in self._closed_facility_ids:
            return True
        if edge.kind == EdgeKind.ELEVATOR_RIDE and edge.facility_id:
            ev = self.elevators.get(edge.facility_id)
            if ev is not None and ev.status == "out_of_service":
                return True
        return False

    def floor_of(self, node_id: str) -> str | None:
        n = self.nodes.get(node_id)
        return n.floor_id if n else None

    def plan_for_floor(self, floor_id: str) -> FloorPlan | None:
        f = self.floors.get(floor_id)
        if f is None or f.plan_id is None:
            return None
        return self.plans.get(f.plan_id)

    def scale_known(self, floor_id: str) -> bool:
        pl = self.plan_for_floor(floor_id)
        return bool(pl and pl.scale_m_per_px.is_known)

    def find_places(self, query: str) -> list[Place]:
        """건물/호실 후보 검색. 모호하면 여러 개를 돌려준다 (임의 확정 금지)."""
        q = query.replace(" ", "").lower()
        if not q:
            return []
        exact, partial = [], []
        for p in self.places.values():
            keys = [p.name, p.room_label or "", *p.aliases]
            keys = [k.replace(" ", "").lower() for k in keys if k]
            if q in keys:
                exact.append(p)
            elif any(q in k or k in q for k in keys):
                partial.append(p)
        return exact or partial

    @classmethod
    def load(cls, path: str | pathlib.Path) -> "Dataset":
        p = pathlib.Path(path)
        with p.open(encoding="utf-8") as fh:
            return cls(json.load(fh), source=str(p))


# ---------------------------------------------------------------- 역직렬화
def _plan_from_json(d: dict) -> FloorPlan:
    return FloorPlan(
        id=d["id"], image_ref=d.get("image_ref", ""),
        width_px=d.get("width_px"), height_px=d.get("height_px"),
        source_tab_label=d.get("source_tab_label"),
        source_filename=d.get("source_filename"),
        drawing_floor_label=d.get("drawing_floor_label"),
        page_tab_id=d.get("page_tab_id"),
        mapping_status=MappingStatus(d.get("mapping_status", "pending_review")),
        scale_m_per_px=Attr.from_json(d.get("scale_m_per_px")),
        control_points=d.get("control_points", []),
        geo_transform=d.get("geo_transform"),
        geo_error_estimate_m=Attr.from_json(d.get("geo_error_estimate_m")),
        revision_date=d.get("revision_date"),
        source_refs=d.get("source_refs", []),
        usage_terms=d.get("usage_terms", "unknown"),
        notes=d.get("notes", []),
    )


def _floor_from_json(d: dict) -> Floor:
    return Floor(
        id=d["id"], building_id=d["building_id"], label=d["label"],
        sort_order=int(d["sort_order"]), wing_id=d.get("wing_id"),
        plan_id=d.get("plan_id"),
        elevation_m=Attr.from_json(d.get("elevation_m")),
        notes=d.get("notes", []),
    )


def _place_from_json(d: dict) -> Place:
    pp = d.get("label_plan_point")
    return Place(
        id=d["id"], name=d["name"], building_id=d["building_id"],
        floor_id=d["floor_id"], room_label=d.get("room_label"),
        aliases=d.get("aliases", []), wing_id=d.get("wing_id"),
        door_node_ids=d.get("door_node_ids", []),
        status=PlaceStatus(d.get("status", "drawing_candidate")),
        label_plan_point=PlanPoint(**pp) if pp else None,
        source_refs=d.get("source_refs", []), notes=d.get("notes", []),
    )


def _node_from_json(d: dict) -> Node:
    pp, gp = d.get("plan_point"), d.get("geo_point")
    return Node(
        id=d["id"], kind=NodeKind(d["kind"]),
        building_id=d.get("building_id"), floor_id=d.get("floor_id"),
        plan_point=PlanPoint(**pp) if pp else None,
        geo_point=GeoPoint(**gp) if gp else None,
        name=d.get("name"), facility_id=d.get("facility_id"),
        source_refs=d.get("source_refs", []), notes=d.get("notes", []),
    )


def _edge_from_json(d: dict) -> Edge:
    return Edge(
        id=d["id"], from_node=d["from_node"], to_node=d["to_node"],
        kind=EdgeKind(d["kind"]),
        horizontal_length_m=Attr.from_json(d.get("horizontal_length_m")),
        traversal_length_m=Attr.from_json(d.get("traversal_length_m")),
        vertical_rise_m=Attr.from_json(d.get("vertical_rise_m")),
        accessibility=Accessibility.from_json(d.get("accessibility")),
        facility_id=d.get("facility_id"), schedule_id=d.get("schedule_id"),
        geometry=d.get("geometry", []),
        elevator_from_floor=d.get("elevator_from_floor"),
        elevator_to_floor=d.get("elevator_to_floor"),
        source_refs=d.get("source_refs", []), notes=d.get("notes", []),
    )


def _elevator_from_json(d: dict) -> Elevator:
    return Elevator(
        id=d["id"], building_id=d["building_id"],
        shaft_group=d.get("shaft_group"),
        served_floor_ids=d.get("served_floor_ids", []),
        served_floors_evidence=Attr.from_json(d.get("served_floors_evidence")),
        door_node_ids=d.get("door_node_ids", {}),
        car_width_m=Attr.from_json(d.get("car_width_m")),
        car_depth_m=Attr.from_json(d.get("car_depth_m")),
        door_width_m=Attr.from_json(d.get("door_width_m")),
        wheelchair_usable=Attr.from_json(d.get("wheelchair_usable")),
        status=d.get("status", "unknown"),
        status_checked_at=d.get("status_checked_at"),
        wait_s_assumed=d.get("wait_s_assumed"),
        ride_s_per_floor_assumed=d.get("ride_s_per_floor_assumed"),
        board_alight_s_assumed=d.get("board_alight_s_assumed"),
        source_refs=d.get("source_refs", []), notes=d.get("notes", []),
    )
