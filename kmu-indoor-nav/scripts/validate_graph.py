"""
그래프 검증기 (스키마 + 토폴로지 + 근거).

발행 절차: draft -> schema validation -> topology validation -> evidence review -> publish
이 스크립트는 앞의 세 단계를 수행하고 근거 검토 대상을 목록으로 뽑는다.

사용법
    python scripts/validate_graph.py [graph.json ...]
종료코드
    0 = 치명적 오류 없음, 1 = 치명적 오류
"""

from __future__ import annotations

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.graph.dataset import Dataset                 # noqa: E402
from backend.app.models.schema import (                        # noqa: E402
    MIN_VERIFICATION_FOR_ACCESSIBILITY,
    EdgeKind,
    NodeKind,
    SchemaError,
    VERTICAL_EDGE_KINDS,
)

DEFAULTS = [ROOT / "data" / "published" / "mirae_indoor_v1.json"]


def topology_checks(ds: Dataset) -> tuple[list[str], list[str]]:
    """(치명적, 경고)"""
    fatal: list[str] = []
    warn: list[str] = []

    # 고립 노드
    reachable_from = {e.from_node for e in ds.edges}
    reachable_to = {e.to_node for e in ds.edges}
    for nid, n in ds.nodes.items():
        if nid not in reachable_from and nid not in reachable_to:
            warn.append(f"고립 노드(엣지 0개): {nid} [{n.kind.value}] {n.name or ''}")

    # 출입구 노드가 실내외를 잇는지
    for nid, n in ds.nodes.items():
        if n.kind in (NodeKind.ENTRANCE_INSIDE, NodeKind.ENTRANCE_OUTSIDE):
            has_entrance = any(
                e.kind == EdgeKind.ENTRANCE and nid in (e.from_node, e.to_node)
                for e in ds.edges
            )
            if not has_entrance:
                warn.append(f"출입구 노드인데 entrance 엣지가 없음: {nid}")

    # 층간 오접속 (스키마에서 이미 막지만 이중 확인)
    for e in ds.edges:
        a, b = ds.nodes[e.from_node], ds.nodes[e.to_node]
        if a.floor_id != b.floor_id and e.kind not in VERTICAL_EDGE_KINDS \
                and e.kind != EdgeKind.ENTRANCE:
            fatal.append(f"층간 오접속: {e.id} ({e.kind.value}) "
                         f"{a.floor_id} -> {b.floor_id}")

    # 근거 없는 연결
    for e in ds.edges:
        if not e.source_refs:
            fatal.append(f"근거(source_refs) 없는 엣지: {e.id}")

    # 근거 없는 엘리베이터/문/관통 통로
    for ev in ds.elevators.values():
        if not ev.served_floors_evidence.is_known:
            fatal.append(f"정차층 근거 없는 승강기: {ev.id}")
    for e in ds.edges:
        if e.kind == EdgeKind.ELEVATOR_RIDE and e.facility_id not in ds.elevators:
            fatal.append(f"미등록 승강기를 참조: {e.id}")

    # 방향 대칭성 (일방향이면 의도된 것인지 표시)
    pairs = {(e.from_node, e.to_node, e.kind.value) for e in ds.edges}
    for e in ds.edges:
        if e.kind in (EdgeKind.ELEVATOR_RIDE,):
            continue
        if (e.to_node, e.from_node, e.kind.value) not in pairs:
            warn.append(f"일방향 엣지(역방향 없음): {e.id} — 의도된 제한인지 확인")

    # 축척 없는 층의 길이 값
    for e in ds.edges:
        a = ds.nodes[e.from_node]
        if a.floor_id and not ds.scale_known(a.floor_id):
            if e.horizontal_length_m.is_known:
                fatal.append(
                    f"축척 unknown 인 층({a.floor_id})의 엣지에 길이가 채워져 있음: {e.id}"
                )
    return fatal, warn


def evidence_review(ds: Dataset) -> list[str]:
    """근거 검토 대상 목록 (현장 조사 필요 항목)."""
    items: list[str] = []
    for e in ds.edges:
        if e.id.endswith("/rev"):
            continue
        miss = [f for f in ("clear_width_m", "threshold_m", "slope_up_pct",
                            "slope_down_pct", "door_operability")
                if not getattr(e.accessibility, f).known_at_least(
                    MIN_VERIFICATION_FOR_ACCESSIBILITY)]
        if miss:
            items.append(f"{e.id} [{e.kind.value}] 미확인: {', '.join(miss)}")
    for p in ds.places.values():
        if p.status.value == "drawing_candidate":
            items.append(f"{p.id} 장소 상태=drawing_candidate (현장 호실 표기 확인 필요)")
    for pl in ds.plans.values():
        if pl.mapping_status.value in ("pending_review", "source_label_conflict"):
            items.append(f"{pl.id} 층 매핑 {pl.mapping_status.value} "
                         f"(web='{pl.source_tab_label}' drawing='{pl.drawing_floor_label}')")
        if pl.geo_transform is None:
            items.append(f"{pl.id} 지리 정합 미수행 (control_points {len(pl.control_points)}개)")
    for n in ds.nodes.values():
        if n.kind == NodeKind.STAIR_LANDING:
            connected = any(
                e.kind in VERTICAL_EDGE_KINDS and n.id in (e.from_node, e.to_node)
                for e in ds.edges
            )
            if not connected:
                items.append(f"{n.id} 계단참인데 층간 엣지 없음 (출입문/연결 확인 필요)")
    return items


def check(path: pathlib.Path) -> int:
    print("=" * 76)
    print(f"검증 대상: {path}")
    print("=" * 76)
    try:
        ds = Dataset.load(path)
    except SchemaError as err:
        print(f"[FATAL] 스키마 오류: {err}")
        return 1

    print(f"graph_version={ds.graph_version}  nodes={len(ds.nodes)} "
          f"edges={len(ds.edges)} places={len(ds.places)} elevators={len(ds.elevators)}")

    print(f"\n[1] 스키마 경고 {len(ds.warnings)}건")
    for w in ds.warnings:
        print(f"  - {w}")

    fatal, warn = topology_checks(ds)
    print(f"\n[2] 토폴로지: 치명적 {len(fatal)}건 / 경고 {len(warn)}건")
    for f in fatal:
        print(f"  [FATAL] {f}")
    for w in warn:
        print(f"  [warn ] {w}")

    review = evidence_review(ds)
    print(f"\n[3] 근거 검토 대상 {len(review)}건")
    for r in review:
        print(f"  - {r}")

    verdict = "발행 불가" if fatal else "발행 가능 (단, 접근성 확인 경로는 제공 불가)"
    print(f"\n판정: {verdict}")
    return 1 if fatal else 0


def main() -> None:
    paths = [pathlib.Path(a) for a in sys.argv[1:]] or DEFAULTS
    rc = 0
    for p in paths:
        rc |= check(p)
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
