/**
 * 노드 ID → SVG 좌표 변환 — UI 전용.
 *
 * 좌표는 두 곳에서 온다.
 *  1. data/graph-coords.json  — 생성기가 만든 그래프 노드 좌표 (실외 보행로 + 건물 층)
 *  2. data/coords.json        — 사람이 손으로 찍은 좌표. 충돌 시 이쪽이 이긴다.
 *
 * 건물 내부 층 노드는 실제 도면이 없어서 건물 무게중심에서 층수만큼 위/아래로 밀어 놓았다.
 * 그래서 엘리베이터 이동이 지도에서 짧은 세로선으로 보인다.
 *
 * 없는 노드는 선을 끊지 않고 건너뛰되 개발 모드에서 콘솔 경고를 남긴다.
 * 좌표 찍는 도구: /dev/coords
 */

import manualJson from '@/data/coords.json';
import graphCoordsJson from '@/data/graph-coords.json';
import type { CoordMap, NodeCoord } from '@/lib/types';

/** `_readme` 처럼 밑줄로 시작하는 메타 키는 좌표가 아니므로 제외한다. */
function sanitize(input: Record<string, unknown>): CoordMap {
  const out: CoordMap = {};
  for (const [key, value] of Object.entries(input)) {
    if (key.startsWith('_')) continue;
    if (
      value &&
      typeof value === 'object' &&
      typeof (value as NodeCoord).svg === 'string' &&
      typeof (value as NodeCoord).x === 'number' &&
      typeof (value as NodeCoord).y === 'number'
    ) {
      out[key] = value as NodeCoord;
    }
  }
  return out;
}

const GRAPH_COORDS: CoordMap = sanitize(
  ((graphCoordsJson as { coords?: Record<string, unknown> }).coords ?? {}) as Record<
    string,
    unknown
  >,
);

const MANUAL_COORDS: CoordMap = sanitize(manualJson as Record<string, unknown>);

/** 충돌 시 사람이 찍은 좌표가 이긴다. */
export const COORDS: CoordMap = { ...GRAPH_COORDS, ...MANUAL_COORDS };

/** 그래프 노드 좌표 수 (실외 보행로 + 건물 층) */
export const GRAPH_NODE_COUNT = Object.keys(GRAPH_COORDS).length;

/** 사람이 직접 찍은 지점 수 */
export const MAPPED_NODE_COUNT = Object.keys(MANUAL_COORDS).length;

/** 이전 이름 호환 */
export const WALK_NODE_COUNT = GRAPH_NODE_COUNT;

const warned = new Set<string>();

export function getCoord(nodeId: string): NodeCoord | null {
  const hit = COORDS[nodeId];
  if (hit) return hit;

  if (process.env.NODE_ENV !== 'production' && !warned.has(nodeId)) {
    warned.add(nodeId);
    console.warn(
      `[coords] "${nodeId}" 의 좌표가 없습니다. 지도에서 이 지점은 건너뜁니다.`,
    );
  }
  return null;
}

/** 이 노드가 어느 SVG 에 있는지. 없으면 null */
export function svgForNode(nodeId: string): string | null {
  return getCoord(nodeId)?.svg ?? null;
}
