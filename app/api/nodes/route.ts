/**
 * GET /api/nodes → 검색 드롭다운용 노드 목록
 * 계약: lib/types.ts 의 NodesResponse
 */

import { NextResponse } from 'next/server';
import { GRAPH_BUILDINGS, GRAPH_VERSION, listSearchableNodes } from '@/lib/graph';

export const dynamic = 'force-static';

export function GET() {
  return NextResponse.json({
    ok: true as const,
    version: GRAPH_VERSION,
    buildings: GRAPH_BUILDINGS,
    nodes: listSearchableNodes(),
  });
}
