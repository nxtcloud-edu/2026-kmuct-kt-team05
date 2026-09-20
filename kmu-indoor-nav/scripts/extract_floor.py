"""
미래관 상층부(3~7층) 실내 그래프 자동 추출.

미래관은 선형 슬래브이고 3~7층이 같은 도면 프레임을 쓴다 (벽선 y 좌표 일치).
구조:
    북측 실열   y 252..333
    북측 복도   y 336..360   센터라인 348
    중앙 실열   y 363..558
    남측 복도   y 561..591   센터라인 576
    남측 실열   y 594..676

파이프라인
    1) 복도에 면한 4개 벽선에서 문(호선) 자동 검출
    2) OCR 호실 라벨과 문을 매칭 (같은 실열 + x 근접)
    3) 복도 센터라인 체인 + 문앞 분기점 생성
    4) 남북 복도 연결 통로 검출 (중앙 실열의 세로 빈 구간)
    5) 층별 JSON 조각 출력

사용법
    python scripts/extract_floor.py Mirae_3F.png mirae/F3
    python scripts/extract_floor.py --all
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys

from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "floorplans"
OCR_DIR = ROOT / "data" / "work" / "ocr"
OUT_DIR = ROOT / "data" / "work" / "extracted"

DARK = 140
SCALE = 0.1008

# 도면 유효 영역 (치수선·표제부 제외)
X_MIN, X_MAX = 250, 1400

# 복도에 면한 벽 정의: (벽 y, 실내 방향, 실열 이름, 실열 y범위, 복도 센터라인 y)
WALLS = [
    (333, "up",   "north", (252, 332), 348),
    (361, "down", "middle_n", (364, 460), 348),
    (558, "up",   "middle_s", (460, 557), 576),
    (592, "down", "south", (595, 676), 576),
]
CORRIDORS = {348: (336, 360), 576: (561, 591)}

ROOM_RE = re.compile(r"^(\d{3}(?:-\d)?)$")


# ------------------------------------------------------------- OCR 라벨
def load_labels(stem: str) -> list[tuple[str, int, int]]:
    """OCR 결과에서 호실 번호 라벨 (번호, x, y) 추출."""
    p = OCR_DIR / f"{stem}.txt"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.startswith("LINE"):
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        for tok in parts[2].split():
            if "@" not in tok:
                continue
            text, _, pos = tok.rpartition("@")
            m = ROOM_RE.match(text.strip())
            if not m:
                continue
            try:
                x, y = (int(v) for v in pos.split(","))
            except ValueError:
                continue
            out.append((m.group(1), x, y))
    return out


# ------------------------------------------------------------- 문 검출
def detect_doors(px, wall_y: int, side: str, band: int = 12) -> list[dict]:
    ys = (range(wall_y - band, wall_y) if side == "up"
          else range(wall_y + 1, wall_y + 1 + band))
    cls = []
    for x in range(X_MIN, X_MAX + 1):
        c = sum(1 for y in ys if px[x, y] <= DARK)
        cls.append("W" if c >= band * 0.7 else ("a" if c >= 1 else "."))

    doors = []
    i = 0
    while i < len(cls):
        if cls[i] != "a":
            i += 1
            continue
        j = i
        while j + 1 < len(cls) and cls[j + 1] == "a":
            j += 1
        L = j - i + 1
        lw = i > 0 and cls[i - 1] == "W"
        rw = j + 1 < len(cls) and cls[j + 1] == "W"
        if 4 <= L <= 16 and (lw or rw):
            doors.append({
                "x0": X_MIN + i, "x1": X_MIN + j,
                "cx": round(X_MIN + (i + j) / 2, 1),
                "width_m": round(L * SCALE, 2),
                "wall_y": wall_y, "side": side,
            })
        i = j + 1
    return doors


# ------------------------------------------------------- 남북 복도 연결
def find_cross_passages(px) -> list[float]:
    """중앙 실열(y 364..557)에서 세로로 벽이 없는 x = 남북 복도 연결 통로."""
    open_x = []
    for x in range(X_MIN, X_MAX + 1):
        dark = sum(1 for y in range(364, 558) if px[x, y] <= DARK)
        if dark <= 2:            # 거의 비어 있음
            open_x.append(x)
    # 연속 구간을 하나의 통로로
    passages = []
    if not open_x:
        return passages
    s = open_x[0]
    prev = open_x[0]
    for x in open_x[1:]:
        if x - prev > 2:
            if prev - s + 1 >= 8:           # 0.8 m 이상
                passages.append(round((s + prev) / 2, 1))
            s = x
        prev = x
    if prev - s + 1 >= 8:
        passages.append(round((s + prev) / 2, 1))
    return passages


# ------------------------------------------------------------- 매칭
def match_room(door: dict, labels: list[tuple[str, int, int]],
               band: tuple[int, int]) -> str | None:
    """문과 같은 실열에 있고 x 가 가장 가까운 호실 라벨."""
    lo, hi = band
    cands = [(abs(x + 18 - door["cx"]), num)
             for num, x, y in labels if lo <= y <= hi]
    if not cands:
        return None
    cands.sort()
    # 30px(3m) 이상 떨어지면 매칭하지 않는다
    return cands[0][1] if cands[0][0] <= 60 else None


# ------------------------------------------------------------- 추출
def extract(fname: str, floor_id: str) -> dict:
    img = Image.open(RAW / fname)
    px = img.convert("L").load()
    stem = pathlib.Path(fname).stem
    labels = load_labels(stem)

    print(f"\n=== {fname} -> {floor_id} ===")
    print(f"  OCR 호실 라벨 {len(labels)}개")

    all_doors = []
    for wall_y, side, band_name, band, corr_y in WALLS:
        ds = detect_doors(px, wall_y, side)
        for d in ds:
            d["band"] = band_name
            d["corridor_y"] = corr_y
            d["room"] = match_room(d, labels, band)
        matched = sum(1 for d in ds if d["room"])
        print(f"  벽 y={wall_y:>3} ({band_name:<8}): 문 {len(ds):>2}개, "
              f"호실 매칭 {matched}개")
        all_doors += ds

    passages = find_cross_passages(px)
    print(f"  남북 복도 연결 통로 {len(passages)}개: {passages}")

    return {
        "floor_id": floor_id, "source": fname,
        "doors": all_doors, "cross_passages": passages,
        "corridors": {str(k): v for k, v in CORRIDORS.items()},
        "label_count": len(labels),
    }


FLOORS = [
    ("Mirae_3F.png", "mirae/F3"),
    ("Mirae_4F.png", "mirae/F4"),
    ("Mirae_5F.png", "mirae/F5"),
    ("Mirae_6F.png", "mirae/F6"),
    ("Mirae_7F.png", "mirae/F7"),
]


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    targets = FLOORS if (len(sys.argv) > 1 and sys.argv[1] == "--all") \
        else [(sys.argv[1], sys.argv[2])]
    for fname, fid in targets:
        res = extract(fname, fid)
        p = OUT_DIR / f"{fid.replace('/', '_')}.json"
        with p.open("w", encoding="utf-8") as fh:
            json.dump(res, fh, ensure_ascii=False, indent=2)
        rooms = sorted({d["room"] for d in res["doors"] if d["room"]})
        print(f"  매칭된 호실: {', '.join(rooms) if rooms else '없음'}")
        print(f"  저장: {p.name}")


if __name__ == "__main__":
    main()
