"""
벽 개구부(문/통로) 픽셀 검출.

도면에 문자 표기가 없으므로, 벽선을 따라 어두운 픽셀의 연속/끊김을 측정해
개구부를 객관적으로 찾는다.

교정 방법: 위치를 이미 아는 개구부(338호 남벽의 문 2개)로 임계값을 맞춘 뒤
판독하지 못한 벽(계단실 북벽)에 같은 기준을 적용한다.

사용법
    python scripts/probe_wall.py h Mirae_3F.png 900 1230 325 338   # 가로벽 스캔
    python scripts/probe_wall.py v Mirae_3F.png 1020 1030 240 430  # 세로벽 스캔
인자
    axis file x0 x1 y0 y1   (axis: h=가로벽, v=세로벽)
"""

from __future__ import annotations

import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "floorplans"

DARK = 128          # 이 값 이하를 선(line work) 으로 본다
MIN_GAP_PX = 4      # 이보다 짧은 끊김은 노이즈로 무시 (0.4 m 미만)
SCALE = 0.1008


def runs(flags: list[bool]) -> list[tuple[bool, int, int]]:
    """연속 구간을 (값, 시작, 끝포함) 목록으로."""
    out = []
    if not flags:
        return out
    cur, start = flags[0], 0
    for i in range(1, len(flags)):
        if flags[i] != cur:
            out.append((cur, start, i - 1))
            cur, start = flags[i], i
    out.append((cur, start, len(flags) - 1))
    return out


def scan(img: Image.Image, axis: str, a0: int, a1: int, b0: int, b1: int) -> None:
    px = img.convert("L").load()

    if axis == "h":
        # 가로벽: x 를 따라가며, y 범위 안에 어두운 픽셀이 하나라도 있으면 '벽 있음'
        along = range(a0, a1 + 1)
        def has_wall(x):
            return any(px[x, y] <= DARK for y in range(b0, b1 + 1))
        label_a, label_b = "x", "y"
    else:
        along = range(b0, b1 + 1)
        def has_wall(y):
            return any(px[x, y] <= DARK for x in range(a0, a1 + 1))
        label_a, label_b = "y", "x"

    flags = [has_wall(v) for v in along]
    base = along.start
    filled = sum(flags)
    print(f"스캔: axis={axis}  {label_a} {base}..{base + len(flags) - 1}  "
          f"({label_b} 두께 범위 {b0 if axis == 'h' else a0}..{b1 if axis == 'h' else a1})")
    print(f"  선 있음 {filled}/{len(flags)} px ({filled / len(flags) * 100:.0f}%)")

    gaps = [(s, e) for v, s, e in runs(flags)
            if not v and (e - s + 1) >= MIN_GAP_PX]
    if not gaps:
        print("  개구부 없음 (연속된 벽)")
        return
    print(f"  개구부 후보 {len(gaps)}개:")
    for s, e in gaps:
        w = e - s + 1
        print(f"    {label_a} {base + s} .. {base + e}   폭 {w}px = {w * SCALE:.2f} m")


def dump_row(img: Image.Image, y0: int, y1: int, x0: int, x1: int) -> None:
    """지정 영역의 그레이스케일 값을 표로 출력 (0=검정, 255=흰색)."""
    px = img.convert("L").load()
    print("      " + "".join(f"{x % 100:4d}" for x in range(x0, x1 + 1)))
    for y in range(y0, y1 + 1):
        row = "".join(f"{px[x, y]:4d}" for x in range(x0, x1 + 1))
        print(f"y={y:4d} {row}")


def main() -> None:
    if sys.argv[1] == "dump":
        fname = sys.argv[2]
        x0, x1, y0, y1 = (int(v) for v in sys.argv[3:7])
        img = Image.open(RAW / fname)
        print(f"{fname} {img.size[0]}x{img.size[1]}  영역 x{x0}-{x1} y{y0}-{y1}")
        dump_row(img, y0, y1, x0, x1)
        return
    if len(sys.argv) < 7:
        raise SystemExit(__doc__)
    axis, fname = sys.argv[1], sys.argv[2]
    x0, x1, y0, y1 = (int(v) for v in sys.argv[3:7])
    img = Image.open(RAW / fname)
    print(f"{fname} {img.size[0]}x{img.size[1]}")
    scan(img, axis, x0, x1, y0, y1)


if __name__ == "__main__":
    main()
