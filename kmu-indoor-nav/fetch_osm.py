"""
1단계: Overpass API 로 국민대 캠퍼스 OSM 원본 데이터를 내려받는다.

가져오는 것:
  - 보행 가능 way + 그 way 를 구성하는 노드 좌표
  - 이름이 있는 건물 폴리곤 (목적지 후보)
  - entrance 노드 (건물 출입구)

사용법:  python fetch_osm.py
결과:    data/raw_osm.json
"""

import json
import sys
import time

import requests

import config


def overpass(query: str) -> dict:
    """Overpass API 호출. 실패 시 재시도."""
    last_err = None
    for attempt in range(1, 4):
        try:
            resp = requests.post(
                config.OVERPASS_URL,
                data={"data": query},
                headers={"User-Agent": config.USER_AGENT},
                timeout=180,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as err:  # noqa: BLE001 - 네트워크/파싱 모두 재시도 대상
            last_err = err
            wait = attempt * 5
            print(f"  ! 실패 ({err}) - {wait}초 후 재시도 {attempt}/3", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"Overpass 호출 실패: {last_err}")


def main() -> None:
    minlat, minlon, maxlat, maxlon = config.CAMPUS_BBOX
    bbox = f"{minlat},{minlon},{maxlat},{maxlon}"

    # way 와 그 구성 노드를 함께 받는다. (._;>;) 는 결과 집합의 하위 노드를 추가.
    query = f"""
    [out:json][timeout:180];
    (
      way["highway"]({bbox});
      way["building"]["name"]({bbox});
      node["entrance"]({bbox});
    );
    (._;>;);
    out body;
    """

    print(f"Overpass 조회 중... bbox={bbox}")
    data = overpass(query)

    elements = data.get("elements", [])
    nodes = [e for e in elements if e["type"] == "node"]
    ways = [e for e in elements if e["type"] == "way"]

    walkable = [
        w for w in ways
        if w.get("tags", {}).get("highway") in config.WALKABLE_HIGHWAYS
    ]
    buildings = [
        w for w in ways
        if "building" in w.get("tags", {}) and w.get("tags", {}).get("name")
    ]
    entrances = [n for n in nodes if "entrance" in n.get("tags", {})]

    print(f"  노드 {len(nodes)}개")
    print(f"  way {len(ways)}개 중 보행가능 {len(walkable)}개")
    print(f"  이름있는 건물 {len(buildings)}개")
    print(f"  출입구 노드 {len(entrances)}개")

    # 보행가능 way 의 highway 종류별 분포
    kinds: dict[str, int] = {}
    for w in walkable:
        k = w["tags"]["highway"]
        kinds[k] = kinds.get(k, 0) + 1
    print("  보행가능 way 분포:")
    for k, v in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"    {v:4d}  {k}")

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with config.RAW_OSM.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    print(f"\n저장: {config.RAW_OSM}")


if __name__ == "__main__":
    main()
