"""
합성 그래프 라우팅 테스트 (구현지시서 13절).

실제 캠퍼스 데이터를 쓰지 않는다. 픽스처는 tests/fixtures/synthetic 에 격리.
Dijkstra 를 정확도 기준으로 사용한다.

실행:  python -m pytest tests/test_routing_synthetic.py -v
      (pytest 없으면)  python tests/test_routing_synthetic.py
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.graph.dataset import Dataset            # noqa: E402
from backend.app.models.schema import SchemaError        # noqa: E402
from backend.app.routing.engine import (                 # noqa: E402
    INSUFFICIENT,
    NO_ROUTE,
    OK,
    OUTSIDE,
    dijkstra,
    route,
    TraversalFilter,
)
from backend.app.routing.policy import Constraints, TIME_MODELS  # noqa: E402

FX = ROOT / "tests" / "fixtures" / "synthetic"


def load(name: str) -> Dataset:
    return Dataset.load(FX / f"{name}.json")


# ------------------------------------------------------- 1. 같은 층
def test_same_floor_uses_real_doors_only():
    ds = load("same_floor")
    r = route(ds, "A/door", "B/door", "normal", "fastest")
    assert r["status"] == str(OK), r
    kinds = [s["kind"] for s in r["segments"]]
    assert kinds == ["door", "corridor", "door"], kinds
    # 벽 반대편 노드를 경유하지 않는다
    nodes = {s["from_node"] for s in r["segments"]} | {s["to_node"] for s in r["segments"]}
    assert "X/behind_wall" not in nodes
    assert r["metrics"]["distance_m"] == 22.0


def test_wall_adjacent_node_is_unreachable():
    """가까워도 엣지가 없으면 연결되지 않는다."""
    ds = load("same_floor")
    r = route(ds, "A/door", "X/behind_wall", "normal", "fastest")
    assert r["status"] == str(NO_ROUTE), r


# ------------------------------------------------------- 2. 계단 vs 엘리베이터
def test_fastest_uses_stairs_shortcut():
    ds = load("stairs_vs_elevator")
    r = route(ds, "f1/lobby", "f3/hall", "normal", "fastest")
    assert r["status"] == str(OK)
    assert r["metrics"]["stair_segments"] == 1
    assert r["metrics"]["elevator_boardings"] == 0


def test_no_stairs_yields_zero_stairs():
    ds = load("stairs_vs_elevator")
    r = route(ds, "f1/lobby", "f3/hall", "normal", "fastest",
              Constraints(no_stairs=True))
    assert r["status"] == str(OK), r
    assert r["metrics"]["stair_segments"] == 0
    assert r["metrics"]["elevator_boardings"] == 1


def test_stair_step_count_reported_not_edge_count():
    ds = load("stairs_vs_elevator")
    r = route(ds, "f1/lobby", "f3/hall", "normal", "fastest")
    assert r["metrics"]["stair_segments"] == 1
    assert r["metrics"]["stair_steps_observed"] == 40   # 엣지 1개 != 단수 1


# ------------------------------------------------------- 3. 계단만 + 계단금지
def test_stairs_only_with_no_stairs_has_no_route():
    ds = load("stairs_only")
    r = route(ds, "f1/a", "f2/b", "normal", "fastest", Constraints(no_stairs=True))
    assert r["status"] == str(NO_ROUTE), r
    # 계단을 자동으로 허용하지 않는다
    assert "stairs_excluded_by_constraint" in r["blocked_counts"]


def test_stairs_only_without_constraint_ok():
    ds = load("stairs_only")
    r = route(ds, "f1/a", "f2/b", "normal", "fastest")
    assert r["status"] == str(OK)


# ------------------------------------------------------- 4. 미확인 접근성
def test_unverified_excluded_for_wheelchair():
    ds = load("unverified")
    r = route(ds, "u/a", "u/b", "wheelchair", "fastest", Constraints(wheelchair=True))
    assert r["status"] == str(INSUFFICIENT), r
    assert r["metrics"] is None
    assert "e/u" in r["unverified_edge_ids"]


def test_unverified_allowed_when_only_no_stairs():
    """'계단 없이' 는 접근성 검증을 요구하지 않는다 (두 개념 구분)."""
    ds = load("unverified")
    r = route(ds, "u/a", "u/b", "normal", "fastest", Constraints(no_stairs=True))
    assert r["status"] == str(OK), r
    assert r["metrics"]["unverified_segments"] == 0


def test_drawing_read_slope_is_not_enough_for_wheelchair():
    ds = load("drawing_only_slope")
    r = route(ds, "d/a", "d/b", "wheelchair", "fastest", Constraints(wheelchair=True))
    assert r["status"] == str(INSUFFICIENT), r


# ------------------------------------------------------- 5. 관측 경사 초과
def test_observed_slope_over_limit_is_excluded():
    ds = load("slope_exceeds")
    r = route(ds, "s/a", "s/b", "wheelchair", "fastest", Constraints(wheelchair=True))
    assert r["status"] == str(NO_ROUTE), r
    assert "observed_slope_exceeds_limit" in r["blocked_counts"]


def test_direction_matters_for_slope():
    """상행은 막히고 하행은 통과. 방향별 정책."""
    ds = load("slope_exceeds")
    down = route(ds, "s/b", "s/a", "wheelchair", "fastest", Constraints(wheelchair=True))
    assert down["status"] == str(OK), down
    assert down["metrics"]["observed_max_slope_pct"] == 4.0


# ------------------------------------------------------- 6. 엘리베이터 대기 1회
def test_elevator_single_wait_for_multi_floor_ride():
    ds = load("stairs_vs_elevator")
    tf = TraversalFilter(ds, Constraints(no_stairs=True), "normal")
    ride13 = next(e for e in ds.edges
                  if e.id == "e/ev/F1-F3")
    tr = tf.check(ride13)
    assert tr is not None
    # wait 25 + board 10 + 5*2층 = 45.  대기가 2회(50)로 들어가면 실패.
    assert abs(tr.time_s - 45.0) < 1e-6, tr.time_s
    # 1->2 와 2->3 을 따로 타면 대기가 2회 들어간다 (구조적으로 다른 경로)
    r12 = tf.check(next(e for e in ds.edges if e.id == "e/ev/F1-F2"))
    r23 = tf.check(next(e for e in ds.edges if e.id == "e/ev/F2-F3"))
    assert abs((r12.time_s + r23.time_s) - 80.0) < 1e-6
    assert tr.time_s < r12.time_s + r23.time_s


def test_elevator_route_boards_once():
    ds = load("stairs_vs_elevator")
    r = route(ds, "f1/lobby", "f3/hall", "wheelchair", "fastest",
              Constraints(wheelchair=True))
    assert r["status"] == str(OK), r
    assert r["metrics"]["elevator_boardings"] == 1
    ev_segs = [s for s in r["segments"] if s["kind"] == "elevator_ride"]
    assert len(ev_segs) == 1
    assert abs(ev_segs[0]["time_s"] - 45.0) < 1e-6


# ------------------------------------------------------- 7. 미정차층 / 고장
def test_elevator_does_not_serve_unlisted_floor():
    ds = load("elevator_skip_floor")
    r = route(ds, "k/f1ev", "k/f2hall", "normal", "fastest")
    assert r["status"] == str(NO_ROUTE), r


def test_elevator_skip_floor_schema_rejects_bad_edge():
    """정차층 목록에 없는 층을 연결하는 엣지는 스키마에서 거부."""
    import copy
    import json
    doc = json.loads((FX / "elevator_skip_floor.json").read_text(encoding="utf-8"))
    bad = copy.deepcopy(doc)
    bad["nodes"].append({"id": "k/f2ev", "kind": "elevator_lobby",
                         "building_id": "synth/tower", "floor_id": "synth/F2",
                         "plan_point": {"coordinate_space": "plan:synth/F2",
                                        "x_px": 300, "y_px": 100}})
    bad["edges"].append({"id": "e/bad", "from_node": "k/f1ev", "to_node": "k/f2ev",
                         "kind": "elevator_ride", "facility_id": "ev/E2",
                         "elevator_from_floor": "synth/F1",
                         "elevator_to_floor": "synth/F2"})
    try:
        Dataset(bad)
    except SchemaError as err:
        assert "정차층" in str(err)
    else:
        raise AssertionError("미정차층 연결이 통과했다")


def test_out_of_service_elevator_falls_back_or_fails():
    ds = load("closure")
    # 계단 허용이면 계단으로 대체
    ok = route(ds, "f1/lobby", "f3/hall", "normal", "fastest")
    assert ok["status"] == str(OK)
    assert ok["metrics"]["elevator_boardings"] == 0
    # 계단 금지면 경로 없음
    bad = route(ds, "f1/lobby", "f3/hall", "normal", "fastest",
                Constraints(no_stairs=True))
    assert bad["status"] == str(NO_ROUTE), bad
    assert "closed_or_restricted" in bad["blocked_counts"]


# ------------------------------------------------------- 8. 층 오접속
def test_same_pixel_different_floor_not_connected():
    ds = load("cross_floor_overlap")
    r = route(ds, "o/f1", "o/f2", "normal", "fastest")
    assert r["status"] == str(NO_ROUTE), r


def test_schema_rejects_corridor_across_floors():
    import json
    doc = json.loads((FX / "cross_floor_overlap.json").read_text(encoding="utf-8"))
    doc["edges"].append({"id": "e/illegal", "from_node": "o/f1", "to_node": "o/f2",
                         "kind": "corridor"})
    try:
        Dataset(doc)
    except SchemaError as err:
        assert "서로 다른 층" in str(err)
    else:
        raise AssertionError("층을 가로지르는 corridor 엣지가 통과했다")


def test_schema_rejects_copied_plan_coordinate_space():
    import json
    doc = json.loads((FX / "cross_floor_overlap.json").read_text(encoding="utf-8"))
    for n in doc["nodes"]:
        if n["id"] == "o/f2":
            n["plan_point"]["coordinate_space"] = "plan:synth/F1"   # 층간 좌표 복사
    try:
        Dataset(doc)
    except SchemaError as err:
        assert "좌표공간 불일치" in str(err)
    else:
        raise AssertionError("층간 좌표 복사가 통과했다")


# ------------------------------------------------------- 9. 경계 조건
def test_origin_equals_destination():
    ds = load("same_floor")
    r = route(ds, "A/door", "A/door", "normal", "fastest")
    assert r["status"] == str(OK)
    assert r["segments"] == []
    assert r["metrics"]["distance_m"] == 0.0
    assert r["metrics"]["estimated_time_s"] == 0.0


def test_unknown_node_is_outside_coverage():
    ds = load("same_floor")
    r = route(ds, "A/door", "없는노드", "normal", "fastest")
    assert r["status"] == str(OUTSIDE)


def test_same_path_for_all_modes_is_valid_success():
    """모든 모드가 같은 경로여도 조건을 충족하면 정상이다."""
    ds = load("same_floor")
    paths = []
    for obj in ("fastest", "comfort", "indoor"):
        r = route(ds, "A/door", "B/door", "normal", obj)
        assert r["status"] == str(OK)
        paths.append(tuple(s["edge_id"] for s in r["segments"]))
    assert len(set(paths)) == 1            # 동일 경로
    # 동일하다는 사실이 실패가 아니다


# ------------------------------------------------------- 10. 시간/선호 분리
def test_time_and_preference_are_separate():
    ds = load("stairs_vs_elevator")
    fast = route(ds, "f1/lobby", "f3/hall", "elderly", "fastest")
    comfort = route(ds, "f1/lobby", "f3/hall", "elderly", "comfort")
    assert fast["status"] == comfort["status"] == str(OK)
    # 노약자: 최단시간은 계단, 편한이동은 엘리베이터가 선택될 수 있다.
    assert fast["metrics"]["estimated_time_s"] <= comfort["metrics"]["estimated_time_s"] + 1e-6
    assert comfort["metrics"]["stair_segments"] <= fast["metrics"]["stair_segments"]


def test_time_uses_speed_model_not_distance_cost():
    ds = load("same_floor")
    r_n = route(ds, "A/door", "B/door", "normal", "fastest")
    r_e = route(ds, "A/door", "B/door", "elderly", "fastest")
    assert r_n["metrics"]["distance_m"] == r_e["metrics"]["distance_m"]
    # 같은 거리인데 시간이 다르다 -> 거리비용의 이름만 바꾼 것이 아니다
    assert r_e["metrics"]["estimated_time_s"] > r_n["metrics"]["estimated_time_s"]
    assert r_n["metrics"]["estimated_time_is_assumption"] is True


# ------------------------------------------------------- 11. Dijkstra 정확성
def test_dijkstra_matches_bruteforce_on_small_graph():
    """소형 그래프에서 완전탐색 최소비용과 일치하는지 확인."""
    ds = load("stairs_vs_elevator")
    tf = TraversalFilter(ds, Constraints(), "normal")
    start, goal = "f1/lobby", "f3/hall"

    got = dijkstra(ds, start, goal, tf, lambda tr: tr.time_s or 0.0)
    assert got is not None
    d_cost = got[1]

    # 완전탐색 (노드 재방문 금지)
    best = [float("inf")]

    def dfs(u, cost, seen):
        if cost >= best[0]:
            return
        if u == goal:
            best[0] = cost
            return
        for e in ds.out.get(u, ()):
            tr = tf.check(e)
            if tr is None or e.to_node in seen:
                continue
            dfs(e.to_node, cost + (tr.time_s or 0.0), seen | {e.to_node})

    dfs(start, 0.0, {start})
    assert abs(best[0] - d_cost) < 1e-6, (best[0], d_cost)


def test_no_negative_weights():
    ds = load("stairs_vs_elevator")
    tf = TraversalFilter(ds, Constraints(), "normal")
    for e in ds.edges:
        tr = tf.check(e)
        if tr is None:
            continue
        assert (tr.time_s or 0.0) >= 0.0
        assert tr.preference_cost >= 0.0


# ------------------------------------------------------- 12. 스키마 단위
def test_unknown_is_not_coerced():
    from backend.app.models.schema import Attr, Verification
    a = Attr.from_json({"value": None, "verification": "unknown"})
    assert a.is_known is False
    assert a.value is None          # 0 이나 False 로 바뀌지 않는다
    assert bool(a.value) is False and a.value is not False

    b = Attr.from_json({"value": 0.0, "verification": "field_measured"})
    assert b.is_known is True and b.value == 0.0
    assert b.known_at_least(Verification.FIELD_MEASURED)

    c = Attr.from_json({"value": 5.0, "verification": "drawing_read"})
    assert c.is_known is True
    assert not c.known_at_least(Verification.FIELD_MEASURED)


def test_time_model_values_are_assumptions():
    for name, tm in TIME_MODELS.items():
        assert tm.walk_speed_mps > 0
        assert "가정값" in tm.assumptions_note


# ------------------------------------------------------- 러너
def _run_all() -> int:
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    fails = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as err:
            fails += 1
            print(f"  FAIL  {name}\n        {err}")
        except Exception as err:  # noqa: BLE001
            fails += 1
            print(f"  ERROR {name}\n        {type(err).__name__}: {err}")
    print(f"\n{len(fns) - fails}/{len(fns)} 통과")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
