"""배경 지도(assets/campusmap.png)에서 청록색 핀 마커의 위치를 검출합니다.

핀의 '뾰족한 아래 끝'이 실제 건물 위치이므로 그 좌표를 뽑습니다.
결과:
  tools/_pins.txt        검출된 좌표 목록
  tools/_pins_debug.png  번호를 붙인 확인용 이미지
"""

import pathlib, collections
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

img = Image.open(ROOT / "assets" / "campusmap.png").convert("RGB")
a = np.asarray(img).astype(np.int16)
H, W, _ = a.shape

R, G, B = a[:, :, 0], a[:, :, 1], a[:, :, 2]

# 네이버/카카오 지도 계열의 청록 핀: 초록이 빨강보다 훨씬 강하고 파랑도 높음
mask = (G - R > 45) & (G > 110) & (B > 95) & (R < 140) & (np.abs(G - B) < 75)

ys, xs = np.nonzero(mask)
print(f"후보 픽셀 {len(xs)}개")

# --- 연결 성분 묶기 (스택 기반 flood fill) ---
visited = np.zeros((H, W), dtype=bool)
clusters = []

for y0, x0 in zip(ys, xs):
    if visited[y0, x0]:
        continue
    stack = [(y0, x0)]
    visited[y0, x0] = True
    pts = []
    while stack:
        y, x = stack.pop()
        pts.append((y, x))
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if 0 <= ny < H and 0 <= nx < W and not visited[ny, nx] and mask[ny, nx]:
                    visited[ny, nx] = True
                    stack.append((ny, nx))
    if len(pts) >= 120:            # 잡티 제거
        clusters.append(pts)

print(f"성분 {len(clusters)}개")

pins = []
for pts in clusters:
    arr = np.array(pts)
    cy, cx = arr[:, 0], arr[:, 1]
    top, bottom = int(cy.min()), int(cy.max())
    left, right = int(cx.min()), int(cx.max())
    h, w = bottom - top + 1, right - left + 1

    # 핀 모양(세로가 가로보다 김)이 아니면 건너뜀
    if h < 14 or w < 10 or h / w < 0.9 or h / w > 2.6:
        continue

    # 아래쪽 10% 구간의 x 평균을 뾰족한 끝으로 봅니다
    tip_band = arr[cy >= bottom - max(2, h * 0.12)]
    tip_x = float(tip_band[:, 1].mean())

    pins.append({
        "x": round(tip_x, 1), "y": float(bottom),
        "cx": round(float(cx.mean()), 1), "cy": round(float(cy.mean()), 1),
        "w": w, "h": h, "px": len(pts),
    })

pins.sort(key=lambda p: (p["y"], p["x"]))

lines = [f"검출된 핀 {len(pins)}개  (이미지 {W}x{H})", ""]
lines += [
    f"{i:2d}. tip=({p['x']:.0f},{p['y']:.0f})  크기={p['w']}x{p['h']}  픽셀={p['px']}"
    for i, p in enumerate(pins)
]
(HERE / "_pins.txt").write_text("\n".join(lines), encoding="utf-8")

# --- 확인용 이미지 ---
dbg = img.copy()
d = ImageDraw.Draw(dbg)
try:
    font = ImageFont.truetype("arialbd.ttf", 15)
except Exception:
    font = ImageFont.load_default()

for i, p in enumerate(pins):
    x, y = p["x"], p["y"]
    d.line([(x - 9, y), (x + 9, y)], fill=(255, 0, 0), width=2)
    d.line([(x, y - 9), (x, y + 9)], fill=(255, 0, 0), width=2)
    d.text((x + 6, y - 20), str(i), fill=(200, 0, 0), font=font,
           stroke_width=3, stroke_fill=(255, 255, 255))

dbg.resize((W * 2, H * 2), Image.LANCZOS).save(HERE / "_pins_debug.png")
print("WROTE _pins.txt, _pins_debug.png")
