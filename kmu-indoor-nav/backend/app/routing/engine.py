"""
경로 탐색 엔진.

탐색 순서 (구현지시서 7절)
  1) 명시적 조건 병합
  2) 통행 불가 엣지 제거   <- 큰 벌점이 아니라 실제 제거
  3) 목적함수 최적화       <- Dijkstra (h=0), 정확도 기준 구현
  4) 결과 제약 재검증      <- 반환 전 하드 제약 위반 0건 확인

상태 구분
  ok                          조건과 검증 범위에 맞는 경로 발견
  insufficient_verified_data  조건을 판정할 자료 부족 (현실 통행불가 아님)
  no_route_under_constraints  등록 그래프에서 조건 충족 경로 없음
  outside_coverage            지원 범위 밖
  needs_clarification         출발/도착/조건 확인 필요 (상위 계층에서 사용)

경로 분기 여부는 성공 기준이 아니다. 같은 경로라도 조건을 충족하면 정상이다.
"""

from __future__ import annotations

import dataclasses
import heapq
import itertools
from typing import Callable

from ..graph.dataset import Dataset
from ..models.schema import (
    MIN_VERIFICATION_FOR_ACCESSIBILITY,
    Edge,
    EdgeKind,
    NodeKind,
    VERTICAL_EDGE_KINDS,
)
from .policy import (
    BLOCK_CLOSED,
    BLOCK_UNVERIFIED,
    BLOCK_WHEELCHAIR_FLAG,
    POLICY_VERSION,
    TIME_MODELS,
    Block,
    Constraints,
    TimeModel,
    edge_block_reason,
    edge_outdoor_length_m,
    edge_preference_cost,
    edge_time_s,
)

OBJECTIVES = ("fastest", "comfort", "indoor")

#: 실내 선호 bi-criteria 탐색의 라벨 상한. 초과하면 approximate=True 로 보고.
INDOOR_LABEL_CAP = 200_000


class Status(str):
    pass


OK = Status("ok")
INSUFFICIENT = Status("insufficient_verified_data")
#: 접근성 근거가 없는 구간을 지나는 '조사용 후보 경로'.
#: 호출부가 allow_unverified_as_candidate 로 명시 요청했을 때만 나온다.
#: ok 와 반드시 구분해서 표시해야 한다.
CANDIDATE = Status("candidate_unverified")
NO_ROUTE = Status("no_route_under_constraints")
OUTSIDE = Status("outside_coverage")


@dataclasses.dataclass
class Traversal:
    """제약 적용 결과 1엣지."""

    edge: Edge
    time_s: float | None
    preference_cost: float
    outdoor_m: float
    floor_span: int = 0


class TraversalFilter:
    """제약을 엣지에 적용하고, 제거 사유와 시간/선호 비용을 계산한다."""

    def __init__(self, ds: Dataset, constraints: Constraints, profile: str,
                 ignore_unverified: bool = False):
        self.ds = ds
        self.c = constraints
        self.profile = profile
        self.tm: TimeModel = TIME_MODELS.get(profile, TIME_MODELS["normal"])
        #: True 면 '미검증' 사유의 제거를 생략한다 (자료부족 진단용 2차 탐색)
        self.ignore_unverified = ignore_unverified
        self.block_counts: dict[str, int] = {}
        self.unverified_edge_ids: set[str] = set()
        self._floor_order = {f.id: f.sort_order for f in ds.floors.values()}

    def _note_block(self, reason: Block) -> None:
        self.block_counts[str(reason)] = self.block_counts.get(str(reason), 0) + 1

    def elevator_floor_span(self, edge: Edge) -> int:
        a = self._floor_order.get(edge.elevator_from_floor or "")
        b = self._floor_order.get(edge.elevator_to_floor or "")
        if a is None or b is None:
            return 1
        return max(1, abs(b - a))

    def check(self, edge: Edge) -> Traversal | None:
        closed = self.ds.is_closed(edge)
        reason = edge_block_reason(edge, self.c, closed)

        # 엘리베이터는 시설 속성으로 별도 판정 (승강기 객체가 필요)
        if reason is None and edge.kind == EdgeKind.ELEVATOR_RIDE and self.c.wheelchair:
            ev = self.ds.elevators.get(edge.facility_id or "")
            # 요구 근거 수준은 엣지(파트)가 선언한 값을 따른다.
            # 전역 상수를 직접 쓰면 실외 파트가 낮춰 선언한 수준이 무시되어
            # 승강기만 전부 차단된다.
            level = edge.accessibility_threshold(self.c.absolute_min_verification)
            if ev is None:
                reason = BLOCK_CLOSED
            elif ev.wheelchair_usable.is_known and ev.wheelchair_usable.value is False:
                reason = BLOCK_WHEELCHAIR_FLAG
            elif not ev.wheelchair_usable.known_at_least(level):
                reason = BLOCK_UNVERIFIED
            elif not ev.served_floors_evidence.is_known:
                reason = BLOCK_UNVERIFIED

        if reason is not None:
            if reason == BLOCK_UNVERIFIED:
                self.unverified_edge_ids.add(edge.id)
                if self.ignore_unverified:
                    reason = None
            if reason is not None:
                self._note_block(reason)
                return None

        span = self.elevator_floor_span(edge) if edge.kind == EdgeKind.ELEVATOR_RIDE else 0
        ev = self.ds.elevators.get(edge.facility_id or "") if span else None
        t = edge_time_s(
            edge, self.tm,
            elevator_wait_s=ev.wait_s_assumed if ev else None,
            elevator_floor_span=span or None,
            elevator_ride_s_per_floor=ev.ride_s_per_floor_assumed if ev else None,
            elevator_board_alight_s=ev.board_alight_s_assumed if ev else None,
        )
        if t is None:
            # 거리/축척 근거가 없어 시간을 산출할 수 없다 -> 자료부족으로 취급
            self.unverified_edge_ids.add(edge.id)
            if not self.ignore_unverified:
                self._note_block(Block("length_or_scale_unknown"))
                return None
            t = 0.0
        return Traversal(
            edge=edge, time_s=t,
            preference_cost=edge_preference_cost(edge, self.profile),
            outdoor_m=edge_outdoor_length_m(edge),
            floor_span=span,
        )


# ---------------------------------------------------------------- Dijkstra
def dijkstra(
    ds: Dataset,
    start: str,
    goal: str,
    tf: TraversalFilter,
    weight: Callable[[Traversal], float],
) -> tuple[list[Traversal], float] | None:
    """h=0 다익스트라. 정확도 기준 구현.

    A* 는 모든 엣지에 대한 허용 하한을 증명하고 이 비용과 비교한 뒤에만 도입한다.
    """
    dist: dict[str, float] = {start: 0.0}
    prev: dict[str, tuple[str, Traversal]] = {}
    seq = itertools.count()
    heap: list[tuple[float, int, str]] = [(0.0, next(seq), start)]
    done: set[str] = set()

    while heap:
        d, _, u = heapq.heappop(heap)
        if u in done:
            continue
        done.add(u)
        if u == goal:
            return _rebuild(prev, start, goal), d
        for edge in ds.out.get(u, ()):
            tr = tf.check(edge)
            if tr is None:
                continue
            w = weight(tr)
            if w < 0:
                raise ValueError(f"음수 가중치: edge {edge.id} w={w}")
            nd = d + w
            v = edge.to_node
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, tr)
                heapq.heappush(heap, (nd, next(seq), v))
    return None


def _rebuild(prev, start, goal) -> list[Traversal]:
    out: list[Traversal] = []
    cur = goal
    while cur != start:
        p, tr = prev[cur]
        out.append(tr)
        cur = p
    out.reverse()
    return out


# ------------------------------------------------ 실내 선호 (bi-criteria)
def indoor_search(
    ds: Dataset, start: str, goal: str, tf: TraversalFilter, time_budget_s: float
) -> tuple[list[Traversal], bool] | None:
    """시간 예산 안에서 실외 이동거리를 최소화.

    (실외거리, 시간) 비지배 라벨을 유지하는 라벨수정 탐색.
    라벨 상한 초과 시 approximate=True 로 보고한다.
    """
    seq = itertools.count()
    # (outdoor, time, node, path)
    heap: list[tuple[float, float, int, str, tuple]] = [(0.0, 0.0, next(seq), start, ())]
    labels: dict[str, list[tuple[float, float]]] = {start: [(0.0, 0.0)]}
    expanded = 0
    approximate = False

    best: tuple[float, float, tuple] | None = None
    while heap:
        out_m, t_s, _, u, path = heapq.heappop(heap)
        expanded += 1
        if expanded > INDOOR_LABEL_CAP:
            approximate = True
            break
        if u == goal:
            if best is None or (out_m, t_s) < (best[0], best[1]):
                best = (out_m, t_s, path)
            continue
        for edge in ds.out.get(u, ()):
            tr = tf.check(edge)
            if tr is None:
                continue
            nt = t_s + (tr.time_s or 0.0)
            if nt > time_budget_s + 1e-9:
                continue
            no = out_m + tr.outdoor_m
            v = edge.to_node
            lab = labels.setdefault(v, [])
            if any(a <= no + 1e-9 and b <= nt + 1e-9 for a, b in lab):
                continue
            lab[:] = [(a, b) for a, b in lab if not (no <= a + 1e-9 and nt <= b + 1e-9)]
            lab.append((no, nt))
            heapq.heappush(heap, (no, nt, next(seq), v, path + (tr,)))

    if best is None:
        return None
    return list(best[2]), approximate


# ---------------------------------------------------------------- 결과
#: 수평 이동거리 개념이 적용되는 엣지. 엘리베이터 승차는 거리가 아니라
#: 시설 시간모델로 계산하므로 '길이 미상'으로 집계하지 않는다.
LENGTH_APPLICABLE_KINDS = {
    EdgeKind.OUTDOOR_WALK, EdgeKind.CORRIDOR, EdgeKind.DOOR,
    EdgeKind.ENTRANCE, EdgeKind.RAMP, EdgeKind.BUILDING_CONNECTOR,
    EdgeKind.STAIRS,
}


def summarize(ds: Dataset, path: list[Traversal], tf: TraversalFilter) -> dict:
    """지표를 항목별로 분리해 반환한다. 엣지 개수를 계단 단수로 쓰지 않는다."""
    total_m = 0.0
    length_unknown = 0
    time_s = 0.0
    outdoor_m = 0.0
    stair_segments = 0
    stair_steps_known = 0
    stair_steps_unknown_segments = 0
    elevator_boardings = 0
    observed_slopes: list[float] = []
    estimated_slopes: list[float] = []
    unverified_segments = 0
    floors_touched: list[str] = []

    for tr in path:
        e = tr.edge
        L = e.traversal_length_m if e.traversal_length_m.is_known else e.horizontal_length_m
        if L.is_known:
            total_m += float(L.value)
        elif e.kind in LENGTH_APPLICABLE_KINDS:
            length_unknown += 1
        time_s += tr.time_s or 0.0
        outdoor_m += tr.outdoor_m

        if e.kind == EdgeKind.STAIRS:
            stair_segments += 1
            sc = e.accessibility.step_count
            if sc.is_known:
                stair_steps_known += int(sc.value)
            else:
                stair_steps_unknown_segments += 1
        if e.kind == EdgeKind.ELEVATOR_RIDE:
            elevator_boardings += 1

        # 경사는 수직이동 엣지에서 집계하지 않는다
        if e.kind not in VERTICAL_EDGE_KINDS:
            for attr in (e.accessibility.slope_up_pct, e.accessibility.slope_down_pct):
                if not attr.is_known:
                    continue
                if attr.known_at_least(MIN_VERIFICATION_FOR_ACCESSIBILITY):
                    observed_slopes.append(abs(float(attr.value)))
                else:
                    estimated_slopes.append(abs(float(attr.value)))

        if e.id in tf.unverified_edge_ids:
            unverified_segments += 1

        for nid in (e.from_node, e.to_node):
            fid = ds.floor_of(nid)
            if fid and (not floors_touched or floors_touched[-1] != fid):
                floors_touched.append(fid)

    scale_ok = all(ds.scale_known(f) for f in floors_touched if f)

    return {
        # 보행거리. 축척/길이 근거가 없는 보행구간이 있으면 확정값으로 제공하지 않는다.
        # (엘리베이터 승차는 보행거리 0 이며 '미상'이 아니다.)
        "distance_m": round(total_m, 1) if length_unknown == 0 else None,
        "distance_partial_m": round(total_m, 1) if length_unknown else None,
        "segments_with_unknown_length": length_unknown,
        "scale_verified_for_all_floors": scale_ok,
        # 시간: 가정값 기반 추정. 경로에 포함된 엣지는 모두 시간 산출이 가능했다.
        "estimated_time_s": round(time_s, 1),
        "estimated_time_is_assumption": True,
        "outdoor_distance_m": round(outdoor_m, 1),
        "stair_segments": stair_segments,
        "stair_steps_observed": stair_steps_known or None,
        "stair_segments_without_step_count": stair_steps_unknown_segments,
        "elevator_boardings": elevator_boardings,
        "observed_max_slope_pct": round(max(observed_slopes), 2) if observed_slopes else None,
        "estimated_max_slope_pct": round(max(estimated_slopes), 2) if estimated_slopes else None,
        "unverified_segments": unverified_segments,
        # 길이가 가정 상수인 구간. 거리·시간이 이 값에 의존한다는 사실을
        # 숨기지 않는다. 이런 구간이 많은 경로는 실측 기반 경로보다 신뢰도가 낮다.
        "assumed_length_segments": sum(
            1 for tr in path if tr.edge.length_is_assumed),
        "assumed_length_m": round(sum(
            float(tr.edge.horizontal_length_m.value)
            for tr in path
            if tr.edge.length_is_assumed
            and tr.edge.horizontal_length_m.is_known), 1),
        # 접근성이 '전제값'인 구간. 확인된 접근성과 구분해 보고한다.
        "assumed_accessibility_segments": sum(
            1 for tr in path if tr.edge.accessibility_is_assumed),
        "accessibility_fully_verified": not any(
            tr.edge.accessibility_is_assumed for tr in path),
        "floors_touched": floors_touched,
    }


def build_segments(ds: Dataset, path: list[Traversal]) -> list[dict]:
    """실외 세그먼트와 실내 세그먼트를 분리하고 전환 지점을 명시한다."""
    segs: list[dict] = []
    for tr in path:
        e = tr.edge
        a, b = ds.nodes[e.from_node], ds.nodes[e.to_node]
        seg = {
            "edge_id": e.id, "kind": e.kind.value,
            "from_node": a.id, "to_node": b.id,
            "from_floor": a.floor_id, "to_floor": b.floor_id,
            "facility_id": e.facility_id,
            "time_s": round(tr.time_s, 1) if tr.time_s is not None else None,
            "source_refs": e.source_refs,
        }
        if e.kind == EdgeKind.OUTDOOR_WALK and a.geo_point and b.geo_point:
            seg["space"] = "geo"
            seg["geojson"] = {
                "type": "LineString",
                "coordinates": [[a.geo_point.lon, a.geo_point.lat],
                                [b.geo_point.lon, b.geo_point.lat]],
            }
        elif a.plan_point and b.plan_point and \
                a.plan_point.coordinate_space == b.plan_point.coordinate_space:
            # 같은 좌표 공간이면 층이 달라도 한 장의 그림 위에 그릴 수 있다.
            # 캠퍼스 배치도에서 건물 사이 연결통로가 이 경우다.
            seg["space"] = a.plan_point.coordinate_space
            seg["polyline_px"] = e.geometry or [
                [a.plan_point.x_px, a.plan_point.y_px],
                [b.plan_point.x_px, b.plan_point.y_px],
            ]
        else:
            seg["space"] = "transition"
            seg["transition"] = {"from_floor": a.floor_id, "to_floor": b.floor_id}
        segs.append(seg)
    return segs


def verify_result(path: list[Traversal], c: Constraints) -> list[str]:
    """반환 전 하드 제약 재검증. 위반이 있으면 사유 목록을 돌려준다."""
    bad: list[str] = []
    for tr in path:
        e = tr.edge
        if (c.no_stairs or c.wheelchair) and e.kind == EdgeKind.STAIRS:
            bad.append(f"{e.id}: 계단 금지 위반")
        if c.wheelchair and e.kind not in (EdgeKind.ELEVATOR_RIDE,):
            miss = e.accessibility.unknown_fields(
                ("clear_width_m",) if e.kind == EdgeKind.DOOR
                else c.required_accessibility_fields
            )
            if miss:
                bad.append(f"{e.id}: 필수 속성 미검증 {miss}")
    return bad


def _coverage_diagnostics(ds: Dataset, origin: str, dest: str) -> list[str]:
    """경로 없음의 원인을 '데이터 범위' 관점에서 구체화한다.

    '조건 때문에 막혔다' 와 '애초에 등록된 통로가 없다' 를 구분해 보고하기 위한 것.
    """
    out: list[str] = []
    fa, fb = ds.floor_of(origin), ds.floor_of(dest)
    if fa and fb and fa != fb:
        vertical = [
            e for e in ds.edges
            if e.kind in VERTICAL_EDGE_KINDS
            and {ds.floor_of(e.from_node), ds.floor_of(e.to_node)} & {fa, fb}
        ]
        if not vertical:
            la = ds.floors[fa].label if fa in ds.floors else fa
            lb = ds.floors[fb].label if fb in ds.floors else fb
            out.append(
                f"데이터 범위: '{la}' 와 '{lb}' 사이에 등록된 층간 이동 시설(계단/승강기) "
                f"엣지가 0개입니다. 조건 때문이 아니라 데이터가 없어서 경로가 없습니다."
            )
            if not ds.elevators:
                out.append(
                    "승강기가 하나도 등록되지 않았습니다. 도면에서 기호를 확정하지 못해 "
                    "추측 생성을 하지 않았습니다 (docs/data_gaps.md 참고)."
                )
            stair_nodes = [n for n in ds.nodes.values()
                           if n.kind == NodeKind.STAIR_LANDING]
            if stair_nodes:
                out.append(
                    f"계단 후보 노드는 {len(stair_nodes)}개 등록되어 있으나 "
                    f"복도 연결/정차층 근거가 없어 통행 엣지를 만들지 않았습니다: "
                    + ", ".join(n.id for n in stair_nodes)
                )
    else:
        same = fa or fb
        if same:
            lbl = ds.floors[same].label if same in ds.floors else same
            out.append(f"데이터 범위: 같은 층('{lbl}') 내에서 두 지점을 잇는 등록 통로가 없습니다.")
    return out


# ---------------------------------------------------------------- 진입점
def route(
    ds: Dataset,
    origin_node: str,
    dest_node: str,
    profile: str = "normal",
    objective: str = "fastest",
    constraints: Constraints | None = None,
) -> dict:
    c = constraints or Constraints()
    if objective not in OBJECTIVES:
        raise ValueError(f"알 수 없는 objective: {objective}")

    base = {
        "graph_version": ds.graph_version,
        "policy_version": POLICY_VERSION,
        "schema_version": ds.schema_version,
        "profile": profile,
        "objective": objective,
        "applied_constraints": c.signature(),
        "verification": {
            "scope": ds.verification_scope,
            "dataset_warnings": ds.warnings,
            "time_model_is_assumption": True,
        },
    }

    for nid in (origin_node, dest_node):
        if nid not in ds.nodes:
            return {**base, "status": str(OUTSIDE), "route_id": None,
                    "segments": [], "metrics": None,
                    "reasons": [f"등록되지 않은 노드: {nid}"]}

    # 출발 == 도착
    if origin_node == dest_node:
        return {**base, "status": str(OK), "route_id": f"{origin_node}->{dest_node}",
                "segments": [],
                "metrics": {"distance_m": 0.0, "estimated_time_s": 0.0,
                            "outdoor_distance_m": 0.0, "stair_segments": 0,
                            "elevator_boardings": 0, "unverified_segments": 0,
                            "floors_touched": [ds.floor_of(origin_node)],
                            "estimated_time_is_assumption": True},
                "instructions": [], "reasons": ["출발지와 목적지가 같습니다."]}

    tf = TraversalFilter(ds, c, profile)

    if objective == "fastest":
        found = dijkstra(ds, origin_node, dest_node, tf, lambda tr: tr.time_s or 0.0)
        path = found[0] if found else None
        approximate = False
    elif objective == "comfort":
        found = dijkstra(ds, origin_node, dest_node, tf,
                         lambda tr: (tr.time_s or 0.0) + tr.preference_cost)
        path = found[0] if found else None
        approximate = False
    else:  # indoor
        fast = dijkstra(ds, origin_node, dest_node, tf, lambda tr: tr.time_s or 0.0)
        if fast is None:
            path, approximate = None, False
        else:
            budget = fast[1] * (1.0 + c.indoor_detour_ratio)
            res = indoor_search(ds, origin_node, dest_node, tf, budget)
            if res is None:
                path, approximate = fast[0], False
            else:
                path, approximate = res

    if path is None:
        # 자료부족과 조건상 경로없음을 구분한다.
        tf2 = TraversalFilter(ds, c, profile, ignore_unverified=True)
        relaxed = dijkstra(ds, origin_node, dest_node, tf2, lambda tr: tr.time_s or 0.0)
        if relaxed is not None:
            if not c.allow_unverified_as_candidate:
                return {**base, "status": str(INSUFFICIENT), "route_id": None,
                        "segments": [], "metrics": None,
                        "blocked_counts": tf.block_counts,
                        "reasons": [
                            "필수 접근성 속성이 미확인인 구간을 제외하면 경로가 없습니다.",
                            "미확인 속성을 현장 조사하면 경로가 성립할 수 있습니다.",
                            f"미확인 구간 수: {len(tf.unverified_edge_ids)}",
                        ],
                        "unverified_edge_ids": sorted(tf.unverified_edge_ids)}
            # 호출부가 '조사용 후보 경로'를 명시적으로 요청했다.
            # 경로를 주되, 접근성을 확인했다고 말하지 않는다.
            path, tf = relaxed[0], tf2
            metrics = summarize(ds, path, tf)
            survey = sorted({
                tr.edge.id for tr in path
                if tr.edge.id in tf2.unverified_edge_ids})
            return {**base, "status": str(CANDIDATE),
                    "route_id": f"{origin_node}->{dest_node}:{objective}:candidate",
                    "segments": build_segments(ds, path),
                    "metrics": metrics,
                    "approximate": True,
                    "instructions": instructions(ds, path),
                    "blocked_counts": tf.block_counts,
                    "accessibility_confirmed": False,
                    "segments_requiring_survey": survey,
                    "reasons": [
                        "접근성이 확인된 경로가 아닙니다. 현장 조사용 후보입니다.",
                        f"근거가 없는 구간 {len(survey)}개를 통과합니다.",
                        "실제 통행 가능 여부는 현장에서 확인해야 합니다.",
                    ]}
        return {**base, "status": str(NO_ROUTE), "route_id": None,
                "segments": [], "metrics": None,
                "blocked_counts": tf.block_counts,
                "reasons": [
                    "현재 등록된 그래프에서 조건을 충족하는 경로가 없습니다.",
                    "현실에서 통행이 불가능하다는 뜻은 아닙니다 "
                    "(미등록 통로가 있을 수 있음).",
                    *_coverage_diagnostics(ds, origin_node, dest_node),
                ]}

    violations = verify_result(path, c)
    if violations:
        return {**base, "status": str(NO_ROUTE), "route_id": None,
                "segments": [], "metrics": None,
                "reasons": ["결과 재검증에서 하드 제약 위반이 발견되어 폐기했습니다.",
                            *violations]}

    metrics = summarize(ds, path, tf)
    return {**base, "status": str(OK),
            "route_id": f"{origin_node}->{dest_node}:{objective}",
            "segments": build_segments(ds, path),
            "metrics": metrics,
            "approximate": approximate,
            "instructions": instructions(ds, path),
            "blocked_counts": tf.block_counts,
            "reasons": []}


#: 연속으로 이어지면 한 단계로 합칠 엣지 종류
MERGEABLE = {EdgeKind.CORRIDOR, EdgeKind.OUTDOOR_WALK, EdgeKind.BUILDING_CONNECTOR}


def _way_word(kinds: set[EdgeKind]) -> str:
    """합쳐진 보행 구간을 무엇이라 부를지.

    실외 보행로를 '복도'라고 안내하면 사용자가 건물 안을 찾는다.
    섞였으면 어느 한쪽으로 단정하지 않고 '길'이라 한다.
    """
    if kinds == {EdgeKind.OUTDOOR_WALK}:
        return "보행로"
    if kinds == {EdgeKind.CORRIDOR}:
        return "복도"
    if kinds == {EdgeKind.BUILDING_CONNECTOR}:
        return "연결통로"
    if kinds <= {EdgeKind.CORRIDOR, EdgeKind.BUILDING_CONNECTOR}:
        return "실내 통로"
    return "길"


def instructions(ds: Dataset, path: list[Traversal]) -> list[dict]:
    """단계 안내. 템플릿 기반이며 LLM 이 내용을 바꾸지 않는다.

    연속된 복도 구간은 하나의 '따라 이동' 단계로 합친다.
    실내 단계는 '층/지점 선택 + 단계 완료 확인' 방식이다 (GPS 자동 층 확정 금지).
    """
    def floor_label(fid: str | None) -> str | None:
        f = ds.floors.get(fid or "")
        return f.label if f else None

    def edge_len(e: Edge) -> float:
        L = e.traversal_length_m if e.traversal_length_m.is_known \
            else e.horizontal_length_m
        return float(L.value) if L.is_known else 0.0

    out: list[dict] = []
    i = 0
    n = len(path)
    while i < n:
        tr = path[i]
        e = tr.edge
        a, b = ds.nodes[e.from_node], ds.nodes[e.to_node]

        if e.kind in MERGEABLE:
            # 같은 층의 연속 보행 구간을 하나로 합친다.
            # 실내 복도·실외 보행로·건물 연결통로를 함께 합치므로,
            # 어떤 종류가 섞였는지 기록해 안내 문구를 맞춘다.
            # (실외 보행로를 '복도'라고 안내하면 안 된다)
            j = i
            dist = 0.0
            secs = 0.0
            kinds: set[EdgeKind] = set()
            while j < n:
                ej = path[j].edge
                nj = ds.nodes[ej.to_node]
                if ej.kind not in MERGEABLE or nj.floor_id != b.floor_id:
                    break
                kinds.add(ej.kind)
                dist += edge_len(ej)
                secs += path[j].time_s or 0.0
                last = nj
                j += 1
            if j == i:              # 안전장치
                j = i + 1
                kinds = {e.kind}
                dist = edge_len(e)
                secs = tr.time_s or 0.0
                last = b
            if dist < 0.6:          # 0.6 m 미만은 안내하지 않는다
                i = j
                continue
            way = _way_word(kinds)
            dest = last.name or _nearby_name(ds, last) or way
            out.append({
                "edge_id": path[i].edge.id,
                "text": f"{way}를 따라 약 {dist:.0f} m 이동 ({dest} 방향)",
                "floor_id": last.floor_id, "floor_label": floor_label(last.floor_id),
                "confirm_prompt": None, "time_s": round(secs, 1),
                "distance_m": round(dist, 1),
            })
            i = j
            continue

        if e.kind == EdgeKind.ELEVATOR_RIDE:
            fa, fb = ds.floors.get(e.elevator_from_floor or ""), \
                ds.floors.get(e.elevator_to_floor or "")
            text = (f"엘리베이터를 타고 {fa.label if fa else '?'} → "
                    f"{fb.label if fb else '?'} 이동")
            confirm = "엘리베이터에서 내렸으면 다음을 누르세요."
        elif e.kind == EdgeKind.STAIRS:
            fa, fb = ds.floors.get(a.floor_id or ""), ds.floors.get(b.floor_id or "")
            sc = e.accessibility.step_count
            steps = f" (약 {int(sc.value)}단)" if sc.is_known else ""
            text = (f"계단으로 {fa.label if fa else '?'} → "
                    f"{fb.label if fb else '?'} 이동{steps}")
            confirm = "계단 이동을 마쳤으면 다음을 누르세요."
        elif e.kind == EdgeKind.DOOR:
            # 문 이름은 room_door 쪽 노드를 우선 사용한다
            door_side = (a if a.kind == NodeKind.ROOM_DOOR
                         else (b if b.kind == NodeKind.ROOM_DOOR else None))
            target = (door_side.name if door_side and door_side.name
                      else (b.name or a.name or "문"))
            text = f"{target}을 통과"
            confirm = "문을 지났으면 다음을 누르세요."
        elif e.kind == EdgeKind.ENTRANCE:
            text = f"{a.name or '출입구'}로 건물 진입/진출"
            confirm = "출입구를 지났으면 다음을 누르세요."
        else:
            d = edge_len(e)
            text = f"약 {d:.0f} m 이동" if d >= 0.6 else "이동"
            confirm = None

        out.append({
            "edge_id": e.id, "text": text,
            "floor_id": b.floor_id, "floor_label": floor_label(b.floor_id),
            "confirm_prompt": confirm,
            "time_s": round(tr.time_s, 1) if tr.time_s is not None else None,
        })
        i += 1
    return out


def _nearby_name(ds: Dataset, node) -> str | None:
    """이름 없는 복도 분기점에 대해, 인접한 이름 있는 노드를 찾아 방향 표시로 쓴다."""
    for e in ds.out.get(node.id, ()):
        nb = ds.nodes.get(e.to_node)
        if nb is not None and nb.name:
            return nb.name
    return None
