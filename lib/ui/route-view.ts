/**
 * RouteResult(엔진 응답) → 지도에 그릴 수 있는 뷰 모델로 변환 — UI 전용.
 *
 * 엔진은 좌표를 모르고 nodeIds 만 준다. 여기서 coords.json 을 붙여
 * "SVG 한 장 = 레이어" 단위로 쪼갠다.
 *
 * 한 세그먼트가 여러 SVG 에 걸치는 경우(예: 계단으로 4F→1F, 연결통로로 다른 건물)
 * 각 SVG 조각을 run 으로 나누고, 조각 사이에 이동 배지(exitTo / enterFrom)를 만든다.
 */

import type { RouteResult, RouteSegment } from '@/lib/types';
import { getCoord } from './coords';
import { getMapMeta, type MapMeta } from './maps';

export type SegmentKind = RouteSegment['kind'];

export interface ViewPoint {
  nodeId: string;
  x: number;
  y: number;
}

export interface RunLink {
  src: string;
  label: string;
  short: string;
}

export interface DrawnRun {
  /** 안정적인 React key */
  id: string;
  /** 원본 RouteResult.segments 인덱스 */
  segIndex: number;
  src: string;
  kind: SegmentKind;
  points: ViewPoint[];
  /** SVG 좌표계 기준 대략적인 경로 길이. 선 그리기 애니메이션에 사용 */
  length: number;
  /** 다음 조각이 다른 SVG 에 있을 때 */
  exitTo: RunLink | null;
  /** 이전 조각이 다른 SVG 에 있을 때 */
  enterFrom: RunLink | null;
  /**
   * 점이 1개뿐이고 그 점이 같은 SVG 의 인접 run 에도 이미 있는 경우 true.
   * 렌더러는 이때 점 마커를 중복으로 찍지 않고 이동 배지만 표시한다.
   */
  redundant: boolean;
}

export interface MapLayer {
  src: string;
  meta: MapMeta;
  runs: DrawnRun[];
  /** 경로에서 이 레이어가 처음 등장한 순서 (0부터) */
  order: number;
}

export interface RouteView {
  layers: MapLayer[];
  /** 출발 노드 (좌표 해석 여부와 무관하게 원본값) */
  startNodeId: string | null;
  endNodeId: string | null;
  /** coords.json 에 좌표가 없어 건너뛴 노드들. 개발 중 경고 배너로 노출 */
  missingNodeIds: string[];
  /** 좌표 해석에 성공한 노드 → SVG 경로 */
  nodeSvg: Record<string, string>;
}

export const EMPTY_ROUTE_VIEW: RouteView = {
  layers: [],
  startNodeId: null,
  endNodeId: null,
  missingNodeIds: [],
  nodeSvg: {},
};

function toLink(src: string): RunLink {
  const meta = getMapMeta(src);
  return { src, label: meta.label, short: meta.short };
}

function polylineLength(points: ViewPoint[]): number {
  let total = 0;
  for (let i = 1; i < points.length; i += 1) {
    const dx = points[i].x - points[i - 1].x;
    const dy = points[i].y - points[i - 1].y;
    total += Math.hypot(dx, dy);
  }
  return total;
}

export function buildRouteView(result: RouteResult | null): RouteView {
  if (!result || result.segments.length === 0) return EMPTY_ROUTE_VIEW;

  const runs: DrawnRun[] = [];
  const missing: string[] = [];
  const nodeSvg: Record<string, string> = {};

  result.segments.forEach((segment, segIndex) => {
    let currentRun: DrawnRun | undefined;
    let currentSrc: string | undefined;

    for (const nodeId of segment.nodeIds) {
      const coord = getCoord(nodeId);
      if (!coord) {
        if (!missing.includes(nodeId)) missing.push(nodeId);
        continue;
      }
      nodeSvg[nodeId] = coord.svg;

      if (currentRun === undefined || currentSrc !== coord.svg) {
        const run: DrawnRun = {
          id: `seg${segIndex}-run${runs.length}`,
          segIndex,
          src: coord.svg,
          kind: segment.kind,
          points: [],
          length: 0,
          exitTo: null,
          enterFrom: null,
          redundant: false,
        };
        runs.push(run);
        currentRun = run;
        currentSrc = coord.svg;
      }

      const points = currentRun.points;
      const last = points[points.length - 1];
      // 세그먼트 경계에서 같은 노드가 연달아 오는 경우 중복 점을 만들지 않는다.
      if (!last || last.nodeId !== nodeId) {
        points.push({ nodeId, x: coord.x, y: coord.y });
      }
    }
  });

  // 조각 사이 이동 배지 연결
  for (let i = 0; i < runs.length; i += 1) {
    const run = runs[i];
    run.length = polylineLength(run.points);

    const next = runs[i + 1];
    if (next && next.src !== run.src) {
      run.exitTo = toLink(next.src);
      next.enterFrom = toLink(run.src);
    }
  }

  // 인접 run 과 겹치는 1점 run 은 마커를 중복 렌더하지 않도록 표시
  for (let i = 0; i < runs.length; i += 1) {
    const run = runs[i];
    if (run.points.length !== 1) continue;
    const only = run.points[0].nodeId;
    const neighbours = [runs[i - 1], runs[i + 1]].filter(Boolean) as DrawnRun[];
    run.redundant = neighbours.some(
      (n) => n.src === run.src && n.points.some((p) => p.nodeId === only),
    );
  }

  // 레이어로 묶기 (경로에서 처음 등장한 순서 유지)
  const layerMap = new Map<string, MapLayer>();
  runs.forEach((run) => {
    let layer = layerMap.get(run.src);
    if (!layer) {
      layer = {
        src: run.src,
        meta: getMapMeta(run.src),
        runs: [],
        order: layerMap.size,
      };
      layerMap.set(run.src, layer);
    }
    layer.runs.push(run);
  });

  const first = result.segments[0];
  const last = result.segments[result.segments.length - 1];

  return {
    layers: [...layerMap.values()],
    startNodeId: first.nodeIds[0] ?? null,
    endNodeId: last.nodeIds[last.nodeIds.length - 1] ?? null,
    missingNodeIds: missing,
    nodeSvg,
  };
}
