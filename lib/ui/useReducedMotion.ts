'use client';

import { useEffect, useState } from 'react';

/**
 * prefers-reduced-motion 존중 — 경로 선 그리기 애니메이션을 끄기 위해 사용.
 * 서버 렌더 시에는 false 로 시작해 하이드레이션 불일치를 피한다.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    setReduced(mq.matches);

    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener('change', onChange);
    return () => mq.removeEventListener('change', onChange);
  }, []);

  return reduced;
}
