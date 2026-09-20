'use client';

/**
 * 경로 탐색 상태 관리 — UI 전용.
 *
 * 출발/도착/모드가 바뀌면 자동으로 재탐색한다.
 * 늦게 도착한 응답이 최신 결과를 덮어쓰지 않도록 요청 순번으로 막는다.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchRoute } from '@/lib/client';
import type { RouteResult, TravelMode, Weather } from '@/lib/types';
import { buildRouteView, type RouteView, EMPTY_ROUTE_VIEW } from './route-view';

export type RouteStatus =
  | 'idle'      // 출발/도착 미선택
  | 'same'      // 출발 == 도착
  | 'loading'
  | 'ready'
  | 'error';

export interface UseRouteResult {
  result: RouteResult | null;
  view: RouteView;
  status: RouteStatus;
  error: string | null;
  retry: () => void;
}

export function useRoute(
  fromNodeId: string | null,
  toNodeId: string | null,
  mode: TravelMode,
  weather?: Weather,
): UseRouteResult {
  const [result, setResult] = useState<RouteResult | null>(null);
  const [status, setStatus] = useState<RouteStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [nonce, setNonce] = useState(0);
  const requestIdRef = useRef(0);

  useEffect(() => {
    if (!fromNodeId || !toNodeId) {
      requestIdRef.current += 1;
      setStatus('idle');
      setResult(null);
      setError(null);
      return;
    }

    if (fromNodeId === toNodeId) {
      requestIdRef.current += 1;
      setStatus('same');
      setResult(null);
      setError(null);
      return;
    }

    requestIdRef.current += 1;
    const requestId = requestIdRef.current;
    setStatus('loading');
    setError(null);

    fetchRoute({ fromNodeId, toNodeId, mode, weather })
      .then((res) => {
        if (requestIdRef.current !== requestId) return;
        setResult(res);
        setStatus('ready');
      })
      .catch((e: unknown) => {
        if (requestIdRef.current !== requestId) return;
        setResult(null);
        setError(e instanceof Error ? e.message : '경로를 불러오지 못했습니다.');
        setStatus('error');
      });
  }, [fromNodeId, toNodeId, mode, weather, nonce]);

  const view = useMemo(
    () => (status === 'ready' ? buildRouteView(result) : EMPTY_ROUTE_VIEW),
    [result, status],
  );

  const retry = useCallback(() => setNonce((n) => n + 1), []);

  return { result, view, status, error, retry };
}
