"""
도면 판독 보조: 원본 PNG 의 지정 영역을 확대해 저장한다.

원본은 수정하지 않는다. 결과는 data/work/crops/ 에 저장한다 (판독 작업용, 재배포 대상 아님).

사용법
    python scripts/crop_plan.py Mirae_3F.png 880 230 1260 400 --scale 3 --out 3f_338_337
    python scripts/crop_plan.py Mirae_3F.png --grid          # 좌표 격자 오버레이
"""

from __future__ import annotations

import argparse
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "floorplans"
OUT = ROOT / "data" / "work" / "crops"


def add_grid(
    img: Image.Image,
    step: int = 100,
    origin: tuple[int, int] = (0, 0),
    scale: float = 1.0,
) -> Image.Image:
    """픽셀 좌표 격자를 덧그린다 (판독용 사본).

    라벨은 항상 **원본 이미지 좌표**로 표시한다. crop/resize 된 사본 위에
    그릴 때 origin(크롭 좌상단)과 scale(확대배율)을 주면 원본 좌표계가 유지된다.
    """
    im = img.convert("RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    ox, oy = origin

    # 원본 좌표 기준 step 간격 -> 사본 픽셀 간격
    first_x = ((ox + step - 1) // step) * step
    x = first_x
    while (x - ox) * scale < w:
        px = int((x - ox) * scale)
        major = x % (step * 5) == 0
        d.line([(px, 0), (px, h)], fill=(255, 0, 0) if major else (255, 175, 175),
               width=2 if major else 1)
        if major:
            d.text((px + 3, 3), str(x), fill=(255, 0, 0))
        x += step

    first_y = ((oy + step - 1) // step) * step
    y = first_y
    while (y - oy) * scale < h:
        py = int((y - oy) * scale)
        major = y % (step * 5) == 0
        d.line([(0, py), (w, py)], fill=(0, 0, 255) if major else (175, 175, 255),
               width=2 if major else 1)
        if major:
            d.text((3, py + 3), str(y), fill=(0, 0, 255))
        y += step
    return im


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("filename")
    ap.add_argument("box", nargs="*", type=int, help="left top right bottom (픽셀)")
    ap.add_argument("--scale", type=float, default=3.0)
    ap.add_argument("--out", default=None)
    ap.add_argument("--grid", action="store_true", help="좌표 격자 오버레이")
    ap.add_argument("--grid-step", type=int, default=100)
    args = ap.parse_args()

    src = RAW / args.filename
    if not src.exists():
        raise SystemExit(f"원본 없음: {src}")
    OUT.mkdir(parents=True, exist_ok=True)

    img = Image.open(src)
    print(f"{args.filename}  원본 {img.size[0]}x{img.size[1]}  mode={img.mode}")

    if args.grid and not args.box:
        out = OUT / (args.out or (src.stem + "_grid"))
        add_grid(img, args.grid_step).save(out.with_suffix(".png"))
        print(f"저장: {out.with_suffix('.png')}")
        return

    if len(args.box) != 4:
        raise SystemExit("box 는 left top right bottom 4개 값이 필요합니다 (또는 --grid)")

    l, t, r, b = args.box
    crop = img.crop((l, t, r, b))
    if args.scale != 1.0:
        crop = crop.resize(
            (int(crop.width * args.scale), int(crop.height * args.scale)),
            Image.LANCZOS,
        )
    if args.grid:
        crop = add_grid(crop, args.grid_step, origin=(l, t), scale=args.scale)
    name = args.out or f"{src.stem}_{l}_{t}_{r}_{b}"
    out = (OUT / name).with_suffix(".png")
    crop.save(out)
    print(f"저장: {out}  ({crop.width}x{crop.height}, 원본영역 {l},{t}-{r},{b})")


if __name__ == "__main__":
    main()
