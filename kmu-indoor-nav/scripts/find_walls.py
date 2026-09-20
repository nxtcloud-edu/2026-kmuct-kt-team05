"""
층 구조 자동 탐지: 가로 벽선(실열 경계)과 복도 밴드를 찾는다.

미래관은 선형 슬래브라 층마다 '북측 실열 / 복도 / 중앙 실열 / 복도 / 남측 실열'
구조가 반복된다. 각 층의 가로 벽선 y 를 찾아 복도 밴드를 추정한다.

방법
    도면 유효 영역(x 범위) 안에서 각 y 행의 어두운 픽셀 비율을 구한다.
    비율이 임계값 이상인 행 = 가로 벽선. 인접 행은 하나로 묶는다.

사용법
    python scripts/find_walls.py Mirae_3F.png
    python scripts/find_walls.py Mirae_3F.png 900 1210   # x 범위 지정
"""

from __future__ import annotations

import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "floorplans"

DARK = 140
WALL_RATIO = 0.55      # 이 비율 이상 어두우면 벽선 행
SCALE = 0.1008


def wall_rows(px, x0: int, x1: int, y0: int, y1: int) -> list[tuple[int, int, float]]:
    n = x1 - x0 + 1
    rows = []
    for y in range(y0, y1 + 1):
        c = sum(1 for x in range(x0, x1 + 1) if px[x, y] <= DARK)
        rows.append((y, c / n))
    # 임계 초과 행을 그룹화
    groups: list[tuple[int, int, float]] = []
    cur: list[tuple[int, float]] = []
    for y, r in rows:
        if r >= WALL_RATIO:
            cur.append((y, r))
        elif cur:
            groups.append((cur[0][0], cur[-1][0], max(v for _, v in cur)))
            cur = []
    if cur:
        groups.append((cur[0][0], cur[-1][0], max(v for _, v in cur)))
    return groups


def main() -> None:
    fname = sys.argv[1]
    img = Image.open(RAW / fname)
    px = img.convert("L").load()
    W, H = img.size
    x0 = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    x1 = int(sys.argv[3]) if len(sys.argv) > 3 else 1400
    y0, y1 = 100, 820

    print(f"{fname} {W}x{H}   분석 x {x0}..{x1}, y {y0}..{y1}")
    gs = wall_rows(px, x0, x1, y0, y1)
    print(f"가로 벽선 그룹 {len(gs)}개 (어두움 비율 >= {WALL_RATIO})")
    prev_end = None
    for i, (a, b, r) in enumerate(gs, 1):
        gap = f"  (이전 벽선과 간격 {a - prev_end - 1}px = " \
              f"{(a - prev_end - 1) * SCALE:.2f}m)" if prev_end is not None else ""
        print(f"  {i:2d}. y {a}..{b}  두께 {b - a + 1}px  최대비율 {r:.2f}{gap}")
        prev_end = b

    # 복도 후보: 벽선 사이 간격이 2.0~4.5 m 인 구간
    print("\n복도 밴드 후보 (벽선 간격 2.0~4.5 m):")
    found = False
    for (a1, b1, _), (a2, b2, _) in zip(gs, gs[1:]):
        gap_px = a2 - b1 - 1
        gap_m = gap_px * SCALE
        if 2.0 <= gap_m <= 4.5:
            found = True
            print(f"  y {b1 + 1} .. {a2 - 1}   폭 {gap_px}px = {gap_m:.2f} m"
                  f"   센터라인 y={(b1 + a2) / 2:.1f}"
                  f"   (위 벽선 y={b1}, 아래 벽선 y={a2})")
    if not found:
        print("  없음")


if __name__ == "__main__":
    main()
