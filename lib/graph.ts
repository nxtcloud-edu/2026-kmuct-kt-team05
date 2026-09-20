/**
 * ============================================================
 *  경로 탐색 엔진 — 다익스트라
 * ============================================================
 *  순수 함수다. 네트워크도 파일 I/O도 없다.
 *  그래서 서버(API 라우트)에서도 브라우저에서도 똑같이 돌아간다.
 *  → API 가 죽어도 클라이언트에서 같은 함수로 폴백할 수 있다. (데모 안전장치)
 *
 *  그래프는 data/campus-graph.json 에서 온다 (tools/build-graph.mjs 가 생성).
 *  실외 보행로·거리·계단 위치: OpenStreetMap
 *  층간 연결·엘리베이터·고도: data/campus-facts.json (학생 제보)
 * ============================================================
 */

import rawGraph from '@/data/campus-graph.json';
import {
  edgeCost,
  estimateSeconds,
  isEdgeAllowed,
  type EdgeLike,
} from './cost';
import type {
  ApiFailure,
  Building,
  CampusEdge,
  CampusNode,
  NodeSummary,
  RouteRequest,
  RouteResult,
  RouteSegment,
  RouteStep,
  StepIcon,
  TravelMode,
  Weather,
} from './types';

interface RawGraph {
  version: string;
  assumptions: Record<string, number>;
  baseElevation: Record<string, number>;
  buildings: Building[];
  nodes: CampusNode[];
  edges: CampusEdge[];
}

const GRAPH = rawGraph as unknown as RawGraph;

/* ------------------------------------------------------------
 * 인덱싱 (모듈 로드 시 1회)
 * ---------------------------------------------------------- */

interface DirectedEdge extends EdgeLike {
  to: string;
  note?: string;
}

const nodeById = new Map<string, CampusNode>();
for (const n of GRAPH.nodes) nodeById.set(n.id, n);

const adjacency = new Map<string, DirectedEdge[]>();
function push(from: string, edge: DirectedEdge) {
  const list = adjacency.get(from);
  if (list) list.push(edge);
  else adjacency.set(from, [edge]);
}

for (const e of GRAPH.edges) {
  if (!nodeById.has(e.from) || !nodeById.has(e.to)) continue;
  push(e.from, {
    to: e.to,
    distance: e.distance,
    stairsUp: e.stairsUp,
    stairsDown: e.stairsDown,
    slope: e.slope,
    indoor: e.indoor,
    elevator: e.elevator,
    note: e.note,
  });
  if (e.bidirectional) {
    // 반대 방향에서는 오르내림이 뒤집힌다
    push(e.to, {
      to: e.from,
      distance: e.distance,
      stairsUp: e.stairsDown,
      stairsDown: e.stairsUp,
      slope: e.slope,
      indoor: e.indoor,
      elevator: e.elevator,
      note: e.note,
    });
  }
}

export const GRAPH_VERSION = GRAPH.version;
export const GRAPH_ASSUMPTIONS = GRAPH.assumptions;
export const GRAPH_BUILDINGS = GRAPH.buildings;

export function listSearchableNodes(): NodeSummary[] {
  return GRAPH.nodes
    .filter((n) => n.searchable)
    .map((n) => ({
      id: n.id,
      label: n.label,
      building: n.building,
      floor: n.floor,
      aliases: n.aliases ?? [],
    }));
}

export function hasNode(id: string): boolean {
  return nodeById.has(id);
}

/* ------------------------------------------------------------
 * 다익스트라
 * ---------------------------------------------------------- */

interface PathResult {
  path: string[];
  /** edges[i] 는 path[i] → path[i+1] 로 실제 사용한 엣지 */
  edges: DirectedEdge[];
}

/**
 * ⚠️ 중요: 어떤 엣지를 썼는지 탐색 중에 기록해 둔다.
 *    같은 두 층을 계단과 엘리베이터가 동시에 잇기 때문에,
 *    나중에 노드 쌍으로 엣지를 되찾으면 실제로 고른 것과 다른 엣지를 집을 수 있다.
 */
function shortestPath(
  fromId: string,
  toId: string,
  mode: TravelMode,
  weather: Weather,
): PathResult | null {
  const dist = new Map<string, number>([[fromId, 0]]);
  const prev = new Map<string, string>();
  const prevEdge = new Map<string, DirectedEdge>();
  const settled = new Set<string>();
  // 노드가 수백 개라 이진 힙 없이도 충분히 빠르다
  const frontier = new Set<string>([fromId]);

  while (frontier.size > 0) {
    let current: string | null = null;
    let currentDist = Infinity;
    for (const id of frontier) {
      const d = dist.get(id) ?? Infinity;
      if (d < currentDist) {
        currentDist = d;
        current = id;
      }
    }
    if (current === null) break;
    if (current === toId) break;

    frontier.delete(current);
    settled.add(current);

    for (const edge of adjacency.get(current) ?? []) {
      if (settled.has(edge.to)) continue;
      if (!isEdgeAllowed(edge, mode)) continue;
      const next = currentDist + edgeCost(edge, mode, weather);
      if (next < (dist.get(edge.to) ?? Infinity)) {
        dist.set(edge.to, next);
        prev.set(edge.to, current);
        prevEdge.set(edge.to, edge);
        frontier.add(edge.to);
      }
    }
  }

  if (!dist.has(toId)) return null;

  const path = [toId];
  const used: DirectedEdge[] = [];
  let cursor = toId;
  while (cursor !== fromId) {
    const p = prev.get(cursor);
    const e = prevEdge.get(cursor);
    if (p === undefined || e === undefined) return null;
    path.push(p);
    used.push(e);
    cursor = p;
  }
  path.reverse();
  used.reverse();
  return { path, edges: used };
}

/* ------------------------------------------------------------
 * 경로 → 세그먼트 / 단계 / 요약
 * ---------------------------------------------------------- */

type SegKind = RouteSegment['kind'];

function kindOf(edge: DirectedEdge, from: CampusNode, to: CampusNode): SegKind {
  if (edge.elevator) return 'elevator';
  if (edge.stairsUp > 0 || edge.stairsDown > 0) return 'stairs';
  if (edge.indoor && from.building !== to.building) return 'bridge';
  return 'walk';
}

const floorLabel = (f: number) => (f < 0 ? `B${-f}` : `${f}층`);

function placeLabel(n: CampusNode): string {
  if (n.building === 'OUTDOOR') return '실외';
  return `${n.building} ${floorLabel(n.floor)}`;
}

interface Leg {
  from: CampusNode;
  to: CampusNode;
  edge: DirectedEdge;
  kind: SegKind;
}

function buildLegs(result: PathResult): Leg[] {
  const legs: Leg[] = [];
  for (let i = 0; i < result.edges.length; i += 1) {
    const from = nodeById.get(result.path[i]);
    const to = nodeById.get(result.path[i + 1]);
    const edge = result.edges[i];
    if (!from || !to || !edge) continue;
    legs.push({ from, to, edge, kind: kindOf(edge, from, to) });
  }
  return legs;
}

function groupSegments(legs: Leg[]): { segment: RouteSegment; legs: Leg[] }[] {
  const out: { segment: RouteSegment; legs: Leg[] }[] = [];

  for (const leg of legs) {
    const building = leg.from.building === 'OUTDOOR' ? 'OUTDOOR' : leg.from.building;
    const last = out[out.length - 1];

    const sameGroup =
      last &&
      last.segment.kind === leg.kind &&
      last.segment.building === building &&
      // 실내 도보는 층이 바뀌면 끊는다. 계단/엘리베이터는 층이 바뀌는 게 정상이므로 묶는다.
      (leg.kind !== 'walk' || last.segment.floor === leg.from.floor);

    if (sameGroup) {
      last.segment.nodeIds.push(leg.to.id);
      last.segment.distanceM += leg.edge.distance;
      last.legs.push(leg);
    } else {
      out.push({
        segment: {
          building,
          floor: leg.from.building === 'OUTDOOR' ? 0 : leg.from.floor,
          nodeIds: [leg.from.id, leg.to.id],
          kind: leg.kind,
          distanceM: leg.edge.distance,
        },
        legs: [leg],
      });
    }
  }

  for (const g of out) g.segment.distanceM = Math.round(g.segment.distanceM);
  return out;
}

function iconFor(group: { segment: RouteSegment; legs: Leg[] }): StepIcon {
  const { segment, legs } = group;
  if (segment.kind === 'elevator') return 'elevator';
  if (segment.kind === 'bridge') return 'bridge';
  if (segment.kind === 'stairs') {
    const up = legs.reduce((s, l) => s + l.edge.stairsUp, 0);
    const down = legs.reduce((s, l) => s + l.edge.stairsDown, 0);
    return up >= down ? 'stairs_up' : 'stairs_down';
  }
  const first = legs[0];
  const last = legs[legs.length - 1];
  if (first.from.building !== 'OUTDOOR' && last.to.building === 'OUTDOOR') return 'exit';
  if (first.from.building === 'OUTDOOR' && last.to.building !== 'OUTDOOR') return 'enter';
  return 'walk';
}

function textFor(group: { segment: RouteSegment; legs: Leg[] }, icon: StepIcon): string {
  const { segment, legs } = group;
  const first = legs[0];
  const last = legs[legs.length - 1];
  const dist = segment.distanceM;

  switch (segment.kind) {
    case 'elevator': {
      const from = floorLabel(first.from.floor);
      const to = floorLabel(last.to.floor);
      const where = first.from.building;
      const note = first.edge.note ? ` (${first.edge.note})` : '';
      return `${where} 엘리베이터로 ${from} → ${to} 이동합니다.${note}`;
    }
    case 'bridge': {
      return `${placeLabel(first.from)} 에서 ${placeLabel(
        last.to,
      )} 로 연결통로를 통해 건너갑니다. 계단이 없습니다.`;
    }
    case 'stairs': {
      const up = legs.reduce((s, l) => s + l.edge.stairsUp, 0);
      const down = legs.reduce((s, l) => s + l.edge.stairsDown, 0);
      const total = up + down;
      const direction = up >= down ? '올라갑니다' : '내려갑니다';
      if (first.from.building === 'OUTDOOR' || last.to.building === 'OUTDOOR') {
        return `실외 계단을 ${direction}. (약 ${total}칸)`;
      }
      return `${first.from.building} 계단으로 ${floorLabel(first.from.floor)} → ${floorLabel(
        last.to.floor,
      )} ${direction}. (약 ${total}칸)`;
    }
    default: {
      const maxSlope = Math.max(...legs.map((l) => l.edge.slope));
      const slopeNote = maxSlope >= 0.08 ? ` 경사 약 ${Math.round(maxSlope * 100)}% 구간입니다.` : '';
      if (icon === 'exit') return `${placeLabel(first.from)} 에서 건물 밖으로 나갑니다.`;
      if (icon === 'enter') return `${placeLabel(last.to)} 으로 들어갑니다.`;
      if (first.from.building === 'OUTDOOR') {
        return `실외 보행로를 따라 ${dist}m 이동합니다.${slopeNote}`;
      }
      return `${placeLabel(first.from)} 복도를 따라 ${dist}m 이동합니다.`;
    }
  }
}

/* ------------------------------------------------------------
 * 메인
 * ---------------------------------------------------------- */

function assemble(
  request: RouteRequest,
  result: PathResult,
  appliedMode: TravelMode,
  warnings: string[],
): RouteResult {
  const path = result.path;
  const legs = buildLegs(result);
  const groups = groupSegments(legs);

  let distanceM = 0;
  let stairsUp = 0;
  let stairsDown = 0;
  let elevatorCount = 0;
  let maxSlope = 0;
  let outdoorM = 0;
  let slopeWeightedM = 0;

  for (const leg of legs) {
    distanceM += leg.edge.distance;
    stairsUp += leg.edge.stairsUp;
    stairsDown += leg.edge.stairsDown;
    if (leg.edge.elevator) elevatorCount += 1;
    maxSlope = Math.max(maxSlope, leg.edge.slope);
    if (!leg.edge.indoor) outdoorM += leg.edge.distance;
    slopeWeightedM += leg.edge.slope * leg.edge.distance;
  }

  const seconds = estimateSeconds({
    distanceM,
    outdoorM,
    stairsUp,
    stairsDown,
    elevatorCount,
    slopeWeightedM,
  });

  const steps: RouteStep[] = groups.map((group, index) => {
    const icon = iconFor(group);
    return {
      index,
      icon,
      text: textFor(group, icon),
      distanceM: group.segment.distanceM,
      building: group.segment.building,
      floor: group.segment.floor,
      focusNodeId: group.segment.nodeIds[0],
    };
  });

  const lastNode = nodeById.get(path[path.length - 1]);
  steps.push({
    index: steps.length,
    icon: 'arrive',
    text: `${lastNode ? lastNode.label : '목적지'} 에 도착했습니다.`,
    distanceM: 0,
    building: lastNode?.building ?? 'OUTDOOR',
    floor: lastNode?.floor ?? 0,
    focusNodeId: path[path.length - 1],
  });

  return {
    ok: true,
    request,
    summary: {
      distanceM: Math.round(distanceM),
      durationMin: Math.max(1, Math.ceil(seconds / 60)),
      stairsUp,
      stairsDown,
      elevatorCount,
      maxSlope: Math.round(maxSlope * 100) / 100,
      outdoorM: Math.round(outdoorM),
      barrierFree: stairsUp === 0 && stairsDown === 0,
    },
    segments: groups.map((g) => g.segment),
    steps,
    narration: null,
    warnings,
    appliedMode,
  };
}

const fail = (code: ApiFailure['error']['code'], message: string): ApiFailure => ({
  ok: false,
  error: { code, message },
});

/**
 * 경로 탐색.
 * 무장애로 경로가 없으면 계단최소로 대체하고 warnings 에 알린다.
 */
export function findRoute(request: RouteRequest): RouteResult | ApiFailure {
  const { fromNodeId, toNodeId, mode } = request;
  const weather: Weather = request.weather ?? 'clear';

  if (!fromNodeId || !toNodeId) {
    return fail('BAD_REQUEST', '출발지와 도착지를 모두 지정해 주세요.');
  }
  if (!nodeById.has(fromNodeId)) {
    return fail('NODE_NOT_FOUND', `출발 지점을 찾을 수 없습니다: ${fromNodeId}`);
  }
  if (!nodeById.has(toNodeId)) {
    return fail('NODE_NOT_FOUND', `도착 지점을 찾을 수 없습니다: ${toNodeId}`);
  }
  if (fromNodeId === toNodeId) {
    return fail('BAD_REQUEST', '출발지와 도착지가 같습니다.');
  }

  const warnings: string[] = [];
  let appliedMode = mode;
  let result = shortestPath(fromNodeId, toNodeId, mode, weather);

  if (!result && mode === 'barrier_free') {
    result = shortestPath(fromNodeId, toNodeId, 'fewest_stairs', weather);
    if (result) {
      appliedMode = 'fewest_stairs';
      warnings.push(
        '계단이 없고 경사가 8% 이하인 무장애 경로를 찾지 못했습니다. ' +
          '계단이 가장 적은 경로로 안내하지만 휠체어로는 통과하기 어려울 수 있습니다.',
      );
    }
  }

  if (!result) {
    return fail('NO_ROUTE', '두 지점을 잇는 경로를 찾지 못했습니다.');
  }

  warnings.push(
    '실외 보행로·거리·계단 위치는 OpenStreetMap 실측 데이터입니다. 층간 연결과 엘리베이터는 학생 제보입니다.',
  );
  warnings.push(
    `경사와 건물 내 계단 칸수는 층고 ${GRAPH.assumptions.floorHeightM}m 가정으로 계산한 추정값입니다.`,
  );

  return assemble(request, result, appliedMode, warnings);
}
