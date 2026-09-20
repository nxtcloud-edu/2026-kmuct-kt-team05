"""
계수 민감도 분석: alpha 를 바꾸면 경로가 언제 갈라지는지 찾는다.

config.PROFILES 의 alpha 값을 임의로 정한 것이 아니라는 근거를 만들기 위한 도구.
캡스톤 보고서에 "alpha 를 왜 이 값으로 정했는가" 를 답하는 데 쓴다.

사용법:
    python sweep.py                        # 기본 OD 쌍으로 스윕
    python sweep.py 평생교육실기관 본부관    # 특정 구간
"""

import sys

import config
from routing import Graph, astar

ALPHAS = [0, 1, 5, 10, 20, 40, 60, 100, 150, 200, 300, 500, 1000]
GRADE_FREE = 0.04  # 노약자 기준값으로 고정하고 alpha 만 변화


def sweep(graph: Graph, origin: str, dest: str, stairs_blocked: bool) -> None:
    src, dst = graph.resolve(origin), graph.resolve(dest)
    if src is None or dst is None:
        print(f"  건물명 해석 실패: {origin} / {dest}")
        return

    mode = "계단 차단" if stairs_blocked else "계단 허용"
    print(f"\n[{origin} -> {dest}]  ({mode}, grade_free={GRADE_FREE*100:.0f}%)")
    print(f"  {'alpha':>6} {'거리':>8} {'상승':>7} {'최대경사':>8} {'계단':>5}  경로ID")
    print("  " + "-" * 56)

    seen: dict[tuple, int] = {}
    prev_id = None
    for alpha in ALPHAS:
        profile = {
            "alpha": float(alpha),
            "grade_exponent": 2.0,
            "grade_free": GRADE_FREE,
            "stair_cost_per_m": 8.0,
            "stairs_blocked": stairs_blocked,
        }
        # 임시 프로파일을 config 에 끼워넣어 astar 재사용
        config.PROFILES["_sweep"] = profile
        r = astar(graph, src, dst, "_sweep")
        if r is None:
            print(f"  {alpha:>6} {'도달 불가':>8}")
            continue
        sig = tuple(r["nodes"])
        if sig not in seen:
            seen[sig] = len(seen) + 1
        pid = seen[sig]
        mark = "  <-- 경로 변경" if prev_id is not None and pid != prev_id else ""
        print(f"  {alpha:>6} {r['length_m']:>7.0f}m {r['ascent_m']:>6.0f}m "
              f"{r['max_grade']*100:>7.1f}% {r['stair_edges']:>3}개  #{pid}{mark}")
        prev_id = pid

    config.PROFILES.pop("_sweep", None)
    print(f"  => 서로 다른 경로 {len(seen)}종류 관측")


def main() -> None:
    graph = Graph()
    if len(sys.argv) >= 3:
        pairs = [(sys.argv[1], sys.argv[2])]
    else:
        pairs = [
            ("평생교육실기관", "본부관"),
            ("평생교육실기관", "성곡도서관"),
            ("평생교육실기관", "조형관"),
        ]
    print("=" * 62)
    print("alpha 민감도 분석 (grade_exponent=2 고정)")
    print("=" * 62)
    for origin, dest in pairs:
        sweep(graph, origin, dest, stairs_blocked=False)
    print("\n" + "=" * 62)
    print("해석: 경로가 처음 바뀌는 alpha 가 '경사를 고려하기 시작하는 임계값'이다.")
    print("      노약자 alpha 는 이 임계값 근처, 휠체어는 그보다 충분히 크게 잡는다.")


if __name__ == "__main__":
    main()
