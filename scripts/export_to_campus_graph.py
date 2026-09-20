"""
미래관 실내 그래프를 루트 Next.js 앱의 campus-graph.json 형식으로 내보낸다.

왜
--
루트 앱(lib/graph.ts)은 미래관을 **층 단위 15개 노드**로만 갖고 있다
(구관 B1~7F, 신관 1F~7F). 호실이 없어서 "미래관 338호" 를 찾을 수 없다.
이 스크립트는 그 15개 노드를 실내 그래프(호실 문 단위)로 교체한다.

보존하는 것
-----------
루트 앱의 미래관 층 노드는 **외부 연결 9개**를 들고 있다
(종합복지관 1~4F, 예술관 B2, 실외 보행로 3곳). 이 연결을 잃으면 캠퍼스에서
미래관으로 들어갈 수 없다. 그래서 각 외부 엣지를 해당 층의 대표 노드로 다시 붙인다.
대표 노드 우선순위: entrance_inside -> elevator_lobby -> 복도 분기점.

스키마 대응
-----------
    실내                          루트 앱
    room_door                     kind=junction, searchable=true, aliases=[호실번호,...]
    entrance_inside               kind=entrance, searchable=true
    elevator_lobby                kind=junction, searchable=true
    stair_landing / corridor      kind=junction, searchable=false
    corridor / door 엣지          stairsUp=0, slope=0, indoor=true
    stairs 엣지                   stairsUp=step_count, indoor=true
    elevator_ride 엣지            elevator=true, distance=0
    mirae/B1, mirae/F1..F7        floor = -1, 1..7
    id 의 '/'                     '_' 로 치환

역방향은 루트 엔진이 bidirectional=true 로 자동 생성하므로
실내 그래프의 '/rev' 엣지는 내보내지 않는다.

사용법
    python scripts/export_to_campus_graph.py --check     # 미리보기만
    python scripts/export_to_campus_graph.py             # 실제 기록 (백업 생성)
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parents[1]      # kmu-indoor-nav/
REPO = ROOT.parent                                       # 저장소 루트
SRC = ROOT / "data" / "demo" / "mirae_nav_v1.json"
DST = REPO / "data" / "campus-graph.json"
COORDS_DST = REPO / "data" / "graph-coords.json"
MAPS_DST = REPO / "public" / "maps"
MAPS_TS = REPO / "lib" / "ui" / "maps.ts"
NAVMAPS = ROOT / "data" / "raw" / "navmaps"

#: 내 층 -> 루트 앱 public/maps 파일명. 도면 픽셀 좌표가 곧 viewBox 좌표가 된다.
FLOOR_MAP = {
    "mirae/B1": ("nav_B1.png", "mirae-b1.png", "미래관 B1", "미래 B1"),
    "mirae/F1": ("nav_1F.png", "mirae-1f.png", "미래관 1F", "미래 1F"),
    "mirae/F2": ("nav_2F.png", "mirae-2f.png", "미래관 2F", "미래 2F"),
    "mirae/F3": ("nav_3F.png", "mirae-3f.png", "미래관 3F", "미래 3F"),
    "mirae/F4": ("nav_4F.png", "mirae-4f.png", "미래관 4F", "미래 4F"),
    "mirae/F5": ("nav_5F.png", "mirae-5f.png", "미래관 5F", "미래 5F"),
    "mirae/F6": ("nav_6F.png", "mirae-6f.png", "미래관 6F", "미래 6F"),
    "mirae/F7": ("nav_7F.png", "mirae-7f.png", "미래관 7F", "미래 7F"),
}

BUILDING = "미래관"
FLOOR_NUM = {"mirae/B1": -1, "mirae/F1": 1, "mirae/F2": 2, "mirae/F3": 3,
             "mirae/F4": 4, "mirae/F5": 5, "mirae/F6": 6, "mirae/F7": 7}
#: 루트 앱의 기존 미래관 노드 id -> 층 번호 (외부 엣지 재연결용)
LEGACY_FLOOR = {
    "mirae_old_b1": -1, "mirae_old_1f": 1, "mirae_old_2f": 2, "mirae_old_3f": 3,
    "mirae_old_4f": 4, "mirae_old_5f": 5, "mirae_old_6f": 6, "mirae_old_7f": 7,
    "mirae_new_1f": 1, "mirae_new_2f": 2, "mirae_new_3f": 3, "mirae_new_4f": 4,
    "mirae_new_5f": 5, "mirae_new_6f": 6, "mirae_new_7f": 7,
}


def sid(x: str) -> str:
    """루트 앱 id 규칙에 맞게 '/' 를 '_' 로."""
    return x.replace("/", "_")


def attr(a: dict | None):
    if not isinstance(a, dict):
        return None
    return a.get("value")


def length_m(e: dict) -> float:
    for k in ("traversal_length_m", "horizontal_length_m"):
        v = attr(e.get(k))
        if v is not None:
            return float(v)
    return 0.0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="기록하지 않고 미리보기")
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--dst", default=str(DST))
    args = ap.parse_args()

    src, dst = pathlib.Path(args.src), pathlib.Path(args.dst)
    if not src.exists():
        raise SystemExit(f"실내 그래프 없음: {src}")
    if not dst.exists():
        raise SystemExit(f"대상 그래프 없음: {dst}")

    indoor = json.loads(src.read_text(encoding="utf-8"))
    campus = json.loads(dst.read_text(encoding="utf-8"))

    inodes = {n["id"]: n for n in indoor["nodes"]}
    places_by_door: dict[str, dict] = {}
    for p in indoor["places"]:
        for d in p.get("door_node_ids", []):
            places_by_door[d] = p

    # ---------------- 1) 실내 노드 -> 루트 형식 ----------------
    out_nodes: list[dict] = []
    floor_reps: dict[int, dict[str, str]] = collections.defaultdict(dict)
    skipped_floor = 0

    for n in indoor["nodes"]:
        fid = n.get("floor_id")
        if fid not in FLOOR_NUM:
            skipped_floor += 1
            continue
        fl = FLOOR_NUM[fid]
        kind = n["kind"]
        nid = sid(n["id"])
        place = places_by_door.get(n["id"])

        if kind == "room_door" and place:
            room = place.get("room_label") or ""
            node = {"id": nid, "building": BUILDING, "floor": fl,
                    "label": f"{BUILDING} {room}호", "kind": "junction",
                    "searchable": True,
                    "aliases": sorted({room, f"{room}호", f"미래관{room}",
                                       f"미래관 {room}"} - {""})}
        elif kind == "entrance_inside":
            node = {"id": nid, "building": BUILDING, "floor": fl,
                    "label": n.get("name") or f"{BUILDING} {fl}층 출입구",
                    "kind": "entrance", "searchable": True, "aliases": []}
            floor_reps[fl].setdefault("entrance", nid)
        elif kind == "elevator_lobby":
            node = {"id": nid, "building": BUILDING, "floor": fl,
                    "label": n.get("name") or f"{BUILDING} {fl}층 엘리베이터",
                    "kind": "junction", "searchable": True, "aliases": []}
            floor_reps[fl].setdefault("elevator", nid)
        else:
            node = {"id": nid, "building": BUILDING, "floor": fl,
                    "label": n.get("name") or f"{BUILDING} {fl}층",
                    "kind": "junction", "searchable": False, "aliases": []}
            floor_reps[fl].setdefault("junction", nid)
        out_nodes.append(node)

    out_ids = {n["id"] for n in out_nodes}

    # ---------------- 2) 실내 엣지 -> 루트 형식 ----------------
    out_edges: list[dict] = []
    kind_count: collections.Counter = collections.Counter()
    for e in indoor["edges"]:
        if e["id"].endswith("/rev"):
            continue                      # 루트 엔진이 bidirectional 로 자동 생성
        a, b = sid(e["from_node"]), sid(e["to_node"])
        if a not in out_ids or b not in out_ids:
            continue
        k = e["kind"]
        kind_count[k] += 1
        dist = round(length_m(e), 1)
        if k == "stairs":
            steps = attr(e["accessibility"].get("step_count")) or 24
            out_edges.append({"from": a, "to": b, "distance": max(1.0, dist),
                              "stairsUp": int(steps), "stairsDown": 0,
                              "slope": 0, "indoor": True, "elevator": False,
                              "bidirectional": True,
                              "note": "계단 (실내 그래프)"})
        elif k == "elevator_ride":
            out_edges.append({"from": a, "to": b, "distance": 0,
                              "stairsUp": 0, "stairsDown": 0, "slope": 0,
                              "indoor": True, "elevator": True,
                              "bidirectional": True,
                              "note": "엘리베이터 (실내 그래프)"})
        else:
            out_edges.append({"from": a, "to": b, "distance": max(0.5, dist),
                              "stairsUp": 0, "stairsDown": 0, "slope": 0,
                              "indoor": True, "elevator": False,
                              "bidirectional": True,
                              "note": f"{k} (실내 그래프)"})

    # ---------------- 3) 기존 미래관 노드/엣지 제거 ----------------
    legacy_ids = {n["id"] for n in campus["nodes"]
                  if n.get("building") == BUILDING}
    kept_nodes = [n for n in campus["nodes"] if n["id"] not in legacy_ids]

    external, dropped_internal = [], 0
    for e in campus["edges"]:
        fi, ti = e["from"] in legacy_ids, e["to"] in legacy_ids
        if fi and ti:
            dropped_internal += 1
        elif fi or ti:
            external.append(e)
    kept_edges = [e for e in campus["edges"]
                  if e["from"] not in legacy_ids and e["to"] not in legacy_ids]

    # ---------------- 4) 외부 연결 재부착 ----------------
    def rep(fl: int) -> str | None:
        r = floor_reps.get(fl) or {}
        return r.get("entrance") or r.get("elevator") or r.get("junction")

    rewired, unmapped = [], []
    for e in external:
        leg = e["from"] if e["from"] in legacy_ids else e["to"]
        other = e["to"] if e["from"] in legacy_ids else e["from"]
        fl = LEGACY_FLOOR.get(leg)
        target = rep(fl) if fl is not None else None
        if target is None:
            unmapped.append((leg, other, fl))
            continue
        ne = dict(e)
        if e["from"] in legacy_ids:
            ne["from"] = target
        else:
            ne["to"] = target
        ne["note"] = ((e.get("note") or "") +
                      f" | 실내 그래프 연결 ({leg} -> {target})").strip(" |")
        rewired.append(ne)

    # ---------------- 5) 조립 ----------------
    new_nodes = kept_nodes + out_nodes
    new_edges = kept_edges + rewired + out_edges
    for b in campus.get("buildings", []):
        if b.get("name") == BUILDING:
            b["floors"] = sorted(set(FLOOR_NUM.values()))

    campus["nodes"] = new_nodes
    campus["edges"] = new_edges
    campus["version"] = campus.get("version", "0") + "+mirae-indoor"
    rd = campus.get("_readme")
    line = ("미래관은 kmu-indoor-nav 의 실내 그래프에서 생성했다 "
            "(scripts/export_to_campus_graph.py). 직접 편집하지 말 것.")
    if isinstance(rd, list):
        if line not in rd:
            rd.append(line)
    else:
        campus["_readme"] = [line]

    # ---------------- 6) 보고 ----------------
    print(f"실내 원본 : {src.name}  노드 {len(indoor['nodes'])} 엣지 {len(indoor['edges'])}")
    print(f"대상 그래프: {dst.name}  노드 {len(campus['nodes']) - len(out_nodes) + len(legacy_ids)}"
          f" -> {len(new_nodes)}")
    print(f"\n기존 미래관 제거 : 노드 {len(legacy_ids)}개, 내부 엣지 {dropped_internal}개")
    print(f"실내 반영        : 노드 {len(out_nodes)}개, 엣지 {len(out_edges)}개")
    print(f"  엣지 종류      : {dict(kind_count)}")
    searchable = sum(1 for n in out_nodes if n["searchable"])
    print(f"  검색 가능 노드  : {searchable}개 (호실/출입구/엘리베이터)")
    if skipped_floor:
        print(f"  층 매핑 없어 제외: {skipped_floor}개 노드")

    print(f"\n외부 연결 재부착 : {len(rewired)}/{len(external)}개")
    for e in rewired:
        print(f"  {e['from']:<28} <-> {e['to']:<28} dist={e.get('distance')}")
    if unmapped:
        print("  ! 재부착 실패:")
        for leg, other, fl in unmapped:
            print(f"    {leg} (floor={fl}) <-> {other}  -> 해당 층 대표 노드 없음")

    print(f"\n층별 대표 노드:")
    for fl in sorted(floor_reps):
        r = floor_reps[fl]
        pick = r.get("entrance") or r.get("elevator") or r.get("junction")
        why = ("출입구" if r.get("entrance") else
               "엘리베이터" if r.get("elevator") else "복도")
        print(f"  {fl:>3}층 -> {pick}  ({why})")

    print(f"\n최종: 노드 {len(new_nodes)}  엣지 {len(new_edges)}")

    if args.check:
        print("\n--check 모드: 기록하지 않았습니다.")
        return

    bak = dst.with_suffix(".json.bak")
    if not bak.exists():
        shutil.copy2(dst, bak)
        print(f"백업 생성: {bak.name}")
    dst.write_text(json.dumps(campus, ensure_ascii=False, indent=2),
                   encoding="utf-8")
    print(f"기록: {dst}  ({dst.stat().st_size/1024:.0f} KB)")

    # ---------------- 7) 지도 이미지 + 좌표 + 레지스트리 ----------------
    write_maps(indoor)
    print("다음: npm run typecheck && npm run build")


def write_maps(indoor: dict) -> None:
    """층 도면 PNG 를 public/maps 로 복사하고, 노드 좌표와 레지스트리를 갱신한다.

    실내 노드의 plan_point 픽셀 좌표가 그대로 오버레이 viewBox 좌표가 된다
    (배경이 <img> 이고 오버레이 svg 의 viewBox 를 이미지 크기로 맞추므로).
    따라서 좌표 변환이 필요 없다.
    """
    from PIL import Image

    MAPS_DST.mkdir(parents=True, exist_ok=True)
    sizes: dict[str, tuple[int, int]] = {}
    copied = 0
    for fid, (srcname, dstname, label, short) in FLOOR_MAP.items():
        s = NAVMAPS / srcname
        if not s.exists():
            print(f"  ! 도면 없음: {srcname}")
            continue
        d = MAPS_DST / dstname
        shutil.copy2(s, d)
        with Image.open(d) as im:
            sizes[fid] = im.size
        copied += 1
    print(f"\n지도 이미지 복사: {copied}개 -> {MAPS_DST}")

    # --- 좌표 기록 ---
    gc = json.loads(COORDS_DST.read_text(encoding="utf-8"))
    coords = gc.setdefault("coords", {})
    removed = [k for k in coords if k.startswith("mirae_old_") or k.startswith("mirae_new_")]
    for k in removed:
        coords.pop(k, None)
    added = 0
    for n in indoor["nodes"]:
        fid = n.get("floor_id")
        pp = n.get("plan_point")
        if fid not in FLOOR_MAP or not pp:
            continue
        coords[sid(n["id"])] = {
            "svg": f"/maps/{FLOOR_MAP[fid][1]}",
            "x": round(float(pp["x_px"]), 1),
            "y": round(float(pp["y_px"]), 1),
        }
        added += 1
    note = ("미래관 좌표는 kmu-indoor-nav 의 층 도면 픽셀 좌표다 "
            "(scripts/export_to_campus_graph.py 가 기록).")
    rd = gc.get("_readme")
    if isinstance(rd, list) and note not in rd:
        rd.append(note)
    COORDS_DST.write_text(json.dumps(gc, ensure_ascii=False), encoding="utf-8")
    print(f"좌표 기록: 기존 미래관 {len(removed)}개 제거, 실내 {added}개 추가 "
          f"-> {COORDS_DST.name} (총 {len(coords)}개)")

    # --- MAP_REGISTRY 갱신 ---
    ts = MAPS_TS.read_text(encoding="utf-8")
    entries = []
    for fid, (srcname, dstname, label, short) in FLOOR_MAP.items():
        if fid not in sizes:
            continue
        w, h = sizes[fid]
        entries.append(
            f"  '/maps/{dstname}': {{\n"
            f"    src: '/maps/{dstname}',\n"
            f"    width: {w},\n"
            f"    height: {h},\n"
            f"    label: '{label}',\n"
            f"    short: '{short}',\n"
            f"    kind: 'floor',\n"
            f"  }},\n"
        )
    block = "".join(entries)
    marker = "  // --- 미래관 (kmu-indoor-nav 생성) ---\n"

    if marker in ts:
        head, _, tail = ts.partition(marker)
        end = tail.find("\n};")
        ts = head + marker + block + tail[end + 1:]
    else:
        # MAP_REGISTRY 객체의 닫는 '};' 를 중괄호 계수로 정확히 찾는다.
        decl = ts.index("export const MAP_REGISTRY")
        open_brace = ts.index("{", decl)
        depth, i = 0, open_brace
        while i < len(ts):
            if ts[i] == "{":
                depth += 1
            elif ts[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        ts = ts[:i] + marker + block + ts[i:]
    MAPS_TS.write_text(ts, encoding="utf-8")
    print(f"MAP_REGISTRY 갱신: 미래관 {len(entries)}개 층 등록 -> {MAPS_TS.name}")


if __name__ == "__main__":
    main()
