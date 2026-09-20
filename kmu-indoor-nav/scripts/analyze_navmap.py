"""
내비게이션맵 시안 분석 + 원본 도면과의 좌표 정합.

시안(data/raw/navmaps/nav_*.png)은 원본 도면을 단순화한 재렌더링이라
좌표계가 원본(1684x1191)과 다르다. 경로를 시안 위에 그리려면 변환이 필요하다.

방법
    1) 두 이미지에서 '건물 외곽 bbox' 를 각자 검출
       - 원본: 도면 영역(치수선/표제부 제외) 안의 어두운 픽셀 bbox
       - 시안: 배경(흰색)이 아닌 픽셀 bbox
    2) bbox 대응으로 scale + offset (축별 독립 affine) 산출
    3) **검증**: 내 복도 센터라인 노드를 변환했을 때
       시안의 '이동 공간(민트)' 색 위에 얼마나 떨어지는지 비율을 측정
       -> 이 비율이 정합 품질의 객관적 지표

사용법
    python scripts/analyze_navmap.py            # 전층 분석 + 정합 산출
    python scripts/analyze_navmap.py --colors   # 색상 팔레트만 출력
"""

from __future__ import annotations

import collections
import json
import pathlib
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
NAV = ROOT / "data" / "raw" / "navmaps"
RAW = ROOT / "data" / "raw" / "floorplans"
OUT = ROOT / "data" / "curated" / "navmap_registration.json"

# 원본 도면에서 건물이 그려진 영역 (치수선·표제부·그리드축 제외)
ORIG_CLIP = (250, 150, 1500, 800)

PAIRS = [
    ("nav_3F.png", "Mirae_3F.png", "mirae/F3"),
    ("nav_4F.png", "Mirae_4F.png", "mirae/F4"),
    ("nav_5F.png", "Mirae_5F.png", "mirae/F5"),
    ("nav_6F.png", "Mirae_6F.png", "mirae/F6"),
    ("nav_7F.png", "Mirae_7F.png", "mirae/F7"),
    ("nav_2F.png", "Mirae_B2_2.png", "mirae/DRAWING-2F"),
    ("nav_1F.png", "Mirae_B2_1.png", "mirae/DRAWING-1F"),
]


def palette(img: Image.Image, top: int = 12) -> list[tuple[tuple[int, int, int], int]]:
    small = img.convert("RGB").resize((img.width // 3, img.height // 3), Image.NEAREST)
    cnt = collections.Counter(small.getdata())
    return cnt.most_common(top)


def is_bg(c: tuple[int, int, int]) -> bool:
    r, g, b = c[:3]
    return r > 245 and g > 245 and b > 245


def content_bbox_nav(img: Image.Image) -> tuple[int, int, int, int]:
    """시안: 배경(흰색) 아닌 픽셀의 bbox."""
    px = img.convert("RGB").load()
    W, H = img.size
    step = 2
    xs, ys = [], []
    for y in range(0, H, step):
        for x in range(0, W, step):
            if not is_bg(px[x, y]):
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def content_bbox_orig(img: Image.Image) -> tuple[int, int, int, int]:
    """원본: 지정 영역 안의 어두운 픽셀 bbox."""
    px = img.convert("L").load()
    x0, y0, x1, y1 = ORIG_CLIP
    xs, ys = [], []
    for y in range(y0, y1, 2):
        for x in range(x0, x1, 2):
            if px[x, y] <= 140:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def fit(orig_bb, nav_bb) -> dict:
    ox0, oy0, ox1, oy1 = orig_bb
    nx0, ny0, nx1, ny1 = nav_bb
    sx = (nx1 - nx0) / max(1, ox1 - ox0)
    sy = (ny1 - ny0) / max(1, oy1 - oy0)
    return {"sx": round(sx, 6), "sy": round(sy, 6),
            "tx": round(nx0 - ox0 * sx, 3), "ty": round(ny0 - oy0 * sy, 3),
            "orig_bbox": list(orig_bb), "nav_bbox": list(nav_bb)}


def apply(tr: dict, x: float, y: float) -> tuple[float, float]:
    return x * tr["sx"] + tr["tx"], y * tr["sy"] + tr["ty"]


def classify(c) -> str:
    r, g, b = c[:3]
    if is_bg(c):
        return "bg"
    if b > 150 and b - r > 40 and b - g > 20:
        return "elevator"      # 파랑
    if r > 190 and 90 < g < 200 and b < 130:
        return "stairs"        # 주황
    if g > 140 and g - r > 40 and g - b > 25:
        return "entrance"      # 초록
    if g > 200 and b > 200 and r < 235 and min(g, b) - r > 8:
        return "walk"          # 연한 민트
    if abs(r - g) < 14 and abs(g - b) < 14 and 120 < r < 235:
        return "gray"          # 주차/차량
    return "other"


def validate(nav_img: Image.Image, tr: dict, pts: list[tuple[float, float]]) -> dict:
    px = nav_img.convert("RGB").load()
    W, H = nav_img.size
    hits = collections.Counter()
    for x, y in pts:
        nx, ny = apply(tr, x, y)
        ix, iy = int(round(nx)), int(round(ny))
        if not (0 <= ix < W and 0 <= iy < H):
            hits["out_of_image"] += 1
            continue
        # 3x3 이웃 중 하나라도 walk 면 적중으로 본다 (선 굵기 오차 허용)
        found = None
        for dy in (-2, 0, 2):
            for dx in (-2, 0, 2):
                jx, jy = min(W - 1, max(0, ix + dx)), min(H - 1, max(0, iy + dy))
                k = classify(px[jx, jy])
                if k in ("walk", "elevator", "stairs", "entrance"):
                    found = k
                    break
            if found:
                break
        hits[found or "miss"] += 1
    total = sum(hits.values()) or 1
    ok = sum(v for k, v in hits.items()
             if k in ("walk", "elevator", "stairs", "entrance"))
    return {"samples": total, "on_walkable": ok,
            "ratio": round(ok / total, 3), "detail": dict(hits)}


def corridor_points(floor_id: str) -> list[tuple[float, float]]:
    """전층 그래프에서 해당 층의 복도/문 노드 좌표."""
    p = ROOT / "data" / "demo" / "mirae_full_v1.json"
    if not p.exists():
        return []
    with p.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    return [(n["plan_point"]["x_px"], n["plan_point"]["y_px"])
            for n in doc["nodes"]
            if n.get("floor_id") == floor_id and n.get("plan_point")]


def main() -> None:
    if "--colors" in sys.argv:
        for f in sorted(NAV.glob("nav_*.png")):
            img = Image.open(f)
            print(f"\n{f.name}  {img.size[0]}x{img.size[1]}")
            for c, n in palette(img):
                print(f"   rgb{c}  {n:>7}  -> {classify(c)}")
        return

    reg = {}
    print(f"{'층':<20} {'시안 bbox':<26} {'원본 bbox':<26} "
          f"{'scale':<16} {'정합 적중률'}")
    print("-" * 110)
    for navf, origf, fid in PAIRS:
        np_, op = NAV / navf, RAW / origf
        if not np_.exists() or not op.exists():
            print(f"{fid:<20} (파일 없음: {navf if not np_.exists() else origf})")
            continue
        nav_img, orig_img = Image.open(np_), Image.open(op)
        nb = content_bbox_nav(nav_img)
        ob = content_bbox_orig(orig_img)
        tr = fit(ob, nb)
        pts = corridor_points(fid)
        v = validate(nav_img, tr, pts) if pts else {"ratio": None, "samples": 0}
        reg[fid] = {"nav_image": navf, "orig_image": origf,
                    "nav_size": list(nav_img.size),
                    "transform": tr, "validation": v}
        print(f"{fid:<20} {str(nb):<26} {str(ob):<26} "
              f"sx={tr['sx']:.3f} sy={tr['sy']:.3f}  "
              f"{v['ratio']} ({v['samples']}점)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump({"note": "시안 좌표계 <- 원본 도면 좌표계 변환. "
                           "시안은 단순화 재렌더링이라 완전 일치하지 않는다.",
                   "registration": reg}, fh, ensure_ascii=False, indent=2)
    print(f"\n저장: {OUT}")


if __name__ == "__main__":
    main()
