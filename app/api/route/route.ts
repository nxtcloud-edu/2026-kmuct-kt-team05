/**
 * POST /api/route → 경로 탐색
 * 계약: lib/types.ts 의 RouteRequest → RouteResponse
 *
 * 실패는 예외를 던지지 않고 항상 HTTP 200 + { ok:false, error } 봉투로 돌려준다.
 */

import { NextResponse } from 'next/server';
import { findRoute } from '@/lib/graph';
import { TRAVEL_MODES, type RouteRequest, type TravelMode, type Weather } from '@/lib/types';

function badRequest(message: string) {
  return NextResponse.json({ ok: false as const, error: { code: 'BAD_REQUEST' as const, message } });
}

export async function POST(request: Request) {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return badRequest('요청 본문이 올바른 JSON 이 아닙니다.');
  }

  if (typeof body !== 'object' || body === null) {
    return badRequest('요청 본문이 비어 있습니다.');
  }

  const raw = body as Record<string, unknown>;
  const fromNodeId = typeof raw.fromNodeId === 'string' ? raw.fromNodeId : null;
  const toNodeId = typeof raw.toNodeId === 'string' ? raw.toNodeId : null;
  const mode = TRAVEL_MODES.includes(raw.mode as TravelMode) ? (raw.mode as TravelMode) : null;
  const weather: Weather | undefined =
    raw.weather === 'rain' || raw.weather === 'clear' ? raw.weather : undefined;

  if (!fromNodeId || !toNodeId) {
    return badRequest('fromNodeId 와 toNodeId 는 문자열이어야 합니다.');
  }
  if (!mode) {
    return badRequest(`mode 는 다음 중 하나여야 합니다: ${TRAVEL_MODES.join(', ')}`);
  }

  const req: RouteRequest = { fromNodeId, toNodeId, mode, weather };

  try {
    return NextResponse.json(findRoute(req));
  } catch (e) {
    return NextResponse.json({
      ok: false as const,
      error: {
        code: 'INTERNAL' as const,
        message: `경로 계산 중 오류가 발생했습니다: ${
          e instanceof Error ? e.message : '알 수 없는 오류'
        }`,
      },
    });
  }
}
