"""
2단계: OSM 원본 -> 고도가 붙은 보행 그래프.

처리 내용:
  1. 보행 가능 way 를 연속 노드쌍 단위 엣지로 분해
     (교차점은 여러 way 가 같은 OSM 노드 id 를 공유하므로 자동으로 연결된다)
  2. 모든 노드의 고도를 DEM 에서 샘플링 (배치 + 디스크 캐시)
  3. 엣지별 수평거리 / 고도차 / 경사 / 계단여부 계산
  4. 이름있는 건물의 중심점을 가장 가까운 보행 노드에 연결

사용법:  python build_graph.py
결과:    data/graph.json, data/graph.geojson, data/elevation_cache.json
"""

import json
import math
import sys
import time

import requests

import config

EARTH_R = 6371008.8  # m, WGS84 평균 반지름


# --- 기하 ---------------------------------------------------------------------
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """두 지점 간 대권거리(m)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_R * math.asin(math.sqrt(a))


# --- 고도 ---------------------------------------------------------------------
def _key(lat: float, lon: float) -> str:
    return f"{lat:.6f},{lon:.6f}"


def load_elev_cache() -> dict[str, float]:
    if config.ELEV_CACHE.exists():
        with config.ELEV_CACHE.open(encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def save_elev_cache(cache: dict[str, float]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with config.ELEV_CACHE.open("w", encoding="utf-8") as fh:
        json.dump(cache, fh)


def fetch_elevations(coords: list[tuple[float, float]]) -> dict[str, float]:
    """(lat, lon) 목록의 고도를 DEM 에서 조회. 캐시를 활용하고 갱신한다."""
    cache = load_elev_cache()
    missing = [c for c in coords if _key(*c) not in cache]
    if not missing:
        print(f"  고도: 전부 캐시 적중 ({len(coords)}개)")
        return cache

    url = config.ELEVATION_URL.format(dataset=config.DEM_DATASET)
    batches = [
        missing[i:i + config.ELEVATION_BATCH]
        for i in range(0, len(missing), config.ELEVATION_BATCH)
    ]
    print(f"  고도: 캐시 미적중 {len(missing)}개 -> {len(batches)}회 요청 "
          f"(dataset={config.DEM_DATASET}, interpolation={config.ELEVATION_INTERPOLATION})")

    for i, batch in enumerate(batches, 1):
        locs = "|".join(f"{lat:.6f},{lon:.6f}" for lat, lon in batch)
        for attempt in range(1, 4):
            try:
                resp = requests.get(
                    url,
                    params={
                        "locations": locs,
                        "interpolation": config.ELEVATION_INTERPOLATION,
                    },
                    headers={"User-Agent": config.USER_AGENT},
                    timeout=60,
                )
                resp.raise_for_status()
                payload = resp.json()
                break
            except Exception as err:  # noqa: BLE001
                print(f"    ! 배치 {i} 실패 ({err}) 재시도 {attempt}/3", file=sys.stderr)
                time.sleep(attempt * 3)
        else:
            raise RuntimeError(f"고도 조회 실패 (배치 {i})")

        for (lat, lon), result in zip(batch, payload["results"]):
            elev = result.get("elevation")
            if elev is None:
                raise RuntimeError(f"고도 없음: {lat},{lon}")
            cache[_key(lat, lon)] = float(elev)

        print(f"    배치 {i}/{len(batches)} 완료")
        if i < len(batches):
            time.sleep(config.ELEVATION_SLEEP)

    save_elev_cache(cache)
    return cache


# --- 고도 스무딩 --------------------------------------------------------------
def smooth_along_ways(
    nodes: dict[str, dict],
    walkable: list[dict],
    valid_refs: set[int],
    half_window: float,
) -> None:
    """way 진행 방향으로 이동평균을 걸어 DEM 보간 노이즈를 줄인다.

    보행로 엣지의 대부분이 DEM 격자(30m)보다 짧기 때문에, 원시 고도를 그대로
    쓰면 구간 경사가 지형이 아니라 보간 오차를 반영한다. way 를 따라
    +-half_window(m) 범위를 평균하면 전체 고도 추세는 유지하면서 노이즈가 줄어든다.

    여러 way 가 공유하는 노드는 way 별 결과를 평균한다.
    결과는 nodes[*]["ele"] 를 덮어쓰고, 원본은 "ele_raw" 로 보존한다.
    """
    if half_window <= 0:
        for nd in nodes.values():
            nd["ele_raw"] = nd["ele"]
        return

    acc: dict[str, list[float]] = {}
    for w in walkable:
        refs = [str(n) for n in w["nodes"] if n in valid_refs]
        if len(refs) < 2:
            continue
        # way 를 따라가는 누적거리
        cum = [0.0]
        for a, b in zip(refs, refs[1:]):
            na, nb = nodes[a], nodes[b]
            cum.append(cum[-1] + haversine(na["lat"], na["lon"], nb["lat"], nb["lon"]))
        raw = [nodes[r]["ele"] for r in refs]

        for i, ref in enumerate(refs):
            lo, hi = cum[i] - half_window, cum[i] + half_window
            vals = [raw[j] for j in range(len(refs)) if lo <= cum[j] <= hi]
            acc.setdefault(ref, []).append(sum(vals) / len(vals))

    for nid, nd in nodes.items():
        nd["ele_raw"] = nd["ele"]
        if nid in acc:
            nd["ele"] = round(sum(acc[nid]) / len(acc[nid]), 2)


# --- 그래프 구축 --------------------------------------------------------------
def main() -> None:
    if not config.RAW_OSM.exists():
        raise SystemExit("data/raw_osm.json 이 없습니다. 먼저 fetch_osm.py 를 실행하세요.")

    with config.RAW_OSM.open(encoding="utf-8") as fh:
        raw = json.load(fh)

    elements = raw["elements"]
    osm_nodes = {e["id"]: e for e in elements if e["type"] == "node"}
    osm_ways = [e for e in elements if e["type"] == "way"]

    walkable = [
        w for w in osm_ways
        if w.get("tags", {}).get("highway") in config.WALKABLE_HIGHWAYS
    ]
    buildings = [
        w for w in osm_ways
        if "building" in w.get("tags", {}) and w.get("tags", {}).get("name")
    ]

    print(f"보행가능 way {len(walkable)}개, 이름있는 건물 {len(buildings)}개")

    # 1) 그래프에 실제로 쓰이는 노드만 수집
    used: set[int] = set()
    for w in walkable:
        used.update(w["nodes"])
    used = {nid for nid in used if nid in osm_nodes}
    print(f"보행 노드 {len(used)}개")

    # 2) 고도 샘플링
    node_list = sorted(used)
    coords = [(osm_nodes[nid]["lat"], osm_nodes[nid]["lon"]) for nid in node_list]

    # 건물 중심점도 같은 배치로 처리
    bld_centroids: dict[int, tuple[float, float]] = {}
    for b in buildings:
        pts = [(osm_nodes[n]["lat"], osm_nodes[n]["lon"]) for n in b["nodes"] if n in osm_nodes]
        if not pts:
            continue
        bld_centroids[b["id"]] = (
            sum(p[0] for p in pts) / len(pts),
            sum(p[1] for p in pts) / len(pts),
        )
    coords += list(bld_centroids.values())

    elev = fetch_elevations(coords)

    nodes: dict[str, dict] = {}
    for nid in node_list:
        lat, lon = osm_nodes[nid]["lat"], osm_nodes[nid]["lon"]
        tags = osm_nodes[nid].get("tags", {})
        nodes[str(nid)] = {
            "lat": lat,
            "lon": lon,
            "ele": elev[_key(lat, lon)],
            "entrance": tags.get("entrance"),
            "kind": "way",
        }

    # 3) 엣지 생성
    edges: list[dict] = []
    skipped_zero = 0
    valid_refs = {int(k) for k in nodes}  # 이 시점의 nodes 는 보행 노드만 포함

    # 2-1) DEM 노이즈 완화: way 방향 이동평균
    print(f"  고도 스무딩: +-{config.SMOOTH_HALF_WINDOW_M:.0f}m 이동평균")
    smooth_along_ways(nodes, walkable, valid_refs, config.SMOOTH_HALF_WINDOW_M)
    deltas = [abs(n["ele"] - n["ele_raw"]) for n in nodes.values()]
    if deltas:
        print(f"    보정량 평균 {sum(deltas)/len(deltas):.1f}m / 최대 {max(deltas):.1f}m")

    for w in walkable:
        tags = w.get("tags", {})
        highway = tags["highway"]
        is_steps = highway == "steps"
        refs = [n for n in w["nodes"] if n in valid_refs]
        for a, b in zip(refs, refs[1:]):
            na, nb = nodes[str(a)], nodes[str(b)]
            length = haversine(na["lat"], na["lon"], nb["lat"], nb["lon"])
            if length < 0.5:
                skipped_zero += 1
                continue
            dz = nb["ele"] - na["ele"]
            edges.append({
                "u": str(a),
                "v": str(b),
                "length": round(length, 2),
                "dz": round(dz, 2),
                "grade": round(dz / max(length, config.MIN_GRADE_BASELINE_M), 4),
                "steps": is_steps,
                "highway": highway,
                "osm_way": w["id"],
                "name": tags.get("name"),
                "incline": tags.get("incline"),
                "kind": "path",
            })

    print(f"엣지 {len(edges)}개 (길이 0 근처 {skipped_zero}개 제외)")

    # 4) 건물을 가장 가까운 보행 노드에 연결
    #    OSM 에 출입구 정보가 거의 없으므로 중심점-최근접 접속으로 근사한다.
    #    실제 출입구 위치를 확보하면 이 부분만 교체하면 된다.
    way_nodes = [(nid, nodes[nid]) for nid in nodes]
    b_connected = 0
    for b in buildings:
        bid = b["id"]
        if bid not in bld_centroids:
            continue
        lat, lon = bld_centroids[bid]
        key = f"B{bid}"
        nodes[key] = {
            "lat": lat,
            "lon": lon,
            "ele": elev[_key(lat, lon)],
            "ele_raw": elev[_key(lat, lon)],
            "kind": "building",
            "name": b["tags"]["name"],
        }
        # 최근접 보행 노드
        best, best_d = None, float("inf")
        for nid, nd in way_nodes:
            d = haversine(lat, lon, nd["lat"], nd["lon"])
            if d < best_d:
                best, best_d = nid, d
        if best is None:
            continue
        dz = nodes[best]["ele"] - nodes[key]["ele"]
        edges.append({
            "u": key,
            "v": best,
            "length": round(best_d, 2),
            "dz": round(dz, 2),
            "grade": round(dz / max(best_d, config.MIN_GRADE_BASELINE_M), 4),
            "steps": False,
            "highway": "building_access",
            "osm_way": None,
            "name": b["tags"]["name"],
            "incline": None,
            "kind": "access",
        })
        b_connected += 1
        if best_d > 60:
            print(f"  ! {b['tags']['name']}: 최근접 보행로가 {best_d:.0f}m 떨어져 있음 "
                  f"(보행로 데이터 보강 필요)")

    print(f"건물 접속 엣지 {b_connected}개")

    # 5) 통계
    grades = [abs(e["grade"]) for e in edges if e["kind"] == "path"]
    eles = [n["ele"] for n in nodes.values()]
    steps_n = sum(1 for e in edges if e["steps"])
    print("\n--- 그래프 통계 ---")
    print(f"노드 {len(nodes)}개 / 엣지 {len(edges)}개 (계단 엣지 {steps_n}개)")
    print(f"고도 범위 {min(eles):.0f} ~ {max(eles):.0f} m (고도차 {max(eles)-min(eles):.0f} m)")
    if grades:
        grades_sorted = sorted(grades)
        print(f"경사 중앙값 {grades_sorted[len(grades)//2]*100:.1f}% / "
              f"90분위 {grades_sorted[int(len(grades)*0.9)]*100:.1f}% / "
              f"최대 {max(grades)*100:.1f}%")
        over = sum(1 for g in grades if g > 0.0833)
        print(f"경사 8.33% 초과 엣지: {over}/{len(grades)} ({over/len(grades)*100:.0f}%)")

    graph = {
        "meta": {
            "bbox": config.CAMPUS_BBOX,
            "dem_dataset": config.DEM_DATASET,
            "interpolation": config.ELEVATION_INTERPOLATION,
            "note": "경사는 30m DEM 추정치. 절대값 신뢰도 낮음. 계단 정보는 OSM 확정값.",
        },
        "nodes": nodes,
        "edges": edges,
    }
    with config.GRAPH.open("w", encoding="utf-8") as fh:
        json.dump(graph, fh, ensure_ascii=False)
    print(f"\n저장: {config.GRAPH}")

    # 시각화용 GeoJSON (geojson.io 에 그대로 올려서 확인 가능)
    features = []
    for e in edges:
        u, v = nodes[e["u"]], nodes[e["v"]]
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[u["lon"], u["lat"]], [v["lon"], v["lat"]]],
            },
            "properties": {
                "highway": e["highway"],
                "steps": e["steps"],
                "length_m": e["length"],
                "grade_pct": round(e["grade"] * 100, 1),
            },
        })
    for nid, nd in nodes.items():
        if nd["kind"] != "building":
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [nd["lon"], nd["lat"]]},
            "properties": {"name": nd["name"], "ele_m": nd["ele"], "node": nid},
        })
    with config.GRAPH_GEOJSON.open("w", encoding="utf-8") as fh:
        json.dump({"type": "FeatureCollection", "features": features}, fh, ensure_ascii=False)
    print(f"저장: {config.GRAPH_GEOJSON}")


def nodes_key_set(nodes: dict[str, dict]) -> set[int]:
    """문자열 키로 저장된 보행 노드 id 를 정수 집합으로."""
    return {int(k) for k in nodes if not k.startswith("B")}


if __name__ == "__main__":
    main()
