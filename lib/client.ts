/**
 * ============================================================
 *  API 클라이언트 — UI 와 엔진을 잇는 유일한 경계(seam)
 * ============================================================
 *  UI 컴포넌트는 fetch 를 직접 쓰지 않고 반드시 이 파일의 함수만 호출한다.
 *
 *  경로 탐색은 lib/graph.ts 의 순수 함수다. 그래서 두 경로가 모두 가능하다.
 *   1. /api/route 호출 (기본, 계약대로)
 *   2. API 가 죽으면 같은 함수를 브라우저에서 직접 실행 (데모 안전장치)
 *  → 데모 중 서버가 터져도 경로 안내는 계속 동작한다.
 *
 *  자연어 파싱과 시간표 OCR 은 아직 구현되지 않았다.
 *  API 가 없으면 null 을 돌려주고, UI 는 드롭다운 흐름을 그대로 유지한다.
 * ============================================================
 */

import {
  API,
  isFailure,
  type Building,
  type NodeSummary,
  type NodesResponse,
  type ParseResult,
  type RouteRequest,
  type RouteResult,
  type TimetableResult,
  type TravelMode,
} from './types';

import { GRAPH_BUILDINGS, GRAPH_VERSION, findRoute, listSearchableNodes } from './graph';
import { MOCK_PARSE, MOCK_TIMETABLE } from './mock';

const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === '1';

async function post<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`${url} ${res.status}`);
  return (await res.json()) as T;
}

/* ------------------------------------------------------------
 * 로컬 엔진 (API 폴백 겸 목 모드)
 * ---------------------------------------------------------- */

function localNodes(): { buildings: Building[]; nodes: NodeSummary[]; version: string } {
  return { buildings: GRAPH_BUILDINGS, nodes: listSearchableNodes(), version: GRAPH_VERSION };
}

function localRoute(req: RouteRequest): RouteResult {
  const result = findRoute(req);
  if (isFailure(result)) {
    // 실패를 UI 에 던지지 않고 경고가 붙은 빈 경로로 바꿔 돌려준다면 화면이 애매해진다.
    // 여기서는 그대로 throw 해서 호출자가 에러 상태를 보여주게 한다.
    throw new Error(result.error.message);
  }
  return result;
}

/* ------------------------------------------------------------
 * 공개 API
 * ---------------------------------------------------------- */

/** 검색 드롭다운용 노드 목록 */
export async function fetchNodes(): Promise<{ buildings: Building[]; nodes: NodeSummary[] }> {
  if (USE_MOCK) return localNodes();
  try {
    const res = await fetch(API.nodes);
    const json = (await res.json()) as NodesResponse;
    if (isFailure(json)) throw new Error(json.error.message);
    return { buildings: json.buildings, nodes: json.nodes };
  } catch {
    console.warn('[client] /api/nodes 실패 → 로컬 그래프로 폴백');
    return localNodes();
  }
}

/** 경로 탐색 */
export async function fetchRoute(req: RouteRequest): Promise<RouteResult> {
  if (USE_MOCK) return localRoute(req);
  try {
    const json = await post<unknown>(API.route, req);
    if (isFailure(json as never)) {
      const err = json as { error: { message: string } };
      // 서버가 명확히 "경로 없음" 이라고 답한 경우는 폴백해도 결과가 같다.
      throw new Error(err.error.message);
    }
    return json as RouteResult;
  } catch (e) {
    console.warn('[client] /api/route 실패 → 로컬 엔진으로 폴백', e);
    return localRoute(req);
  }
}

/** 자연어 파싱. 미구현이면 null → UI 는 드롭다운으로 계속 진행한다. */
export async function parseNaturalLanguage(
  text: string,
  currentNodeId?: string,
): Promise<ParseResult | null> {
  if (USE_MOCK) return MOCK_PARSE;
  try {
    const json = await post<ParseResult>(API.parse, { text, currentNodeId });
    if (isFailure(json as never)) return null;
    return json;
  } catch {
    console.warn('[client] /api/parse 를 쓸 수 없습니다 (아직 미구현)');
    return null;
  }
}

/** 시간표 이미지 업로드. 미구현이면 null. */
export async function uploadTimetable(file: File): Promise<TimetableResult | null> {
  if (USE_MOCK) return MOCK_TIMETABLE;
  try {
    const fd = new FormData();
    fd.append('image', file);
    const res = await fetch(API.timetable, { method: 'POST', body: fd });
    const json = (await res.json()) as TimetableResult;
    if (isFailure(json as never)) return null;
    return json;
  } catch {
    console.warn('[client] /api/timetable 을 쓸 수 없습니다 (아직 미구현)');
    return null;
  }
}

/** 모드 4개를 한 번에 비교 (데모 하이라이트용) */
export async function fetchRouteComparison(
  fromNodeId: string,
  toNodeId: string,
  modes: TravelMode[],
): Promise<Record<string, RouteResult>> {
  const entries = await Promise.all(
    modes.map(async (mode) => [mode, await fetchRoute({ fromNodeId, toNodeId, mode })] as const),
  );
  return Object.fromEntries(entries);
}
