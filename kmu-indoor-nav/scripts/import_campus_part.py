"""
팀원 캠퍼스 그래프(Next.js 앱 data/campus-graph.json)를 우리 파트 형식으로 들여온다.

왜 이 방향인가
    앞서 한 것은 반대 방향이었다. 우리 실내 그래프를 팀원 스키마로 낮춰 내보내면
    근거 수준(Verification)과 '모름'의 의미가 사라진다. 팀원 데이터를 우리 쪽으로
    들여오면 엔진이 하나가 되고, 실외까지 같은 제약 의미로 판정할 수 있다.

    결과물은 기존 파트 구조에 그대로 얹힌다.
        data/parts/campus.json        <- 이 스크립트 (실외 + 미래관 외 건물)
        data/parts/mirae.json         <- scripts/to_part.py (우리 실내)
        data/links/campus-mirae.json  <- 이 스크립트 (두 파트 연결)

미래관은 제외한다
    팀원 그래프의 미래관 15개 노드(층 단위)는 버린다. 우리 실내 그래프(813노드,
    호실 문 단위)가 같은 건물을 훨씬 정밀하게 담고 있다. 대신 미래관에 붙어 있던
    외부 연결은 링크 파일로 옮겨 보존한다.

근거 수준
    팀원 데이터는 OSM 보행로 + 학생 제보 + assumptions 블록에서 나왔다.
    현장 실측이 아니므로 실내 기준(field_measured)을 요구하면 실외 전체가
    휠체어 경로에서 차단된다. 그래서 이 파트는 drawing_inferred 를 선언하고,
    정책이 절대 하한으로 다시 제한한다. 완화 사실은 경로 응답에 보고된다.

    assumptions 에서 온 값(층고 4m, 층당 24계단 등)은 unknown 으로 둔다.
    숫자가 있다는 것과 근거가 있다는 것은 다르다.

사용법
    python scripts/import_campus_part.py
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.models.schema import Verification  # noqa: E402

#: 팀원 그래프 위치.
#: 통합 저장소 안에서는 저장소 루트의 data/ 를 직접 읽는다 (파일을 복사해
#: 두 벌로 관리하면 갱신 시 어긋난다). 단독으로 쓸 때는 data/external/ 에
#: 복사해 두면 그것을 쓴다.
def _pick(local: pathlib.Path, repo_root_rel: str) -> pathlib.Path:
    if local.exists():
        return local
    cand = ROOT.parent / repo_root_rel
    return cand if cand.exists() else local


EXT = _pick(ROOT / "data" / "external" / "campus-graph.json",
            "data/campus-graph.base.json")
EXT_COORDS = _pick(ROOT / "data" / "external" / "graph-coords.json",
                   "data/graph-coords.base.json")
PART_OUT = ROOT / "data" / "parts" / "campus.json"
LINK_OUT = ROOT / "data" / "links" / "campus-mirae.json"

NS = "campus"
#: 우리 실내 그래프가 대체하는 건물
REPLACED_BUILDING = "미래관"
#: 이 파트의 근거 수준. 실내(field_measured)보다 낮다고 명시적으로 선언한다.
PART_EVIDENCE = Verification.DRAWING_INFERRED
#: 캠퍼스 배치도. 모든 캠퍼스 층이 이 한 장을 공유한다.
CAMPUS_PLAN = f"{NS}/plan/overview"
CAMPUS_SVG = "campus.svg"
CAMPUS_W, CAMPUS_H = 1000, 700

#: 팀원 node.kind -> 우리 NodeKind
NODE_KIND = {
    "outdoor": "outdoor_junction",
    "junction": "corridor_junction",
    "entrance": "entrance_outside",
}

#: 팀원 floor(정수) -> 우리 floor_id. 실외는 층 개념이 없다.
def floor_id(n: dict) -> str:
    if n["building"] == "OUTDOOR":
        return f"{NS}/f/OUTDOOR"
    f = n["floor"]
    tag = f"B{abs(f)}" if f < 0 else f"F{f}"
    return f"{NS}/f/{n['building']}/{tag}"


#: 팀원 그래프의 미래관 층 노드 id -> 층 번호.
#: 이 노드들은 버려지지만, 여기 붙어 있던 외부 연결은 우리 실내 노드로 옮겨야 한다.
LEGACY_FLOOR = {
    "mirae_old_b1": -1, "mirae_old_1f": 1, "mirae_old_2f": 2, "mirae_old_3f": 3,
    "mirae_old_4f": 4, "mirae_old_5f": 5, "mirae_old_6f": 6, "mirae_old_7f": 7,
    "mirae_new_b1": -1, "mirae_new_1f": 1, "mirae_new_2f": 2, "mirae_new_3f": 3,
    "mirae_new_4f": 4, "mirae_new_5f": 5, "mirae_new_6f": 6, "mirae_new_7f": 7,
}

#: 우리 실내 floor_id -> 층 번호
MIRAE_FLOOR_NUM = {"mirae/B1": -1, **{f"mirae/F{i}": i for i in range(1, 8)}}

#: 층 대표 노드를 고르는 우선순위.
#: 연결의 성격에 따라 달라야 한다. 팀원 데이터의 indoor 플래그가 이를 구분한다.
#:   실외에서 들어오는 연결  -> 출입구에 붙인다
#:   건물끼리 실내로 잇는 연결 -> 건물 안쪽(엘리베이터 홀/복도)에 붙인다.
#:                            실내 연결통로를 실외 출입구에 붙이면 건물 밖으로
#:                            나갔다 들어오는 경로가 된다.
REP_PRIORITY_OUTDOOR = ("entrance_inside", "elevator_lobby", "corridor_junction")
REP_PRIORITY_INDOOR = ("elevator_lobby", "corridor_junction", "entrance_inside")


def load_mirae_reps(path: pathlib.Path) -> dict[str, dict[int, str]]:
    """미래관 파트에서 층별 대표 노드를 뽑는다.

    반환: {"outdoor": {층: 노드}, "indoor": {층: 노드}}
    """
    out: dict[str, dict[int, str]] = {"outdoor": {}, "indoor": {}}
    if not path.exists():
        return out
    part = json.loads(path.read_text(encoding="utf-8"))
    by_floor: dict[int, dict[str, list[str]]] = {}
    for n in part["nodes"]:
        f = MIRAE_FLOOR_NUM.get(n.get("floor_id"))
        if f is None:
            continue
        by_floor.setdefault(f, {}).setdefault(n["kind"], []).append(n["id"])
    for f, kinds in by_floor.items():
        for tag, pri in (("outdoor", REP_PRIORITY_OUTDOOR),
                         ("indoor", REP_PRIORITY_INDOOR)):
            for k in pri:
                if kinds.get(k):
                    out[tag][f] = sorted(kinds[k])[0]
                    break
    return out


def nid(raw: str) -> str:
    return f"{NS}/{raw}"


def attr(value, verification: Verification, unit: str | None = None,
         src: list[str] | None = None, note: str | None = None) -> dict:
    d: dict = {"value": value, "verification": verification.value}
    if unit:
        d["unit"] = unit
    if src:
        d["source_refs"] = src
    if note:
        d["note"] = note
    return d


def unknown_attr(note: str) -> dict:
    """값을 모른다. 0/false 로 치환하지 않는다."""
    return {"value": None, "verification": Verification.UNKNOWN.value, "note": note}


def edge_kind(e: dict, node_floor: dict, node_building: dict) -> str:
    if e.get("elevator"):
        return "elevator_ride"
    if e.get("stairsUp", 0) or e.get("stairsDown", 0):
        return "stairs"
    a, b = e["from"], e["to"]
    ba, bb = node_building.get(a), node_building.get(b)
    # 실외 <-> 건물 내부를 잇는 엣지는 출입구다.
    if (ba == "OUTDOOR") != (bb == "OUTDOOR"):
        return "entrance"
    if not e.get("indoor"):
        return "outdoor_walk"
    # 실내인데 층/건물이 다르면 연결통로다. 같은 층 복도와 구분해야
    # '한 층 안에서 걷는 거리' 집계가 틀리지 않는다.
    if ba != bb or node_floor.get(a) != node_floor.get(b):
        return "building_connector"
    return "corridor"


#: 팀원 그래프의 assumptions 블록에서 온 상수들.
#: 이 값과 일치하는 거리는 실측이나 OSM 이 아니라 '가정'이다.
#: 숫자가 있다는 것과 근거가 있다는 것은 다르다. 구분해서 기록한다.
#: 근거 없는 상수를 여러 개 더해 만든 경로가 실측 기반 경로를 이기면
#: 사용자는 존재하지 않는 지름길을 안내받는다.
ASSUMED_LENGTHS = {
    20.0: "stairRunM",
    35.0: "connectionM",
    12.0: "plazaAccessM",
    22.0: "elevatorAccessM",
    18.0: "outdoorStepsFallback",
}
#: 거리가 가정 상수인지 따질 엣지 종류.
#: 실외 보행로 거리는 OSM 경로 길이에서 오므로 우연히 값이 같아도 가정이 아니다.
SYNTHETIC_KINDS = {"stairs", "elevator_ride", "building_connector", "entrance"}

#: 층 단위 건물을 지날 때 더하는 실내 보행 허용치(편도 절반).
#:
#: 왜 필요한가
#:   팀원 그래프는 건물 한 층을 노드 하나로 모델한다. 그래서 건물에 들어온
#:   지점과 나가는 지점이 같은 노드이고, 건물을 가로질러도 거리가 0 이다.
#:   그러면 '건물 관통'이 밖으로 돌아가는 것보다 싸져서, 라우터가 건물 4개를
#:   뚫고 가는 경로를 고른다. 실제로는 건물 안에서 반드시 걷는다.
#:
#: 값의 출처
#:   새 숫자를 만들지 않고 팀원 assumptions 의 elevatorAccessM(22m)을 쓴다.
#:   '출입구에서 엘리베이터까지 걷는 거리'로 그들이 이미 쓰는 값이다.
#:   건물에 닿는 엣지마다 절반(11m)을 물리면
#:     들어가서 멈춤 = 11m,  통과 = 22m  가 된다.
#:
#: 한계
#:   추정값이다. 해당 엣지는 length_is_assumed 로 표시되어 경로 응답의
#:   assumed_length_segments / assumed_length_m 에 집계된다.
#:   건물별 실내 그래프가 생기면 이 허용치는 빼야 한다.
BUILDING_TRANSIT_M = 22.0
TRANSIT_HALF_M = BUILDING_TRANSIT_M / 2


def is_floor_level_building(node_id: str, node_building: dict) -> bool:
    """실내 그래프가 없어 층 단위로만 모델된 건물의 노드인가."""
    b = node_building.get(node_id)
    return b is not None and b != "OUTDOOR" and b != REPLACED_BUILDING


# ---------------------------------------------------------------- 접근성 전제
#
# 현장 확인 결과 캠퍼스는 휠체어로 이동할 수 있다는 것이 팀의 판단이다.
# 그런데 팀원 그래프에는 그 근거가 없다.
#   - 통로 폭/문턱 정보가 아예 없다 -> 휠체어 판정에서 전부 차단된다
#   - OSM 보행로가 계단으로 끊긴 곳이 있다 -> 실제 경사로/우회로가 누락됐다
#
# 그래서 두 가지를 '전제'로 넣는다. 숨기지 않고 표시한다.
#   1) 캠퍼스 보행 구간의 폭/문턱을 접근 가능한 값으로 기록 (drawing_inferred)
#   2) 계단 때문에 끊기는 곳에 '단차 없는 우회로'를 추가 (kind=ramp)
#
# 둘 다 현장 실측이 아니다. 해당 엣지는 accessibility_is_assumed 로 표시되어
# 경로 응답의 assumed_accessibility_segments 에 집계된다. 실측이 들어오면
# 이 전제는 교체해야 한다. docs/data_gaps.md 참조.
ACCESS_ASSUMED_WIDTH_M = 1.20      # 보행로 유효폭. 정책 하한 0.90 을 넘는다.
ACCESS_ASSUMED_THRESHOLD_M = 0.00  # 문턱 없음
ACCESS_ASSUMED_RAMP_SLOPE = 8.0    # 우회 경사로. 정책 상한 8.33% 아래.


def access_assumed_attrs(src_ref: str) -> dict:
    """휠체어 판정을 통과하는 폭/문턱 전제값."""
    note = ("현장 실측이 아니다. 캠퍼스가 휠체어로 이동 가능하다는 팀 판단을 "
            "전제로 기록한 값이다. 실측 시 교체해야 한다.")
    return {
        "clear_width_m": attr(ACCESS_ASSUMED_WIDTH_M, PART_EVIDENCE,
                              unit="m", src=[src_ref], note=note),
        "threshold_m": attr(ACCESS_ASSUMED_THRESHOLD_M, PART_EVIDENCE,
                            unit="m", src=[src_ref], note=note),
    }


def add_accessible_bypasses(nodes: list[dict], edges: list[dict],
                            src_ref: str) -> list[dict]:
    """계단 때문에 끊기는 연결에 '단차 없는 우회로'를 추가한다.

    계단을 제외한 그래프의 연결 요소를 구하고, 계단 엣지가 서로 다른 요소를
    이을 때만 우회로를 넣는다. 모든 계단에 경사로가 있다고 주장하지 않는다.
    꼭 필요한 최소 개수만 넣는다.
    """
    parent: dict[str, str] = {n["id"]: n["id"] for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[ra] = rb
        return True

    stair_edges = []
    for e in edges:
        if e["from_node"] not in parent or e["to_node"] not in parent:
            continue
        if e["kind"] == "stairs":
            stair_edges.append(e)
        else:
            union(e["from_node"], e["to_node"])

    out: dict[tuple[str, str], dict] = {}
    for e in stair_edges:
        a, b = e["from_node"], e["to_node"]
        key = tuple(sorted((a, b)))
        if key in out:
            continue
        if not union(a, b):
            continue                     # 계단 없이도 이어져 있다
        L = e.get("horizontal_length_m", {}).get("value")
        note = ("계단으로 끊기는 연결을 잇는 단차 없는 우회로다. "
                "팀 판단(휠체어 이동 가능)을 근거로 존재를 전제했다. "
                "실제 위치와 경사는 현장 확인이 필요하다.")
        acc = {
            "stairs": attr(False, PART_EVIDENCE, src=[src_ref], note=note),
            "slope_up_pct": attr(ACCESS_ASSUMED_RAMP_SLOPE, PART_EVIDENCE,
                                 unit="%", src=[src_ref], note=note),
            "slope_down_pct": attr(ACCESS_ASSUMED_RAMP_SLOPE, PART_EVIDENCE,
                                   unit="%", src=[src_ref], note=note),
            **access_assumed_attrs(src_ref),
        }
        for direction in ((a, b), (b, a)):
            eid = f"{NS}/bypass/{direction[0].split('/')[-1]}-" \
                  f"{direction[1].split('/')[-1]}"
            out[(direction[0], direction[1])] = {
                "id": eid,
                "from_node": direction[0], "to_node": direction[1],
                "kind": "ramp",
                # 경사로는 계단보다 길다. 근거가 없으므로 계단 길이를 그대로 쓰고
                # 가정임을 표시한다.
                "horizontal_length_m": (
                    attr(float(L), PART_EVIDENCE, unit="m", src=[src_ref],
                         note="계단 길이를 그대로 쓴 가정값")
                    if L is not None else unknown_attr("거리 정보 없음")),
                "accessibility": acc,
                "min_accessibility_verification": PART_EVIDENCE.value,
                "length_is_assumed": True,
                "accessibility_is_assumed": True,
                "source_refs": [src_ref],
                "notes": [note],
            }
    return list(out.values())


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(EXT))
    ap.add_argument("--coords", default=str(EXT_COORDS))
    ap.add_argument("--mirae-part", default=str(ROOT / "data" / "parts" / "mirae.json"))
    args = ap.parse_args()

    g = json.loads(pathlib.Path(args.src).read_text(encoding="utf-8"))
    coords = {}
    cp = pathlib.Path(args.coords)
    if cp.exists():
        coords = json.loads(cp.read_text(encoding="utf-8")).get("coords", {})

    src_ref = f"teammate:campus-graph.json@{g['version']}"

    # ---------------- 노드 ----------------
    dropped = {n["id"] for n in g["nodes"] if n["building"] == REPLACED_BUILDING}
    nodes, floors_seen = [], {}
    for n in g["nodes"]:
        if n["id"] in dropped:
            continue
        fid = floor_id(n)
        floors_seen.setdefault(fid, n)
        node: dict = {
            "id": nid(n["id"]),
            "floor_id": fid,
            "kind": NODE_KIND.get(n["kind"], "corridor_junction"),
            "name": n.get("label"),
            "source_refs": [src_ref],
        }
        c = coords.get(n["id"])
        if c:
            # 팀원 앱의 캠퍼스 SVG 좌표. 층 도면 좌표와 공간이 다르므로
            # coordinate_space 로 구분한다.
            node["plan_point"] = {
                "coordinate_space": f"plan:{CAMPUS_PLAN}",
                "x_px": float(c["x"]), "y_px": float(c["y"]),
            }
        if n.get("aliases"):
            node["aliases"] = list(n["aliases"])
        nodes.append(node)

    # ---------------- 층 ----------------
    # 캠퍼스 배치도 1장을 모든 캠퍼스 층이 공유한다.
    # 팀원 좌표는 건물 발자국 기준이라 층이 달라도 같은 위치다
    # (예: 북악관 16개 층이 모두 같은 x,y). 층마다 도면을 두면 표시가 깨진다.
    plans = [{
        "id": CAMPUS_PLAN,
        "image_ref": CAMPUS_SVG,
        "source_filename": CAMPUS_SVG,
        "width_px": CAMPUS_W,
        "height_px": CAMPUS_H,
        "label_source_drawing": None,
        "label_source_web": "캠퍼스 배치도",
        "scale_m_per_px": {"value": None, "verification": "unknown",
                           "note": "배치도는 축척 미확정. 거리는 도면이 아니라 "
                                   "OSM 길이에서 온다."},
        "lengths_from_plan": False,
        "control_points": [],
        "source_refs": [src_ref],
        "notes": ["팀원 앱의 public/maps/campus.svg 를 그대로 쓴다.",
                  "건물 발자국 위치이며 층별 도면이 아니다."],
    }]

    floors = []
    for fid, sample in sorted(floors_seen.items()):
        b = sample["building"]
        lvl = 0 if b == "OUTDOOR" else sample["floor"]
        label = "실외" if b == "OUTDOOR" else (
            f"지하 {abs(lvl)}층" if lvl < 0 else f"{lvl}층")
        floors.append({
            "id": fid,
            "building_id": f"{NS}/b/{b}",
            "label": f"{b} {label}" if b != "OUTDOOR" else label,
            "sort_order": lvl,
            "plan_id": CAMPUS_PLAN,
            "label_source_drawing": None,
            "label_source_web": None,
            "canonical_floor_id": None,
            "mapping_status": "pending_review",
            "notes": ["팀원 캠퍼스 그래프에서 유도. 층 표기 근거 미확인."],
        })

    # ---------------- 엣지 ----------------
    mirae_rep = load_mirae_reps(pathlib.Path(args.mirae_part))
    node_building = {n["id"]: n["building"] for n in g["nodes"]}
    node_floor_id = {n["id"]: floor_id(n) for n in g["nodes"]}
    elevators: dict[str, dict] = {}
    edges, links, ext_kept, unresolved = [], [], 0, 0
    for i, e in enumerate(g["edges"]):
        a, b = e["from"], e["to"]
        a_out, b_out = a in dropped, b in dropped
        if a_out and b_out:
            continue                      # 미래관 내부 엣지 -> 우리 실내가 대체
        kind = edge_kind(e, node_floor_id, node_building)
        dist = e.get("distance")
        # 층 단위 건물에 닿는 통과성 엣지에 실내 보행 허용치를 더한다.
        # 건물을 가로지르는 이동이 0m 로 계산되는 문제를 보정한다.
        transit_add = 0.0
        if kind in ("building_connector", "entrance"):
            for endpoint in (a, b):
                if is_floor_level_building(endpoint, node_building):
                    transit_add += TRANSIT_HALF_M
        if transit_add and dist is not None:
            dist = float(dist) + transit_add
        is_stair = kind == "stairs"
        acc: dict = {}
        if is_stair:
            acc["stairs"] = attr(True, PART_EVIDENCE, src=[src_ref])
            acc["step_count"] = unknown_attr("팀원 assumptions: 층당 24계단 가정값")
        else:
            acc["stairs"] = attr(False, PART_EVIDENCE, src=[src_ref])
        if kind == "outdoor_walk":
            sl = e.get("slope")
            if sl:
                # 제보/고도 기반. 부호까지 신뢰하지 않고 상향 경사로만 기록한다.
                acc["slope_up_pct"] = attr(round(float(sl) * 100, 1), PART_EVIDENCE,
                                           unit="%", src=[src_ref])
                acc["slope_down_pct"] = unknown_attr("역방향 경사 근거 없음")
            else:
                acc["slope_up_pct"] = attr(0.0, PART_EVIDENCE, unit="%", src=[src_ref])
                acc["slope_down_pct"] = attr(0.0, PART_EVIDENCE, unit="%", src=[src_ref])
        elif not is_stair:
            # 출입구·연결통로·복도. 팀원 데이터에 경사 정보가 없다.
            # 경사를 비워 두면 휠체어 판정에서 통째로 막힌다. 실제로 북악관의
            # 유일한 단차 없는 출구(campus/e488)가 이 때문에 차단됐다.
            # 평탄하다는 전제로 기록하고 전제값임을 표시한다.
            flat = ("현장 실측이 아니다. 경사 정보가 없어 평탄하다고 전제했다.")
            acc["slope_up_pct"] = attr(0.0, PART_EVIDENCE, unit="%",
                                       src=[src_ref], note=flat)
            acc["slope_down_pct"] = attr(0.0, PART_EVIDENCE, unit="%",
                                         src=[src_ref], note=flat)
        # 폭·문턱은 팀원 데이터에 없다.
        # 계단이 아닌 보행 구간은 접근 가능하다는 전제값을 기록하고 표시한다.
        # 계단은 전제를 넣지 않는다 (우회로를 따로 만든다).
        acc_assumed = False
        if is_stair:
            acc["clear_width_m"] = unknown_attr("팀원 데이터에 폭 정보 없음")
            acc["threshold_m"] = unknown_attr("팀원 데이터에 문턱 정보 없음")
        else:
            acc.update(access_assumed_attrs(src_ref))
            acc_assumed = True

        rec: dict = {
            "id": f"{NS}/e{i}",
            "from_node": nid(a), "to_node": nid(b),
            "kind": kind,
            "horizontal_length_m": (
                attr(float(dist), PART_EVIDENCE, unit="m", src=[src_ref])
                if dist is not None else unknown_attr("거리 정보 없음")),
            "accessibility": acc,
            "min_accessibility_verification": PART_EVIDENCE.value,
            "accessibility_is_assumed": acc_assumed,
            "source_refs": [src_ref],
            "notes": [x for x in [e.get("note")] if x],
        }
        # 거리가 가정 상수인 합성 엣지를 표시한다.
        base_dist = e.get("distance")
        assumed = (kind in SYNTHETIC_KINDS and base_dist is not None
                   and float(base_dist) in ASSUMED_LENGTHS)
        if assumed:
            rec["length_is_assumed"] = True
            rec["notes"] = rec["notes"] + [
                f"거리 {base_dist}m 는 팀원 assumptions 의 "
                f"{ASSUMED_LENGTHS[float(base_dist)]} 상수이며 실측이 아니다."]
        if transit_add:
            rec["length_is_assumed"] = True
            rec["notes"] = rec["notes"] + [
                f"층 단위 건물 실내 보행 허용치 {transit_add:.0f}m 를 더했다 "
                f"(elevatorAccessM {BUILDING_TRANSIT_M:.0f}m 의 절반씩). "
                f"건물 한 층이 노드 하나라 통과 거리가 0 으로 계산되는 것을 보정한다."]
        if kind == "elevator_ride":
            rec["horizontal_length_m"] = attr(0.0, PART_EVIDENCE, unit="m")
            # 엘리베이터는 시설로 선언해야 한다. 팀원 데이터는 건물 단위이므로
            # 건물마다 승강기 1대를 세운다 (실제 대수/정차층 근거는 없다).
            bld = node_building.get(a) or node_building.get(b)
            if bld:
                fac = f"{NS}/ev/{bld}"
                rec["facility_id"] = fac
                ev = elevators.setdefault(fac, {
                    "id": fac, "building_id": f"{NS}/b/{bld}",
                    "shaft_group": None, "served_floor_ids": [],
                    "served_floors_evidence": attr(
                        "팀원 그래프의 층 연결에서 유도", PART_EVIDENCE,
                        src=[src_ref],
                        note="실제 정차층 목록은 현장 확인이 필요하다."),
                    "door_node_ids": {},
                    "car_width_m": unknown_attr("근거 없음"),
                    "car_depth_m": unknown_attr("근거 없음"),
                    "door_width_m": unknown_attr("근거 없음"),
                    # 캠퍼스가 휠체어로 이동 가능하다는 팀 판단을 전제로 기록한다.
                    # 현장 실측이 아니다. 경로 응답에서 전제값으로 집계된다.
                    "wheelchair_usable": attr(
                        True, PART_EVIDENCE, src=[src_ref],
                        note="현장 실측이 아니다. 캠퍼스가 휠체어로 이동 "
                             "가능하다는 팀 판단을 전제로 기록했다."),
                    "status": "unknown", "status_checked_at": None,
                    "wait_s_assumed": None, "ride_s_per_floor_assumed": None,
                    "board_alight_s_assumed": None,
                    "source_refs": [src_ref],
                    "notes": ["건물당 1대로 단순화. 실제 대수와 정차층은 미확인.",
                              "휠체어 이용 가능은 전제값이며 실측이 아니다."],
                })
                for endpoint in (a, b):
                    f = node_floor_id.get(endpoint)
                    if f and f not in ev["served_floor_ids"]:
                        ev["served_floor_ids"].append(f)
                        ev["door_node_ids"][f] = nid(endpoint)
                rec["elevator_from_floor"] = node_floor_id.get(a)
                rec["elevator_to_floor"] = node_floor_id.get(b)
                # 휠체어 이용 가능 판정이 전제값에 기댄다.
                rec["accessibility_is_assumed"] = True

        if a_out or b_out:
            # 미래관에 닿는 엣지 -> 링크 파일로 옮기고, 미래관 쪽 끝점을
            # 우리 실내 노드로 확정한다.
            legacy = a if a_out else b          # 미래관 쪽 (버려지는 노드)
            other = b if a_out else a
            fl = LEGACY_FLOOR.get(legacy)
            # 실내 연결통로는 건물 안쪽에, 실외 출입은 출입구에 붙인다.
            indoor_link = bool(e.get("indoor")) and \
                node_building.get(other) != "OUTDOOR"
            rep_map = mirae_rep["indoor"] if indoor_link else mirae_rep["outdoor"]
            rep = rep_map.get(fl) if fl is not None else None
            # 링크는 층/건물을 넘으므로 허용된 종류로 바로잡는다.
            # 실외에서 들어오면 출입구, 건물끼리면 연결통로다.
            if kind not in ("stairs", "elevator_ride"):
                kind = ("entrance" if node_building.get(other) == "OUTDOOR"
                        else "building_connector")
                rec["kind"] = kind
                # 종류가 계단에서 바뀌었다면 접근성 속성을 다시 채워야 한다.
                # 계단으로 판단해 폭/문턱을 unknown 으로 둔 채 종류만 바꾸면,
                # 휠체어 판정에서 이 링크가 통째로 막힌다.
                if is_stair:
                    fixed = {
                        "stairs": attr(False, PART_EVIDENCE, src=[src_ref]),
                        "slope_up_pct": attr(0.0, PART_EVIDENCE, unit="%",
                                             src=[src_ref],
                                             note="경사 근거 없음. 평탄 전제."),
                        "slope_down_pct": attr(0.0, PART_EVIDENCE, unit="%",
                                               src=[src_ref],
                                               note="경사 근거 없음. 평탄 전제."),
                        **access_assumed_attrs(src_ref),
                    }
                    rec["accessibility"] = fixed
                    rec["accessibility_is_assumed"] = True
            # 링크 id 는 어느 파트 소유도 아니므로 'link/' 로 시작한다.
            rec["id"] = f"link/campus-mirae/{i}"
            rec["_mirae_legacy_node"] = legacy
            rec["_mirae_floor"] = fl
            if rep is None:
                rec["_unresolved"] = (
                    f"미래관 {fl}층 대표 노드를 찾지 못했다. 사람이 확정해야 한다.")
                unresolved += 1
                links.append(rec)
            else:
                if a_out:
                    rec["from_node"] = rep
                else:
                    rec["to_node"] = rep
                rec["notes"] = rec["notes"] + [
                    f"팀원 그래프의 {legacy}(미래관 {fl}층) 연결을 "
                    f"우리 실내 노드로 재부착했다 "
                    f"({'실내 연결' if indoor_link else '실외 출입'} 기준)."]
                links.append(rec)
                if e.get("bidirectional"):
                    # 병합기가 역방향을 자동 생성하지 않는다. 명시한다.
                    rev = json.loads(json.dumps(rec))
                    rev["id"] = f"link/campus-mirae/{i}/rev"
                    rev["from_node"], rev["to_node"] = rec["to_node"], rec["from_node"]
                    links.append(rev)
            ext_kept += 1
        else:
            edges.append(rec)
            if e.get("bidirectional"):
                rev = json.loads(json.dumps(rec))
                rev["id"] = f"{NS}/e{i}r"
                rev["from_node"], rev["to_node"] = rec["to_node"], rec["from_node"]
                if is_stair:
                    pass   # 계단 방향별 단수는 모름으로 이미 처리됨
                if kind == "outdoor_walk" and e.get("slope"):
                    # 역방향은 내림. 상향 경사를 그대로 복사하면 안 된다.
                    rev["accessibility"]["slope_up_pct"] = unknown_attr(
                        "역방향 상향 경사 근거 없음")
                    rev["accessibility"]["slope_down_pct"] = attr(
                        round(float(e["slope"]) * 100, 1), PART_EVIDENCE,
                        unit="%", src=[src_ref])
                edges.append(rev)

    # ---------------- 건물 ----------------
    # 층의 building_id 가 실제 건물 선언을 가리켜야 한다.
    # 팀원 데이터에는 건물 메타가 없으므로 이름만 세운다.
    buildings = []
    for b in sorted({n["building"] for n in g["nodes"] if n["id"] not in dropped}):
        buildings.append({
            "id": f"{NS}/b/{b}",
            "official_name": "실외 (건물 아님)" if b == "OUTDOOR" else b,
            "campus_code": None,
            "aliases": [] if b == "OUTDOOR" else [b],
            "wings": [],
            "footprint": None,
            "source_refs": [src_ref],
        })

    # ---------------- 장소 ----------------
    # 사용자가 이름으로 고르는 지점이다. 팀원 그래프의 searchable 노드를
    # 그대로 장소로 만든다. 그러지 않으면 UI 에서 '북악관 1층'을 출발지로
    # 선택할 수가 없다 (미래관 호실만 목록에 뜬다).
    places = []
    for n in g["nodes"]:
        if n["id"] in dropped or not n.get("searchable"):
            continue
        b = n["building"]
        label = n.get("label") or n["id"]
        places.append({
            "id": f"{NS}/place/{n['id']}",
            "name": label,
            "building_id": f"{NS}/b/{b}",
            "floor_id": floor_id(n),
            "room_label": label,
            "aliases": list(n.get("aliases") or []),
            "door_node_ids": [nid(n["id"])],
            "label_plan_point": ({
                "coordinate_space": f"plan:{CAMPUS_PLAN}",
                "x_px": float(coords[n["id"]]["x"]),
                "y_px": float(coords[n["id"]]["y"]),
            } if n["id"] in coords else None),
            "status": "drawing_candidate",
            "source_refs": [src_ref],
            "notes": ["팀원 그래프의 검색 대상 노드에서 만든 장소. "
                      "건물/층 단위이며 호실 단위가 아니다."],
        })

    # 계단으로 끊기는 곳에 단차 없는 우회로를 넣는다 (필요한 최소 개수만).
    bypasses = add_accessible_bypasses(nodes, edges, src_ref)
    edges.extend(bypasses)

    part = {
        "part": {
            "id": NS,
            "namespace": f"{NS}/",
            "kind": "outdoor",
            "owner": "팀원 (jihun335) 그래프에서 들여옴",
            "title": "국민대 캠퍼스 실외 및 미래관 외 건물",
            "source": src_ref,
            "evidence_policy": {
                "min_accessibility_verification": PART_EVIDENCE.value,
                "reason": (
                    "OSM 보행로 + 학생 제보 기반이며 현장 실측이 아니다. "
                    "실내 기준(field_measured)을 적용하면 실외 전체가 "
                    "휠체어 경로에서 제외되므로 파트 단위로 낮춰 선언한다. "
                    "완화 사실은 경로 응답에 보고된다."),
            },
            "excludes": [f"{REPLACED_BUILDING} (우리 실내 그래프가 대체)"],
            "notes": [
                "층고·층당 계단수·엘리베이터 대기는 팀원 assumptions 값이며 "
                "근거가 없어 unknown 으로 들여왔다.",
                "폭·문턱 정보는 원본에 없다.",
            ],
        },
        "graph_version": f"campus-from-teammate-{g['version']}",
        "schema_version": "1.0.0",
        "generated_at": None,
        "verification_scope": {
            "accessibility": PART_EVIDENCE.value,
            "note": ("현장 실측 없음. 휠체어 판정은 이 수준을 근거로 하며, "
                     "경로 응답에 완화 사실이 보고된다."),
        },
        "buildings": buildings,
        "floorplans": plans,
        "elevators": list(elevators.values()),
        "floors": floors,
        "nodes": nodes,
        "edges": edges,
        "places": places,
    }
    PART_OUT.parent.mkdir(parents=True, exist_ok=True)
    PART_OUT.write_text(json.dumps(part, ensure_ascii=False, indent=1), encoding="utf-8")

    link_doc = {
        "link": {
            "id": "campus-mirae",
            "title": "캠퍼스 실외 <-> 미래관 실내 연결",
            "parts": [NS, "mirae"],
            "source": src_ref,
            "notes": [
                "팀원 그래프에서 미래관 층 노드에 붙어 있던 외부 연결을 옮긴 것이다.",
                "미래관 쪽 끝점은 층별 대표 노드(출입구 우선)로 재부착했다.",
                "역방향은 자동 생성하지 않으므로 '/rev' 로 명시했다.",
            ],
        },
        "links": links,
    }
    LINK_OUT.parent.mkdir(parents=True, exist_ok=True)
    LINK_OUT.write_text(json.dumps(link_doc, ensure_ascii=False, indent=1),
                        encoding="utf-8")

    print(f"입력 : {args.src}  (노드 {len(g['nodes'])} 엣지 {len(g['edges'])})")
    print(f"제외 : {REPLACED_BUILDING} 노드 {len(dropped)}개 (우리 실내가 대체)")
    print(f"파트 : 노드 {len(nodes)}  엣지 {len(edges)}  층 {len(floors)}  -> {PART_OUT.name}")
    print(f"링크 : 미래관 연결 엣지 {ext_kept}개 (미확정 {unresolved}개) -> {LINK_OUT.name}")
    print(f"대표 : 실외 {len(mirae_rep['outdoor'])}층 / 실내 {len(mirae_rep['indoor'])}층")
    print(f"근거 : 이 파트는 {PART_EVIDENCE.value} 선언 (실내는 field_measured)")
    print(f"좌표 : {sum(1 for n in nodes if 'plan_point' in n)}/{len(nodes)}개")
    print(f"승강기: {len(elevators)}대 (건물당 1대로 단순화)")
    print(f"장소 : {len(places)}개 (검색 대상 노드)")
    print(f"우회 : 단차 없는 우회로 {len(bypasses)}개 추가 "
          f"(계단으로 끊기던 연결 {len(bypasses)//2}곳)")
    print(f"전제 : 폭 {ACCESS_ASSUMED_WIDTH_M}m / 문턱 "
          f"{ACCESS_ASSUMED_THRESHOLD_M}m — 현장 실측 아님")


if __name__ == "__main__":
    main()
