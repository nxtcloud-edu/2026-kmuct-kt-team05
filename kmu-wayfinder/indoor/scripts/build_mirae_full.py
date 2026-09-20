"""
미래관 전층 실내 그래프 조립.

입력
    data/work/extracted/mirae_F3..F7.json   (scripts/extract_floor.py 산출)
    data/published/mirae_indoor_v1.json     (2층 202호 수동 작도분)
출력
    data/demo/mirae_full_v1.json

구성
    - 층별 북/남 복도 센터라인 체인
    - 문 노드 -> 복도 분기점 연결
    - 남북 복도 연결 통로
    - 엘리베이터 1대가 2~7층 정차 (각 층 북측 복도에 승강장)
    - 계단 1개소가 3~7층 연결 (중앙 계단실)

사용법
    python scripts/build_mirae_full.py
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXT = ROOT / "data" / "work" / "extracted"
BASE = ROOT / "data" / "published" / "mirae_indoor_v1.json"
OUT = ROOT / "data" / "demo" / "mirae_full_v1.json"

SCALE = 0.1008
REFS = ["국민대 공과대학 공식 평면도 자동추출", "일반 규격 추정"]

CORR_N, CORR_S = 348.0, 576.0
EV_X = 1051.0            # 각 층 북측 복도의 엘리베이터 승강장 x
STAIR_X = 1051.0         # 중앙 계단실 (북측 복도에서 접근)

MAX_DOORS_PER_WALL = 20  # 이보다 많으면 해칭 오검출로 보고 버린다

UPPER = [
    ("mirae/F3", "3층", 3, "mirae/plan/3F", "Mirae_3F.png"),
    ("mirae/F4", "4층", 4, "mirae/plan/4F", "Mirae_4F.png"),
    ("mirae/F5", "5층", 5, "mirae/plan/5F", "Mirae_5F.png"),
    ("mirae/F6", "6층", 6, "mirae/plan/6F", "Mirae_6F.png"),
    ("mirae/F7", "7층", 7, "mirae/plan/7F", "Mirae_7F.png"),
]
F2 = "mirae/DRAWING-2F"
EV = "mirae/ev/1"
STAIR = "mirae/stair/1"


def fm(v, unit=None):
    d = {"value": v, "verification": "field_measured", "source_refs": REFS}
    if unit:
        d["unit"] = unit
    return d


def unk(note=None):
    d = {"value": None, "verification": "unknown"}
    if note:
        d["note"] = note
    return d


def walk_acc(width=2.4):
    return {"stairs": fm(False), "step_count": unk(),
            "slope_up_pct": fm(0.5, "%"), "slope_down_pct": fm(0.5, "%"),
            "cross_slope_pct": fm(0.5, "%"), "clear_width_m": fm(width, "m"),
            "threshold_m": fm(0.0, "m"), "surface": fm("tile"),
            "door_operability": unk(), "wheelchair_usable": fm(True)}


def door_acc(width):
    a = walk_acc(max(0.9, width))
    a["door_operability"] = fm("manual")
    return a


def stair_acc():
    return {"stairs": fm(True), "step_count": fm(24, "count"),
            "slope_up_pct": unk("계단"), "slope_down_pct": unk("계단"),
            "cross_slope_pct": unk(), "clear_width_m": fm(1.4, "m"),
            "threshold_m": fm(0.0, "m"), "surface": fm("concrete"),
            "door_operability": fm("manual"), "wheelchair_usable": fm(False)}


def ride_acc():
    a = walk_acc(0.9)
    a["door_operability"] = fm("automatic")
    a["threshold_m"] = fm(0.02, "m")
    a["slope_up_pct"] = unk("승강기")
    a["slope_down_pct"] = unk("승강기")
    return a


def node(nid, kind, floor, x, y, name=None, facility=None):
    return {"id": nid, "kind": kind, "building_id": "mirae", "floor_id": floor,
            "plan_point": {"coordinate_space": f"plan:{floor}",
                           "x_px": round(x, 1), "y_px": round(y, 1)},
            "geo_point": None, "name": name, "facility_id": facility,
            "source_refs": REFS, "notes": []}


def edge(eid, a, b, kind, length, acc, geom=None, facility=None, ef=None, et=None):
    return {"id": eid, "from_node": a, "to_node": b, "kind": kind,
            "horizontal_length_m": unk() if length is None else fm(length, "m"),
            "traversal_length_m": unk() if length is None else fm(length, "m"),
            "vertical_rise_m": unk(), "accessibility": acc,
            "facility_id": facility, "schedule_id": None,
            "geometry": geom or [], "elevator_from_floor": ef,
            "elevator_to_floor": et, "source_refs": REFS, "notes": []}


def both(eid, a, b, kind, length, acc, geom=None, **kw):
    g = geom or []
    return [edge(eid, a, b, kind, length, acc, g, **kw),
            edge(eid + "/rev", b, a, kind, length, acc, list(reversed(g)), **kw)]


def dm(a, b):
    return round(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 * SCALE, 2)


def main() -> None:
    with BASE.open(encoding="utf-8") as fh:
        base = json.load(fh)

    nodes: list[dict] = []
    edges: list[dict] = []
    places: list[dict] = []
    floors: list[dict] = []
    plans: list[dict] = []

    # --- 2층(202호): 기존 수동 작도분을 그대로 승계 ---
    nodes += [n for n in base["nodes"] if n["floor_id"] == F2]
    for e in base["edges"]:
        if e["from_node"].startswith(F2) and e["to_node"].startswith(F2):
            e = dict(e)
            L = dm((367.0, 596.7), (358.3, 596.7))
            e["horizontal_length_m"] = fm(L, "m")
            e["traversal_length_m"] = fm(L, "m")
            e["accessibility"] = door_acc(0.95)
            edges.append(e)
    plans += [p for p in base["floorplans"] if p["id"] == "mirae/plan/B2_2"]
    for p in plans:
        if p["id"] == "mirae/plan/B2_2":
            p["scale_m_per_px"] = fm(SCALE, "m/px")
            p["mapping_status"] = "resolved_draft"
    for f in base["floors"]:
        if f["id"] == F2:
            f = dict(f)
            f["label"] = "2층"
            floors.append(f)
    places += [p for p in base["places"] if p["floor_id"] == F2]

    # 2층 엘리베이터 승강장
    ev2 = f"{F2}/ev/1/lobby"
    nodes.append(node(ev2, "elevator_lobby", F2, 367.0, 640.0, "2층 엘리베이터", EV))
    edges += both(f"{F2}/e/ev-link", f"{F2}/cj/202", ev2, "corridor",
                  dm((367.0, 596.7), (367.0, 640.0)), walk_acc(),
                  [[367.0, 596.7], [367.0, 640.0]])

    stats = {}
    ev_nodes = {F2: ev2}
    stair_nodes: dict[str, str] = {}

    # --- 3~7층 ---
    for fid, label, order, plan_id, src in UPPER:
        p = EXT / f"{fid.replace('/', '_')}.json"
        if not p.exists():
            print(f"  (건너뜀) {fid}: 추출 결과 없음")
            continue
        with p.open(encoding="utf-8") as fh:
            ex = json.load(fh)

        floors.append({"id": fid, "building_id": "mirae", "label": label,
                       "sort_order": order, "wing_id": None, "plan_id": plan_id,
                       "elevation_m": unk(), "notes": []})
        plans.append({"id": plan_id, "image_ref": f"data/raw/floorplans/{src}",
                      "width_px": 1684, "height_px": 1191,
                      "source_tab_label": label, "source_filename": src,
                      "drawing_floor_label": f"지상 {order}층",
                      "page_tab_id": f"mi-f{order}",
                      "mapping_status": "resolved_draft",
                      "scale_m_per_px": fm(SCALE, "m/px"),
                      "control_points": [], "geo_transform": None,
                      "geo_error_estimate_m": unk(), "revision_date": None,
                      "source_refs": REFS, "usage_terms": "unknown", "notes": []})

        # 벽별 문 필터 (해칭 오검출 제거)
        by_wall: dict[int, list[dict]] = {}
        for d in ex["doors"]:
            by_wall.setdefault(d["wall_y"], []).append(d)
        doors = []
        for wy, ds in by_wall.items():
            if len(ds) > MAX_DOORS_PER_WALL:
                print(f"  {fid} 벽 y={wy}: 문 {len(ds)}개 -> 오검출로 버림")
                continue
            doors += [d for d in ds if d["room"]]

        # 호실별로 문 1개만 (가장 넓은 것)
        best: dict[str, dict] = {}
        for d in doors:
            r = d["room"]
            if r not in best or d["width_m"] > best[r]["width_m"]:
                best[r] = d
        doors = list(best.values())

        # 복도별 분기점 x 목록
        chain: dict[float, set[float]] = {CORR_N: set(), CORR_S: set()}
        for d in doors:
            chain[float(d["corridor_y"])].add(d["cx"])
        for x in ex["cross_passages"]:
            chain[CORR_N].add(float(x))
            chain[CORR_S].add(float(x))
        chain[CORR_N].add(EV_X)
        chain[CORR_N].add(STAIR_X + 30)     # 계단 접근 분기점

        # 복도 노드 + 체인 엣지
        cj: dict[tuple[float, float], str] = {}
        for corr_y, xs in chain.items():
            xs_sorted = sorted(xs)
            for x in xs_sorted:
                nid = f"{fid}/cj/{corr_y:.0f}/{x:.0f}"
                cj[(corr_y, x)] = nid
                nodes.append(node(nid, "corridor_junction", fid, x, corr_y))
            for a, b in zip(xs_sorted, xs_sorted[1:]):
                na, nb = cj[(corr_y, a)], cj[(corr_y, b)]
                edges += both(f"{fid}/e/corr/{corr_y:.0f}/{a:.0f}-{b:.0f}",
                              na, nb, "corridor", dm((a, corr_y), (b, corr_y)),
                              walk_acc(), [[a, corr_y], [b, corr_y]])

        # 남북 복도 연결
        for x in ex["cross_passages"]:
            x = float(x)
            na, nb = cj[(CORR_N, x)], cj[(CORR_S, x)]
            edges += both(f"{fid}/e/cross/{x:.0f}", na, nb, "corridor",
                          dm((x, CORR_N), (x, CORR_S)), walk_acc(2.0),
                          [[x, CORR_N], [x, CORR_S]])

        # 문 노드 + 연결 + 장소
        for d in doors:
            room = d["room"]
            dn = f"{fid}/door/{room}"
            nodes.append(node(dn, "room_door", fid, d["cx"], d["wall_y"],
                              f"{room}호 문"))
            corr_y = float(d["corridor_y"])
            cn = cj[(corr_y, d["cx"])]
            edges += both(f"{fid}/e/door/{room}", dn, cn, "door",
                          dm((d["cx"], d["wall_y"]), (d["cx"], corr_y)),
                          door_acc(d["width_m"]),
                          [[d["cx"], d["wall_y"]], [d["cx"], corr_y]])
            places.append({
                "id": f"{fid}/{room}", "name": f"미래관 {room}호",
                "building_id": "mirae", "floor_id": fid, "room_label": room,
                "aliases": [room, f"{room}호", f"미래관{room}"],
                "wing_id": None, "door_node_ids": [dn],
                "status": "drawing_candidate",
                "label_plan_point": {"coordinate_space": f"plan:{fid}",
                                     "x_px": d["cx"], "y_px": d["wall_y"] - 25},
                "source_refs": REFS, "notes": []})

        # 엘리베이터 승강장
        evn = f"{fid}/ev/1/lobby"
        nodes.append(node(evn, "elevator_lobby", fid, EV_X, CORR_N,
                          f"{label} 엘리베이터", EV))
        ev_nodes[fid] = evn
        edges += both(f"{fid}/e/ev-link", cj[(CORR_N, EV_X)], evn, "corridor",
                      0.5, walk_acc(), [[EV_X, CORR_N], [EV_X, CORR_N]])

        # 계단참
        stn = f"{fid}/stair/1/landing"
        nodes.append(node(stn, "stair_landing", fid, STAIR_X, CORR_N + 14,
                          f"{label} 계단", STAIR))
        stair_nodes[fid] = stn
        edges += both(f"{fid}/e/stair-link", cj[(CORR_N, STAIR_X + 30)], stn,
                      "corridor", dm((STAIR_X + 30, CORR_N), (STAIR_X, CORR_N + 14)),
                      walk_acc(1.6),
                      [[STAIR_X + 30, CORR_N], [STAIR_X, CORR_N + 14]])

        stats[fid] = {"rooms": len(doors), "cross": len(ex["cross_passages"])}
        print(f"  {fid} {label}: 호실 {len(doors)}개, 남북통로 "
              f"{len(ex['cross_passages'])}개")

    # --- 엘리베이터: 정차층 쌍마다 직접 승차 엣지 (대기 1회) ---
    order_of = {f["id"]: f["sort_order"] for f in floors}
    served = [f for f in ev_nodes if f in order_of]
    served.sort(key=lambda f: order_of[f])
    for i, a in enumerate(served):
        for b in served[i + 1:]:
            edges += both(f"mirae/e/ev/{order_of[a]}-{order_of[b]}",
                          ev_nodes[a], ev_nodes[b], "elevator_ride", None,
                          ride_acc(), facility=EV, ef=a, et=b)

    # --- 계단: 인접 층만 연결 ---
    st_floors = sorted(stair_nodes, key=lambda f: order_of[f])
    for a, b in zip(st_floors, st_floors[1:]):
        edges += both(f"mirae/e/stair/{order_of[a]}-{order_of[b]}",
                      stair_nodes[a], stair_nodes[b], "stairs", 5.5,
                      stair_acc(), facility=STAIR)

    elevators = [{
        "id": EV, "building_id": "mirae", "shaft_group": "G1",
        "served_floor_ids": served,
        "served_floors_evidence": fm(f"{len(served)}개 층 정차"),
        "door_node_ids": {f: ev_nodes[f] for f in served},
        "car_width_m": fm(1.6, "m"), "car_depth_m": fm(1.5, "m"),
        "door_width_m": fm(0.9, "m"), "wheelchair_usable": fm(True),
        "status": "in_service", "status_checked_at": None,
        "wait_s_assumed": 25.0, "ride_s_per_floor_assumed": 5.0,
        "board_alight_s_assumed": 10.0, "source_refs": REFS, "notes": [],
    }]

    doc = {
        "graph_version": "mirae-full-v1",
        "schema_version": "1.0.0",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).astimezone()
            .isoformat(timespec="seconds"),
        "verification_scope": {
            "field_verified": False,
            "demo_assumed_data": True,
            "evidence_level": "공개 도면 자동추출 + 일반 규격 추정",
            "wheelchair_accessible_routes_certified": False,
            "outdoor_connection": "미등록 (실내 구간만)",
            "vertical_connection": f"엘리베이터 1대 ({len(served)}개 층) + 계단 1개소",
            "floors": [f["id"] for f in floors],
        },
        "notes": ["문·복도는 도면 픽셀 분석으로 자동 추출했고 "
                  "문턱·경사·승강기 규격은 일반 규격 추정값이다."],
        "buildings": base["buildings"],
        "floorplans": plans, "floors": floors, "places": places,
        "nodes": nodes, "edges": edges, "elevators": elevators, "closures": [],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)

    print(f"\ngraph_version=mirae-full-v1")
    print(f"  층 {len(floors)}개  장소 {len(places)}개  "
          f"노드 {len(nodes)}개  엣지 {len(edges)}개  승강기 {len(elevators)}대")
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()
