"""
파트 병합기: 여러 사람이 만든 그래프 조각을 하나로 합친다.

왜 필요한가
-----------
그래프를 단일 JSON 한 파일로 두면 팀원 A가 공학관, B가 실외를 작업할 때
같은 파일을 고치게 되어 git 충돌이 난다. 그래서 **파트 단위로 파일을 분리**하고
빌드 시점에 합친다. 각자 자기 파일만 건드리므로 충돌이 없다.

디렉터리 규약
-------------
    data/parts/<part-id>.json      건물/지역 1개 단위. 담당자가 소유
    data/links/<link-id>.json      파트 사이를 잇는 연결만 따로 선언
    data/published/campus_v1.json  병합 산출물 (직접 편집 금지)

ID 네임스페이스 규칙 (병합기가 강제한다)
----------------------------------------
파트 안의 모든 id 는 `<namespace>` 로 시작해야 한다.
    mirae.json    -> namespace "mirae/"   ex) mirae/F3/338, mirae/ev/1
    gonghak.json  -> namespace "gonghak/" ex) gonghak/F3/352
    outdoor.json  -> namespace "outdoor/" ex) outdoor/n/1024

이 규칙 덕분에 서로 다른 파트가 우연히 같은 id 를 쓸 수 없다.

파트 간 연결은 links 파일에만 쓴다
----------------------------------
실외 ↔ 건물 출입구처럼 파트를 넘는 엣지는 파트 파일에 쓰지 않는다.
양쪽 파트가 서로를 수정해야 하므로 충돌이 나기 때문이다.
대신 `data/links/` 에 별도 파일로 선언하고, 병합기가 양쪽 노드가 실제로
존재하는지 검사한다.

사용법
    python scripts/merge_graphs.py                      # 전체 병합
    python scripts/merge_graphs.py --check              # 검사만 (CI 용)
    python scripts/merge_graphs.py --parts mirae outdoor
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PARTS = ROOT / "data" / "parts"
LINKS = ROOT / "data" / "links"
OUT = ROOT / "data" / "published" / "campus_v1.json"

COLLECTIONS = ("buildings", "floorplans", "floors", "places",
               "nodes", "edges", "elevators", "closures")

#: 파트 파일에서 이 필드는 네임스페이스 검사 대상
ID_FIELDS = {
    "buildings": ["id"],
    "floorplans": ["id"],
    "floors": ["id", "building_id", "plan_id"],
    "places": ["id", "building_id", "floor_id"],
    "nodes": ["id", "building_id", "floor_id", "facility_id"],
    "edges": ["id", "from_node", "to_node", "facility_id",
              "elevator_from_floor", "elevator_to_floor"],
    "elevators": ["id", "building_id"],
    "closures": ["id"],
}


class MergeError(Exception):
    pass


def load_part(p: pathlib.Path) -> dict:
    with p.open(encoding="utf-8") as fh:
        doc = json.load(fh)
    meta = doc.get("part")
    if not meta:
        raise MergeError(f"{p.name}: 'part' 메타 블록이 없습니다. "
                         f"_TEMPLATE.json 을 참고하세요.")
    pid = meta.get("id")
    ns = meta.get("namespace")
    if not pid or not ns:
        raise MergeError(f"{p.name}: part.id / part.namespace 가 필요합니다.")
    if p.stem != pid:
        raise MergeError(f"{p.name}: 파일명과 part.id 가 다릅니다 "
                         f"(파일 '{p.stem}' vs id '{pid}')")
    if not ns.endswith("/"):
        raise MergeError(f"{p.name}: namespace 는 '/' 로 끝나야 합니다: {ns!r}")
    return doc


def check_namespace(doc: dict, name: str) -> list[str]:
    """네임스페이스 위반 목록.

    허용 형태는 두 가지다.
      - `<ns>...`          예: namespace "mirae/" 에서 "mirae/F3/338"
      - `<ns 의 루트>`     예: "mirae"  (건물 id 처럼 네임스페이스 자체를 가리킬 때)
    """
    ns = doc["part"]["namespace"]
    root = ns.rstrip("/")
    bad: list[str] = []

    def ok(v: str) -> bool:
        return v == root or v.startswith(ns)

    for coll, fields in ID_FIELDS.items():
        for item in doc.get(coll, []):
            for f in fields:
                v = item.get(f)
                if not isinstance(v, str) or not v:
                    continue
                if not ok(v):
                    bad.append(f"{name}:{coll}[{item.get('id','?')}].{f} = {v!r} "
                               f"('{ns}' 또는 '{root}' 로 시작해야 함)")
    # plan 좌표공간도 검사
    for n in doc.get("nodes", []):
        pp = n.get("plan_point")
        if pp and not str(pp.get("coordinate_space", "")).startswith(f"plan:{ns}"):
            bad.append(f"{name}:nodes[{n.get('id')}].plan_point.coordinate_space = "
                       f"{pp.get('coordinate_space')!r} (plan:{ns}... 이어야 함)")
    return bad


def merge(part_files: list[pathlib.Path], link_files: list[pathlib.Path],
          strict: bool = True) -> tuple[dict, list[str]]:
    merged: dict[str, list] = {c: [] for c in COLLECTIONS}
    seen_ids: dict[str, str] = {}      # id -> 출처
    problems: list[str] = []
    parts_meta = []
    namespaces: dict[str, str] = {}

    for p in part_files:
        doc = load_part(p)
        meta = doc["part"]
        ns = meta["namespace"]
        if ns in namespaces:
            problems.append(f"네임스페이스 중복: '{ns}' 를 "
                            f"{namespaces[ns]} 와 {p.name} 이 함께 사용")
        namespaces[ns] = p.name

        problems += check_namespace(doc, p.name)

        counts = {}
        for coll in COLLECTIONS:
            items = doc.get(coll, [])
            counts[coll] = len(items)
            for it in items:
                iid = it.get("id")
                if iid:
                    if iid in seen_ids:
                        problems.append(f"id 충돌: {iid!r} "
                                        f"({seen_ids[iid]} / {p.name})")
                    seen_ids[iid] = p.name
            merged[coll] += items

        parts_meta.append({
            "id": meta["id"], "namespace": ns,
            "kind": meta.get("kind"), "owner": meta.get("owner"),
            "source_graph_version": doc.get("graph_version"),
            "verification_scope": doc.get("verification_scope", {}),
            "counts": counts,
        })

    # --- 파트 간 연결 ---
    node_ids = {n["id"] for n in merged["nodes"]}
    link_count = 0
    for lf in link_files:
        with lf.open(encoding="utf-8") as fh:
            ldoc = json.load(fh)
        for e in ldoc.get("links", []):
            eid = e.get("id")
            if not eid:
                problems.append(f"{lf.name}: id 없는 link")
                continue
            if eid in seen_ids:
                problems.append(f"id 충돌(link): {eid!r} "
                                f"({seen_ids[eid]} / {lf.name})")
            seen_ids[eid] = lf.name
            for side in ("from_node", "to_node"):
                ref = e.get(side)
                if ref not in node_ids:
                    problems.append(f"{lf.name}:{eid}.{side} = {ref!r} "
                                    f"-> 어느 파트에도 없는 노드")
            ns_from = e.get("from_node", "").split("/")[0]
            ns_to = e.get("to_node", "").split("/")[0]
            if ns_from == ns_to:
                problems.append(f"{lf.name}:{eid} 은 같은 파트 내부 연결입니다. "
                                f"links 가 아니라 파트 파일에 넣으세요.")
            merged["edges"].append(e)
            # 역방향이 필요하면 links 파일에 명시적으로 쓴다 (자동 생성하지 않음)
            link_count += 1

    if problems and strict:
        raise MergeError("병합 검사 실패:\n  - " + "\n  - ".join(problems))

    now = _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")
    scopes = [pm["verification_scope"] for pm in parts_meta]
    doc = {
        "graph_version": "campus-v1",
        "schema_version": "1.0.0",
        "generated_at": now,
        "composed_from": parts_meta,
        "cross_part_links": link_count,
        "verification_scope": {
            # 하나라도 미검증이면 전체를 미검증으로 본다
            "field_verified": all(s.get("field_verified") is True for s in scopes) if scopes else False,
            "wheelchair_accessible_routes_certified": all(
                s.get("wheelchair_accessible_routes_certified") is True for s in scopes) if scopes else False,
            "parts": [pm["id"] for pm in parts_meta],
            "evidence_level": " / ".join(
                f"{pm['id']}: {pm['verification_scope'].get('evidence_level','-')}"
                for pm in parts_meta),
        },
        "notes": ["scripts/merge_graphs.py 산출물. 직접 편집하지 말고 "
                  "data/parts/ 와 data/links/ 를 고치세요."],
        **merged,
    }
    return doc, problems


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="검사만 하고 쓰지 않음")
    ap.add_argument("--parts", nargs="*", help="특정 파트만 병합")
    ap.add_argument("--allow-problems", action="store_true",
                    help="문제가 있어도 병합 (개발 중에만)")
    args = ap.parse_args()

    PARTS.mkdir(parents=True, exist_ok=True)
    LINKS.mkdir(parents=True, exist_ok=True)

    pfs = sorted(p for p in PARTS.glob("*.json") if not p.stem.startswith("_"))
    if args.parts:
        want = set(args.parts)
        pfs = [p for p in pfs if p.stem in want]
    lfs = sorted(p for p in LINKS.glob("*.json") if not p.stem.startswith("_"))

    print(f"파트 {len(pfs)}개: {[p.stem for p in pfs] or '없음'}")
    print(f"연결 파일 {len(lfs)}개: {[p.stem for p in lfs] or '없음'}")
    if not pfs:
        print("\ndata/parts/ 에 파트 파일이 없습니다. "
              "data/parts/_TEMPLATE.json 을 복사해 시작하세요.")
        raise SystemExit(1)

    try:
        doc, problems = merge(pfs, lfs, strict=not args.allow_problems)
    except MergeError as err:
        print(f"\n[실패] {err}")
        raise SystemExit(1)

    print("\n파트별 규모:")
    for pm in doc["composed_from"]:
        c = pm["counts"]
        print(f"  {pm['id']:<12} {pm['kind'] or '-':<10} "
              f"층 {c['floors']:>3}  장소 {c['places']:>4}  "
              f"노드 {c['nodes']:>5}  엣지 {c['edges']:>5}  "
              f"승강기 {c['elevators']:>2}   담당 {pm['owner'] or '-'}")
    print(f"\n합계: 건물 {len(doc['buildings'])}  층 {len(doc['floors'])}  "
          f"장소 {len(doc['places'])}  노드 {len(doc['nodes'])}  "
          f"엣지 {len(doc['edges'])}  승강기 {len(doc['elevators'])}")
    print(f"파트 간 연결: {doc['cross_part_links']}개")
    if problems:
        print(f"\n경고 {len(problems)}건:")
        for x in problems[:20]:
            print(f"  - {x}")

    if args.check:
        print("\n--check 모드: 파일을 쓰지 않았습니다.")
        return

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"\n저장: {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")
    print("다음: python scripts/validate_graph.py data/published/campus_v1.json")


if __name__ == "__main__":
    main()
