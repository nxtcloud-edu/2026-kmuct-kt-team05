"""
데모 서버 (표준 라이브러리만 사용).

실행
    python demo/server.py          # http://127.0.0.1:8765

엔드포인트
    GET /                          데모 UI
    GET /plan/<filename>           도면 PNG (data/raw/floorplans)
    GET /api/status                graph_version / 검증 수준
    GET /api/places                등록된 장소 + 층 + 도면 정보
    GET /api/intent?text=          한국어 요청 -> 구조화 의도
    GET /api/route?from&to&...      경로

보안 메모: 로컬 데모용이라 인증이 없다. 127.0.0.1 에만 바인딩한다.
외부에 노출하려면 인증/사용량 제한을 먼저 붙여야 한다.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.app.graph.dataset import Dataset             # noqa: E402
from backend.app.intent.parse import parse, session_from  # noqa: E402
from backend.app.routing.engine import route              # noqa: E402
from backend.app.routing.policy import Constraints        # noqa: E402

# 여러 그래프를 동시에 로드하고 ?graph= 로 선택한다.
#   nav       : 내비게이션맵 시안 기반 (8개 층, 화면과 좌표 일치)  <- 기본
#   full      : 원본 도면 자동추출 (2~7층)
#   published : 도면 판독 근거만 (3층 338/337 + 2층 202)
GRAPHS_SPEC = {
    "nav": ROOT / "data" / "demo" / "mirae_nav_v1.json",
    "full": ROOT / "data" / "demo" / "mirae_full_v1.json",
    "published": ROOT / "data" / "published" / "mirae_indoor_v1.json",
}
DEFAULT_GRAPH = os.environ.get("NAV_GRAPH_KEY", "nav")
PLAN_DIRS = [
    ROOT / "data" / "raw" / "navmaps",
    ROOT / "data" / "raw" / "floorplans",
]
HERE = pathlib.Path(__file__).resolve().parent

GRAPHS: dict[str, Dataset] = {}
for _k, _p in GRAPHS_SPEC.items():
    if not _p.exists():
        print(f"  (없음) {_k}: {_p.name}")
        continue
    GRAPHS[_k] = Dataset.load(_p)
    _d = GRAPHS[_k]
    print(f"{_k:<10} version={_d.graph_version}  nodes={len(_d.nodes)} "
          f"edges={len(_d.edges)} elevators={len(_d.elevators)}"
          + ("  *** 가정값 포함 ***"
             if _d.verification_scope.get("demo_assumed_data") else ""))
    for w in _d.warnings:
        print(f"             warn: {w}")
if DEFAULT_GRAPH not in GRAPHS:
    DEFAULT_GRAPH = next(iter(GRAPHS))


def pick(q: dict) -> tuple[str, Dataset]:
    k = (q.get("graph", [DEFAULT_GRAPH]) or [DEFAULT_GRAPH])[0]
    if k not in GRAPHS:
        k = DEFAULT_GRAPH
    return k, GRAPHS[k]


def places_payload(DS: Dataset, overlay: bool = False) -> dict:
    out = []
    for p in DS.places.values():
        f = DS.floors.get(p.floor_id)
        pl = DS.plan_for_floor(p.floor_id)
        out.append({
            "id": p.id, "name": p.name, "room_label": p.room_label,
            "aliases": p.aliases, "status": p.status.value,
            "floor_id": p.floor_id,
            "floor_label": f.label if f else p.floor_id,
            "door_node_ids": p.door_node_ids,
            "label_plan_point": (p.label_plan_point.to_json()
                                 if p.label_plan_point else None),
            "plan_image": (f"/plan/{pl.source_filename}" if pl and pl.source_filename
                           else None),
            "plan_size": [pl.width_px, pl.height_px] if pl else None,
            "scale_m_per_px": pl.scale_m_per_px.value if pl else None,
            "notes": p.notes,
        })
    floors = []
    for f in DS.floors.values():
        pl = DS.plan_for_floor(f.id)
        floors.append({
            "id": f.id, "label": f.label, "sort_order": f.sort_order,
            "plan_image": (f"/plan/{pl.source_filename}" if pl and pl.source_filename
                           else None),
            "plan_size": [pl.width_px, pl.height_px] if pl else None,
            "scale_m_per_px": pl.scale_m_per_px.value if pl else None,
            "source_tab_label": pl.source_tab_label if pl else None,
            "drawing_floor_label": pl.drawing_floor_label if pl else None,
            "mapping_status": pl.mapping_status.value if pl else None,
        })
    # 그래프 오버레이는 용량이 커서 기본으로 보내지 않는다 (?overlay=1)
    nodes, edges = [], []
    if overlay:
        nodes = [{
            "id": n.id, "kind": n.kind.value, "floor_id": n.floor_id,
            "name": n.name,
            "x": n.plan_point.x_px if n.plan_point else None,
            "y": n.plan_point.y_px if n.plan_point else None,
        } for n in DS.nodes.values() if n.plan_point]
        edges = [{
            "id": e.id, "kind": e.kind.value,
            "from_node": e.from_node, "to_node": e.to_node,
            "geometry": e.geometry,
        } for e in DS.edges if not e.id.endswith("/rev")]
    facilities = [{
        "id": n.id, "kind": n.kind.value, "floor_id": n.floor_id,
        "name": n.name,
        "x": n.plan_point.x_px if n.plan_point else None,
        "y": n.plan_point.y_px if n.plan_point else None,
    } for n in DS.nodes.values()
        if n.plan_point and n.kind.value in
        ("elevator_lobby", "stair_landing", "entrance_inside", "entrance_outside")]
    return {"places": out, "floors": floors, "nodes": nodes, "edges": edges,
            "facilities": facilities}


def resolve_place(DS: Dataset, q: str) -> tuple[str | None, list[dict]]:
    if q in DS.nodes:
        return q, []
    cands = DS.find_places(q)
    if len(cands) == 1 and cands[0].door_node_ids:
        return cands[0].door_node_ids[0], []
    return None, [{"id": c.id, "name": c.name} for c in cands]


class H(BaseHTTPRequestHandler):
    server_version = "MiraeNavDemo/0.1"

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def log_message(self, fmt, *args):  # 로그 간소화
        sys.stderr.write("  %s\n" % (fmt % args))

    def do_GET(self):  # noqa: N802
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        one = lambda k, d=None: (q.get(k, [d]) or [d])[0]

        if u.path in ("/", "/index.html"):
            p = HERE / "index.html"
            self._send(200, p.read_bytes(), "text/html; charset=utf-8")
            return

        if u.path.startswith("/plan/"):
            name = pathlib.PurePosixPath(u.path).name
            for d in PLAN_DIRS:
                f = d / name
                if f.is_file() and f.parent.resolve() == d.resolve():
                    self._send(200, f.read_bytes(), "image/png")
                    return
            self._json({"error": "not found"}, 404)
            return

        if u.path == "/api/status":
            key, DS = pick(q)
            self._json({
                "graph_key": key,
                "available_graphs": sorted(GRAPHS),
                "graph_version": DS.graph_version,
                "schema_version": DS.schema_version,
                "generated_at": DS.generated_at,
                "verification_scope": DS.verification_scope,
                "warnings": DS.warnings,
                "notes": DS.notes,
                "elevators_registered": len(DS.elevators),
            })
            return

        if u.path == "/api/places":
            key, DS = pick(q)
            ov = one("overlay", "0") in ("1", "true", "True")
            self._json({"graph_key": key, **places_payload(DS, ov)})
            return

        if u.path == "/api/intent":
            key, DS = pick(q)
            text = one("text", "")
            sess = {}
            if one("session"):
                try:
                    sess = json.loads(one("session"))
                except Exception:  # noqa: BLE001
                    sess = {}
            intent = parse(text, sess)
            # 장소 검증: 파서가 place_id 를 만들지 않는다
            for key2 in ("origin", "destination"):
                raw = intent[key2]["raw_text"]
                if not raw:
                    continue
                nid, cands = resolve_place(DS, raw)
                intent[key2]["place_id"] = nid
                intent[key2]["candidates"] = cands
                if nid is None and key2 not in intent["needs_clarification"]:
                    intent["needs_clarification"].append(key2)
                if nid is not None and key2 in intent["needs_clarification"]:
                    intent["needs_clarification"].remove(key2)
            intent["session"] = session_from(intent)
            intent["graph_key"] = key
            self._json(intent)
            return

        if u.path == "/api/route":
            key, DS = pick(q)
            src_q, dst_q = one("from", ""), one("to", "")
            src, src_c = resolve_place(DS, src_q)
            dst, dst_c = resolve_place(DS, dst_q)
            if src is None or dst is None:
                self._json({
                    "status": "needs_clarification",
                    "graph_key": key,
                    "graph_version": DS.graph_version,
                    "origin_candidates": src_c, "destination_candidates": dst_c,
                    "reasons": ["출발지/목적지를 확정할 수 없습니다. "
                                "후보를 선택해 주세요. 임의로 고르지 않습니다."],
                })
                return
            wc = one("wheelchair", "0") in ("1", "true", "True")
            ns = one("no_stairs", "0") in ("1", "true", "True") or wc
            objective = one("objective", "fastest")
            profile = one("profile", "wheelchair" if wc else "normal")
            c = Constraints(no_stairs=ns, wheelchair=wc)
            r = route(DS, src, dst, profile, objective, c)
            r["graph_key"] = key
            self._json(r)
            return

        self._json({"error": "not found", "path": u.path}, 404)


def main() -> None:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"\n데모 서버: http://127.0.0.1:{port}")
    print("  (로컬 전용. 인증 없음)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")


if __name__ == "__main__":
    main()
