"""
P0-2 보강: 도면 내부 층 표기를 OCR 로 판독해 manifest 에 기록한다.

Windows.Media.Ocr (ko) 로 표제부를 읽는다. scripts/ocr_win.ps1 참고.
웹 탭 이름/파일명과 **분리된 필드**에 저장하고 canonical_floor_id 는 건드리지 않는다.

사용법
    python scripts/record_floor_labels.py
"""

from __future__ import annotations

import datetime as _dt
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "sources" / "manifest.json"
CROP = ROOT / "scripts" / "crop_plan.py"
OCR = ROOT / "scripts" / "ocr_win.ps1"
CROPS = ROOT / "data" / "work" / "crops"

# 표제부는 도면마다 위치가 약간 달라 두 범위를 순차 시도한다.
BOXES = [(1400, 1040, 1684, 1130), (1300, 1000, 1684, 1150)]
FLOOR_RE = re.compile(r"(지상|지하)\s*(\d+)\s*층")


def run(cmd: list[str]) -> str:
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT)
    return (p.stdout or "") + (p.stderr or "")


def read_label(fname: str) -> tuple[str | None, str]:
    """(판독된 층 표기, 판독 방법 기록)"""
    for i, box in enumerate(BOXES):
        out_name = f"tb{i}_{pathlib.Path(fname).stem}"
        run([sys.executable, str(CROP), fname, *map(str, box),
             "--scale", "2.4", "--out", out_name])
        crop = CROPS / f"{out_name}.png"
        if not crop.exists():
            continue
        txt = run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(OCR),
                   "-Path", str(crop.relative_to(ROOT)), "-Lang", "ko",
                   "-Upscale", "3.0"])
        for line in txt.splitlines():
            if not line.startswith("LINE"):
                continue
            m = FLOOR_RE.search(line)
            if m:
                return (f"{m.group(1)} {m.group(2)}층",
                        f"windows-media-ocr-ko crop={box} upscale=3.0")
    return None, "ocr_failed"


def main() -> None:
    with MANIFEST.open(encoding="utf-8") as fh:
        man = json.load(fh)

    now = _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    print(f"{'web 탭':<14} {'파일':<18} {'OCR 판독':<10} {'기존 기록':<10} 일치")
    print("-" * 70)

    for a in man["assets"]:
        if a.get("download_status") != "ok":
            continue
        label, method = read_label(a["source_filename"])
        prev = a.get("drawing_floor_label")
        a["drawing_floor_label_ocr"] = label
        a["drawing_floor_label_ocr_method"] = method
        a["drawing_floor_label_ocr_at"] = now
        # 기존 기록이 없으면 OCR 결과를 초안으로 채운다 (canonical 은 여전히 null)
        if prev is None and label:
            a["drawing_floor_label"] = label
            a["inspection_status"] = "ocr_title_block"
        elif label and prev:
            norm = lambda s: s.replace(" ", "")
            a["drawing_floor_label_agrees"] = norm(prev) == norm(label)
        # 웹 탭 이름과 도면 표기 비교
        tab = (a.get("source_tab_label") or "").replace(" ", "")
        if label and norm_tab(tab) != norm_tab(label):
            a["mapping_status"] = "source_label_conflict" \
                if a.get("mapping_status") != "not_found_on_page" else a["mapping_status"]
        agree = a.get("drawing_floor_label_agrees")
        print(f"{a.get('source_tab_label','?'):<14} {a['source_filename']:<18} "
              f"{str(label):<10} {str(prev):<10} {agree}")

    man["floor_label_ocr"] = {
        "engine": "Windows.Media.Ocr",
        "language": "ko",
        "recorded_at": now,
        "note": "도면 내부 표기만 기록. 서비스 층 ID(canonical_floor_id)는 여전히 null.",
    }
    with MANIFEST.open("w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2)
    print(f"\n기록: {MANIFEST}")


def norm_tab(s: str) -> str:
    """'3층' vs '지상 3층' 비교용 정규화. 지하/지상 접두어를 살린 채 공백만 제거."""
    return s.replace(" ", "")


if __name__ == "__main__":
    main()
