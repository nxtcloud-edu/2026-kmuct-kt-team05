"""
P2-5: 실제 도면 기반 경로 CLI.

사용법
    python scripts/route_cli.py --list
    python scripts/route_cli.py --from "338" --to "337"
    python scripts/route_cli.py --from "338" --to "337" --no-stairs
    python scripts/route_cli.py --from "202" --to "338" --wheelchair
    python scripts/route_cli.py --from "338" --to "337" --json

출력에는 graph_version, policy_version, 검증 수준을 항상 포함한다.
경로가 없을 때 '데이터 부족' 과 '조건상 경로 없음' 을 구분해 표시한다.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.graph.dataset import Dataset            # noqa: E402
from backend.app.routing.engine import route             # noqa: E402
from backend.app.routing.policy import Constraints       # noqa: E402

DEFAULT_GRAPH = ROOT / "data" / "published" / "mirae_indoor_v1.json"


def resolve(ds: Dataset, q: str) -> tuple[str | None, list]:
    """장소 문자열 -> 문 노드 ID. 후보가 여럿이면 확정하지 않는다."""
    if q in ds.nodes:
        return q, []
    cands = ds.find_places(q)
    if len(cands) == 1:
        p = cands[0]
        if not p.door_node_ids:
            return None, cands
        return p.door_node_ids[0], []
    return None, cands


def print_header(ds: Dataset) -> None:
    vs = ds.verification_scope
    print("=" * 76)
    print(f"graph_version : {ds.graph_version}")
    print(f"schema_version: {ds.schema_version}")
    print(f"source        : {ds.source}")
    print(f"검증 수준     : {vs.get('evidence_level')}")
    print(f"현장 검증     : {vs.get('field_verified')}")
    print(f"휠체어 인증   : {vs.get('wheelchair_accessible_routes_certified')}")
    print(f"실외 연결     : {vs.get('outdoor_connection')}")
    print(f"층간 연결     : {vs.get('vertical_connection')}")
    if ds.warnings:
        print(f"데이터 경고   : {len(ds.warnings)}건")
        for w in ds.warnings:
            print(f"  - {w}")
    print("=" * 76)


def print_places(ds: Dataset) -> None:
    print("\n[등록된 장소]")
    for p in ds.places.values():
        f = ds.floors.get(p.floor_id)
        print(f"  {p.id}")
        print(f"     이름={p.name}  층={f.label if f else p.floor_id}  상태={p.status.value}")
        print(f"     문 노드={p.door_node_ids}")
        for n in p.notes:
            print(f"     ! {n}")
    print("\n[층]")
    for f in ds.floors.values():
        pl = ds.plans.get(f.plan_id or "")
        print(f"  {f.id}  label={f.label}  sort={f.sort_order}")
        if pl:
            print(f"     도면: web탭='{pl.source_tab_label}' 파일='{pl.source_filename}' "
                  f"내부표기='{pl.drawing_floor_label}' 매핑={pl.mapping_status.value}")
            print(f"     축척: {pl.scale_m_per_px.value} ({pl.scale_m_per_px.verification.value})")


def print_route(r: dict) -> None:
    print(f"\n상태: {r['status']}")
    print(f"policy_version: {r['policy_version']}   objective={r['objective']}   "
          f"profile={r['profile']}")
    print(f"적용 제약: {json.dumps(r['applied_constraints'], ensure_ascii=False)}")

    if r["status"] != "ok":
        if r.get("blocked_counts"):
            print(f"\n제거된 엣지 사유별 집계: {r['blocked_counts']}")
        if r.get("unverified_edge_ids"):
            print(f"미검증 엣지: {r['unverified_edge_ids']}")
        print("\n사유:")
        for x in r["reasons"]:
            print(f"  - {x}")
        return

    m = r["metrics"]
    print(f"\n지표 (항목 분리)")
    print(f"  보행거리          : {m['distance_m']} m"
          + ("" if m["segments_with_unknown_length"] == 0
             else f"  (길이 미상 구간 {m['segments_with_unknown_length']}개 -> 확정값 아님)"))
    print(f"  추정 소요시간     : {m['estimated_time_s']} s  "
          f"(가정값={m['estimated_time_is_assumption']})")
    print(f"  실외 이동거리     : {m['outdoor_distance_m']} m")
    print(f"  계단 구간 수      : {m['stair_segments']}")
    print(f"  계단 실제 단수    : {m['stair_steps_observed']}"
          f"  (단수 미상 구간 {m['stair_segments_without_step_count']}개)")
    print(f"  엘리베이터 탑승   : {m['elevator_boardings']} 회")
    print(f"  관측 기반 최대경사: {m['observed_max_slope_pct']}")
    print(f"  추정 기반 최대경사: {m['estimated_max_slope_pct']}")
    print(f"  미검증 구간 수    : {m['unverified_segments']}")
    print(f"  경유 층           : {m['floors_touched']}")
    print(f"  전층 축척 검증    : {m['scale_verified_for_all_floors']}")
    if r.get("approximate"):
        print("  ! approximate=True (자원 제한으로 근사 후보만 비교)")

    print(f"\n세그먼트 ({len(r['segments'])}개)")
    for i, s in enumerate(r["segments"], 1):
        print(f"  {i:2d}. [{s['kind']:<14}] {s['from_node']} -> {s['to_node']}"
              f"  {s['time_s']}s  space={s['space']}")

    print("\n단계 안내")
    for i, ins in enumerate(r["instructions"], 1):
        print(f"  {i:2d}. ({ins['floor_label']}) {ins['text']}")
        if ins["confirm_prompt"]:
            print(f"      -> {ins['confirm_prompt']}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--graph", default=str(DEFAULT_GRAPH))
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--from", dest="origin")
    ap.add_argument("--to", dest="dest")
    ap.add_argument("--profile", default="normal",
                    choices=["normal", "elderly", "wheelchair"])
    ap.add_argument("--objective", default="fastest",
                    choices=["fastest", "comfort", "indoor"])
    ap.add_argument("--no-stairs", action="store_true")
    ap.add_argument("--wheelchair", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    ds = Dataset.load(args.graph)

    if args.list or not (args.origin and args.dest):
        print_header(ds)
        print_places(ds)
        if not (args.origin and args.dest):
            print("\n경로를 보려면 --from/--to 를 지정하세요.")
        return

    src, src_cands = resolve(ds, args.origin)
    dst, dst_cands = resolve(ds, args.dest)
    if src is None or dst is None:
        print_header(ds)
        print("\n상태: needs_clarification")
        if src is None:
            print(f"  출발지 '{args.origin}' 후보: "
                  f"{[c.id for c in src_cands] or '없음(미등록)'}")
        if dst is None:
            print(f"  목적지 '{args.dest}' 후보: "
                  f"{[c.id for c in dst_cands] or '없음(미등록)'}")
        print("  -> 후보를 하나로 확정한 뒤 다시 요청하세요. 임의로 선택하지 않습니다.")
        return

    c = Constraints(no_stairs=args.no_stairs or args.wheelchair,
                    wheelchair=args.wheelchair)
    profile = "wheelchair" if args.wheelchair else args.profile
    r = route(ds, src, dst, profile, args.objective, c)

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2))
        return

    print_header(ds)
    print(f"\n요청: {args.origin} -> {args.dest}   ({src} -> {dst})")
    print_route(r)


if __name__ == "__main__":
    main()
