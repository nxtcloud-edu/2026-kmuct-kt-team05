"""그래프 연결성 진단 (실내 스키마용)."""
from __future__ import annotations

import collections
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.graph.dataset import Dataset   # noqa: E402


def main() -> None:
    ds = Dataset.load(sys.argv[1])
    print(f"{ds.graph_version}  nodes={len(ds.nodes)} edges={len(ds.edges)}")

    # 무향 연결요소
    adj = collections.defaultdict(set)
    for e in ds.edges:
        adj[e.from_node].add(e.to_node)
        adj[e.to_node].add(e.from_node)
    seen, comps = set(), []
    for n in ds.nodes:
        if n in seen:
            continue
        stack, comp = [n], set()
        while stack:
            c = stack.pop()
            if c in comp:
                continue
            comp.add(c)
            stack += [x for x in adj[c] if x not in comp]
        seen |= comp
        comps.append(comp)
    comps.sort(key=len, reverse=True)
    print(f"연결요소 {len(comps)}개, 크기 상위: {[len(c) for c in comps[:10]]}")

    # 층별
    by_floor = collections.defaultdict(list)
    for nid, n in ds.nodes.items():
        by_floor[n.floor_id].append(nid)
    print("\n층별 노드/요소:")
    for fid in sorted(by_floor, key=lambda f: ds.floors[f].sort_order
                      if f in ds.floors else -1):
        ns = set(by_floor[fid])
        cs = [c for c in comps if c & ns]
        big = max((len(c & ns) for c in cs), default=0)
        lbl = ds.floors[fid].label if fid in ds.floors else fid
        print(f"  {lbl:<8} 노드 {len(ns):>4}  요소 {len(cs):>3}개  "
              f"최대 {big:>4} ({big/max(1,len(ns))*100:.0f}%)")

    # 장소 도달성 (최대 요소 기준)
    main_c = comps[0]
    ok = sum(1 for p in ds.places.values()
             if p.door_node_ids and p.door_node_ids[0] in main_c)
    print(f"\n장소 {len(ds.places)}개 중 최대요소 포함 {ok}개")

    # 시설 노드 상태
    for kind in ("elevator_lobby", "stair_landing", "entrance_inside"):
        ns = [nid for nid, n in ds.nodes.items() if n.kind.value == kind]
        inmain = sum(1 for n in ns if n in main_c)
        print(f"  {kind:<16} {len(ns):>3}개 (최대요소 {inmain}개)")

    # 엘리베이터 승차 엣지 확인
    rides = [e for e in ds.edges if e.kind.value == "elevator_ride"]
    print(f"\nelevator_ride 엣지 {len(rides)}개")
    for e in rides[:4]:
        print(f"  {e.id}: {e.from_node} -> {e.to_node}")


if __name__ == "__main__":
    main()
