"""
파트 병합 테스트: 네임스페이스 강제, id 충돌 검출, 파트 간 연결 검사.

여러 사람이 각자 파트를 올렸을 때 병합기가 실제로 문제를 잡아내는지 확인한다.
실행:  python tests/test_merge_parts.py
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.merge_graphs import MergeError, merge   # noqa: E402


def unk():
    return {"value": None, "verification": "unknown"}


def acc():
    return {k: unk() for k in
            ("stairs", "step_count", "slope_up_pct", "slope_down_pct",
             "cross_slope_pct", "clear_width_m", "threshold_m", "surface",
             "door_operability", "wheelchair_usable")}


def part(pid: str, kind="building", owner="tester"):
    ns = f"{pid}/"
    return {
        "part": {"id": pid, "namespace": ns, "kind": kind, "owner": owner},
        "graph_version": f"{pid}-v1", "schema_version": "1.0.0",
        "verification_scope": {"field_verified": False,
                               "evidence_level": "테스트"},
        "notes": [],
        "buildings": [{"id": pid, "official_name": pid, "campus_code": "S0",
                       "aliases": [], "wings": [], "footprint": None,
                       "source_refs": []}],
        "floorplans": [],
        "floors": [{"id": f"{ns}F1", "building_id": pid, "label": "1층",
                    "sort_order": 1, "wing_id": None, "plan_id": None,
                    "elevation_m": unk(), "notes": []}],
        "places": [{"id": f"{ns}F1/101", "name": "101호", "building_id": pid,
                    "floor_id": f"{ns}F1", "room_label": "101",
                    "aliases": ["101"], "wing_id": None,
                    "door_node_ids": [f"{ns}F1/door/101"],
                    "status": "drawing_candidate", "label_plan_point": None,
                    "source_refs": [], "notes": []}],
        "nodes": [
            {"id": f"{ns}F1/door/101", "kind": "room_door", "building_id": pid,
             "floor_id": f"{ns}F1",
             "plan_point": {"coordinate_space": f"plan:{ns}F1",
                            "x_px": 10.0, "y_px": 10.0},
             "geo_point": None, "name": "101호 문", "facility_id": None,
             "source_refs": [], "notes": []},
            {"id": f"{ns}F1/entrance/1", "kind": "entrance_inside",
             "building_id": pid, "floor_id": f"{ns}F1",
             "plan_point": {"coordinate_space": f"plan:{ns}F1",
                            "x_px": 50.0, "y_px": 50.0},
             "geo_point": None, "name": "출입구", "facility_id": None,
             "source_refs": [], "notes": []},
        ],
        "edges": [{"id": f"{ns}F1/e/1", "from_node": f"{ns}F1/door/101",
                   "to_node": f"{ns}F1/entrance/1", "kind": "corridor",
                   "horizontal_length_m": unk(), "traversal_length_m": unk(),
                   "vertical_rise_m": unk(), "accessibility": acc(),
                   "facility_id": None, "schedule_id": None, "geometry": [],
                   "elevator_from_floor": None, "elevator_to_floor": None,
                   "source_refs": [], "notes": []}],
        "elevators": [], "closures": [],
    }


def outdoor_part():
    d = part("outdoor", kind="outdoor")
    d["floors"] = []
    d["places"] = []
    d["floorplans"] = []
    d["buildings"] = []
    d["nodes"] = [{"id": "outdoor/n/1", "kind": "outdoor_junction",
                   "building_id": None, "floor_id": None, "plan_point": None,
                   "geo_point": {"lon": 126.9975, "lat": 37.6115},
                   "name": "정문 앞", "facility_id": None,
                   "source_refs": [], "notes": []},
                  {"id": "outdoor/n/2", "kind": "outdoor_junction",
                   "building_id": None, "floor_id": None, "plan_point": None,
                   "geo_point": {"lon": 126.9980, "lat": 37.6120},
                   "name": None, "facility_id": None,
                   "source_refs": [], "notes": []}]
    d["edges"] = [{"id": "outdoor/e/1", "from_node": "outdoor/n/1",
                   "to_node": "outdoor/n/2", "kind": "outdoor_walk",
                   "horizontal_length_m": unk(), "traversal_length_m": unk(),
                   "vertical_rise_m": unk(), "accessibility": acc(),
                   "facility_id": None, "schedule_id": None, "geometry": [],
                   "elevator_from_floor": None, "elevator_to_floor": None,
                   "source_refs": [], "notes": []}]
    return d


def write(tmp: pathlib.Path, name: str, doc: dict) -> pathlib.Path:
    p = tmp / f"{name}.json"
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return p


# ------------------------------------------------------------------ 테스트
def test_two_parts_merge_cleanly():
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        a = write(t, "mirae", part("mirae"))
        b = write(t, "gonghak", part("gonghak"))
        doc, probs = merge([a, b], [])
        assert probs == [], probs
        assert len(doc["buildings"]) == 2
        assert len(doc["places"]) == 2
        assert {p["id"] for p in doc["composed_from"]} == {"mirae", "gonghak"}


def test_filename_must_match_part_id():
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        p = write(t, "wrongname", part("mirae"))
        try:
            merge([p], [])
        except MergeError as e:
            assert "파일명과 part.id" in str(e)
        else:
            raise AssertionError("파일명 불일치를 통과시켰다")


def test_namespace_is_enforced():
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        d = part("gonghak")
        d["nodes"][0]["id"] = "mirae/F1/door/101"      # 남의 네임스페이스 침범
        p = write(t, "gonghak", d)
        try:
            merge([p], [])
        except MergeError as e:
            assert "로 시작해야 함" in str(e)
        else:
            raise AssertionError("네임스페이스 침범을 통과시켰다")


def test_id_collision_between_parts_is_detected():
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        a = part("mirae")
        b = part("gonghak")
        # gonghak 파트가 mirae 와 같은 id 를 쓰도록 강제 (네임스페이스는 우회)
        b["part"]["namespace"] = "mirae/"
        b["part"]["id"] = "gonghak"
        pa = write(t, "mirae", a)
        pb = write(t, "gonghak", b)
        try:
            merge([pa, pb], [])
        except MergeError as e:
            msg = str(e)
            assert "네임스페이스 중복" in msg or "id 충돌" in msg, msg
        else:
            raise AssertionError("id 충돌을 통과시켰다")


def test_plan_coordinate_space_must_be_own_namespace():
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        d = part("gonghak")
        d["nodes"][0]["plan_point"]["coordinate_space"] = "plan:mirae/F1"
        p = write(t, "gonghak", d)
        try:
            merge([p], [])
        except MergeError as e:
            assert "coordinate_space" in str(e)
        else:
            raise AssertionError("층간/파트간 좌표공간 혼용을 통과시켰다")


def test_cross_part_link_requires_existing_nodes():
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        a = write(t, "mirae", part("mirae"))
        o = write(t, "outdoor", outdoor_part())
        link = {"links": [{
            "id": "link/1", "from_node": "outdoor/n/999",   # 없는 노드
            "to_node": "mirae/F1/entrance/1", "kind": "entrance",
            "horizontal_length_m": unk(), "traversal_length_m": unk(),
            "vertical_rise_m": unk(), "accessibility": acc(),
            "facility_id": None, "schedule_id": None, "geometry": [],
            "elevator_from_floor": None, "elevator_to_floor": None,
            "source_refs": [], "notes": []}]}
        lp = write(t, "links1", link)
        try:
            merge([a, o], [lp])
        except MergeError as e:
            assert "어느 파트에도 없는 노드" in str(e)
        else:
            raise AssertionError("존재하지 않는 노드 연결을 통과시켰다")


def test_valid_cross_part_link_merges():
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        a = write(t, "mirae", part("mirae"))
        o = write(t, "outdoor", outdoor_part())
        link = {"links": [{
            "id": "link/outdoor-mirae-1", "from_node": "outdoor/n/1",
            "to_node": "mirae/F1/entrance/1", "kind": "entrance",
            "horizontal_length_m": unk(), "traversal_length_m": unk(),
            "vertical_rise_m": unk(), "accessibility": acc(),
            "facility_id": None, "schedule_id": None, "geometry": [],
            "elevator_from_floor": None, "elevator_to_floor": None,
            "source_refs": [], "notes": []}]}
        lp = write(t, "links1", link)
        doc, probs = merge([a, o], [lp])
        assert probs == [], probs
        assert doc["cross_part_links"] == 1
        ids = {e["id"] for e in doc["edges"]}
        assert "link/outdoor-mirae-1" in ids


def test_same_part_link_is_rejected():
    """파트 내부 연결을 links 에 쓰면 경고한다 (파트 파일에 써야 함)."""
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        a = write(t, "mirae", part("mirae"))
        link = {"links": [{
            "id": "link/bad", "from_node": "mirae/F1/door/101",
            "to_node": "mirae/F1/entrance/1", "kind": "corridor",
            "horizontal_length_m": unk(), "traversal_length_m": unk(),
            "vertical_rise_m": unk(), "accessibility": acc(),
            "facility_id": None, "schedule_id": None, "geometry": [],
            "elevator_from_floor": None, "elevator_to_floor": None,
            "source_refs": [], "notes": []}]}
        lp = write(t, "links1", link)
        try:
            merge([a], [lp])
        except MergeError as e:
            assert "같은 파트 내부 연결" in str(e)
        else:
            raise AssertionError("파트 내부 연결을 links 에서 통과시켰다")


def test_verification_scope_is_conservative():
    """파트 하나라도 미검증이면 전체를 미검증으로 본다."""
    with tempfile.TemporaryDirectory() as td:
        t = pathlib.Path(td)
        a = part("mirae")
        a["verification_scope"]["field_verified"] = True
        b = part("gonghak")
        b["verification_scope"]["field_verified"] = False
        pa = write(t, "mirae", a)
        pb = write(t, "gonghak", b)
        doc, _ = merge([pa, pb], [])
        assert doc["verification_scope"]["field_verified"] is False


def test_real_mirae_part_merges():
    """실제 data/parts/mirae.json 이 있으면 그것도 검사한다."""
    p = ROOT / "data" / "parts" / "mirae.json"
    if not p.exists():
        print("      (건너뜀: data/parts/mirae.json 없음)")
        return
    doc, probs = merge([p], [])
    assert probs == [], probs[:5]
    assert len(doc["places"]) > 0


def _run_all() -> int:
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    fails = 0
    for name, fn in fns:
        try:
            fn()
            print(f"  PASS  {name}")
        except AssertionError as err:
            fails += 1
            print(f"  FAIL  {name}\n        {err}")
        except Exception as err:  # noqa: BLE001
            fails += 1
            print(f"  ERROR {name}\n        {type(err).__name__}: {err}")
    print(f"\nRESULT {len(fns)-fails}/{len(fns)} passed")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(_run_all())
