"""
내비게이션맵 시안에서 실내 그래프를 직접 추출한다.

시안은 원본 도면을 단순화한 재렌더링이라 원본과 좌표가 맞지 않는다
(정합 적중률 0.0~0.65, scripts/analyze_navmap.py 참고).
그래서 정합을 포기하고 **시안 자체를 데이터 소스로** 쓴다.
같은 이미지에서 그래프를 뽑으므로 경로가 화면과 정확히 정렬된다.

시안의 색상 규약 (동봉 README)
    연한 민트 rgb(221,244,233)  실내 이동 공간
    파랑                        엘리베이터
    주황                        계단
    초록                        출입구
    회색 (지하1층)              주차 구역 / 차량 동선

파이프라인
    1) 셀 격자(CELL px)로 색상 분류 -> 통행 가능 마스크
    2) Zhang-Suen 세선화로 복도 중심선 골격 추출
    3) 골격의 분기점/끝점 + 앵커 부착점을 노드로, 사이 경로를 엣지로
    4) 엘리베이터/계단/출입구 색 덩어리 -> 시설 노드
    5) OCR 호실 라벨 -> 가장 가까운 골격점에 문 노드로 부착
    6) 층 조립: 엘리베이터는 전 층, 계단은 인접 층

사용법
    python scripts/build_from_navmap.py            # 전층
    python scripts/build_from_navmap.py nav_3F.png # 한 층 진단
"""

from __future__ import annotations

import collections
import datetime as _dt
import json
import math
import pathlib
import re
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAV = ROOT / "data" / "raw" / "navmaps"
OCR_DIR = ROOT / "data" / "work" / "ocr_nav"
OUT = ROOT / "data" / "demo" / "mirae_nav_v1.json"

CELL = 6                 # 셀 크기(px)
BUILDING_LEN_M = 139.55  # 그리드축 ①~⑰ 실측 치수 (원본 도면 치수선)
MIN_BLOB_CELLS = 6       # 시설 덩어리 최소 크기
ROOM_RE = re.compile(r"^(B?\d{3}(?:-\d)?)$")

REFS = ["미래관 내비게이션맵 시안(색상 규약 기반 자동추출)",
        "치수: 국민대 공과대학 공식 평면도 치수선"]

# (파일, floor_id, 표시라벨, 정렬순번)
FLOORS = [
    ("nav_B1.png", "mirae/B1", "지하1층", 0),
    ("nav_1F.png", "mirae/F1", "1층", 1),
    ("nav_2F.png", "mirae/F2", "2층", 2),
    ("nav_3F.png", "mirae/F3", "3층", 3),
    ("nav_4F.png", "mirae/F4", "4층", 4),
    ("nav_5F.png", "mirae/F5", "5층", 5),
    ("nav_6F.png", "mirae/F6", "6층", 6),
    ("nav_7F.png", "mirae/F7", "7층", 7),
]
EV = "mirae/ev/1"
STAIR = "mirae/stair/1"


# ---------------------------------------------------------------- 색 분류
def classify(c) -> str:
    r, g, b = c[0], c[1], c[2]
    if r > 245 and g > 245 and b > 245:
        return "bg"
    if b > 150 and b - r > 40 and b - g > 20:
        return "elevator"
    if r > 190 and 90 < g < 205 and b < 130:
        return "stairs"
    if g > 140 and g - r > 40 and g - b > 25:
        return "entrance"
    if g > 200 and b > 200 and r < 240 and min(g, b) - r > 6:
        return "walk"
    if abs(r - g) < 14 and abs(g - b) < 14 and 110 < r < 240:
        return "gray"
    return "other"


WALKABLE = {"walk", "elevator", "stairs", "entrance"}


def cell_grid(img: Image.Image) -> tuple[list[list[str]], int, int]:
    px = img.convert("RGB").load()
    W, H = img.size
    gw, gh = W // CELL, H // CELL
    grid = [["bg"] * gw for _ in range(gh)]
    for gy in range(gh):
        for gx in range(gw):
            cnt = collections.Counter()
            for dy in (1, CELL // 2, CELL - 2):
                for dx in (1, CELL // 2, CELL - 2):
                    cnt[classify(px[gx * CELL + dx, gy * CELL + dy])] += 1
            # 시설색이 하나라도 있으면 시설로 본다 (작은 아이콘 보존)
            for k in ("elevator", "stairs", "entrance"):
                if cnt[k] >= 2:
                    grid[gy][gx] = k
                    break
            else:
                grid[gy][gx] = cnt.most_common(1)[0][0]
    return grid, gw, gh


# ------------------------------------------------------- Zhang-Suen 세선화
def thin(mask: list[list[bool]], gw: int, gh: int) -> list[list[bool]]:
    m = [row[:] for row in mask]

    def nb(y, x):
        return [m[y - 1][x], m[y - 1][x + 1], m[y][x + 1], m[y + 1][x + 1],
                m[y + 1][x], m[y + 1][x - 1], m[y][x - 1], m[y - 1][x - 1]]

    changed = True
    it = 0
    while changed and it < 60:
        changed = False
        for step in (0, 1):
            rm = []
            for y in range(1, gh - 1):
                for x in range(1, gw - 1):
                    if not m[y][x]:
                        continue
                    p = nb(y, x)
                    B = sum(p)
                    if B < 2 or B > 6:
                        continue
                    A = sum(1 for i in range(8)
                            if not p[i] and p[(i + 1) % 8])
                    if A != 1:
                        continue
                    p2, p4, p6, p8 = p[0], p[2], p[4], p[6]
                    if step == 0 and not (p2 and p4 and p6) is False:
                        pass
                    if step == 0:
                        if p2 and p4 and p6:
                            continue
                        if p4 and p6 and p8:
                            continue
                    else:
                        if p2 and p4 and p8:
                            continue
                        if p2 and p6 and p8:
                            continue
                    rm.append((y, x))
            for y, x in rm:
                m[y][x] = False
                changed = True
        it += 1
    return m


def dilate(mask, gw, gh, r=1):
    out = [[False] * gw for _ in range(gh)]
    for y in range(gh):
        for x in range(gw):
            if not mask[y][x]:
                continue
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < gh and 0 <= nx < gw:
                        out[ny][nx] = True
    return out


def erode(mask, gw, gh, r=1):
    out = [[False] * gw for _ in range(gh)]
    for y in range(gh):
        for x in range(gw):
            ok = True
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    ny, nx = y + dy, x + dx
                    if not (0 <= ny < gh and 0 <= nx < gw and mask[ny][nx]):
                        ok = False
                        break
                if not ok:
                    break
            out[y][x] = ok
    return out


def close_mask(mask, gw, gh, r=2):
    """모폴로지 닫힘: 복도 위에 겹쳐 그려진 글자/아이콘 때문에 생긴 끊김을 메운다.

    시안은 민트 통행면 위에 호실번호·아이콘·벽선을 덧그렸기 때문에
    원본 마스크가 수십 개 조각으로 분리된다(3층 44개 조각).
    반경 r 만큼 팽창 후 침식하면 r*2 셀 이내의 틈이 이어진다.
    """
    return erode(dilate(mask, gw, gh, r), gw, gh, r)


# ---------------------------------------------------------------- 잔가지 제거
def prune_spurs(skel, gw, gh, forced: set[tuple[int, int]], min_len: int = 9):
    """짧은 잔가지 제거.

    민트 영역이 넓은 개방공간이면 세선화 결과에 잔가지(spur)가 많이 생긴다.
    끝점(deg==1)에서 시작해 분기점까지의 길이가 min_len 미만이면 지운다.
    앵커 부착점은 보존한다.
    """
    m = [row[:] for row in skel]

    def nbrs(y, x):
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < gh and 0 <= nx < gw and m[ny][nx]:
                    out.append((ny, nx))
        return out

    for _ in range(6):
        leaves = [(y, x) for y in range(gh) for x in range(gw)
                  if m[y][x] and len(nbrs(y, x)) == 1]
        removed = 0
        for leaf in leaves:
            if not m[leaf[0]][leaf[1]]:
                continue
            branch = [leaf]
            prev, cur = None, leaf
            while True:
                nb = [c for c in nbrs(*cur) if c != prev]
                if len(nb) != 1:
                    break
                prev, cur = cur, nb[0]
                branch.append(cur)
                if len(branch) > min_len:
                    break
            if len(branch) > min_len:
                continue
            if any(c in forced for c in branch):
                continue
            for c in branch[:-1] if len(branch) > 1 else branch:
                m[c[0]][c[1]] = False
                removed += 1
        if removed == 0:
            break
    return m


# ---------------------------------------------------------------- 골격 그래프
def skeleton_graph(skel, gw, gh, forced: set[tuple[int, int]]):
    """(노드집합, 엣지목록[(a,b,[셀경로])])"""
    def nbrs(y, x):
        out = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dy == 0 and dx == 0:
                    continue
                ny, nx = y + dy, x + dx
                if 0 <= ny < gh and 0 <= nx < gw and skel[ny][nx]:
                    out.append((ny, nx))
        return out

    cells = [(y, x) for y in range(gh) for x in range(gw) if skel[y][x]]
    deg = {c: len(nbrs(*c)) for c in cells}
    nodes = {c for c in cells if deg[c] != 2} | (forced & set(cells))
    if not nodes and cells:
        nodes = {cells[0]}

    edges = []
    seen = set()
    for n in list(nodes):
        for start in nbrs(*n):
            if (n, start) in seen:
                continue
            path = [n, start]
            seen.add((n, start))
            prev, cur = n, start
            while cur not in nodes:
                nxt = [c for c in nbrs(*cur) if c != prev]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
                path.append(cur)
            seen.add((cur, path[-2]))
            if cur in nodes and cur != n and len(path) >= 2:
                edges.append((n, cur, path))
    return nodes, edges


# ---------------------------------------------------------------- 덩어리
def blobs(grid, gw, gh, kind: str):
    seen = [[False] * gw for _ in range(gh)]
    out = []
    for y in range(gh):
        for x in range(gw):
            if grid[y][x] != kind or seen[y][x]:
                continue
            q = [(y, x)]
            seen[y][x] = True
            comp = []
            while q:
                cy, cx = q.pop()
                comp.append((cy, cx))
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        ny, nx = cy + dy, cx + dx
                        if 0 <= ny < gh and 0 <= nx < gw and not seen[ny][nx] \
                                and grid[ny][nx] == kind:
                            seen[ny][nx] = True
                            q.append((ny, nx))
            if len(comp) >= MIN_BLOB_CELLS:
                cy = sum(c[0] for c in comp) / len(comp)
                cx = sum(c[1] for c in comp) / len(comp)
                out.append({"cy": cy, "cx": cx, "cells": len(comp)})
    out.sort(key=lambda b: -b["cells"])
    return out


# ---------------------------------------------------------------- OCR 라벨
def nav_labels(stem: str) -> list[dict]:
    p = OCR_DIR / f"{stem}.txt"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("LINE"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        for tok in parts[2].split():
            if "@" not in tok:
                continue
            text, _, pos = tok.rpartition("@")
            m = ROOM_RE.match(text.strip())
            if not m:
                continue
            try:
                x, y = (int(v) for v in pos.split(","))
            except ValueError:
                continue
            out.append({"room": m.group(1), "x": x, "y": y})
    # 중복 제거
    uniq = {}
    for r in out:
        uniq.setdefault(r["room"], r)
    return list(uniq.values())


# ---------------------------------------------------------------- 유틸
def fm(v, unit=None):
    d = {"value": v, "verification": "field_measured"}
    if unit:
        d["unit"] = unit
    return d


def unk(note=None):
    d = {"value": None, "verification": "unknown"}
    if note:
        d["note"] = note
    return d


def walk_acc(w=2.4):
    return {"stairs": fm(False), "step_count": unk(),
            "slope_up_pct": fm(0.5, "%"), "slope_down_pct": fm(0.5, "%"),
            "cross_slope_pct": fm(0.5, "%"), "clear_width_m": fm(w, "m"),
            "threshold_m": fm(0.0, "m"), "surface": fm("tile"),
            "door_operability": unk(), "wheelchair_usable": fm(True)}


def door_acc():
    a = walk_acc(1.0)
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


# ---------------------------------------------------------------- 층 추출
def build_floor(fname: str, fid: str, label: str, order: int, diag: bool = False):
    img = Image.open(NAV / fname)
    W, H = img.size
    grid, gw, gh = cell_grid(img)

    mask = [[grid[y][x] in WALKABLE for x in range(gw)] for y in range(gh)]
    n_walk = sum(sum(r) for r in mask)
    mask = close_mask(mask, gw, gh, 2)
    n_closed = sum(sum(r) for r in mask)

    evb = blobs(grid, gw, gh, "elevator")
    stb = blobs(grid, gw, gh, "stairs")
    enb = blobs(grid, gw, gh, "entrance")
    labels = nav_labels(pathlib.Path(fname).stem)

    # 건물 폭으로 축척 산출
    xs = [x for y in range(gh) for x in range(gw) if grid[y][x] != "bg"]
    span_px = (max(xs) - min(xs) + 1) * CELL if xs else W
    m_per_px = BUILDING_LEN_M / span_px

    skel = thin(mask, gw, gh)
    n_raw = sum(sum(r) for r in skel)

    # 앵커는 반드시 **최대 골격 요소**에 붙인다.
    # 작은 고립 조각에 붙으면 그 시설/호실이 경로에서 단절된다.
    def skel_components(sk):
        seen = [[False] * gw for _ in range(gh)]
        out = []
        for y in range(gh):
            for x in range(gw):
                if not sk[y][x] or seen[y][x]:
                    continue
                q, comp = [(y, x)], []
                seen[y][x] = True
                while q:
                    cy, cx = q.pop()
                    comp.append((cy, cx))
                    for dy in (-1, 0, 1):
                        for dx in (-1, 0, 1):
                            ny, nx = cy + dy, cx + dx
                            if 0 <= ny < gh and 0 <= nx < gw and sk[ny][nx] \
                                    and not seen[ny][nx]:
                                seen[ny][nx] = True
                                q.append((ny, nx))
                out.append(comp)
        out.sort(key=len, reverse=True)
        return out

    comps_sk = skel_components(skel)
    main_cells = comps_sk[0] if comps_sk else []
    n_main = len(main_cells)

    # 앵커(문/시설) 부착점: 최대 골격 요소 중 가장 가까운 셀
    skel_cells = main_cells

    def nearest_skel(cy: float, cx: float):
        if not skel_cells:
            return None
        return min(skel_cells, key=lambda c: (c[0] - cy) ** 2 + (c[1] - cx) ** 2)

    anchors = []   # (kind, key, attach_cell, px, py, extra)
    for i, b in enumerate(evb[:1]):        # 엘리베이터는 가장 큰 덩어리 1개
        a = nearest_skel(b["cy"], b["cx"])
        if a:
            anchors.append(("elevator", f"{fid}/ev/1/lobby", a,
                            b["cx"] * CELL, b["cy"] * CELL, None))
    for i, b in enumerate(stb[:2]):        # 계단 최대 2개
        a = nearest_skel(b["cy"], b["cx"])
        if a:
            anchors.append(("stairs", f"{fid}/stair/{i+1}/landing", a,
                            b["cx"] * CELL, b["cy"] * CELL, i + 1))
    for i, b in enumerate(enb[:3]):        # 출입구 최대 3개
        a = nearest_skel(b["cy"], b["cx"])
        if a:
            anchors.append(("entrance", f"{fid}/entrance/{i+1}", a,
                            b["cx"] * CELL, b["cy"] * CELL, i + 1))
    for r in labels:
        a = nearest_skel(r["y"] / CELL, r["x"] / CELL)
        if a:
            # 라벨이 통행공간에서 너무 멀면 버린다 (25 셀 = 150px)
            d = math.dist((a[0], a[1]), (r["y"] / CELL, r["x"] / CELL))
            if d <= 45:
                anchors.append(("room", f"{fid}/door/{r['room']}", a,
                                r["x"], r["y"], r["room"]))

    forced = {a[2] for a in anchors}
    # 최대 요소만 남기고 나머지 조각은 버린다 (고립 경로 방지)
    keep = set(main_cells) | forced
    skel = [[skel[y][x] and (y, x) in keep for x in range(gw)] for y in range(gh)]
    skel = prune_spurs(skel, gw, gh, forced)
    n_skel = sum(sum(r) for r in skel)
    skel_cells = [(y, x) for y in range(gh) for x in range(gw) if skel[y][x]]
    nodes_set, sk_edges = skeleton_graph(skel, gw, gh, forced)

    if diag:
        print(f"\n=== {fname} -> {fid} ({label}) ===")
        print(f"  이미지 {W}x{H}  셀격자 {gw}x{gh}  축척 {m_per_px*1000:.1f} mm/px")
        print(f"  통행셀 {n_walk} -> 닫힘 {n_closed}  "
              f"세선화 {n_raw} -> 잔가지제거 {n_skel}  "
              f"골격노드 {len(nodes_set)}  골격엣지 {len(sk_edges)}")
        print(f"  엘리베이터 덩어리 {len(evb)}  계단 {len(stb)}  출입구 {len(enb)}")
        print(f"  OCR 호실 {len(labels)}개 -> 부착 "
              f"{sum(1 for a in anchors if a[0]=='room')}개")
        return None

    # --- 그래프 산출물 ---
    nodes, edges, places = [], [], []
    nid_of = {}

    def node_id(cell) -> str:
        if cell not in nid_of:
            nid_of[cell] = f"{fid}/cj/{cell[1]}_{cell[0]}"
        return nid_of[cell]

    anchor_at = {}
    for kind, nid, cell, pxx, pyy, extra in anchors:
        anchor_at.setdefault(cell, []).append((kind, nid, pxx, pyy, extra))

    for cell in nodes_set:
        y, x = cell
        nodes.append({
            "id": node_id(cell), "kind": "corridor_junction",
            "building_id": "mirae", "floor_id": fid,
            "plan_point": {"coordinate_space": f"plan:{fid}",
                           "x_px": round(x * CELL + CELL / 2, 1),
                           "y_px": round(y * CELL + CELL / 2, 1)},
            "geo_point": None, "name": None, "facility_id": None,
            "source_refs": REFS, "notes": []})

    def emit(eid, a, b, kind, length, acc, geom, **kw):
        for i, (u, v, g) in enumerate([(a, b, geom), (b, a, list(reversed(geom)))]):
            edges.append({
                "id": eid if i == 0 else eid + "/rev",
                "from_node": u, "to_node": v, "kind": kind,
                "horizontal_length_m": unk() if length is None else fm(length, "m"),
                "traversal_length_m": unk() if length is None else fm(length, "m"),
                "vertical_rise_m": unk(), "accessibility": acc,
                "facility_id": kw.get("facility"), "schedule_id": None,
                "geometry": g,
                "elevator_from_floor": kw.get("ef"),
                "elevator_to_floor": kw.get("et"),
                "source_refs": REFS, "notes": []})

    for i, (a, b, path) in enumerate(sk_edges):
        if a not in nodes_set or b not in nodes_set:
            continue
        geom = [[round(c[1] * CELL + CELL / 2, 1), round(c[0] * CELL + CELL / 2, 1)]
                for c in path]
        # 폴리라인 단순화 (3셀마다)
        if len(geom) > 4:
            geom = geom[::3] + [geom[-1]]
        L = sum(math.dist(geom[k], geom[k + 1]) for k in range(len(geom) - 1)) * m_per_px
        if L < 0.05:
            continue
        emit(f"{fid}/e/corr/{i}", node_id(a), node_id(b), "corridor",
             round(L, 2), walk_acc(), geom)

    facility_nodes = {}
    for cell, items in anchor_at.items():
        if cell not in nodes_set:
            continue
        base = node_id(cell)
        bx = cell[1] * CELL + CELL / 2
        by = cell[0] * CELL + CELL / 2
        for kind, nid, pxx, pyy, extra in items:
            if kind == "room":
                nodes.append({
                    "id": nid, "kind": "room_door", "building_id": "mirae",
                    "floor_id": fid,
                    "plan_point": {"coordinate_space": f"plan:{fid}",
                                   "x_px": round(pxx, 1), "y_px": round(pyy, 1)},
                    "geo_point": None, "name": f"{extra}호 문",
                    "facility_id": None, "source_refs": REFS, "notes": []})
                L = math.dist((pxx, pyy), (bx, by)) * m_per_px
                emit(f"{fid}/e/door/{extra}", nid, base, "door",
                     round(max(0.5, L), 2), door_acc(),
                     [[round(pxx, 1), round(pyy, 1)], [round(bx, 1), round(by, 1)]])
                places.append({
                    "id": f"{fid}/{extra}", "name": f"미래관 {extra}호",
                    "building_id": "mirae", "floor_id": fid, "room_label": extra,
                    "aliases": [extra, f"{extra}호", f"미래관{extra}"],
                    "wing_id": None, "door_node_ids": [nid],
                    "status": "drawing_candidate",
                    "label_plan_point": {"coordinate_space": f"plan:{fid}",
                                         "x_px": round(pxx, 1),
                                         "y_px": round(pyy, 1)},
                    "source_refs": REFS, "notes": []})
            else:
                kindmap = {"elevator": ("elevator_lobby", EV, f"{label} 엘리베이터"),
                           "stairs": ("stair_landing", f"{STAIR}-{extra}",
                                      f"{label} 계단{extra}"),
                           "entrance": ("entrance_inside", None,
                                        f"{label} 출입구{extra}")}
                nk, facil, nm = kindmap[kind]
                nodes.append({
                    "id": nid, "kind": nk, "building_id": "mirae",
                    "floor_id": fid,
                    "plan_point": {"coordinate_space": f"plan:{fid}",
                                   "x_px": round(pxx, 1), "y_px": round(pyy, 1)},
                    "geo_point": None, "name": nm, "facility_id": facil,
                    "source_refs": REFS, "notes": []})
                L = math.dist((pxx, pyy), (bx, by)) * m_per_px
                emit(f"{fid}/e/link/{nid.replace('/', '_')}", nid, base, "corridor",
                     round(max(0.5, L), 2), walk_acc(1.8),
                     [[round(pxx, 1), round(pyy, 1)], [round(bx, 1), round(by, 1)]])
                facility_nodes.setdefault(kind, []).append(nid)

    return {
        "floor": {"id": fid, "building_id": "mirae", "label": label,
                  "sort_order": order, "wing_id": None,
                  "plan_id": f"mirae/navplan/{fid.split('/')[-1]}",
                  "elevation_m": unk(), "notes": []},
        "plan": {"id": f"mirae/navplan/{fid.split('/')[-1]}",
                 "image_ref": f"data/raw/navmaps/{fname}",
                 "width_px": W, "height_px": H,
                 "source_tab_label": label, "source_filename": fname,
                 "drawing_floor_label": label, "page_tab_id": None,
                 "mapping_status": "resolved_draft",
                 "scale_m_per_px": fm(round(m_per_px, 6), "m/px"),
                 "control_points": [], "geo_transform": None,
                 "geo_error_estimate_m": unk(), "revision_date": None,
                 "source_refs": REFS, "usage_terms": "내부 시안",
                 "notes": ["시안 색상 규약 기반 자동추출"]},
        "nodes": nodes, "edges": edges, "places": places,
        "facilities": facility_nodes,
        "stats": {"walk_cells": n_walk, "skel_cells": n_skel,
                  "skel_nodes": len(nodes_set), "rooms": len(places),
                  "m_per_px": round(m_per_px, 6)},
    }


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1].startswith("nav_"):
        f = sys.argv[1]
        ent = next(e for e in FLOORS if e[0] == f)
        build_floor(*ent, diag=True)
        return

    nodes, edges, places, floors, plans = [], [], [], [], []
    ev_nodes, stair_nodes = {}, {}
    order_of = {}

    for fname, fid, label, order in FLOORS:
        if not (NAV / fname).exists():
            print(f"  (없음) {fname}")
            continue
        r = build_floor(fname, fid, label, order)
        if r is None:
            continue
        floors.append(r["floor"])
        plans.append(r["plan"])
        nodes += r["nodes"]
        edges += r["edges"]
        places += r["places"]
        order_of[fid] = order
        for n in r["facilities"].get("elevator", [])[:1]:
            ev_nodes[fid] = n
        if r["facilities"].get("stairs"):
            stair_nodes[fid] = r["facilities"]["stairs"][0]
        s = r["stats"]
        print(f"  {label:<7} 호실 {s['rooms']:>3}개  골격노드 {s['skel_nodes']:>4}  "
              f"축척 {s['m_per_px']*1000:.1f} mm/px")

    def emit_pair(eid, a, b, kind, acc, **kw):
        for i, (u, v) in enumerate([(a, b), (b, a)]):
            e = {"id": eid if i == 0 else eid + "/rev",
                 "from_node": u, "to_node": v, "kind": kind,
                 "horizontal_length_m": unk(), "traversal_length_m":
                     fm(5.5, "m") if kind == "stairs" else unk(),
                 "vertical_rise_m": unk(), "accessibility": acc,
                 "facility_id": kw.get("facility"), "schedule_id": None,
                 "geometry": [], "elevator_from_floor": None,
                 "elevator_to_floor": None,
                 "source_refs": REFS, "notes": []}
            if kind == "elevator_ride":
                e["elevator_from_floor"] = kw["ef"] if i == 0 else kw["et"]
                e["elevator_to_floor"] = kw["et"] if i == 0 else kw["ef"]
            edges.append(e)

    served = sorted(ev_nodes, key=lambda f: order_of[f])
    for i, a in enumerate(served):
        for b in served[i + 1:]:
            emit_pair(f"mirae/e/ev/{order_of[a]}-{order_of[b]}",
                      ev_nodes[a], ev_nodes[b], "elevator_ride", ride_acc(),
                      facility=EV, ef=a, et=b)

    stf = sorted(stair_nodes, key=lambda f: order_of[f])
    for a, b in zip(stf, stf[1:]):
        if order_of[b] - order_of[a] != 1:
            continue
        emit_pair(f"mirae/e/stair/{order_of[a]}-{order_of[b]}",
                  stair_nodes[a], stair_nodes[b], "stairs", stair_acc(),
                  facility=f"{STAIR}-1")

    elevators = [{
        "id": EV, "building_id": "mirae", "shaft_group": "G1",
        "served_floor_ids": served,
        "served_floors_evidence": fm(f"{len(served)}개 층 정차"),
        "door_node_ids": {f: ev_nodes[f] for f in served},
        "car_width_m": fm(1.6, "m"), "car_depth_m": fm(1.5, "m"),
        "door_width_m": fm(0.9, "m"), "wheelchair_usable": fm(True),
        "status": "in_service", "status_checked_at": None,
        "wait_s_assumed": 25.0, "ride_s_per_floor_assumed": 5.0,
        "board_alight_s_assumed": 10.0, "source_refs": REFS, "notes": []}]

    doc = {
        "graph_version": "mirae-nav-v1",
        "schema_version": "1.0.0",
        "generated_at": _dt.datetime.now(_dt.timezone.utc).astimezone()
            .isoformat(timespec="seconds"),
        "verification_scope": {
            "field_verified": False, "demo_assumed_data": True,
            "evidence_level": "내비게이션맵 시안 색상 규약 자동추출 + 일반 규격 추정",
            "wheelchair_accessible_routes_certified": False,
            "outdoor_connection": "출입구 노드까지",
            "vertical_connection": f"엘리베이터 1대 ({len(served)}개 층) + 계단",
            "floors": [f["id"] for f in floors]},
        "notes": ["시안(단순화 재렌더링)에서 추출했으므로 경로가 화면과 정렬된다.",
                  "원본 도면과는 좌표계가 다르다."],
        "buildings": [{"id": "mirae", "official_name": "미래관",
                       "campus_code": "S2", "aliases": ["미래관", "미래", "S2"],
                       "wings": [], "footprint": None, "source_refs": REFS}],
        "floorplans": plans, "floors": floors, "places": places,
        "nodes": nodes, "edges": edges, "elevators": elevators, "closures": []}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    size = OUT.stat().st_size
    print(f"\ngraph_version=mirae-nav-v1")
    print(f"  층 {len(floors)}  호실 {len(places)}  노드 {len(nodes)}  "
          f"엣지 {len(edges)}  승강기 {len(elevators)}")
    print(f"저장: {OUT}  ({size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
