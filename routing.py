"""
3단계: 프로파일별 가중 A* 경로탐색.

비용 함수
---------
    w(e) = L * (1 + alpha * max(0, |grade| - grade_free)) + stair_penalty

  - 계단(steps): 휠체어는 무한 비용(완전 차단). 나머지는 m 당 가산.
  - 경사(grade): 연속 페널티. grade_free 이하는 무료.
  - A* 휴리스틱: 직선거리(haversine). w(e) >= L 이 항상 성립하므로
    admissible 하며 최적해를 보장한다.
"""

import heapq
import json
import math

import config
from build_graph import haversine


class Graph:
    def __init__(self, path=None):
        path = path or config.GRAPH
        if not path.exists():
            raise SystemExit("data/graph.json 이 없습니다. build_graph.py 를 먼저 실행하세요.")
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
        self.meta = data["meta"]
        self.nodes = data["nodes"]
        self.edges = data["edges"]

        # 양방향 인접 리스트
        self.adj: dict[str, list[dict]] = {nid: [] for nid in self.nodes}
        for e in self.edges:
            self.adj[e["u"]].append({**e, "to": e["v"], "dir": 1})
            # 역방향은 경사 부호가 반대
            self.adj[e["v"]].append({
                **e, "to": e["u"], "dir": -1,
                "dz": -e["dz"], "grade": -e["grade"],
            })

        self.buildings = {
            nd["name"]: nid
            for nid, nd in self.nodes.items()
            if nd.get("kind") == "building"
        }

    # --- 조회 헬퍼 ---
    def nearest_node(self, lat: float, lon: float, walk_only: bool = True) -> str:
        """좌표에서 가장 가까운 노드. GPS 위치를 그래프에 스냅할 때 사용."""
        best, best_d = None, float("inf")
        for nid, nd in self.nodes.items():
            if walk_only and nd.get("kind") == "building":
                continue
            d = haversine(lat, lon, nd["lat"], nd["lon"])
            if d < best_d:
                best, best_d = nid, d
        return best

    def resolve(self, query: str) -> str | None:
        """건물명 -> 노드 id. 부분일치/공백무시 허용."""
        q = query.replace(" ", "")
        if query in self.buildings:
            return self.buildings[query]
        for name, nid in self.buildings.items():
            if q == name.replace(" ", ""):
                return nid
        cands = [(n, i) for n, i in self.buildings.items() if q in n.replace(" ", "")]
        if len(cands) == 1:
            return cands[0][1]
        cands = [(n, i) for n, i in self.buildings.items() if n.replace(" ", "") in q]
        if len(cands) == 1:
            return cands[0][1]
        return None


def edge_cost(edge: dict, profile: dict) -> float:
    """단일 엣지 통행 비용. 통행 불가면 inf.

    w = L * (1 + alpha * max(0, |grade| - grade_free) ** p) + stair_penalty

    p >= 2 (볼록) 여야 완만한 우회로가 실제로 선택된다. p=1 이면 페널티 총합이
    고도차에 의해 고정되어 최단거리해와 같아진다 (config.py 주석 참고).
    """
    length = edge["length"]

    if edge["steps"]:
        if profile["stairs_blocked"]:
            return math.inf
        stair_penalty = length * profile["stair_cost_per_m"]
    else:
        stair_penalty = 0.0

    excess = max(0.0, abs(edge["grade"]) - profile["grade_free"])
    p = profile.get("grade_exponent", 2.0)
    return length * (1.0 + profile["alpha"] * excess ** p) + stair_penalty


def astar(graph: Graph, start: str, goal: str, profile_name: str) -> dict | None:
    """가중 A*. 경로와 요약 지표를 돌려준다. 도달 불가면 None."""
    profile = config.PROFILES[profile_name]
    gn = graph.nodes[goal]

    def h(nid: str) -> float:
        nd = graph.nodes[nid]
        return haversine(nd["lat"], nd["lon"], gn["lat"], gn["lon"])

    open_heap = [(h(start), 0.0, start)]
    came_from: dict[str, tuple[str, dict]] = {}
    g_score = {start: 0.0}
    closed: set[str] = set()

    while open_heap:
        _, g_cur, cur = heapq.heappop(open_heap)
        if cur in closed:
            continue
        if cur == goal:
            return _reconstruct(graph, came_from, start, goal, g_cur, profile)
        closed.add(cur)

        for edge in graph.adj[cur]:
            nxt = edge["to"]
            if nxt in closed:
                continue
            cost = edge_cost(edge, profile)
            if cost == math.inf:
                continue
            tentative = g_cur + cost
            if tentative < g_score.get(nxt, math.inf):
                g_score[nxt] = tentative
                came_from[nxt] = (cur, edge)
                heapq.heappush(open_heap, (tentative + h(nxt), tentative, nxt))

    return None


def _reconstruct(graph, came_from, start, goal, total_cost, profile) -> dict:
    path_nodes = [goal]
    path_edges = []
    cur = goal
    while cur != start:
        prev, edge = came_from[cur]
        path_edges.append(edge)
        path_nodes.append(prev)
        cur = prev
    path_nodes.reverse()
    path_edges.reverse()

    length = sum(e["length"] for e in path_edges)
    ascent = sum(e["dz"] for e in path_edges if e["dz"] > 0)
    descent = -sum(e["dz"] for e in path_edges if e["dz"] < 0)
    grades = [abs(e["grade"]) for e in path_edges]
    stairs = [e for e in path_edges if e["steps"]]
    max_grade = max(grades) if grades else 0.0
    over = [e for e in path_edges if abs(e["grade"]) > 0.0833]

    return {
        "nodes": path_nodes,
        "edges": path_edges,
        "cost": total_cost,
        "length_m": length,
        "ascent_m": ascent,
        "descent_m": descent,
        "max_grade": max_grade,
        "mean_grade": sum(grades) / len(grades) if grades else 0.0,
        "stair_edges": len(stairs),
        "stair_length_m": sum(e["length"] for e in stairs),
        "over_833_edges": len(over),
        "over_833_length_m": sum(e["length"] for e in over),
    }


def route_geojson(graph: Graph, result: dict, props: dict) -> dict:
    coords = [
        [graph.nodes[nid]["lon"], graph.nodes[nid]["lat"]]
        for nid in result["nodes"]
    ]
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": {
            **props,
            "length_m": round(result["length_m"], 1),
            "ascent_m": round(result["ascent_m"], 1),
            "max_grade_pct": round(result["max_grade"] * 100, 1),
            "stair_edges": result["stair_edges"],
        },
    }
