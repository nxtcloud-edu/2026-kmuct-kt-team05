"""data.js 의 건물/교차점 좌표를 새 좌표계로 선형 변환합니다.

배경 지도 이미지를 교체해서 크기가 바뀌었을 때 씁니다.
사용법:
    py tools/rescale_coords.py <이전W> <이전H> <새W> <새H>
예:
    py tools/rescale_coords.py 829 591 824 611
"""

import re, sys, pathlib

if len(sys.argv) != 5:
    raise SystemExit(__doc__)

ow, oh, nw, nh = (int(v) for v in sys.argv[1:5])
kx, ky = nw / ow, nh / oh

path = pathlib.Path(__file__).resolve().parent.parent / "js" / "data.js"
src = path.read_text(encoding="utf-8")

changed = []


def fix(m):
    x, y = int(m.group(1)), int(m.group(2))
    nx, ny = round(x * kx), round(y * ky)
    changed.append((x, y, nx, ny))
    return f"x: {nx}, y: {ny}"


out = re.sub(r"x:\s*(-?\d+),\s*y:\s*(-?\d+)", fix, src)
path.write_text(out, encoding="utf-8")

report = [
    f"배율  x {kx:.5f}  y {ky:.5f}",
    f"좌표 {len(changed)}개 변환",
]
report += [f"  ({a},{b}) -> ({c},{d})" for a, b, c, d in changed[:6]]
(pathlib.Path(__file__).parent / "_rescale.txt").write_text("\n".join(report), encoding="utf-8")
print("ok")
