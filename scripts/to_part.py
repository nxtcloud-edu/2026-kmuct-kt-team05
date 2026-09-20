"""
기존 단일 그래프를 파트 파일로 변환한다.

사용법
    python scripts/to_part.py data/demo/mirae_nav_v1.json mirae building "이태곤"
인자
    입력그래프  part-id  kind(building|outdoor|area)  담당자
결과
    data/parts/<part-id>.json
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PARTS = ROOT / "data" / "parts"

COLLECTIONS = ("buildings", "floorplans", "floors", "places",
               "nodes", "edges", "elevators", "closures")


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    src = pathlib.Path(sys.argv[1])
    pid, kind = sys.argv[2], sys.argv[3]
    owner = sys.argv[4] if len(sys.argv) > 4 else None
    ns = f"{pid}/"

    with src.open(encoding="utf-8") as fh:
        doc = json.load(fh)

    out = {
        "part": {"id": pid, "namespace": ns, "kind": kind, "owner": owner},
        "graph_version": doc.get("graph_version"),
        "schema_version": doc.get("schema_version", "1.0.0"),
        "generated_at": doc.get("generated_at"),
        "verification_scope": doc.get("verification_scope", {}),
        "notes": doc.get("notes", []),
    }
    for c in COLLECTIONS:
        out[c] = doc.get(c, [])

    # 파트 간 연결로 옮겨야 하는 엣지 탐지 (네임스페이스가 다른 양끝)
    cross = [e for e in out["edges"]
             if not (str(e.get("from_node", "")).startswith(ns)
                     and str(e.get("to_node", "")).startswith(ns))]
    if cross:
        print(f"! 파트 경계를 넘는 엣지 {len(cross)}개 발견 -> data/links/ 로 옮기세요:")
        for e in cross[:10]:
            print(f"    {e['id']}: {e.get('from_node')} -> {e.get('to_node')}")
        out["edges"] = [e for e in out["edges"] if e not in cross]

    PARTS.mkdir(parents=True, exist_ok=True)
    p = PARTS / f"{pid}.json"
    with p.open("w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, separators=(",", ":"))

    print(f"part={pid}  namespace={ns}  kind={kind}  owner={owner}")
    for c in COLLECTIONS:
        if out[c]:
            print(f"  {c:<12} {len(out[c])}")
    print(f"저장: {p}  ({p.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    main()
