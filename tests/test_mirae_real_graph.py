"""
실제 도면 기반 그래프(mirae-indoor-v1) 고정 사례 테스트.

여기서는 **정답을 사람이 도면에서 확인한 허용 경로/금지 구간으로 정의**하고
알고리즘 출력 자체를 정답으로 삼지 않는다.

경로가 프로파일별로 다른지는 합격 조건이 아니다.

실행:  python tests/test_mirae_real_graph.py
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.graph.dataset import Dataset                 # noqa: E402
from backend.app.routing.engine import (                       # noqa: E402
    INSUFFICIENT, NO_ROUTE, OK, route,
)
from backend.app.routing.policy import Constraints             # noqa: E402

GRAPH = ROOT / "data" / "published" / "mirae_indoor_v1.json"

D338W = "mirae/F3/door/338-W"
D338E = "mirae/F3/door/338-E"
D337W = "mirae/F3/door/337-W"
D337E = "mirae/F3/door/337-E"
D202 = "mirae/DRAWING-2F/door/202"


def ds() -> Dataset:
    return Dataset.load(GRAPH)


# ------------------------------------------------- 데이터 무결성
def test_graph_loads_without_fatal_error():
    d = ds()
    assert d.graph_version == "mirae-indoor-v1"
    assert len(d.nodes) == 13
    assert len(d.edges) == 20


def test_no_elevator_is_invented():
    """도면에서 기호를 확정하지 못했으므로 승강기가 하나도 없어야 한다."""
    d = ds()
    assert d.elevators == {}
    assert not any(e.kind.value == "elevator_ride" for e in d.edges)


def test_no_outdoor_or_virtual_connection():
    """건물 중심점 접속 등 가상 연결이 사용자용 그래프에 없어야 한다."""
    d = ds()
    assert all(n.geo_point is None for n in d.nodes.values())
    assert not any(e.kind.value in ("outdoor_walk", "entrance", "building_connector")
                   for e in d.edges)
    assert d.verification_scope["outdoor_connection"].startswith("없음")


def test_floor_label_conflict_is_recorded_not_resolved():
    d = ds()
    b22 = d.plans["mirae/plan/B2_2"]
    assert b22.source_tab_label == "지하 2층-②"
    assert b22.drawing_floor_label == "지상 2층"
    assert b22.mapping_status.value == "source_label_conflict"
    # 서비스 층 ID 를 어느 쪽으로도 확정하지 않았다
    assert d.floors["mirae/DRAWING-2F"].label.startswith("원본상 2층")


def test_b22_scale_not_copied_from_3f():
    d = ds()
    assert d.plans["mirae/plan/3F"].scale_m_per_px.is_known
    assert not d.plans["mirae/plan/B2_2"].scale_m_per_px.is_known


def test_places_are_drawing_candidates():
    d = ds()
    for pid in ("mirae/F3/338", "mirae/F3/337", "mirae/DRAWING-2F/202"):
        assert d.places[pid].status.value == "drawing_candidate"


# ------------------------------------------------- 338 <-> 337 같은 층
def test_338_to_337_fastest_ok():
    """도면에서 확인한 허용 경로: 338 문 -> 복도 -> 337 문."""
    r = route(ds(), D338W, D337W, "normal", "fastest")
    assert r["status"] == str(OK), r["reasons"]
    assert r["metrics"]["stair_segments"] == 0
    assert r["metrics"]["elevator_boardings"] == 0
    assert r["metrics"]["floors_touched"] == ["mirae/F3"]
    assert r["metrics"]["distance_m"] == 20.5
    kinds = [s["kind"] for s in r["segments"]]
    assert kinds == ["door", "corridor", "corridor", "corridor", "corridor", "door"]


def test_338_to_337_does_not_pass_through_restroom_interior():
    """338-337 사이 코어는 화장실이다. 통과 동선으로 쓰이면 안 된다.

    금지 구간 정의: 화장실 내부를 가로지르는 엣지는 그래프에 존재하지 않아야 한다.
    복도 노드 wc-W / wc-E 는 화장실 '전면 복도' 이며 내부가 아니다.
    """
    d = ds()
    # 화장실 내부 노드가 애초에 없다
    assert not any("wc" in nid and d.nodes[nid].kind.value != "corridor_junction"
                   for nid in d.nodes)
    # wc 노드는 복도 센터라인(y=346.9) 위에 있다 = 복도지 화장실 내부가 아니다
    for nid in ("mirae/F3/cj/wc-W", "mirae/F3/cj/wc-E"):
        assert abs(d.nodes[nid].plan_point.y_px - 346.9) < 0.01
    # 북측 실열(화장실) 영역인 y < 331.5 를 지나는 복도 엣지가 없다
    for e in d.edges:
        if e.kind.value != "corridor":
            continue
        for nid in (e.from_node, e.to_node):
            assert d.nodes[nid].plan_point.y_px >= 331.5


def test_338_to_337_no_stairs_ok():
    """'계단 없이' 는 접근성 검증을 요구하지 않는다."""
    r = route(ds(), D338W, D337W, "normal", "fastest", Constraints(no_stairs=True))
    assert r["status"] == str(OK), r["reasons"]
    assert r["metrics"]["stair_segments"] == 0


def test_338_to_337_wheelchair_is_insufficient_data():
    """'휠체어 접근성 확인' 은 현장 근거를 요구하므로 자료 부족이어야 한다."""
    r = route(ds(), D338W, D337W, "wheelchair", "fastest",
              Constraints(no_stairs=True, wheelchair=True))
    assert r["status"] == str(INSUFFICIENT), r
    assert r["metrics"] is None
    assert r["blocked_counts"].get("required_accessibility_unverified", 0) >= 1
    # 실제 통행 불가라고 단정하지 않는다
    assert any("현장 조사" in x for x in r["reasons"])


def test_east_doors_are_shorter_than_west_doors():
    """도면 근거: 338 동측 문과 337 서측 문이 가장 가깝다."""
    d = ds()
    near = route(d, D338E, D337W, "normal", "fastest")
    far = route(d, D338W, D337E, "normal", "fastest")
    assert near["status"] == far["status"] == str(OK)
    assert near["metrics"]["distance_m"] < far["metrics"]["distance_m"]


def test_bidirectional_symmetry():
    d = ds()
    a = route(d, D338W, D337W, "normal", "fastest")
    b = route(d, D337W, D338W, "normal", "fastest")
    assert a["metrics"]["distance_m"] == b["metrics"]["distance_m"]


def test_same_door_is_zero():
    r = route(ds(), D338W, D338W, "normal", "fastest")
    assert r["status"] == str(OK)
    assert r["segments"] == []
    assert r["metrics"]["distance_m"] == 0.0


# ------------------------------------------------- 202 <-> 338 층간
def test_202_to_338_is_no_route_with_coverage_diagnostic():
    """층간 시설이 등록되지 않았음을 '데이터 범위' 로 명시해야 한다."""
    r = route(ds(), D202, D338W, "normal", "fastest", Constraints(no_stairs=True))
    assert r["status"] == str(NO_ROUTE), r
    joined = " ".join(r["reasons"])
    assert "데이터 범위" in joined
    assert "층간 이동 시설" in joined
    assert "0개" in joined
    assert "승강기가 하나도 등록되지 않았" in joined
    assert "계단 후보 노드" in joined


def test_202_same_floor_door_has_unknown_length():
    """B2_2 축척 미산출 -> 이 층 엣지 길이는 unknown 이어야 한다."""
    d = ds()
    e = next(x for x in d.edges if x.id == "mirae/DRAWING-2F/e/door/202")
    assert not e.horizontal_length_m.is_known
    assert not e.traversal_length_m.is_known


# ------------------------------------------------- 가정 시나리오 (what-if)
def _hypothetical_field_survey(doc: dict) -> dict:
    """**가정 데이터**: C-1(문 4개소)과 C-2(복도 5구간)를 실측했다고 가정한다.

    docs/data_gaps.md 의 '해소 조건' 주장을 검증하기 위한 것이며
    발행 그래프(data/published)에 절대 반영하지 않는다.
    """
    out = copy.deepcopy(doc)
    out["graph_version"] = "HYPOTHETICAL-not-for-publication"
    ref = ["HYPOTHETICAL: 가정 실측값. 실제 관측 아님"]

    def fm(v, unit=None):
        d = {"value": v, "verification": "field_measured", "source_refs": ref}
        if unit:
            d["unit"] = unit
        return d

    for e in out["edges"]:
        if not e["id"].startswith("mirae/F3/"):
            continue
        a = e["accessibility"]
        if e["kind"] == "door":
            a["clear_width_m"] = fm(0.95, "m")
            a["threshold_m"] = fm(0.0, "m")
            a["door_operability"] = fm("manual")
            a["slope_up_pct"] = fm(0.0, "%")
            a["slope_down_pct"] = fm(0.0, "%")
        elif e["kind"] == "corridor":
            a["clear_width_m"] = fm(2.40, "m")
            a["threshold_m"] = fm(0.0, "m")
            a["slope_up_pct"] = fm(0.5, "%")
            a["slope_down_pct"] = fm(0.5, "%")
    return out


def test_hypothetical_survey_would_make_wheelchair_route_ok():
    with GRAPH.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    hyp = Dataset(_hypothetical_field_survey(doc), source="<hypothetical>")
    r = route(hyp, D338W, D337W, "wheelchair", "fastest",
              Constraints(no_stairs=True, wheelchair=True))
    assert r["status"] == str(OK), r
    assert r["metrics"]["unverified_segments"] == 0
    assert r["metrics"]["observed_max_slope_pct"] == 0.5
    assert r["graph_version"] == "HYPOTHETICAL-not-for-publication"


def test_hypothetical_narrow_corridor_would_block():
    """가정 실측폭이 한계 미달이면 비용과 무관하게 제외돼야 한다."""
    with GRAPH.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    h = _hypothetical_field_survey(doc)
    for e in h["edges"]:
        if e["kind"] == "corridor":
            e["accessibility"]["clear_width_m"] = {
                "value": 0.70, "unit": "m", "verification": "field_measured",
                "source_refs": ["HYPOTHETICAL"]}
    hyp = Dataset(h, source="<hypothetical>")
    r = route(hyp, D338W, D337W, "wheelchair", "fastest",
              Constraints(no_stairs=True, wheelchair=True))
    assert r["status"] == str(NO_ROUTE), r
    assert "observed_clear_width_below_limit" in r["blocked_counts"]


def test_published_graph_has_no_hypothetical_data():
    """발행 그래프에 가정 데이터가 섞이지 않았는지 확인."""
    raw = GRAPH.read_text(encoding="utf-8")
    assert "HYPOTHETICAL" not in raw
    assert "synthetic" not in raw.lower()
    d = ds()
    assert d.verification_scope["field_verified"] is False
    assert d.verification_scope["wheelchair_accessible_routes_certified"] is False
    # field_measured 근거가 하나도 없어야 한다 (아직 현장 조사 전)
    assert "field_measured" not in raw


# ------------------------------------------------- 러너
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
    print(f"\nRESULT {len(fns) - fails}/{len(fns)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
