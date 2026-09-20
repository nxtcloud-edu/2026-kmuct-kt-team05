"""
4단계: 검증 하네스.

이 스크립트가 답해야 하는 질문 (프로젝트 진행 여부를 결정하는 관문):
  Q1. 그래프가 연결되어 있는가? (OSM 보행로 커버리지가 충분한가)
  Q2. 프로파일을 바꾸면 경로가 실제로 달라지는가?
  Q3. 휠체어로 도달 불가한 건물이 있는가?
  Q4. 경사/계단 지표가 프로파일별로 개선되는가?

Q2 가 부정이면 이후 개발은 의미가 없다.

사용법
    python verify.py                    # 자동 선정 OD 쌍 일괄 검증
    python verify.py 종합복지관 공학관    # 특정 구간만
"""

import json
import sys

import config
from build_graph import haversine
from routing import Graph, astar, route_geojson

PROFILE_ORDER = ["normal", "elderly", "wheelchair"]


# --- Q1: 연결성 ---------------------------------------------------------------
def components(graph: Graph, stairs_blocked: bool = False) -> list[set[str]]:
    seen: set[str] = set()
    comps: list[set[str]] = []
    for start in graph.nodes:
        if start in seen:
            continue
        stack, comp = [start], set()
        while stack:
            cur = stack.pop()
            if cur in comp:
                continue
            comp.add(cur)
            for e in graph.adj[cur]:
                if stairs_blocked and e["steps"]:
                    continue
                if e["to"] not in comp:
                    stack.append(e["to"])
        seen |= comp
        comps.append(comp)
    return sorted(comps, key=len, reverse=True)


def report_connectivity(graph: Graph) -> set[str]:
    print("=" * 78)
    print("Q1. 그래프 연결성")
    print("=" * 78)
    comps = components(graph)
    main = comps[0]
    print(f"노드 {len(graph.nodes)}개 / 연결요소 {len(comps)}개 / "
          f"최대요소 {len(main)}개 ({len(main)/len(graph.nodes)*100:.0f}%)")
    if len(comps) > 1:
        print("  단절된 요소 크기:", [len(c) for c in comps[1:12]])

    bld_in_main = [
        graph.nodes[n]["name"] for n in graph.buildings.values() if n in main
    ]
    bld_out = [
        graph.nodes[n]["name"] for n in graph.buildings.values() if n not in main
    ]
    print(f"건물 {len(graph.buildings)}개 중 최대요소 포함 {len(bld_in_main)}개")
    if bld_out:
        print(f"  ! 최대요소에서 단절된 건물: {', '.join(bld_out)}")
        print("    -> 해당 지역 보행로를 OSM 에 보강해야 함")

    # 계단 제거 시 연결성 (휠체어 관점)
    wc = components(graph, stairs_blocked=True)
    wc_main = wc[0]
    wc_out = [
        graph.nodes[n]["name"] for n in graph.buildings.values()
        if n in main and n not in wc_main
    ]
    print(f"\n계단 제외 시: 연결요소 {len(wc)}개 / 최대요소 {len(wc_main)}개")
    if wc_out:
        print(f"  ! 계단을 빼면 단절되는 건물: {', '.join(wc_out)}")
    return main


# --- OD 쌍 자동 선정 ----------------------------------------------------------
def pick_pairs(graph: Graph, main: set[str], top: int = 6) -> list[tuple[str, str]]:
    """고도차가 큰 건물쌍을 우선 선정. 경사 문제가 드러나는 구간을 고른다."""
    blds = [(n, nid) for n, nid in graph.buildings.items() if nid in main]
    scored = []
    for i in range(len(blds)):
        for j in range(i + 1, len(blds)):
            (na, ia), (nb, ib) = blds[i], blds[j]
            a, b = graph.nodes[ia], graph.nodes[ib]
            dz = abs(a["ele"] - b["ele"])
            dist = haversine(a["lat"], a["lon"], b["lat"], b["lon"])
            if dist < 80:
                continue
            scored.append((dz, dist, na, nb))
    scored.sort(reverse=True)
    # 저지대 -> 고지대 방향(오르막)으로 방향을 맞춘다
    out = []
    for dz, dist, na, nb in scored[:top]:
        ia, ib = graph.buildings[na], graph.buildings[nb]
        if graph.nodes[ia]["ele"] > graph.nodes[ib]["ele"]:
            na, nb = nb, na
        out.append((na, nb))
    return out


# --- Q2~Q4: 프로파일 비교 -----------------------------------------------------
def compare(graph: Graph, origin: str, dest: str, features: list) -> dict:
    src, dst = graph.resolve(origin), graph.resolve(dest)
    if src is None or dst is None:
        print(f"  ! 건물명 해석 실패: {origin if src is None else dest}")
        return {}

    a, b = graph.nodes[src], graph.nodes[dst]
    print(f"\n[{origin} ({a['ele']:.0f}m) -> {dest} ({b['ele']:.0f}m)]  "
          f"고도차 {b['ele']-a['ele']:+.0f}m  "
          f"직선 {haversine(a['lat'],a['lon'],b['lat'],b['lon']):.0f}m")
    print(f"  {'프로파일':<8} {'거리':>8} {'상승':>7} {'평균경사':>8} {'최대경사':>8} "
          f"{'계단':>6} {'8.33%초과':>10}")
    print("  " + "-" * 68)

    results = {}
    for pname in PROFILE_ORDER:
        r = astar(graph, src, dst, pname)
        label = config.PROFILES[pname]["label"]
        if r is None:
            print(f"  {label:<8} {'도달 불가':>8}")
            results[pname] = None
            continue
        print(f"  {label:<8} {r['length_m']:>7.0f}m {r['ascent_m']:>6.0f}m "
              f"{r['mean_grade']*100:>7.1f}% {r['max_grade']*100:>7.1f}% "
              f"{r['stair_edges']:>4}개 {r['over_833_length_m']:>8.0f}m")
        results[pname] = r
        features.append(route_geojson(graph, r, {
            "od": f"{origin}->{dest}", "profile": pname,
            "profile_label": label,
        }))

    # 경로 분기 판정
    seqs = {p: tuple(r["nodes"]) for p, r in results.items() if r}
    uniq = len(set(seqs.values()))
    if len(seqs) <= 1:
        verdict = "비교불가"
    elif uniq == 1:
        verdict = "동일 (분기 없음)"
    else:
        verdict = f"{uniq}종류로 분기"
    print(f"  => 경로: {verdict}")

    n, w = results.get("normal"), results.get("wheelchair")
    if n and w:
        print(f"     휠체어 우회 비용: 거리 {w['length_m']/n['length_m']:.2f}배, "
              f"계단 {n['stair_edges']}개 -> 0개, "
              f"최대경사 {n['max_grade']*100:.1f}% -> {w['max_grade']*100:.1f}%")
    return {"results": results, "unique_paths": uniq if len(seqs) > 1 else 0}


def main() -> None:
    graph = Graph()
    print(f"DEM: {graph.meta['dem_dataset']} ({graph.meta['interpolation']})")
    print(f"주의: {graph.meta['note']}\n")

    main_comp = report_connectivity(graph)

    print("\n" + "=" * 78)
    print("Q2~Q4. 프로파일별 경로 비교")
    print("=" * 78)

    features: list = []
    if len(sys.argv) >= 3:
        pairs = [(sys.argv[1], sys.argv[2])]
    else:
        pairs = pick_pairs(graph, main_comp)
        print(f"고도차 기준 상위 {len(pairs)}개 구간 자동 선정")

    summaries = []
    for origin, dest in pairs:
        s = compare(graph, origin, dest, features)
        if s:
            summaries.append(s)

    # 최종 판정
    print("\n" + "=" * 78)
    print("판정")
    print("=" * 78)
    diverged = sum(1 for s in summaries if s.get("unique_paths", 0) > 1)
    unreachable = sum(
        1 for s in summaries if s["results"].get("wheelchair") is None
    )
    print(f"검증 구간 {len(summaries)}개")
    print(f"  프로파일별 경로가 분기한 구간: {diverged}개")
    print(f"  휠체어 도달 불가 구간: {unreachable}개")

    if diverged == 0:
        print("\n  [실패] 프로파일을 바꿔도 경로가 같습니다.")
        print("  원인 후보: (a) 보행로 대안 경로가 그래프에 없음 -> OSM 보강 필요")
        print("             (b) 계단 엣지가 주요 경로에 없음")
        print("             (c) 페널티 계수가 너무 작음 -> config.PROFILES 조정")
    else:
        print(f"\n  [성공] {diverged}/{len(summaries)} 구간에서 경로가 분기했습니다.")
        print("  프로파일별 경로 차별화가 성립합니다. 다음 단계 진행 가능.")

    if features:
        with config.ROUTES_GEOJSON.open("w", encoding="utf-8") as fh:
            json.dump({"type": "FeatureCollection", "features": features},
                      fh, ensure_ascii=False)
        print(f"\n경로 GeoJSON 저장: {config.ROUTES_GEOJSON}")
        print("  geojson.io 에 올리면 프로파일별 경로를 지도에서 비교할 수 있습니다.")


if __name__ == "__main__":
    main()
