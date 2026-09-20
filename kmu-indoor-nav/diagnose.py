"""
진단: 그래프가 왜 프로파일별 경로를 못 만들어내는지 구조적으로 분석한다.

핵심 지표는 circuit rank (독립 순환 수) = E - V + C.
  rank == 0  -> 그래프가 트리. 두 노드 사이 경로가 유일하므로
                비용함수를 어떻게 바꿔도 경로는 절대 달라지지 않는다.
  rank >  0  -> 우회로가 존재. 비용함수 조정이 의미를 가진다.

사용법:  python diagnose.py
"""

import config
from routing import Graph
from verify import components


def main() -> None:
    g = Graph()
    comps = components(g)

    print("=" * 78)
    print("컴포넌트별 순환 구조")
    print("=" * 78)
    print(f"{'#':>3} {'노드':>6} {'엣지':>6} {'순환수':>7}  {'건물':>5}  판정")
    print("-" * 78)

    total_rank = 0
    for i, c in enumerate(comps, 1):
        e_in = sum(1 for e in g.edges if e["u"] in c and e["v"] in c)
        v = len(c)
        rank = e_in - v + 1
        total_rank += max(0, rank)
        nb = sum(1 for nid in g.buildings.values() if nid in c)
        verdict = "트리 - 우회로 없음" if rank <= 0 else f"우회로 {rank}개"
        print(f"{i:>3} {v:>6} {e_in:>6} {rank:>7} {nb:>5}개  {verdict}")

    v, e, cN = len(g.nodes), len(g.edges), len(comps)
    print("-" * 78)
    print(f"전체: 노드 {v}, 엣지 {e}, 컴포넌트 {cN}, 독립 순환 {e - v + cN}")

    print()
    print("=" * 78)
    print("계단 엣지가 어디에 있는가")
    print("=" * 78)
    steps = [x for x in g.edges if x["steps"]]
    print(f"계단 엣지 {len(steps)}개, 총 길이 {sum(x['length'] for x in steps):.0f}m")
    # 계단을 제거했을 때 끊어지는지 = 그 계단이 유일 통로인지 (cut edge)
    cut = 0
    for s in steps:
        if is_cut_edge(g, s):
            cut += 1
    print(f"그 중 유일 통로(cut edge)인 계단: {cut}개")
    if cut:
        print("  -> 이 계단들은 휠체어 경로에서 '우회'가 아니라 '도달 불가'를 만든다.")
        print("     대체 램프/엘리베이터 경로를 데이터에 넣어야 해결된다.")

    print()
    print("=" * 78)
    print("경사 분포 (DEM 추정치 신뢰도 점검)")
    print("=" * 78)
    paths = [x for x in g.edges if x["kind"] == "path"]
    buckets = [(0, 0.03), (0.03, 0.0833), (0.0833, 0.15), (0.15, 0.25), (0.25, 9)]
    for lo, hi in buckets:
        sel = [x for x in paths if lo <= abs(x["grade"]) < hi]
        label = f"{lo*100:.1f}~{hi*100:.0f}%" if hi < 9 else f"{lo*100:.0f}%+"
        bar = "#" * int(len(sel) / max(1, len(paths)) * 50)
        print(f"  {label:>12}  {len(sel):>4}개 ({len(sel)/len(paths)*100:>4.1f}%) {bar}")

    short = [x for x in paths if x["length"] < 30]
    print(f"\n길이 30m 미만 엣지: {len(short)}/{len(paths)} "
          f"({len(short)/len(paths)*100:.0f}%)")
    print("  DEM 격자가 30m 이므로 이 구간들의 경사는 사실상 보간 노이즈다.")
    if short:
        sg = sorted(abs(x["grade"]) for x in short)
        print(f"  해당 구간 경사 중앙값 {sg[len(sg)//2]*100:.1f}%, 최대 {sg[-1]*100:.1f}%")

    print()
    print("=" * 78)
    print("결론")
    print("=" * 78)
    if total_rank == 0:
        print("그래프에 순환이 전혀 없다. 경로가 유일하므로 비용함수 조정은 무의미하다.")
        print("해결책은 단 하나: 보행로 데이터 보강.")
    else:
        print(f"독립 순환 {total_rank}개가 존재하므로 우회로 탐색 자체는 가능하다.")
        print("경로가 분기하지 않았다면 순환이 목적지 쌍 주변에 없기 때문이다.")
    print()
    print("보강이 필요한 지점:")
    main_comp = comps[0]
    for i, c in enumerate(comps[1:], 2):
        names = [g.nodes[n]["name"] for n in g.buildings.values() if n in c]
        if names:
            print(f"  컴포넌트 {i} ({len(c)}노드): {', '.join(names)} "
                  f"-> 최대 컴포넌트와 연결되는 보행로 누락")
        else:
            print(f"  컴포넌트 {i} ({len(c)}노드): 건물 없음 - 고립된 길 조각")


def is_cut_edge(g: Graph, edge: dict) -> bool:
    """이 엣지를 지우면 u 에서 v 로 갈 수 없게 되는가."""
    u, v = edge["u"], edge["v"]
    target = (edge["u"], edge["v"], edge["osm_way"], edge["length"])
    stack, seen = [u], {u}
    while stack:
        cur = stack.pop()
        if cur == v:
            return False
        for e in g.adj[cur]:
            same = (
                e["osm_way"] == target[2]
                and e["length"] == target[3]
                and {e["u"], e["v"]} == {u, v}
            )
            if same:
                continue
            if e["to"] not in seen:
                seen.add(e["to"])
                stack.append(e["to"])
    return True


if __name__ == "__main__":
    main()
