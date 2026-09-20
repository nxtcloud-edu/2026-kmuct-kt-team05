'use client';

/**
 * SVG 지도 + 경로 오버레이.
 *
 * 실제 지도 API 를 쓰지 않는다. 직접 그린 SVG(public/maps/*.svg) 위에
 * 엔진이 준 nodeIds → coords.json 으로 변환한 폴리라인을 얹는다.
 *
 * 구조:
 *  - 배경: <img> (SVG 파일 그대로)
 *  - 경로: 같은 viewBox 를 쓰는 오버레이 <svg> (aria-hidden, 순수 그래픽)
 *  - 층 이동 배지: HTML <button> 으로 지도 위에 절대배치 (키보드 접근 가능해야 하므로)
 *
 * 배경 img 와 오버레이 svg 의 종횡비를 컨테이너 aspect-ratio 로 강제해서
 * 레터박스 없이 좌표가 1:1 로 맞도록 한다.
 */

import { useEffect, useMemo, useState } from 'react';
import { CornerDownRight, Flag, Layers, MapPin } from 'lucide-react';
import type { TravelMode } from '@/lib/types';
import type { DrawnRun, MapLayer, RouteView } from '@/lib/ui/route-view';
import { KIND_STYLE, MODE_STYLE } from '@/lib/ui/theme';
import { getMapMeta } from '@/lib/ui/maps';
import { useReducedMotion } from '@/lib/ui/useReducedMotion';
import { cn } from '@/lib/ui/cn';

interface MapViewProps {
  view: RouteView;
  mode: TravelMode;
  loading?: boolean;
  focusNodeId: string | null;
  fromLabel?: string | null;
  toLabel?: string | null;
  /** 경로가 아직 없을 때 지도 위에 보여줄 안내 문구 */
  placeholder?: string;
}

export function MapView({
  view,
  mode,
  loading = false,
  focusNodeId,
  fromLabel,
  toLabel,
  placeholder = '출발지와 도착지를 선택하면 경로가 표시됩니다.',
}: MapViewProps) {
  const reduced = useReducedMotion();
  const [activeSrc, setActiveSrc] = useState<string | null>(null);

  // 경로가 바뀌면 첫 레이어로. 이미 보고 있는 레이어가 여전히 존재하면 유지한다.
  useEffect(() => {
    if (view.layers.length === 0) {
      setActiveSrc(null);
      return;
    }
    setActiveSrc((prev) =>
      prev && view.layers.some((l) => l.src === prev) ? prev : view.layers[0].src,
    );
  }, [view]);

  // 단계 리스트에서 항목을 고르면 그 노드가 있는 층으로 이동
  useEffect(() => {
    if (!focusNodeId) return;
    const src = view.nodeSvg[focusNodeId];
    if (src) setActiveSrc(src);
  }, [focusNodeId, view]);

  const activeLayer: MapLayer | null = useMemo(
    () => view.layers.find((l) => l.src === activeSrc) ?? null,
    [view.layers, activeSrc],
  );

  const meta = activeLayer?.meta ?? getMapMeta('/maps/campus.svg');

  const animKey = `${activeSrc ?? 'none'}|${mode}|${view.layers.length}|${view.startNodeId ?? ''}|${view.endNodeId ?? ''}`;
  const [drawnKey, setDrawnKey] = useState<string | null>(null);

  useEffect(() => {
    if (reduced) {
      setDrawnKey(animKey);
      return;
    }
    setDrawnKey(null);
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setDrawnKey(animKey));
    });
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
    };
  }, [animKey, reduced]);

  const drawn = drawnKey === animKey;
  const stroke = MODE_STYLE[mode].stroke;

  const kindsPresent = useMemo(() => {
    const set = new Set<DrawnRun['kind']>();
    view.layers.forEach((l) => l.runs.forEach((r) => set.add(r.kind)));
    return [...set];
  }, [view.layers]);

  const startOnThisMap = view.startNodeId ? view.nodeSvg[view.startNodeId] === activeSrc : false;
  const endOnThisMap = view.endNodeId ? view.nodeSvg[view.endNodeId] === activeSrc : false;

  const pointOf = (nodeId: string | null) => {
    if (!nodeId || !activeLayer) return null;
    for (const run of activeLayer.runs) {
      const hit = run.points.find((p) => p.nodeId === nodeId);
      if (hit) return hit;
    }
    return null;
  };

  const startPoint = startOnThisMap ? pointOf(view.startNodeId) : null;
  const endPoint = endOnThisMap ? pointOf(view.endNodeId) : null;
  const focusPoint = pointOf(focusNodeId);

  const pct = (x: number, y: number) => ({
    left: `${(x / meta.width) * 100}%`,
    top: `${(y / meta.height) * 100}%`,
  });

  return (
    <section aria-label="경로 지도" className="flex flex-col gap-2">
      {/* 층 탭 */}
      {view.layers.length > 0 && (
        <div
          role="tablist"
          aria-label="층 선택"
          className="flex items-center gap-1.5 overflow-x-auto pb-1"
        >
          <Layers className="size-4 shrink-0 text-slate-400" aria-hidden="true" />
          {view.layers.map((layer, index) => {
            const selected = layer.src === activeSrc;
            return (
              <button
                key={layer.src}
                role="tab"
                type="button"
                aria-selected={selected}
                aria-controls="map-panel"
                tabIndex={selected ? 0 : -1}
                onClick={() => setActiveSrc(layer.src)}
                onKeyDown={(e) => {
                  if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
                  e.preventDefault();
                  const delta = e.key === 'ArrowRight' ? 1 : -1;
                  const next = (index + delta + view.layers.length) % view.layers.length;
                  setActiveSrc(view.layers[next].src);
                }}
                className={cn(
                  'flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 text-sm font-semibold transition',
                  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-blue-500',
                  selected
                    ? 'border-slate-900 bg-slate-900 text-white'
                    : 'border-slate-300 bg-white text-slate-600 hover:border-slate-400 hover:bg-slate-50',
                )}
              >
                <span className="grid size-5 place-items-center rounded-full bg-white/20 text-[11px] font-bold">
                  {index + 1}
                </span>
                {layer.meta.label}
              </button>
            );
          })}
        </div>
      )}

      {/* 지도 패널 */}
      <div
        id="map-panel"
        role="tabpanel"
        aria-label={`${meta.label} 지도`}
        className="relative overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-sm"
        style={{ aspectRatio: `${meta.width} / ${meta.height}` }}
      >
        {/* 배경 도면 */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={activeLayer ? meta.src : '/maps/campus.svg'}
          alt={`${meta.label} 도면`}
          className="absolute inset-0 h-full w-full select-none"
          draggable={false}
        />

        {/* 경로 오버레이 (순수 그래픽) */}
        {activeLayer && (
          <svg
            viewBox={`0 0 ${meta.width} ${meta.height}`}
            className="absolute inset-0 h-full w-full"
            aria-hidden="true"
          >
            {/* 흰 테두리(casing) → 배경 위에서도 선이 또렷하게 */}
            {activeLayer.runs
              .filter((run) => run.points.length >= 2)
              .map((run) => (
                <polyline
                  key={`${run.id}-casing`}
                  points={run.points.map((p) => `${p.x},${p.y}`).join(' ')}
                  fill="none"
                  stroke="#ffffff"
                  strokeWidth={KIND_STYLE[run.kind].width + 5}
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  opacity={0.9}
                />
              ))}

            {activeLayer.runs.map((run) => {
              const kind = KIND_STYLE[run.kind];
              if (run.points.length >= 2) {
                const len = Math.max(1, run.length);
                const isSolid = kind.dash === null;
                return (
                  <polyline
                    key={run.id}
                    points={run.points.map((p) => `${p.x},${p.y}`).join(' ')}
                    fill="none"
                    stroke={stroke}
                    strokeWidth={kind.width}
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    style={
                      isSolid
                        ? {
                            strokeDasharray: len,
                            strokeDashoffset: drawn ? 0 : len,
                            transition: reduced
                              ? undefined
                              : 'stroke-dashoffset 480ms cubic-bezier(0.22, 1, 0.36, 1)',
                          }
                        : {
                            strokeDasharray: kind.dash ?? undefined,
                            opacity: drawn ? 1 : 0,
                            transition: reduced ? undefined : 'opacity 320ms ease-out',
                          }
                    }
                  />
                );
              }

              // 점이 하나뿐이고 인접 run 과 겹치지 않는 경우에만 표식을 찍는다.
              if (run.points.length === 1 && !run.redundant) {
                const p = run.points[0];
                return (
                  <circle
                    key={run.id}
                    cx={p.x}
                    cy={p.y}
                    r={7}
                    fill={stroke}
                    stroke="#ffffff"
                    strokeWidth={3}
                    style={{
                      opacity: drawn ? 1 : 0,
                      transition: reduced ? undefined : 'opacity 320ms ease-out',
                    }}
                  />
                );
              }
              return null;
            })}

            {/* 선택된 단계 강조 */}
            {focusPoint && (
              <g>
                <circle
                  cx={focusPoint.x}
                  cy={focusPoint.y}
                  r={18}
                  fill="none"
                  stroke={stroke}
                  strokeWidth={3}
                  opacity={0.45}
                />
                <circle cx={focusPoint.x} cy={focusPoint.y} r={6} fill={stroke} />
              </g>
            )}

            {/* 출발 / 도착 핀 */}
            {startPoint && (
              <g>
                <circle cx={startPoint.x} cy={startPoint.y} r={11} fill="#ffffff" />
                <circle cx={startPoint.x} cy={startPoint.y} r={8} fill="#10b981" />
              </g>
            )}
            {endPoint && (
              <g>
                <circle cx={endPoint.x} cy={endPoint.y} r={11} fill="#ffffff" />
                <circle cx={endPoint.x} cy={endPoint.y} r={8} fill="#f43f5e" />
              </g>
            )}
          </svg>
        )}

        {/* 층 이동 배지 (키보드로 조작 가능해야 하므로 HTML 버튼) */}
        {activeLayer?.runs.map((run) => {
          const nodes: React.ReactNode[] = [];

          if (run.enterFrom && run.points.length > 0) {
            const p = run.points[0];
            nodes.push(
              <button
                key={`${run.id}-enter`}
                type="button"
                onClick={() => setActiveSrc(run.enterFrom!.src)}
                style={{ ...pct(p.x, p.y), transform: 'translate(-50%, -160%)' }}
                className="absolute flex items-center gap-1 whitespace-nowrap rounded-full border border-slate-300 bg-white/95 px-2.5 py-1 text-[11px] font-semibold text-slate-600 shadow-sm backdrop-blur transition hover:border-slate-500 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
              >
                ← {run.enterFrom.short}에서
              </button>,
            );
          }

          if (run.exitTo && run.points.length > 0) {
            const p = run.points[run.points.length - 1];
            nodes.push(
              <button
                key={`${run.id}-exit`}
                type="button"
                onClick={() => setActiveSrc(run.exitTo!.src)}
                style={{ ...pct(p.x, p.y), transform: 'translate(-50%, 60%)' }}
                className="absolute flex items-center gap-1 whitespace-nowrap rounded-full border-2 border-emerald-500 bg-white px-2.5 py-1 text-[11px] font-bold text-emerald-700 shadow-md transition hover:bg-emerald-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
              >
                <CornerDownRight className="size-3" aria-hidden="true" />
                {run.exitTo.label}로 이동
              </button>,
            );
          }

          return nodes;
        })}

        {/* 출발 / 도착 라벨 칩 */}
        {startPoint && fromLabel && (
          <span
            style={{ ...pct(startPoint.x, startPoint.y), transform: 'translate(-50%, -210%)' }}
            className="absolute flex items-center gap-1 whitespace-nowrap rounded-full bg-emerald-600 px-2.5 py-1 text-[11px] font-bold text-white shadow-md"
          >
            <MapPin className="size-3" aria-hidden="true" />
            출발 · {fromLabel}
          </span>
        )}
        {endPoint && toLabel && (
          <span
            style={{ ...pct(endPoint.x, endPoint.y), transform: 'translate(-50%, -210%)' }}
            className="absolute flex items-center gap-1 whitespace-nowrap rounded-full bg-rose-600 px-2.5 py-1 text-[11px] font-bold text-white shadow-md"
          >
            <Flag className="size-3" aria-hidden="true" />
            도착 · {toLabel}
          </span>
        )}

        {/* 경로 없음 안내 */}
        {!activeLayer && !loading && (
          <div className="absolute inset-0 grid place-items-center bg-white/65 p-6 backdrop-blur-[1px]">
            <p className="max-w-xs text-center text-sm font-medium text-slate-600">{placeholder}</p>
          </div>
        )}

        {/* 로딩 */}
        {loading && (
          <div className="absolute inset-0 grid place-items-center bg-white/70 backdrop-blur-[1px]">
            <div className="flex flex-col items-center gap-3">
              <span className="size-8 animate-spin rounded-full border-[3px] border-slate-300 border-t-slate-800" />
              <p className="text-sm font-medium text-slate-600">경로를 계산하는 중…</p>
            </div>
          </div>
        )}

        {/* 축척 대신 쓰는 안내: 좌표계가 우리 것임을 명시 */}
        {activeLayer && (
          <span className="absolute bottom-2 right-3 rounded bg-white/80 px-2 py-0.5 text-[10px] font-medium text-slate-500">
            {meta.width}×{meta.height} 자체 좌표계
          </span>
        )}
      </div>

      {/* 범례 — 색 외에 선 모양으로도 구분된다는 것을 보여준다 */}
      {kindsPresent.length > 0 && (
        <ul className="flex flex-wrap items-center gap-x-4 gap-y-1.5 px-1 text-[11px] text-slate-600">
          {kindsPresent.map((kind) => {
            const style = KIND_STYLE[kind];
            return (
              <li key={kind} className="flex items-center gap-1.5">
                <svg width="26" height="8" viewBox="0 0 26 8" aria-hidden="true">
                  <line
                    x1="1"
                    y1="4"
                    x2="25"
                    y2="4"
                    stroke={stroke}
                    strokeWidth={4}
                    strokeLinecap="round"
                    strokeDasharray={style.dash ?? undefined}
                  />
                </svg>
                {style.label}
              </li>
            );
          })}
          <li className="flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-full bg-emerald-500" aria-hidden="true" />
            출발
          </li>
          <li className="flex items-center gap-1.5">
            <span className="inline-block size-2.5 rounded-full bg-rose-500" aria-hidden="true" />
            도착
          </li>
        </ul>
      )}
    </section>
  );
}
