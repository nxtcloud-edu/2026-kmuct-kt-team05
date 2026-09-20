"""
합성 그래프 픽스처 생성기.

**실제 캠퍼스 데이터와 완전히 분리된 가상 건물이다.**
- building id 는 `synth/...` 로 시작한다. 실제 지도/발행 그래프에 노출하지 않는다.
- 좌표는 가상 도면 픽셀이며 지리 좌표를 갖지 않는다.

사용법
    python tests/fixtures/synthetic/build_fixtures.py
결과
    tests/fixtures/synthetic/*.json
"""

from __future__ import annotations

import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent

FIELD = "field_measured"
DRAW = "drawing_read"


def attr(value, unit=None, verification=FIELD, refs=("synthetic",)):
    d = {"value": value, "verification": verification}
    if unit:
        d["unit"] = unit
    if refs:
        d["source_refs"] = list(refs)
    return d


def unknown():
    return {"value": None, "verification": "unknown"}


def acc(*, stairs=False, steps=None, up=0.0, down=0.0, width=1.8,
        threshold=0.0, door_op=None, wheelchair=None, verification=FIELD):
    """접근성 블록. 기본값은 '현장 실측으로 양호'인 가상 조건."""
    d = {
        "stairs": attr(stairs, verification=verification),
        "step_count": unknown() if steps is None else attr(steps, "count", verification),
        "slope_up_pct": unknown() if up is None else attr(up, "%", verification),
        "slope_down_pct": unknown() if down is None else attr(down, "%", verification),
        "cross_slope_pct": attr(0.0, "%", verification),
        "clear_width_m": unknown() if width is None else attr(width, "m", verification),
        "threshold_m": unknown() if threshold is None else attr(threshold, "m", verification),
        "surface": attr("concrete", verification=verification),
        "door_operability": unknown() if door_op is None else attr(door_op, verification=verification),
        "wheelchair_usable": unknown() if wheelchair is None else attr(wheelchair, verification=verification),
    }
    return d


def node(nid, kind, floor=None, x=0.0, y=0.0, name=None, facility=None, geo=None):
    d = {"id": nid, "kind": kind, "building_id": "synth/tower", "floor_id": floor,
         "name": name, "facility_id": facility, "source_refs": ["synthetic"]}
    if floor:
        d["plan_point"] = {"coordinate_space": f"plan:{floor}", "x_px": x, "y_px": y}
    if geo:
        d["geo_point"] = {"lon": geo[0], "lat": geo[1]}
    return d


def edge(eid, a, b, kind, length_m=None, accessibility=None, facility=None,
         ef=None, et=None, rise=None, both=False):
    """방향 엣지 하나. both=True 면 역방향도 함께 만들어 돌려준다."""
    def one(i, u, v, up_down_swap=False):
        ac = dict(accessibility or acc())
        if up_down_swap:
            ac = dict(ac)
            ac["slope_up_pct"], ac["slope_down_pct"] = ac["slope_down_pct"], ac["slope_up_pct"]
        d = {
            "id": i, "from_node": u, "to_node": v, "kind": kind,
            "horizontal_length_m": unknown() if length_m is None else attr(length_m, "m"),
            "traversal_length_m": unknown() if length_m is None else attr(length_m, "m"),
            "vertical_rise_m": unknown() if rise is None else attr(rise, "m"),
            "accessibility": ac, "facility_id": facility,
            "elevator_from_floor": ef, "elevator_to_floor": et,
            "source_refs": ["synthetic"],
        }
        return d
    out = [one(eid, a, b)]
    if both:
        out.append(one(eid + "/rev", b, a, up_down_swap=True))
    return out


def base_doc(name: str) -> dict:
    return {
        "graph_version": f"synthetic-{name}-1",
        "schema_version": "1.0.0",
        "generated_at": "2026-09-20T00:00:00+09:00",
        "verification_scope": {"synthetic": True,
                               "note": "가상 데이터. 실제 캠퍼스와 무관."},
        "notes": ["tests/fixtures/synthetic - 실제 지도에 노출 금지"],
        "buildings": [{"id": "synth/tower", "official_name": "합성타워",
                       "campus_code": None, "aliases": [], "wings": [],
                       "footprint": None, "source_refs": ["synthetic"]}],
        "floorplans": [
            {"id": "synth/plan/F1", "image_ref": "synthetic://F1",
             "width_px": 1000, "height_px": 1000,
             "scale_m_per_px": attr(0.1, "m/px"), "mapping_status": "field_confirmed"},
            {"id": "synth/plan/F2", "image_ref": "synthetic://F2",
             "width_px": 1000, "height_px": 1000,
             "scale_m_per_px": attr(0.1, "m/px"), "mapping_status": "field_confirmed"},
            {"id": "synth/plan/F3", "image_ref": "synthetic://F3",
             "width_px": 1000, "height_px": 1000,
             "scale_m_per_px": attr(0.1, "m/px"), "mapping_status": "field_confirmed"},
        ],
        "floors": [
            {"id": "synth/F1", "building_id": "synth/tower", "label": "1층",
             "sort_order": 1, "plan_id": "synth/plan/F1", "elevation_m": attr(0.0, "m")},
            {"id": "synth/F2", "building_id": "synth/tower", "label": "2층",
             "sort_order": 2, "plan_id": "synth/plan/F2", "elevation_m": attr(4.0, "m")},
            {"id": "synth/F3", "building_id": "synth/tower", "label": "3층",
             "sort_order": 3, "plan_id": "synth/plan/F3", "elevation_m": attr(8.0, "m")},
        ],
        "places": [], "nodes": [], "edges": [], "elevators": [], "closures": [],
    }


# ------------------------------------------------------------------ 픽스처들
def fx_same_floor() -> dict:
    """같은 층 두 지점. 실제 복도/문 연결만 이용. 벽 건너 최근접 연결 없음."""
    d = base_doc("same-floor")
    d["nodes"] += [
        node("A/door", "room_door", "synth/F3", 100, 500, "A실 문"),
        node("c1", "corridor_junction", "synth/F3", 100, 550),
        node("c2", "corridor_junction", "synth/F3", 300, 550),
        node("B/door", "room_door", "synth/F3", 300, 500, "B실 문"),
        # 벽 반대편의 가까운 노드. 연결 엣지를 만들지 않는다.
        node("X/behind_wall", "corridor_junction", "synth/F3", 105, 495, "벽 반대편"),
    ]
    d["edges"] += edge("e/A-c1", "A/door", "c1", "door", 1.0,
                       acc(width=1.0, threshold=0.0, door_op="manual"), both=True)
    d["edges"] += edge("e/c1-c2", "c1", "c2", "corridor", 20.0, acc(), both=True)
    d["edges"] += edge("e/B-c2", "B/door", "c2", "door", 1.0,
                       acc(width=1.0, threshold=0.0, door_op="manual"), both=True)
    d["places"] += [
        {"id": "synth/F3/A", "name": "A실", "building_id": "synth/tower",
         "floor_id": "synth/F3", "room_label": "A", "door_node_ids": ["A/door"],
         "status": "field_confirmed"},
        {"id": "synth/F3/B", "name": "B실", "building_id": "synth/tower",
         "floor_id": "synth/F3", "room_label": "B", "door_node_ids": ["B/door"],
         "status": "field_confirmed"},
    ]
    return d


def fx_stairs_vs_elevator() -> dict:
    """계단 지름길 + 엘리베이터 우회. 1층 <-> 3층."""
    d = base_doc("stairs-vs-elevator")
    d["nodes"] += [
        node("f1/lobby", "corridor_junction", "synth/F1", 100, 100, "1층 로비"),
        node("f1/stair", "stair_landing", "synth/F1", 200, 100, "1층 계단참", facility="stair/S1"),
        node("f3/stair", "stair_landing", "synth/F3", 200, 100, "3층 계단참", facility="stair/S1"),
        node("f3/hall", "corridor_junction", "synth/F3", 100, 100, "3층 홀"),
        node("f1/ev", "elevator_lobby", "synth/F1", 300, 100, "1층 승강장", facility="ev/E1"),
        node("f2/ev", "elevator_lobby", "synth/F2", 300, 100, "2층 승강장", facility="ev/E1"),
        node("f3/ev", "elevator_lobby", "synth/F3", 300, 100, "3층 승강장", facility="ev/E1"),
    ]
    d["edges"] += edge("e/f1lobby-stair", "f1/lobby", "f1/stair", "corridor", 10.0, acc(), both=True)
    d["edges"] += edge("e/stairs13", "f1/stair", "f3/stair", "stairs", 12.0,
                       acc(stairs=True, steps=40, up=None, down=None,
                           width=1.4, threshold=None), rise=8.0, both=True)
    d["edges"] += edge("e/f3stair-hall", "f3/stair", "f3/hall", "corridor", 10.0, acc(), both=True)
    d["edges"] += edge("e/f1lobby-ev", "f1/lobby", "f1/ev", "corridor", 20.0, acc(), both=True)
    d["edges"] += edge("e/f3ev-hall", "f3/ev", "f3/hall", "corridor", 20.0, acc(), both=True)
    # 엘리베이터: 정차층 쌍마다 직접 승차 엣지 1개 (대기 1회)
    for a, b in [("synth/F1", "synth/F2"), ("synth/F1", "synth/F3"),
                 ("synth/F2", "synth/F3")]:
        na = {"synth/F1": "f1/ev", "synth/F2": "f2/ev", "synth/F3": "f3/ev"}[a]
        nb = {"synth/F1": "f1/ev", "synth/F2": "f2/ev", "synth/F3": "f3/ev"}[b]
        d["edges"] += edge(f"e/ev/{a[-2:]}-{b[-2:]}", na, nb, "elevator_ride",
                           None, acc(width=None, up=None, down=None, threshold=None),
                           facility="ev/E1", ef=a, et=b, both=True)
    d["elevators"].append({
        "id": "ev/E1", "building_id": "synth/tower", "shaft_group": "G1",
        "served_floor_ids": ["synth/F1", "synth/F2", "synth/F3"],
        "served_floors_evidence": attr("현장 확인(가상)", verification=FIELD),
        "door_node_ids": {"synth/F1": "f1/ev", "synth/F2": "f2/ev", "synth/F3": "f3/ev"},
        "car_width_m": attr(1.6, "m"), "car_depth_m": attr(1.5, "m"),
        "door_width_m": attr(0.9, "m"),
        "wheelchair_usable": attr(True, verification=FIELD),
        "status": "in_service", "status_checked_at": "2026-09-20",
        "wait_s_assumed": 25.0, "ride_s_per_floor_assumed": 5.0,
        "board_alight_s_assumed": 10.0,
        "source_refs": ["synthetic"],
    })
    return d


def fx_stairs_only() -> dict:
    """계단만 존재. 계단 금지면 경로 없음 (자동 허용 금지)."""
    d = base_doc("stairs-only")
    d["nodes"] += [
        node("f1/a", "corridor_junction", "synth/F1", 100, 100),
        node("f1/s", "stair_landing", "synth/F1", 200, 100, facility="stair/S9"),
        node("f2/s", "stair_landing", "synth/F2", 200, 100, facility="stair/S9"),
        node("f2/b", "corridor_junction", "synth/F2", 100, 100),
    ]
    d["edges"] += edge("e/a-s", "f1/a", "f1/s", "corridor", 8.0, acc(), both=True)
    d["edges"] += edge("e/s12", "f1/s", "f2/s", "stairs", 6.0,
                       acc(stairs=True, steps=22, up=None, down=None,
                           width=1.3, threshold=None), rise=4.0, both=True)
    d["edges"] += edge("e/s-b", "f2/s", "f2/b", "corridor", 8.0, acc(), both=True)
    return d


def fx_unverified() -> dict:
    """필수 접근성 속성이 미확인인 복도. 휠체어 조건에서 제외돼야 한다."""
    d = base_doc("unverified")
    d["nodes"] += [
        node("u/a", "corridor_junction", "synth/F1", 100, 100),
        node("u/b", "corridor_junction", "synth/F1", 300, 100),
    ]
    # 폭/문턱/경사가 unknown. 0 이나 '이용 가능'으로 바꾸지 않는다.
    d["edges"] += edge("e/u", "u/a", "u/b", "corridor", 20.0,
                       acc(width=None, threshold=None, up=None, down=None),
                       both=True)
    return d


def fx_drawing_only_slope() -> dict:
    """도면 판독 수준 경사만 있는 경우. 휠체어 확인 경로로 인정하지 않는다."""
    d = base_doc("drawing-only-slope")
    d["nodes"] += [
        node("d/a", "corridor_junction", "synth/F1", 100, 100),
        node("d/b", "corridor_junction", "synth/F1", 300, 100),
    ]
    d["edges"] += edge("e/d", "d/a", "d/b", "ramp", 20.0,
                       acc(up=5.0, down=0.0, width=1.5, threshold=0.0,
                           verification=DRAW), both=True)
    return d


def fx_slope_exceeds() -> dict:
    """관측 경사가 한계를 넘음. 비용을 아무리 낮춰도 제외돼야 한다."""
    d = base_doc("slope-exceeds")
    d["nodes"] += [
        node("s/a", "corridor_junction", "synth/F1", 100, 100),
        node("s/b", "corridor_junction", "synth/F1", 300, 100),
    ]
    # 상행 12% (한계 8.33% 초과), 하행 0%  -> 방향별로 판정이 달라야 한다
    d["edges"] += edge("e/s/up", "s/a", "s/b", "ramp", 20.0,
                       acc(up=12.0, down=0.0, width=1.5, threshold=0.0))
    d["edges"] += edge("e/s/down", "s/b", "s/a", "ramp", 20.0,
                       acc(up=0.0, down=4.0, width=1.5, threshold=0.0))
    return d


def fx_elevator_skip_floor() -> dict:
    """엘리베이터가 2층에 정차하지 않는다. 2층 연결을 만들어선 안 된다."""
    d = base_doc("elevator-skip-floor")
    d["nodes"] += [
        node("k/f1ev", "elevator_lobby", "synth/F1", 300, 100, facility="ev/E2"),
        node("k/f3ev", "elevator_lobby", "synth/F3", 300, 100, facility="ev/E2"),
        node("k/f2hall", "corridor_junction", "synth/F2", 100, 100, "2층 홀"),
    ]
    d["edges"] += edge("e/ev2/13", "k/f1ev", "k/f3ev", "elevator_ride", None,
                       acc(width=None, up=None, down=None, threshold=None),
                       facility="ev/E2", ef="synth/F1", et="synth/F3", both=True)
    d["elevators"].append({
        "id": "ev/E2", "building_id": "synth/tower",
        "served_floor_ids": ["synth/F1", "synth/F3"],   # 2층 없음
        "served_floors_evidence": attr("현장 확인(가상): 2층 미정차", verification=FIELD),
        "door_node_ids": {"synth/F1": "k/f1ev", "synth/F3": "k/f3ev"},
        "wheelchair_usable": attr(True, verification=FIELD),
        "status": "in_service", "wait_s_assumed": 25.0,
        "ride_s_per_floor_assumed": 5.0, "board_alight_s_assumed": 10.0,
        "source_refs": ["synthetic"],
    })
    return d


def fx_closure() -> dict:
    """엘리베이터 고장 + 출입구 폐쇄. 대체 경로 또는 경로 없음."""
    d = fx_stairs_vs_elevator()
    d["graph_version"] = "synthetic-closure-1"
    d["elevators"][0]["status"] = "out_of_service"
    d["elevators"][0]["status_checked_at"] = "2026-09-20T09:00+09:00"
    d["closures"].append({
        "id": "cl/1", "target_kind": "facility", "target_id": "ev/E1",
        "status": "closed", "reason": "정기 점검(가상)",
        "source_ref": "synthetic", "updated_at": "2026-09-20T09:00+09:00",
    })
    return d


def fx_cross_floor_overlap() -> dict:
    """서로 다른 층의 선이 도면상 겹침. 명시적 층간 시설이 없으면 연결 안 됨.

    같은 픽셀 좌표를 갖지만 floor_id 가 다르고 층간 엣지가 없으므로
    탐색에서 연결되지 않아야 한다.
    """
    d = base_doc("cross-floor-overlap")
    d["nodes"] += [
        node("o/f1", "corridor_junction", "synth/F1", 500, 500, "1층 지점"),
        node("o/f1b", "corridor_junction", "synth/F1", 600, 500),
        node("o/f2", "corridor_junction", "synth/F2", 500, 500, "2층 같은 픽셀"),
        node("o/f2b", "corridor_junction", "synth/F2", 600, 500),
    ]
    d["edges"] += edge("e/o1", "o/f1", "o/f1b", "corridor", 10.0, acc(), both=True)
    d["edges"] += edge("e/o2", "o/f2", "o/f2b", "corridor", 10.0, acc(), both=True)
    return d


FIXTURES = {
    "same_floor": fx_same_floor,
    "stairs_vs_elevator": fx_stairs_vs_elevator,
    "stairs_only": fx_stairs_only,
    "unverified": fx_unverified,
    "drawing_only_slope": fx_drawing_only_slope,
    "slope_exceeds": fx_slope_exceeds,
    "elevator_skip_floor": fx_elevator_skip_floor,
    "closure": fx_closure,
    "cross_floor_overlap": fx_cross_floor_overlap,
}


def main() -> None:
    for name, fn in FIXTURES.items():
        doc = fn()
        p = HERE / f"{name}.json"
        with p.open("w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=2)
        print(f"{name:24s} nodes={len(doc['nodes']):3d} edges={len(doc['edges']):3d} -> {p.name}")


if __name__ == "__main__":
    main()
