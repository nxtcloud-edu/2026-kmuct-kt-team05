"""
P2-1/P2-2: 미래관 실내 그래프 빌더 (실제 공개 도면 판독 결과).

모든 좌표는 **원본 PNG 픽셀**이며 근거는 아래 판독 기록에 남긴다.
지리 좌표는 아직 없다 (정합 미수행).

판독 방법
---------
- 원본: data/raw/floorplans/Mirae_3F.png (1684x1191), 표제부 "지상3층 평면도 / 미래관"
- 확대 판독: scripts/crop_plan.py 로 좌표격자를 덧그린 사본을 만들어 읽음
- 호실 라벨 좌표: scripts/ocr_win.ps1 (Windows.Media.Ocr, ko) 결과와 대조
- 축척: 도면 자체의 통줄 치수선으로 산출 (아래 SCALE 주석 참고)

작성하지 않은 것 (중요)
-----------------------
- 벽을 관통하는 최근접 연결: 만들지 않음
- 엘리베이터: 도면에서 기호를 확정하지 못했으므로 **생성하지 않음**
- 3층 계단 <-> 복도 연결: 계단실 북측 벽의 점선 요소를 판독하지 못해 **연결하지 않음**
- 실외 연결: 확인된 외부 지점이 없어 **연결하지 않음**
- 원본상 2층(202호) <-> 3층: 같은 승강기/실제 정차층 근거가 없어 **연결하지 않음**

사용법
    python scripts/build_indoor.py
결과
    data/published/mirae_indoor_v1.json
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "data" / "published" / "mirae_indoor_v1.json"
MANIFEST = ROOT / "data" / "sources" / "manifest.json"

GRAPH_VERSION = "mirae-indoor-v1"
SCHEMA_VERSION = "1.0.0"

# ---------------------------------------------------------------- 축척
# 수평: 그리드축 ①(x=139.0px) -> ⑯(x=1412.0px) = 1273.0px,
#       도면 치수 ①->⑰ 139550mm 중 ⑯->⑰ 11200mm 를 뺀 128350mm
#       => 100.83 mm/px   (①②,②⑤,⑤⑥,⑥⑦ ... 13개 부분구간 모두 99~102 범위)
# 수직: 그리드축 H(y=253.5px) -> A(y=759.4px) = 505.9px, 치수 50100mm
#       => 99.03 mm/px
# 두 값의 차이 1.8% 를 불확실성으로 명시하고 0.1008 m/px 를 채택한다.
SCALE_M_PER_PX = 0.1008
SCALE_UNCERTAINTY_PCT = 2.0

SRC_3F = "source:manifest#mirae/Mirae_3F.png"
SRC_B22 = "source:manifest#mirae/Mirae_B2_2.png"
READ_3F = "reading:2026-09-20/Mirae_3F/crop+grid"
READ_B22 = "reading:2026-09-20/Mirae_B2_2/crop+grid"
OCR_3F = "ocr:2026-09-20/Mirae_3F/windows-media-ocr-ko"
OCR_B22 = "ocr:2026-09-20/Mirae_B2_2/windows-media-ocr-ko"

DRAW = "drawing_read"
INFER = "drawing_inferred"

# ---------------------------------------------------------------- 3층 판독값
# 복도: 북측 실열 남벽 y=331.5 ~ 중앙실열 북벽 y=362.3  (폭 30.8px = 3.10m)
CORRIDOR_Y = 346.9
WALL_Y = 331.5
MID_WALL_Y = 362.3
CORRIDOR_BAND_PX = MID_WALL_Y - WALL_Y

# 338호: bbox x 903.0..1022.0, y 251.9..331.5. 남벽에 문 2개.
D338_W_X, D338_E_X = 918.8, 1014.8
D338_W_OPEN = (913.8, 923.8)
D338_E_OPEN = (1009.5, 1020.0)
# 337호: bbox x 1083.3..1200.8, y 251.9..331.5. 남벽에 문 2개.
D337_W_X, D337_E_X = 1091.3, 1185.0
D337_W_OPEN = (1086.3, 1096.3)
D337_E_OPEN = (1180.0, 1190.0)

# 338과 337 사이 코어 x 1022.0..1083.3 = 화장실 (계단/승강기 아님).
# 대변기 칸과 중앙 세면대를 고배율에서 확인. 통과 동선으로 쓰지 않는다.
WC_X0, WC_X1 = 1022.0, 1083.3

# 3층 계단실: x 1026.6..1076.6, y 361.9..~420. 2개 계단참 + 중간참.
# 북측 벽에 점선 요소(방화셔터 추정)만 있고 문 호선을 판독하지 못했다.
STAIR_3F = {"x0": 1026.6, "x1": 1076.6, "y0": 361.9, "y1": 420.0}

# 원본상 2층(Mirae_B2_2.png) 202호: 북벽 y=589.4, 동벽 x=358.3,
# 서측은 사선벽 (296.7,588.9)-(266.7,671.1). 동벽 문 중심 (358.3, 596.7).
D202_X, D202_Y = 358.3, 596.7
CORRIDOR_2F_X = 367.0     # 202 동벽과 203/204 서벽 사이 복도 중심 (판독 개략)


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def attr(value, unit=None, verification=DRAW, refs=(), note=None):
    d = {"value": value, "verification": verification}
    if unit:
        d["unit"] = unit
    if refs:
        d["source_refs"] = list(refs)
    if note:
        d["note"] = note
    return d


def unknown(note=None):
    d = {"value": None, "verification": "unknown"}
    if note:
        d["note"] = note
    return d


def px(a, b) -> float:
    """픽셀 거리 -> 미터."""
    return round(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 * SCALE_M_PER_PX, 2)


# ---------------------------------------------------------------- 접근성 블록
def acc_corridor(width_px: float, refs) -> dict:
    """실내 복도. 도면에서 읽을 수 있는 것만 채우고 나머지는 unknown 유지."""
    return {
        # 계단 아님: 도면에서 판독 가능
        "stairs": attr(False, verification=DRAW, refs=refs),
        "step_count": unknown("계단 아님"),
        # 실내 복도가 평지라고 가정하지 않는다. 단차/경사는 현장 확인 항목.
        "slope_up_pct": unknown("도면으로 판정 불가. 현장 확인 필요"),
        "slope_down_pct": unknown("도면으로 판정 불가. 현장 확인 필요"),
        "cross_slope_pct": unknown("도면으로 판정 불가"),
        # 벽-벽 사이 폭이며 유효폭(가구/게시대/소화기 등 제외)이 아니다.
        "clear_width_m": attr(round(width_px * SCALE_M_PER_PX, 2), "m",
                              verification=DRAW, refs=refs,
                              note="벽-벽 이격. 유효폭 아님. 현장 실측 필요"),
        "threshold_m": unknown("도면으로 판정 불가"),
        "surface": unknown("도면으로 판정 불가"),
        "door_operability": unknown("복도 구간"),
        "wheelchair_usable": unknown("필수 속성 미확인"),
    }


def acc_door(open_px: tuple[float, float], refs) -> dict:
    w = round((open_px[1] - open_px[0]) * SCALE_M_PER_PX, 2)
    return {
        "stairs": attr(False, verification=DRAW, refs=refs),
        "step_count": unknown("계단 아님"),
        "slope_up_pct": unknown("도면으로 판정 불가"),
        "slope_down_pct": unknown("도면으로 판정 불가"),
        "cross_slope_pct": unknown(),
        "clear_width_m": attr(w, "m", verification=DRAW, refs=refs,
                              note="도면상 개구부 폭. 문짝/손잡이 제외한 유효폭 아님"),
        "threshold_m": unknown("문턱 유무를 도면으로 판정 불가. 현장 확인 필요"),
        "surface": unknown(),
        "door_operability": unknown("수동/자동, 개폐력 미확인"),
        "wheelchair_usable": unknown("필수 속성 미확인"),
    }


def acc_stairs(refs) -> dict:
    return {
        "stairs": attr(True, verification=DRAW, refs=refs),
        "step_count": unknown("도면에서 단수를 계수하지 않았다"),
        "slope_up_pct": unknown("계단 - 보행경사 지표 비적용"),
        "slope_down_pct": unknown("계단 - 보행경사 지표 비적용"),
        "cross_slope_pct": unknown(),
        "clear_width_m": unknown("계단 유효폭 미판독"),
        "threshold_m": unknown(),
        "surface": unknown(),
        "door_operability": unknown(),
        "wheelchair_usable": attr(False, verification=DRAW, refs=refs,
                                  note="계단이므로 휠체어 통행 불가"),
    }


def node(nid, kind, floor, x, y, name=None, facility=None, refs=(), notes=()):
    return {
        "id": nid, "kind": kind, "building_id": "mirae", "floor_id": floor,
        "plan_point": {"coordinate_space": f"plan:{floor}", "x_px": round(x, 2),
                       "y_px": round(y, 2)},
        "geo_point": None, "name": name, "facility_id": facility,
        "source_refs": list(refs), "notes": list(notes),
    }


def edge(eid, a, b, kind, length_m, accessibility, geometry=None, refs=(),
         notes=(), both=True, facility=None):
    def one(i, u, v):
        return {
            "id": i, "from_node": u, "to_node": v, "kind": kind,
            "horizontal_length_m": (unknown() if length_m is None
                                    else attr(length_m, "m", DRAW, refs,
                                              note=f"도면 축척 {SCALE_M_PER_PX} m/px "
                                                   f"(불확실성 ±{SCALE_UNCERTAINTY_PCT}%)")),
            "traversal_length_m": (unknown() if length_m is None
                                   else attr(length_m, "m", DRAW, refs)),
            "vertical_rise_m": unknown(),
            "accessibility": accessibility, "facility_id": facility,
            "schedule_id": None, "geometry": geometry or [],
            "elevator_from_floor": None, "elevator_to_floor": None,
            "source_refs": list(refs), "notes": list(notes),
        }
    out = [one(eid, a, b)]
    if both:
        out.append(one(eid + "/rev", b, a))
    return out


def main() -> None:
    with MANIFEST.open(encoding="utf-8") as fh:
        man = json.load(fh)
    by_file = {a["source_filename"]: a for a in man["assets"]}

    def plan_entry(fname: str, plan_id: str) -> dict:
        a = by_file[fname]
        return {
            "id": plan_id,
            "image_ref": a.get("local_path") or "",
            "width_px": a.get("width_px"), "height_px": a.get("height_px"),
            "source_tab_label": a.get("source_tab_label"),
            "source_filename": fname,
            "drawing_floor_label": a.get("drawing_floor_label"),
            "page_tab_id": a.get("page_tab_id"),
            "mapping_status": a.get("mapping_status", "pending_review"),
            "scale_m_per_px": attr(
                SCALE_M_PER_PX, "m/px", DRAW,
                [f"source:manifest#mirae/{fname}", f"reading:2026-09-20/{fname}/dimension-line"],
                note=f"도면 통줄 치수선 기반. 수평 100.83 / 수직 99.03 mm/px, "
                     f"편차 1.8%. 실측 검증 전 값") if fname == "Mirae_3F.png"
                else unknown("이 층의 축척을 독립 산출하지 않았다. 3층 값을 복사하지 않는다."),
            "control_points": ([
                {"label": "grid-1", "x_px": 139.0, "y_px": None, "dim_mm_from_axis1": 0},
                {"label": "grid-16", "x_px": 1412.0, "y_px": None, "dim_mm_from_axis1": 128350},
                {"label": "grid-H", "x_px": None, "y_px": 253.5, "dim_mm_from_H": 0},
                {"label": "grid-A", "x_px": None, "y_px": 759.4, "dim_mm_from_H": 50100},
            ] if fname == "Mirae_3F.png" else []),
            "geo_transform": None,
            "geo_error_estimate_m": unknown("지리 정합 미수행"),
            "revision_date": a.get("revision_date"),
            "source_refs": [f"source:manifest#mirae/{fname}", man["source_page"]],
            "usage_terms": a.get("usage_terms", "unknown"),
            "notes": (["웹 탭 이름과 도면 내부 표기가 불일치"]
                      if a.get("mapping_status") == "source_label_conflict" else []),
        }

    plans = [
        plan_entry("Mirae_3F.png", "mirae/plan/3F"),
        plan_entry("Mirae_B2_2.png", "mirae/plan/B2_2"),
    ]

    floors = [
        {
            "id": "mirae/F3", "building_id": "mirae", "label": "3층",
            "sort_order": 3, "wing_id": None, "plan_id": "mirae/plan/3F",
            "elevation_m": unknown("층 높이 미확인"),
            "notes": ["도면 내부 표기 '지상3층' 과 웹 탭 '3층' 이 일치."],
        },
        {
            # 웹 탭은 '지하 2층-②' 인데 도면 내부 표기는 '지상 2층'.
            # 서비스 층 ID 를 어느 쪽으로도 확정하지 않고 별도 임시 ID 를 쓴다.
            "id": "mirae/DRAWING-2F", "building_id": "mirae",
            "label": "원본상 2층 (서비스 층 미확정)",
            "sort_order": 2, "wing_id": None, "plan_id": "mirae/plan/B2_2",
            "elevation_m": unknown("층 높이 미확인"),
            "notes": [
                "웹 탭='지하 2층-②', 도면 내부 표기='지상2층'. 원인 미확인.",
                "호실이 201~237 의 2xx 계열인 점은 도면 내부 표기를 뒷받침한다.",
                "3층과의 상하 인접 여부를 확정하지 않았다. sort_order 는 임시값.",
                "Mirae_B2_1.png(웹 '지하 2층-①', 도면 '지상1층') 과 병합하지 않았다.",
            ],
        },
    ]

    nodes: list[dict] = []
    edges: list[dict] = []

    # ---------------- 3층: 338 / 337 / 복도 ----------------
    R3 = [SRC_3F, READ_3F]
    R3O = [SRC_3F, READ_3F, OCR_3F]

    nodes += [
        node("mirae/F3/door/338-W", "room_door", "mirae/F3", D338_W_X, WALL_Y,
             "338호 서측 문", refs=R3O),
        node("mirae/F3/door/338-E", "room_door", "mirae/F3", D338_E_X, WALL_Y,
             "338호 동측 문", refs=R3O),
        node("mirae/F3/door/337-W", "room_door", "mirae/F3", D337_W_X, WALL_Y,
             "337호 서측 문", refs=R3O),
        node("mirae/F3/door/337-E", "room_door", "mirae/F3", D337_E_X, WALL_Y,
             "337호 동측 문", refs=R3O),
        node("mirae/F3/cj/338-W", "corridor_junction", "mirae/F3", D338_W_X, CORRIDOR_Y,
             "338호 서측 문 앞 복도", refs=R3),
        node("mirae/F3/cj/338-E", "corridor_junction", "mirae/F3", D338_E_X, CORRIDOR_Y,
             "338호 동측 문 앞 복도", refs=R3),
        node("mirae/F3/cj/wc-W", "corridor_junction", "mirae/F3", WC_X0 + 6, CORRIDOR_Y,
             "화장실 서측 출입부 앞", refs=R3,
             notes=["338/337 사이 코어는 화장실. 통과 동선 아님."]),
        node("mirae/F3/cj/wc-E", "corridor_junction", "mirae/F3", WC_X1 - 6, CORRIDOR_Y,
             "화장실 동측 출입부 앞", refs=R3),
        node("mirae/F3/cj/337-W", "corridor_junction", "mirae/F3", D337_W_X, CORRIDOR_Y,
             "337호 서측 문 앞 복도", refs=R3),
        node("mirae/F3/cj/337-E", "corridor_junction", "mirae/F3", D337_E_X, CORRIDOR_Y,
             "337호 동측 문 앞 복도", refs=R3),
    ]

    # 문 엣지 (문 통과)
    for did, cj, opening in (
        ("338-W", "mirae/F3/cj/338-W", D338_W_OPEN),
        ("338-E", "mirae/F3/cj/338-E", D338_E_OPEN),
        ("337-W", "mirae/F3/cj/337-W", D337_W_OPEN),
        ("337-E", "mirae/F3/cj/337-E", D337_E_OPEN),
    ):
        edges += edge(
            f"mirae/F3/e/door/{did}", f"mirae/F3/door/{did}", cj, "door",
            round((CORRIDOR_Y - WALL_Y) * SCALE_M_PER_PX, 2),
            acc_door(opening, R3), refs=R3,
            notes=["문턱/개폐방식 미확인 - 휠체어 판정 불가"],
        )

    # 복도 엣지 (센터라인 따라 동서 방향)
    corridor_chain = [
        ("mirae/F3/cj/338-W", "mirae/F3/cj/338-E"),
        ("mirae/F3/cj/338-E", "mirae/F3/cj/wc-W"),
        ("mirae/F3/cj/wc-W", "mirae/F3/cj/wc-E"),
        ("mirae/F3/cj/wc-E", "mirae/F3/cj/337-W"),
        ("mirae/F3/cj/337-W", "mirae/F3/cj/337-E"),
    ]
    pos = {n["id"]: (n["plan_point"]["x_px"], n["plan_point"]["y_px"]) for n in nodes}
    for i, (u, v) in enumerate(corridor_chain, 1):
        edges += edge(
            f"mirae/F3/e/corr/{i}", u, v, "corridor", px(pos[u], pos[v]),
            acc_corridor(CORRIDOR_BAND_PX, R3),
            geometry=[list(pos[u]), list(pos[v])], refs=R3,
            notes=["복도 센터라인. 벽-벽 폭 3.10m (유효폭 아님)"],
        )

    # ---------------- 3층 계단실: 위치만 등록, 복도 연결 없음 ----------------
    nodes.append(node(
        "mirae/F3/stair/S-mid/landing", "stair_landing", "mirae/F3",
        (STAIR_3F["x0"] + STAIR_3F["x1"]) / 2,
        (STAIR_3F["y0"] + STAIR_3F["y1"]) / 2,
        "3층 중앙 계단실(후보)", facility="mirae/stair/S-mid", refs=R3,
        notes=[
            "도면에서 2개 계단참 + 중간참을 확인. 계단 자체는 실재로 판독됨.",
            "복도(북측)와의 문 연결을 판독하지 못했다. 북측 벽에 점선 요소"
            "(방화셔터 추정)만 보이고 문 호선이 없다. 따라서 연결 엣지를 만들지 않았다.",
            "현장 확인 항목: 이 계단실의 3층 출입문 위치/유무.",
        ],
    ))

    # ---------------- 원본상 2층: 202호 ----------------
    R2 = [SRC_B22, READ_B22]
    R2O = [SRC_B22, READ_B22, OCR_B22]
    nodes += [
        node("mirae/DRAWING-2F/door/202", "room_door", "mirae/DRAWING-2F",
             D202_X, D202_Y, "202호 문 (동벽)", refs=R2O,
             notes=["OCR 라벨 '202'@(308,624), '강의실'@(300,638)"]),
        node("mirae/DRAWING-2F/cj/202", "corridor_junction", "mirae/DRAWING-2F",
             CORRIDOR_2F_X, D202_Y, "202호 문 앞 복도", refs=R2,
             notes=["202 동벽(x=358.3)과 203/204 서벽 사이 복도. 폭 개략 판독."]),
    ]
    edges += edge(
        "mirae/DRAWING-2F/e/door/202", "mirae/DRAWING-2F/door/202",
        "mirae/DRAWING-2F/cj/202", "door",
        None,          # 이 층의 축척을 독립 산출하지 않았다 -> 길이 unknown
        acc_door((0.0, 0.0), R2) | {
            "clear_width_m": unknown("개구부 폭 미판독"),
        },
        refs=R2,
        notes=["이 층 축척 미산출로 거리 unknown. 3층 축척을 복사하지 않았다."],
    )

    places = [
        {
            "id": "mirae/F3/338", "name": "미래관 338호", "building_id": "mirae",
            "floor_id": "mirae/F3", "room_label": "338",
            "aliases": ["338", "338호", "미래관338", "미래관 338 강의실"],
            "wing_id": None,
            "door_node_ids": ["mirae/F3/door/338-W", "mirae/F3/door/338-E"],
            "status": "drawing_candidate",
            "label_plan_point": {"coordinate_space": "plan:mirae/F3",
                                 "x_px": 956.0, "y_px": 280.0},
            "source_refs": R3O,
            "notes": ["도면상 '338 강의실'. 현재 호실 표기/용도 현장 미확인."],
        },
        {
            "id": "mirae/F3/337", "name": "미래관 337호", "building_id": "mirae",
            "floor_id": "mirae/F3", "room_label": "337",
            "aliases": ["337", "337호", "미래관337"],
            "wing_id": None,
            "door_node_ids": ["mirae/F3/door/337-W", "mirae/F3/door/337-E"],
            "status": "drawing_candidate",
            "label_plan_point": {"coordinate_space": "plan:mirae/F3",
                                 "x_px": 1124.0, "y_px": 280.0},
            "source_refs": R3O,
            "notes": ["도면상 '337 강의실'. 현재 호실 표기/용도 현장 미확인."],
        },
        {
            "id": "mirae/DRAWING-2F/202", "name": "미래관 202호 (원본상 2층)",
            "building_id": "mirae", "floor_id": "mirae/DRAWING-2F",
            "room_label": "202", "aliases": ["202", "202호"],
            "wing_id": None,
            "door_node_ids": ["mirae/DRAWING-2F/door/202"],
            "status": "drawing_candidate",
            "label_plan_point": {"coordinate_space": "plan:mirae/DRAWING-2F",
                                 "x_px": 308.0, "y_px": 624.0},
            "source_refs": R2O,
            "notes": [
                "도면 Mirae_B2_2.png(웹 탭 '지하 2층-②', 도면 내부 '지상2층') 의 '202 강의실'.",
                "서비스 층 ID 미확정. 3층과의 층간 연결은 근거 부족으로 미등록.",
            ],
        },
    ]

    doc = {
        "graph_version": GRAPH_VERSION,
        "schema_version": SCHEMA_VERSION,
        "generated_at": now(),
        "verification_scope": {
            "field_verified": False,
            "floors_with_graph": ["mirae/F3", "mirae/DRAWING-2F"],
            "evidence_level": "공개 도면 판독(drawing_read) 까지. 현장 실측 없음.",
            "wheelchair_accessible_routes_certified": False,
            "outdoor_connection": "없음 - 확인된 외부 지점이 없어 미등록",
            "vertical_connection": "없음 - 확정된 계단 출입문/승강기 근거 없음",
            "scale": {"mirae/plan/3F": f"{SCALE_M_PER_PX} m/px (±{SCALE_UNCERTAINTY_PCT}%)",
                      "mirae/plan/B2_2": "미산출"},
        },
        "notes": [
            "이 그래프는 공개 도면 판독만으로 만들었다. 접근성 확인 경로를 제공하지 않는다.",
            "엘리베이터는 도면에서 기호를 확정하지 못해 생성하지 않았다.",
            "338/337 사이 코어는 화장실이며 통과 동선이 아니다.",
            "실외 연결 없음: 정문 등에서 미래관까지의 경로를 가상 통로로 잇지 않았다.",
            "초기 시제품(data/graph.json, 건물중심점 접속)은 별도로 보존되며 "
            "이 사용자용 그래프에는 포함하지 않는다.",
        ],
        "buildings": [{
            "id": "mirae", "official_name": "미래관", "campus_code": "S2",
            "aliases": ["미래관", "미래", "S2"], "wings": [], "footprint": None,
            "source_refs": [
                "https://www.kookmin.ac.kr/user/unIntr/campusGuide/bukakCampusGuide/index.do",
                "https://engineering.kookmin.ac.kr/engineering/etc/engineering-floor-guide.do",
            ],
        }],
        "floorplans": plans,
        "floors": floors,
        "places": places,
        "nodes": nodes,
        "edges": edges,
        "elevators": [],
        "closures": [],
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)

    print(f"graph_version={GRAPH_VERSION}")
    print(f"  floors={len(floors)} plans={len(plans)} places={len(places)}")
    print(f"  nodes={len(nodes)} edges={len(edges)} elevators=0")
    print(f"저장: {OUT}")


if __name__ == "__main__":
    main()
