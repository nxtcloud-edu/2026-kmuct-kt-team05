"""
계단으로만 닿는 구역에 '단차 없는 우회로'를 추가한다 (병합 후 단계).

왜 필요한가
    현장 판단은 캠퍼스를 휠체어로 이동할 수 있다는 것이다. 그런데 그래프에는
    그 경로가 없다. 실외는 OSM 에 경사로가 빠져 있고, 미래관 실내는 도면
    골격화 과정에서 일부 구역이 계단실로만 이어졌다.

    계단을 제외한 그래프의 연결 요소를 구하고, 계단 엣지가 서로 다른 요소를
    이을 때만 우회로를 넣는다. 모든 계단에 경사로가 있다고 주장하지 않는다.
    연결에 꼭 필요한 최소 개수만 넣는다.

무엇을 전제하는가
    이 엣지들은 실측이 아니다. accessibility_is_assumed=True 로 표시되어
    경로 응답의 assumed_accessibility_segments 에 집계된다.
    엘리베이터가 있는 층 사이라면 경사로보다 승강기가 실제 경로일 것이다.
    여기서는 '단차 없이 갈 방법이 있다'는 사실만 모델한다.

    파일 하나만 되돌리면 엄격한 그래프로 돌아간다. 이 스크립트를 돌리지 않으면
    병합 결과에는 우회로가 없다.

사용법
    python scripts/merge_graphs.py
    python scripts/add_stepfree_bypasses.py
"""

from __future__ import annotations

import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PUBLISHED = ROOT / "data" / "published" / "campus_v1.json"

#: 우회 경사로 전제값. 정책 한계(경사 8.33%, 폭 0.90m, 문턱 0.02m) 안쪽.
RAMP_SLOPE_PCT = 8.0
RAMP_WIDTH_M = 1.20
RAMP_THRESHOLD_M = 0.0
EVIDENCE = "drawing_inferred"

NOTE = ("계단으로만 이어지던 구간을 잇는 단차 없는 우회로다. "
        "현장 판단(휠체어 이동 가능)을 근거로 존재를 전제했다. "
        "실제 경로는 경사로일 수도, 별도 승강기일 수도 있다. "
        "위치와 경사는 현장 확인이 필요하다.")


def a(value, unit: str | None = None) -> dict:
    d = {"value": value, "verification": EVIDENCE, "note": NOTE}
    if unit:
        d["unit"] = unit
    return d


def is_stair(e: dict) -> bool:
    if e.get("kind") == "stairs":
        return True
    st = (e.get("accessibility") or {}).get("stairs") or {}
    return st.get("value") is True


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--path", default=str(PUBLISHED))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    p = pathlib.Path(args.path)
    doc = json.loads(p.read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in doc["nodes"]}
    edges = doc["edges"]

    # 이미 돌렸다면 먼저 제거해 멱등하게 만든다.
    before = len(edges)
    edges = [e for e in edges if not e["id"].startswith("assumed/bypass/")]
    removed = before - len(edges)

    parent = {nid: nid for nid in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: str, y: str) -> bool:
        rx, ry = find(x), find(y)
        if rx == ry:
            return False
        parent[rx] = ry
        return True

    stairs = []
    for e in edges:
        f, t = e["from_node"], e["to_node"]
        if f not in parent or t not in parent:
            continue
        if is_stair(e):
            stairs.append(e)
        else:
            union(f, t)

    added: list[dict] = []
    joined = 0
    for e in stairs:
        f, t = e["from_node"], e["to_node"]
        if not union(f, t):
            continue                     # 계단 없이도 이어져 있다
        joined += 1
        length = (e.get("horizontal_length_m") or {}).get("value")
        acc = {
            "stairs": a(False),
            "slope_up_pct": a(RAMP_SLOPE_PCT, "%"),
            "slope_down_pct": a(RAMP_SLOPE_PCT, "%"),
            "clear_width_m": a(RAMP_WIDTH_M, "m"),
            "threshold_m": a(RAMP_THRESHOLD_M, "m"),
        }
        for x, y in ((f, t), (t, f)):
            added.append({
                "id": f"assumed/bypass/{x}__{y}".replace("/", "_")
                      .replace("assumed_bypass_", "assumed/bypass/", 1),
                "from_node": x, "to_node": y,
                "kind": "ramp",
                "horizontal_length_m": (a(float(length), "m")
                                        if length is not None
                                        else {"value": None,
                                              "verification": "unknown",
                                              "note": NOTE}),
                "traversal_length_m": {"value": None, "verification": "unknown"},
                "vertical_rise_m": {"value": None, "verification": "unknown"},
                "accessibility": acc,
                "facility_id": None, "schedule_id": None,
                "geometry": [],
                "elevator_from_floor": None, "elevator_to_floor": None,
                "min_accessibility_verification": EVIDENCE,
                "length_is_assumed": True,
                "accessibility_is_assumed": True,
                "source_refs": ["현장 판단: 휠체어 이동 가능"],
                "notes": [NOTE, f"대체 대상 계단 엣지: {e['id']}"],
            })

    # 결과 확인: 계단 없이 한 덩어리인가
    adj = collections.defaultdict(list)
    for e in edges + added:
        if is_stair(e):
            continue
        adj[e["from_node"]].append(e["to_node"])
    seen = set()
    start = next(iter(nodes))
    stack = [start]
    seen.add(start)
    while stack:
        u = stack.pop()
        for v in adj[u]:
            if v not in seen:
                seen.add(v)
                stack.append(v)

    print(f"대상: {p.name}")
    if removed:
        print(f"기존 우회로 {removed}개 제거 (멱등)")
    print(f"계단으로만 이어지던 연결 {joined}곳 -> 우회로 {len(added)}개 추가")
    print(f"계단 제외 시 한 덩어리 크기: {len(seen)} / {len(nodes)}")
    if len(seen) < len(nodes):
        rest = collections.Counter()
        for nid in nodes:
            if nid in seen:
                continue
            f = nodes[nid].get("floor_id") or "?"
            rest["미래관" if f.startswith("mirae/") else f] += 1
        print("  아직 빠진 노드:")
        for k, v in rest.most_common(8):
            print(f"    {k:<28} {v}개")
        print("  (엣지가 아예 없는 고립 노드는 우회로로 이을 수 없다)")

    if args.dry_run:
        print("dry-run: 파일을 쓰지 않았다.")
        return
    doc["edges"] = edges + added
    doc.setdefault("build_steps", [])
    doc["build_steps"] = [s for s in doc["build_steps"]
                          if s.get("step") != "add_stepfree_bypasses"]
    doc["build_steps"].append({
        "step": "add_stepfree_bypasses",
        "added_edges": len(added),
        "joined_connections": joined,
        "evidence": EVIDENCE,
        "note": NOTE,
    })
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    print(f"저장: {p}")


if __name__ == "__main__":
    main()
