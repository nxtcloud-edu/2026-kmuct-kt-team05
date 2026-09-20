"""
캠퍼스 배치도에서 주석 알약(EV 3대, 지면 = 1F, 계단 24칸 등)을 지운 사본을 만든다.

왜 사본인가
    public/maps/campus.svg 는 팀원 Next.js 앱도 쓴다. 원본을 고치면 그쪽 화면이
    같이 바뀐다. 우리 UI 전용 정리본을 data/raw/navmaps/campus.svg 로 쓴다.
    demo/server.py 의 PLAN_DIRS 가 navmaps 를 먼저 보므로, 같은 이름이면
    우리 UI 에서는 정리본이 쓰이고 팀원 앱은 원본을 그대로 쓴다.

무엇을 지우는가
    지도 위에 인쇄된 설비 주석만 지운다. 건물 이름, 도로, 광장, 운동장 같은
    지리 정보는 남긴다. 경로 표시는 캔버스에 따로 그리므로 영향 없다.

    EV 5대 · 1F~16F     승강기 대수/정차층 알약
    지면 = 1F           지면 접합층 알약
    계단 24칸           계단 단수 알약
    2F~4F, B1~5F        연결 층범위 알약

사용법
    python scripts/clean_campus_svg.py
    python scripts/clean_campus_svg.py --dry-run
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]

#: 원본 배치도. data/upstream/ 사본을 먼저 보고, 없으면 저장소 루트의
#: 팀원 앱 자산을 본다. 배포 브랜치에는 팀원 앱이 없으므로 사본이 필요하다.
def _src_svg() -> pathlib.Path:
    up = ROOT / "data" / "upstream" / "campus.svg"
    return up if up.exists() else ROOT.parent / "public" / "maps" / "campus.svg"


SRC = _src_svg()
DST = ROOT / "data" / "raw" / "navmaps" / "campus.svg"

#: 이 문구를 담은 <g> 묶음을 통째로 지운다 (알약 배경 rect 까지 함께).
DROP_TEXT = [
    re.compile(r"EV\s*\d+\s*대"),
    re.compile(r"지면\s*="),
    re.compile(r"계단\s*\d+\s*칸"),
    re.compile(r"^\s*B?\d+F\s*~\s*B?\d+F\s*$"),   # 2F~4F, B1~5F
    re.compile(r"^\s*B?\d+F\s*↔\s*B?\d+F\s*$"),   # B1 ↔ 1F
]

TEXT_RE = re.compile(r"<text\b[^>]*>(.*?)</text>", re.S)


def inner_texts(block: str) -> list[str]:
    return [re.sub(r"<[^>]+>", "", t).strip() for t in TEXT_RE.findall(block)]


def should_drop(block: str) -> bool:
    texts = inner_texts(block)
    if not texts:
        return False
    # 묶음 안의 텍스트가 모두 주석이어야 지운다.
    # 건물 이름이 섞인 묶음은 건드리지 않는다.
    return all(any(p.search(t) for p in DROP_TEXT) for t in texts)


def find_group_end(s: str, start: int) -> int:
    """start 가 가리키는 <g ...> 의 대응 </g> 끝 위치."""
    depth = 0
    i = start
    n = len(s)
    while i < n:
        if s.startswith("<g", i) and (i + 2 < n and s[i + 2] in " >\t\n"):
            depth += 1
            i += 2
            continue
        if s.startswith("</g>", i):
            depth -= 1
            i += 4
            if depth == 0:
                return i
            continue
        i += 1
    return -1


def clean(s: str) -> tuple[str, list[str]]:
    removed: list[str] = []
    out = []
    i = 0
    n = len(s)
    while i < n:
        if s.startswith("<g", i) and (i + 2 < n and s[i + 2] in " >\t\n"):
            end = find_group_end(s, i)
            if end == -1:
                out.append(s[i])
                i += 1
                continue
            block = s[i:end]
            # 중첩 묶음은 안쪽부터 판단해야 하므로, 자식이 있으면 재귀한다.
            if block.count("<g") > 1:
                head_end = s.index(">", i) + 1
                inner, rm = clean(s[head_end:end - 4])
                removed.extend(rm)
                out.append(s[i:head_end] + inner + "</g>")
            elif should_drop(block):
                removed.extend(inner_texts(block))
            else:
                out.append(block)
            i = end
            continue
        out.append(s[i])
        i += 1
    return "".join(out), removed


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--dst", default=str(DST))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    src = pathlib.Path(args.src)
    if not src.exists():
        raise SystemExit(f"원본 배치도가 없다: {src}")
    s = src.read_text(encoding="utf-8")
    cleaned, removed = clean(s)

    print(f"원본 : {src}  {len(s):,}자")
    print(f"정리 : {len(cleaned):,}자  ({len(s)-len(cleaned):,}자 감소)")
    print(f"지운 주석 {len(removed)}개")
    seen = []
    for t in removed:
        if t not in seen:
            seen.append(t)
    for t in seen[:20]:
        print(f"  - {t}")
    if len(seen) > 20:
        print(f"  ... 그 외 {len(seen)-20}종")

    # 남아 있어야 하는 것 확인
    for keep in ("조형관", "운동장", "미래관"):
        if keep in s and keep not in cleaned:
            raise SystemExit(f"[중단] '{keep}' 이 사라졌다. 지리 정보를 지우면 안 된다.")
    print("건물명·지형 유지 확인: 조형관/운동장/미래관 남아 있음")

    if args.dry_run:
        print("dry-run: 파일을 쓰지 않았다.")
        return
    dst = pathlib.Path(args.dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(cleaned, encoding="utf-8")
    print(f"저장 : {dst}")
    print("팀원 앱의 public/maps/campus.svg 는 그대로다.")


if __name__ == "__main__":
    main()
