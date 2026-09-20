"""
표제부(title block) 몬타주: 각 도면의 내부 층 표기를 한 번에 대조한다.

웹 탭 이름/파일명이 아니라 **도면 안에 인쇄된 층 표기**를 읽기 위한 도구.

사용법
    python scripts/titleblock_montage.py
결과
    data/work/crops/titleblocks.png
"""

from __future__ import annotations

import json
import pathlib

from PIL import Image, ImageDraw

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "floorplans"
OUT = ROOT / "data" / "work" / "crops" / "titleblocks.png"
MANIFEST = ROOT / "data" / "sources" / "manifest.json"

# 표제부 위치 (3F 에서 확인: 오른쪽 아래). 도면별로 약간 다를 수 있어 넉넉히 잡는다.
BOX = (1400, 1040, 1684, 1130)
SCALE = 1.8
LABEL_W = 210
COLS = 2


def main() -> None:
    with MANIFEST.open(encoding="utf-8") as fh:
        man = json.load(fh)
    assets = [a for a in man["assets"] if a.get("download_status") == "ok"]

    tiles = []
    for a in assets:
        img = Image.open(RAW / a["source_filename"])
        crop = img.crop(BOX).convert("RGB")
        crop = crop.resize((int(crop.width * SCALE), int(crop.height * SCALE)), Image.LANCZOS)
        tiles.append((a, crop))

    tw = max(t.width for _, t in tiles)
    th = max(t.height for _, t in tiles)
    cell_w = LABEL_W + tw
    rows = (len(tiles) + COLS - 1) // COLS
    canvas = Image.new("RGB", (cell_w * COLS, th * rows), (255, 255, 255))
    d = ImageDraw.Draw(canvas)

    for i, (a, t) in enumerate(tiles):
        cx = (i % COLS) * cell_w
        cy = (i // COLS) * th
        canvas.paste(t, (cx + LABEL_W, cy))
        d.rectangle([(cx, cy), (cx + cell_w - 1, cy + th - 1)], outline=(200, 0, 0), width=2)
        d.text((cx + 6, cy + 8), f"web: {a.get('source_tab_label')}", fill=(0, 0, 200))
        d.text((cx + 6, cy + 26), f"{a['source_filename']}", fill=(0, 0, 0))
        d.text((cx + 6, cy + 44), f"{a.get('page_tab_id')}", fill=(90, 90, 90))
        d.text((cx + 6, cy + 62), f"{a.get('width_px')}x{a.get('height_px')}", fill=(90, 90, 90))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(OUT)
    print(f"저장: {OUT}  ({canvas.width}x{canvas.height}, {len(tiles)}장)")


if __name__ == "__main__":
    main()
