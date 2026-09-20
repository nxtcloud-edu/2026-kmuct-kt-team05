"""경로/시설 배치 점검: 엘리베이터 노드가 어디에 붙었는지, 연결선이 튀지 않는지."""
from __future__ import annotations

import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.graph.dataset import Dataset            # noqa: E402
from backend.app.routing.engine import route             # noqa: E402
from backend.app.routing.policy import Constraints       # noqa: E402


def main() -> None:
    g = sys.argv[1]
    ds = Dataset.load(g)

    print("=== 엘리베이터/계단 노드 배치 ===")
    for nid, n in sorted(ds.nodes.items()):
        if n.kind.value not in ("elevator_lobby", "stair_landing"):
            continue
        p = n.plan_point
        # 이 노드에 붙은 연결 엣지 길이
        links = []
        for e in ds.out.get(nid, ()):
            L = e.traversal_length_m if e.traversal_length_m.is_known \
                else e.horizontal_length_m
            if e.kind.value == "corridor" and L.is_known:
                b = ds.nodes[e.to_node].plan_point
                d_px = math.dist((p.x_px, p.y_px), (b.x_px, b.y_px)) if b else 0
                links.append((round(float(L.value), 1), round(d_px, 0)))
        fl = ds.floors[n.floor_id].label if n.floor_id in ds.floors else n.floor_id
        print(f"  {fl:<7} {n.kind.value:<15} ({p.x_px:>6.1f},{p.y_px:>6.1f})  "
              f"연결 {links}")

    if len(sys.argv) < 4:
        return
    a, b = sys.argv[2], sys.argv[3]
    wc = "--wheelchair" in sys.argv
    ns = wc or "--no-stairs" in sys.argv
    src = ds.find_places(a)[0].door_node_ids[0]
    dst = ds.find_places(b)[0].door_node_ids[0]
    r = route(ds, src, dst, "wheelchair" if wc else "normal", "fastest",
              Constraints(no_stairs=ns, wheelchair=wc))
    print(f"\n=== 경로 {a} -> {b}  status={r['status']} ===")
    if r["status"] != "ok":
        for x in r["reasons"]:
            print("  ", x)
        return
    m = r["metrics"]
    print(f"  {m['distance_m']}m  {m['estimated_time_s']}s  "
          f"층 {m['floors_touched']}")
    print(f"\n  세그먼트 {len(r['segments'])}개:")
    for i, s in enumerate(r["segments"], 1):
        n1, n2 = ds.nodes[s["from_node"]], ds.nodes[s["to_node"]]
        p1 = f"({n1.plan_point.x_px:.0f},{n1.plan_point.y_px:.0f})" if n1.plan_point else "-"
        p2 = f"({n2.plan_point.x_px:.0f},{n2.plan_point.y_px:.0f})" if n2.plan_point else "-"
        poly = len(s.get("polyline_px") or [])
        jump = ""
        if n1.plan_point and n2.plan_point and n1.floor_id == n2.floor_id:
            d = math.dist((n1.plan_point.x_px, n1.plan_point.y_px),
                          (n2.plan_point.x_px, n2.plan_point.y_px))
            if d > 120:
                jump = f"  <<< 직선 {d:.0f}px 점프"
        print(f"   {i:>2}. {s['kind']:<14} {s['space']:<22} {p1}->{p2} "
              f"poly={poly}{jump}")


if __name__ == "__main__":
    main()
