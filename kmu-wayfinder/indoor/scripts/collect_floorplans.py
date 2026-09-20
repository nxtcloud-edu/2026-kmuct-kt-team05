"""
P0-2: 미래관 평면도 원본 수집.

원칙
----
- 파일명 패턴으로 URL 을 추정하지 않는다. 공식 페이지 HTML 에서 실제 링크를 추출해
  첨부 목록(미래관_도면목록.json)과 대조한다.
- 다운로드 실패는 실패로 기록한다. 성공으로 바꾸지 않는다.
- 도면 개정일이 불명이면 null 로 둔다. HTTP Last-Modified 는 서버 파일 시각일 뿐
  도면 개정일이 아니므로 별도 필드에 보관한다.
- 웹 탭 이름 / 파일명 / 도면 내부 표기 / 서비스 층 ID 를 각각 다른 필드에 저장한다.
  canonical_floor_id 는 이 스크립트가 채우지 않는다 (현장/추가자료 대조 후 결정).

사용법
    python scripts/collect_floorplans.py

산출물
    data/raw/floorplans/<filename>          원본 (수정 금지)
    data/sources/manifest.json              수집 기록
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import pathlib
import re
import struct
import sys
import urllib.parse

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "floorplans"
SRC_DIR = ROOT / "data" / "sources"
MANIFEST = SRC_DIR / "manifest.json"

SOURCE_PAGE = "https://engineering.kookmin.ac.kr/engineering/etc/engineering-floor-guide.do"
CAMPUS_MAP_PAGE = (
    "https://www.kookmin.ac.kr/user/unIntr/campusGuide/bukakCampusGuide/index.do"
)
# 첨부된 도면 목록 (사용자 제공). 없으면 페이지 추출 결과만 사용한다.
ATTACHED_LIST = pathlib.Path(
    r"C:\Users\User\Documents\Codex\2026-09-20\ai-352\outputs\미래관_도면목록.json"
)

UA = "Mozilla/5.0 (campus-nav research; KMU capstone; contact=local)"


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def png_size(data: bytes) -> tuple[int | None, int | None]:
    """PNG IHDR 에서 픽셀 크기를 읽는다. PNG 가 아니면 (None, None)."""
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n":
        return None, None
    if data[12:16] != b"IHDR":
        return None, None
    w, h = struct.unpack(">II", data[16:24])
    return int(w), int(h)


def extract_page_assets(html: str) -> list[dict]:
    """페이지에서 미래관 도면 블록을 추출한다.

    구조:  <div class="fm-tab" onclick="fmFloor('mi-f3', this)">3층</div>
           <div class="fm-floor ..." id="mi-f3"><img src="...Mirae_3F.png" alt="미래관 3층">
    탭 id 를 매개로 탭 라벨과 이미지 src 를 연결한다.
    """
    tabs: dict[str, str] = {}
    for m in re.finditer(
        r"""fmFloor\(\s*['"](?P<tid>[^'"]+)['"]\s*,\s*this\s*\)\s*"\s*>\s*(?P<label>[^<]+)<""",
        html,
    ):
        tabs[m.group("tid")] = m.group("label").strip()

    assets: list[dict] = []
    for m in re.finditer(
        r"""<div[^>]*class="fm-floor[^"]*"[^>]*id="(?P<tid>[^"]+)"[^>]*>\s*"""
        r"""<img[^>]*src="(?P<src>[^"]+)"[^>]*alt="(?P<alt>[^"]*)""",
        html,
    ):
        tid, src, alt = m.group("tid"), m.group("src"), m.group("alt")
        if "Mirae" not in src:
            continue
        assets.append({
            "page_tab_id": tid,
            "source_tab_label": tabs.get(tid),
            "img_alt": alt,
            "url": urllib.parse.urljoin(SOURCE_PAGE, src),
            "filename": src.rsplit("/", 1)[-1],
        })
    return assets


def load_attached() -> dict[str, dict]:
    if not ATTACHED_LIST.exists():
        print(f"  ! 첨부 목록 없음: {ATTACHED_LIST}", file=sys.stderr)
        return {}
    with ATTACHED_LIST.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    return {a["filename"]: a for a in doc.get("assets", [])}


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    SRC_DIR.mkdir(parents=True, exist_ok=True)

    sess = requests.Session()
    sess.headers.update({"User-Agent": UA})

    print(f"공식 페이지 조회: {SOURCE_PAGE}")
    page_fetched_at = now_iso()
    try:
        resp = sess.get(SOURCE_PAGE, timeout=60)
        resp.raise_for_status()
        html = resp.text
        page_status = {"ok": True, "http_status": resp.status_code,
                       "bytes": len(resp.content),
                       "sha256": hashlib.sha256(resp.content).hexdigest()}
    except Exception as err:  # noqa: BLE001
        print(f"  ! 페이지 수집 실패: {err}", file=sys.stderr)
        html = ""
        page_status = {"ok": False, "error": str(err)}

    page_assets = extract_page_assets(html) if html else []
    print(f"  페이지에서 추출한 미래관 도면 링크: {len(page_assets)}개")

    attached = load_attached()
    print(f"  첨부 목록 항목: {len(attached)}개")

    records: list[dict] = []
    for pa in page_assets:
        att = attached.get(pa["filename"], {})
        url = pa["url"]
        rec: dict = {
            # --- 식별 ---
            "asset_id": f"mirae/{pa['filename']}",
            "building_name_official": "미래관",
            "campus_code": "S2",
            # --- 층 표기를 4종류로 분리 (합치지 않는다) ---
            "source_tab_label": pa["source_tab_label"],
            "page_tab_id": pa["page_tab_id"],
            "img_alt": pa["img_alt"],
            "source_filename": pa["filename"],
            "drawing_floor_label": att.get("drawing_floor_label"),
            "canonical_floor_id": None,
            "mapping_status": att.get("mapping_status", "pending_review"),
            # --- 출처 ---
            "source_page": SOURCE_PAGE,
            "url": url,
            "url_matches_attached_list": (att.get("url") == url) if att else None,
            # --- 수집 결과 ---
            "download_status": "not_attempted",
            "http_status": None,
            "bytes": None,
            "sha256": None,
            "width_px": None,
            "height_px": None,
            "local_path": None,
            "collected_at": None,
            "http_last_modified": None,
            "revision_date": None,   # 도면 개정일: 불명 -> null
            # --- 판독/검증 ---
            "inspection_status": att.get("inspection_status", "not_inspected"),
            "observed_room_labels": att.get("observed_room_labels", []),
            "field_verified": False,
            "usage_terms": "unknown",  # 재배포 조건 미확인
            "notes": [],
        }

        print(f"  다운로드: {pa['filename']} ({pa['source_tab_label']})")
        try:
            r = sess.get(url, timeout=120)
            rec["http_status"] = r.status_code
            r.raise_for_status()
            data = r.content
            out = RAW_DIR / pa["filename"]
            out.write_bytes(data)
            w, h = png_size(data)
            rec.update({
                "download_status": "ok",
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "width_px": w,
                "height_px": h,
                "local_path": str(out.relative_to(ROOT)).replace("\\", "/"),
                "collected_at": now_iso(),
                "http_last_modified": r.headers.get("Last-Modified"),
            })
            if w is None:
                rec["notes"].append("PNG IHDR 파싱 실패 - 이미지 형식 확인 필요")
            print(f"    ok  {len(data)} bytes  {w}x{h}")
        except Exception as err:  # noqa: BLE001
            rec["download_status"] = "failed"
            rec["notes"].append(f"download error: {err}")
            print(f"    ! 실패: {err}", file=sys.stderr)

        records.append(rec)

    # 첨부 목록에만 있고 페이지에서 못 찾은 항목
    page_names = {pa["filename"] for pa in page_assets}
    for fname, att in attached.items():
        if fname in page_names:
            continue
        records.append({
            "asset_id": f"mirae/{fname}",
            "source_filename": fname,
            "source_tab_label": att.get("source_tab_label"),
            "url": att.get("url"),
            "download_status": "not_attempted",
            "mapping_status": "not_found_on_page",
            "notes": ["첨부 목록에 있으나 공식 페이지 HTML 에서 링크를 찾지 못함"],
            "field_verified": False,
        })

    ok = sum(1 for r in records if r.get("download_status") == "ok")
    manifest = {
        "schema_version": "1.0.0",
        "generated_at": now_iso(),
        "source_page": SOURCE_PAGE,
        "source_page_fetched_at": page_fetched_at,
        "source_page_status": page_status,
        "campus_map_page": CAMPUS_MAP_PAGE,
        "attached_list_path": str(ATTACHED_LIST),
        "summary": {
            "expected": len(attached) or len(page_assets),
            "found_on_page": len(page_assets),
            "downloaded_ok": ok,
            "failed": sum(1 for r in records if r.get("download_status") == "failed"),
        },
        "caveats": [
            "canonical_floor_id 는 미결정(null). 웹 탭 이름/파일명으로 층을 확정하지 않는다.",
            "Mirae_B2_1.png(웹: 지하 2층-①) 내부 표기는 '지상 1층', "
            "Mirae_B2_2.png(웹: 지하 2층-②) 내부 표기는 '지상 2층'. 원인 미확인.",
            "두 B2 파일을 하나의 지하층 구역으로 병합하지 않는다.",
            "revision_date 는 도면 개정일이며 불명이면 null. "
            "http_last_modified 는 서버 파일 시각으로 개정일이 아니다.",
            "usage_terms=unknown. 앱에서 원본 재배포 가능 여부는 미확인.",
        ],
        "assets": records,
    }
    with MANIFEST.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)

    print(f"\n수집 성공 {ok}/{len(page_assets)}  -> {MANIFEST}")


if __name__ == "__main__":
    main()
