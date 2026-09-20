"""시안 통행 마스크의 연결성 점검.

민트 영역이 원래 끊겨 있는지, 세선화/추적 단계에서 끊기는지 구분한다.
"""
from __future__ import annotations

import collections
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from scripts.build_from_navmap import (  # noqa: E402
    CELL, WALKABLE, cell_grid, close_mask, prune_spurs, skeleton_graph, thin,
)
from PIL import Image  # noqa: E402

NAV = pathlib.Path(__file__).resolve().parents[1] / "data" / "raw" / "navmaps"


def comps(mask, gw, gh, conn8=True):
    seen = [[False] * gw for _ in range(gh)]
    out = []
    dirs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)] \
        if conn8 else [(-1, 0), (1, 0), (0, -1), (0, 1)]
    for y in range(gh):
        for x in range(gw):
            if not mask[y][x] or seen[y][x]:
                continue
            q, n = [(y, x)], 0
            seen[y][x] = True
            while q:
                cy, cx = q.pop()
                n += 1
                for dy, dx in dirs:
                    ny, nx = cy + dy, cx + dx
                    if 0 <= ny < gh and 0 <= nx < gw and mask[ny][nx] \
                            and not seen[ny][nx]:
                        seen[ny][nx] = True
                        q.append((ny, nx))
            out.append(n)
    out.sort(reverse=True)
    return out


def main() -> None:
    f = sys.argv[1] if len(sys.argv) > 1 else "nav_3F.png"
    img = Image.open(NAV / f)
    grid, gw, gh = cell_grid(img)
    kinds = collections.Counter(grid[y][x] for y in range(gh) for x in range(gw))
    print(f"{f}  격자 {gw}x{gh}")
    print("  색 분류:", dict(kinds.most_common()))

    mask = [[grid[y][x] in WALKABLE for x in range(gw)] for y in range(gh)]
    mask = close_mask(mask, gw, gh, 2)
    c = comps(mask, gw, gh)
    print(f"\n통행 마스크 연결요소 {len(c)}개, 상위 크기 {c[:12]}")
    print(f"  전체 통행셀 {sum(c)}, 최대요소 비중 {c[0]/max(1,sum(c))*100:.0f}%")

    skel = thin(mask, gw, gh)
    cs = comps(skel, gw, gh)
    print(f"\n세선화 후 연결요소 {len(cs)}개, 상위 {cs[:12]}")

    sk2 = prune_spurs(skel, gw, gh, set())
    cs2 = comps(sk2, gw, gh)
    print(f"잔가지제거 후 연결요소 {len(cs2)}개, 상위 {cs2[:12]}")

    ns, es = skeleton_graph(sk2, gw, gh, set())
    print(f"\n추적 결과: 노드 {len(ns)}  엣지 {len(es)}")
    adj = collections.defaultdict(set)
    for a, b, _ in es:
        adj[a].add(b)
        adj[b].add(a)
    seen, gc = set(), []
    for n in ns:
        if n in seen:
            continue
        st, comp = [n], set()
        while st:
            cur = st.pop()
            if cur in comp:
                continue
            comp.add(cur)
            st += [x for x in adj[cur] if x not in comp]
        seen |= comp
        gc.append(len(comp))
    gc.sort(reverse=True)
    print(f"그래프 연결요소 {len(gc)}개, 상위 {gc[:12]}")


if __name__ == "__main__":
    main()
