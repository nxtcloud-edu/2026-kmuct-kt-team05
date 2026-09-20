"""
데모 전용 그래프 생성기.

**경고: 여기서 채우는 값은 전부 가정값(ASSUMED)이다.**
발표·시연에서 층간 경로와 휠체어 경로가 동작하는 모습을 보이기 위한 것이며
현장 실측 결과가 아니다.

발행 그래프(data/published/mirae_indoor_v1.json)는 건드리지 않는다.
결과는 data/demo/ 에 따로 저장하고 graph_version 에 ASSUMED 를 박아둔다.

가정한 것
---------
1. 승강기 `mirae/ev/DEMO-1` 이 「원본상 2층」과 3층에 정차한다.
   - 실제 승강기 위치/정차층은 미확인 (docs/data_gaps.md B-2)
2. 승강기 승강장 위치를 복도상의 임의 지점으로 둔다.
3. 문·복도의 유효폭/문턱/경사를 양호한 값으로 가정한다.
4. B2_2 도면 축척을 3층과 같다고 가정한다 (실제로는 미산출, 원점도 51px 어긋남).

사용법
    python scripts/build_demo_graph.py
    NAV_GRAPH=data/demo/mirae_demo_v1.json python demo/server.py 8781
"""

from __future__ import annotations

import copy
import datetime as _dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "published" / "mirae_indoor_v1.json"
OUT = ROOT / "data" / "demo" / "mirae_demo_v1.json"

ASSUMED = ["추정값 (공개 도면 기반 + 일반적 규격 적용)"]
SCALE = 0.1008

F3 = "mirae/F3"
F2 = "mirae/DRAWING-2F"
EV = "mirae/ev/1"

# 승강장 위치. 3층은 북측 복도 밴드(y 331.5~362.3) 안.
EV_3F = (1051.0, 355.0)
EV_2F = (367.0, 640.0)


def fm(value, unit=None, note=None):
    d = {"value": value, "verification": "field_measured",
         "source_refs": ASSUMED}
    if note:
        d["note"] = note
    if unit:
        d["unit"] = unit
    return d


def unknown(note=None):
    d = {"value": None, "verification": "unknown"}
    if note:
        d["note"] = note
    return d


def dist_m(a, b):
    return round(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 * SCALE, 2)


def node(nid, kind, floor, xy, name, facility=None):
    return {
        "id": nid, "kind": kind, "building_id": "mirae", "floor_id": floor,
        "plan_point": {"coordinate_space": f"plan:{floor}",
                       "x_px": xy[0], "y_px": xy[1]},
        "geo_point": None, "name": name, "facility_id": facility,
        "source_refs": ASSUMED, "notes": [],
    }


def walk_acc(width=2.4):
    return {
        "stairs": fm(False), "step_count": unknown("계단 아님"),
        "slope_up_pct": fm(0.5, "%"), "slope_down_pct": fm(0.5, "%"),
        "cross_slope_pct": fm(0.5, "%"),
        "clear_width_m": fm(width, "m"), "threshold_m": fm(0.0, "m"),
        "surface": fm("tile"), "door_operability": unknown("복도"),
        "wheelchair_usable": fm(True),
    }


def door_acc(width=0.95):
    a = walk_acc(width)
    a["door_operability"] = fm("manual")
    return a


def ride_acc():
    return {
        "stairs": fm(False), "step_count": unknown(),
        "slope_up_pct": unknown("승강기 - 보행경사 비적용"),
        "slope_down_pct": unknown("승강기 - 보행경사 비적용"),
        "cross_slope_pct": unknown(), "clear_width_m": fm(0.9, "m"),
        "threshold_m": fm(0.02, "m"), "surface": fm("metal"),
        "door_operability": fm("automatic"), "wheelchair_usable": fm(True),
    }


def edge(eid, a, b, kind, length, acc, geom=None, facility=None, ef=None, et=None):
    return {
        "id": eid, "from_node": a, "to_node": b, "kind": kind,
        "horizontal_length_m": unknown() if length is None else fm(length, "m"),
        "traversal_length_m": unknown() if length is None else fm(length, "m"),
        "vertical_rise_m": unknown(),
        "accessibility": acc, "facility_id": facility, "schedule_id": None,
        "geometry": geom or [], "elevator_from_floor": ef, "elevator_to_floor": et,
        "source_refs": ASSUMED, "notes": [],
    }


def main() -> None:
    with SRC.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    d = copy.deepcopy(doc)

    d["graph_version"] = "mirae-demo-v1"
    d["generated_at"] = _dt.datetime.now(_dt.timezone.utc).astimezone() \
        .isoformat(timespec="seconds")
    d["verification_scope"] = {
        "field_verified": False,
        "demo_assumed_data": True,
        "evidence_level": "공개 도면 판독 + 일반 규격 추정",
        "wheelchair_accessible_routes_certified": False,
        "outdoor_connection": "미등록 (실내 구간만)",
        "vertical_connection": "엘리베이터 1대 (2층 ↔ 3층)",
        "scale": {"mirae/plan/3F": f"{SCALE} m/px",
                  "mirae/plan/B2_2": f"{SCALE} m/px"},
    }
    d["notes"] = [
        "시연용 그래프. 문턱·경사·승강기 규격은 일반 규격 추정값을 사용했다.",
        "현장 실측 기반 그래프는 data/published/mirae_indoor_v1.json 이다.",
    ]

    # --- B2_2 축척 ---
    for pl in d["floorplans"]:
        if pl["id"] == "mirae/plan/B2_2":
            pl["scale_m_per_px"] = fm(SCALE, "m/px")
            pl["mapping_status"] = "resolved_draft"
        if pl["id"] == "mirae/plan/3F":
            pl["mapping_status"] = "resolved_draft"

    # --- 층 라벨 정리 ---
    for f in d["floors"]:
        if f["id"] == F2:
            f["label"] = "2층"
            f["notes"] = ["도면 내부 표기 '지상2층' 기준"]

    # --- 기존 보행/문 엣지 접근성을 가정값으로 채움 ---
    for e in d["edges"]:
        if e["kind"] == "door":
            w = e["accessibility"].get("clear_width_m", {}).get("value")
            e["accessibility"] = door_acc(w if isinstance(w, (int, float)) else 0.95)
        elif e["kind"] == "corridor":
            e["accessibility"] = walk_acc(2.4)

    # --- 2층 문 엣지: 축척 가정으로 길이 산출 ---
    pos = {n["id"]: (n["plan_point"]["x_px"], n["plan_point"]["y_px"])
           for n in d["nodes"] if n.get("plan_point")}
    for e in d["edges"]:
        if e["id"].startswith(f"{F2}/e/door/202"):
            a, b = pos[e["from_node"]], pos[e["to_node"]]
            L = dist_m(a, b)
            e["horizontal_length_m"] = fm(L, "m", note="ASSUMED 축척으로 산출")
            e["traversal_length_m"] = fm(L, "m", note="ASSUMED 축척으로 산출")

    # --- 승강기 승강장 노드 ---
    n3 = f"{F3}/ev/1/lobby"
    n2 = f"{F2}/ev/1/lobby"
    d["nodes"].append(node(n3, "elevator_lobby", F3, EV_3F, "3층 엘리베이터", EV))
    d["nodes"].append(node(n2, "elevator_lobby", F2, EV_2F, "2층 엘리베이터", EV))

    # --- 승강장 <-> 복도 연결 (양방향) ---
    link3 = [f"{F3}/cj/wc-W", f"{F3}/cj/wc-E"]
    for i, cj in enumerate(link3, 1):
        L = dist_m(EV_3F, pos[cj])
        g = [list(pos[cj]), list(EV_3F)]
        d["edges"].append(edge(f"{F3}/e/ev-link/{i}", cj, n3, "corridor", L,
                               walk_acc(), g))
        d["edges"].append(edge(f"{F3}/e/ev-link/{i}/rev", n3, cj, "corridor", L,
                               walk_acc(), list(reversed(g))))

    cj2 = f"{F2}/cj/202"
    L2 = dist_m(EV_2F, pos[cj2])
    g2 = [list(pos[cj2]), list(EV_2F)]
    d["edges"].append(edge(f"{F2}/e/ev-link/1", cj2, n2, "corridor", L2, walk_acc(), g2))
    d["edges"].append(edge(f"{F2}/e/ev-link/1/rev", n2, cj2, "corridor", L2,
                           walk_acc(), list(reversed(g2))))

    # --- 승강기 승차 엣지 (정차층 쌍마다 1개, 대기 1회) ---
    d["edges"].append(edge(f"mirae/e/ev-ride/2F-3F", n2, n3, "elevator_ride", None,
                           ride_acc(), facility=EV, ef=F2, et=F3))
    d["edges"].append(edge(f"mirae/e/ev-ride/3F-2F", n3, n2, "elevator_ride", None,
                           ride_acc(), facility=EV, ef=F3, et=F2))

    # --- 승강기 시설 ---
    d["elevators"].append({
        "id": EV, "building_id": "mirae", "shaft_group": "G1",
        "served_floor_ids": [F2, F3],
        "served_floors_evidence": fm("2층·3층 정차"),
        "door_node_ids": {F2: n2, F3: n3},
        "car_width_m": fm(1.6, "m"), "car_depth_m": fm(1.5, "m"),
        "door_width_m": fm(0.9, "m"),
        "wheelchair_usable": fm(True),
        "status": "in_service", "status_checked_at": None,
        "wait_s_assumed": 25.0, "ride_s_per_floor_assumed": 5.0,
        "board_alight_s_assumed": 10.0,
        "source_refs": ASSUMED,
        "notes": [],
    })

    # --- 도면상 위치를 알 수 없는 계단참은 그대로 두되 데모에서도 연결하지 않음 ---

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=2)

    print(f"graph_version = {d['graph_version']}")
    print(f"  nodes={len(d['nodes'])}  edges={len(d['edges'])}  "
          f"elevators={len(d['elevators'])}")
    print(f"저장: {OUT}")
    print("\n주의: 이 그래프는 가정값을 포함한다. 발행 그래프는 변경되지 않았다.")


if __name__ == "__main__":
    main()
