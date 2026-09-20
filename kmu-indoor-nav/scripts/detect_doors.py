"""
문(door) 검출: 벽선에 인접한 호선(arc) 패턴을 찾는다.

이 도면의 관례
--------------
- 벽선은 문 위치에서도 **끊기지 않는다** (연속 검정선).
- 문은 실내쪽에 그려진 **사분원 호선 + 문짝선** 으로만 표현된다.
- 따라서 '벽선의 빈틈' 으로는 문을 찾을 수 없다. 호선을 찾아야 한다.

방법
----
가로벽(y=WALL)에 대해 x 를 따라가며, 실내쪽 밴드(y=WALL-band .. WALL-1)의
어두운 픽셀 수를 센다.
  - 밴드 대부분이 어두움      -> 벽/기둥/문틀(jamb)
  - 1~4 개만 어두움           -> 호선 또는 얇은 선
  - 0 개                      -> 개방(실내 공간)
호선 컬럼이 연속으로 이어지는 구간을 문 후보로 본다.

사용법
    python scripts/detect_doors.py Mirae_3F.png 903 1205 333 up      # 338/337 남벽
    python scripts/detect_doors.py Mirae_3F.png 1024 1080 362 down   # 계단실 북벽
인자: file x0 x1 wall_y side(up|down) [band]
"""

from __future__ import annotations

import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "floorplans"

DARK = 140
SCALE = 0.1008


def classify(counts: list[int], band: int) -> list[str]:
    out = []
    for c in counts:
        if c >= band * 0.7:
            out.append("W")     # wall / jamb
        elif c >= 1:
            out.append("a")     # arc / thin line
        else:
            out.append(".")     # open
    return out


def main() -> None:
    if len(sys.argv) < 6:
        raise SystemExit(__doc__)
    fname = sys.argv[1]
    x0, x1, wall_y = int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    side = sys.argv[5]
    band = int(sys.argv[6]) if len(sys.argv) > 6 else 12

    img = Image.open(RAW / fname)
    px = img.convert("L").load()
    print(f"{fname} {img.size[0]}x{img.size[1]}")
    print(f"벽 y={wall_y}  실내쪽={side}  밴드 {band}px  x {x0}..{x1}")

    ys = (range(wall_y - band, wall_y) if side == "up"
          else range(wall_y + 1, wall_y + 1 + band))

    counts = [sum(1 for y in ys if px[x, y] <= DARK) for x in range(x0, x1 + 1)]
    cls = classify(counts, band)

    # 시각화 문자열 (50px 단위로 줄바꿈)
    print("\n분류도 (W=벽/문틀  a=호선/얇은선  .=개방)")
    for i in range(0, len(cls), 60):
        seg = cls[i:i + 60]
        print(f"  x{x0 + i:>5}: {''.join(seg)}")

    # 호선 구간 추출
    doors = []
    i = 0
    while i < len(cls):
        if cls[i] == "a":
            j = i
            while j + 1 < len(cls) and cls[j + 1] == "a":
                j += 1
            length = j - i + 1
            # 문 후보: 호선 길이 4~16px (0.4~1.6 m), 양쪽 중 하나가 벽/문틀
            left_w = i > 0 and cls[i - 1] == "W"
            right_w = j + 1 < len(cls) and cls[j + 1] == "W"
            if 4 <= length <= 16 and (left_w or right_w):
                doors.append((x0 + i, x0 + j, length, left_w, right_w))
            i = j + 1
        else:
            i += 1

    print(f"\n문 후보 {len(doors)}개")
    if not doors:
        print("  없음 -> 이 벽에는 호선으로 표현된 문이 검출되지 않았다.")
    for s, e, L, lw, rw in doors:
        hinge = "좌측" if lw and not rw else ("우측" if rw and not lw else "양측벽")
        print(f"  x {s}..{e}  호선길이 {L}px = {L * SCALE:.2f} m  "
              f"중심 x={(s + e) / 2:.1f}  문틀 {hinge}")

    # 벽선 자체의 연속성도 함께 보고
    wall_dark = sum(1 for x in range(x0, x1 + 1) if px[x, wall_y] <= DARK)
    n = x1 - x0 + 1
    print(f"\n벽선(y={wall_y}) 연속성: {wall_dark}/{n} ({wall_dark / n * 100:.0f}%)")


if __name__ == "__main__":
    main()
