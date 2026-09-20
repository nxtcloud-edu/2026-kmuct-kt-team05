'use client';

/**
 * 검색 드롭다운용 노드 목록 로딩 — UI 전용.
 * lib/client.ts 의 fetchNodes() 만 호출한다. fetch 를 직접 쓰지 않는다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchNodes } from '@/lib/client';
import type { Building, NodeSummary } from '@/lib/types';

export type NodesStatus = 'loading' | 'ready' | 'error';

export interface UseNodesResult {
  nodes: NodeSummary[];
  buildings: Building[];
  byId: Map<string, NodeSummary>;
  status: NodesStatus;
  reload: () => void;
}

export function useNodes(): UseNodesResult {
  const [nodes, setNodes] = useState<NodeSummary[]>([]);
  const [buildings, setBuildings] = useState<Building[]>([]);
  const [status, setStatus] = useState<NodesStatus>('loading');
  const [nonce, setNonce] = useState(0);
  const aliveRef = useRef(true);

  useEffect(() => {
    aliveRef.current = true;
    setStatus('loading');

    fetchNodes()
      .then((data) => {
        if (!aliveRef.current) return;
        setNodes(data.nodes);
        setBuildings(data.buildings);
        setStatus('ready');
      })
      .catch(() => {
        if (!aliveRef.current) return;
        setStatus('error');
      });

    return () => {
      aliveRef.current = false;
    };
  }, [nonce]);

  const byId = useMemo(() => {
    const map = new Map<string, NodeSummary>();
    nodes.forEach((n) => map.set(n.id, n));
    return map;
  }, [nodes]);

  const reload = useCallback(() => setNonce((n) => n + 1), []);

  return { nodes, buildings, byId, status, reload };
}

/**
 * 라벨 + 별칭 + 건물명으로 검색. 정확히 시작하는 항목을 위로 올린다.
 */
export function filterNodes(nodes: NodeSummary[], query: string, limit = 40): NodeSummary[] {
  const q = query.trim().toLowerCase().replace(/\s+/g, '');
  if (!q) return nodes.slice(0, limit);

  const scored: { node: NodeSummary; score: number }[] = [];

  for (const node of nodes) {
    const haystacks = [
      node.label,
      node.building,
      `${node.building}${node.floor}f`,
      ...(node.aliases ?? []),
    ].map((s) => s.toLowerCase().replace(/\s+/g, ''));

    let best = -1;
    for (const h of haystacks) {
      if (h.startsWith(q)) {
        best = Math.max(best, 2);
      } else if (h.includes(q)) {
        best = Math.max(best, 1);
      }
    }
    if (best >= 0) scored.push({ node, score: best });
  }

  scored.sort((a, b) => b.score - a.score || a.node.label.localeCompare(b.node.label, 'ko'));
  return scored.slice(0, limit).map((s) => s.node);
}
