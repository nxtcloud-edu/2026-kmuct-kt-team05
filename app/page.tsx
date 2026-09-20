'use client';

/**
 * 메인 화면 — UI 담당 소유.
 *
 * 이 파일은 경로 계산/LLM 로직을 전혀 갖고 있지 않다.
 * 모든 데이터는 lib/client.ts 를 통해서만 들어온다.
 * NEXT_PUBLIC_USE_MOCK=1 이면 엔진이 0% 완성된 상태에서도 전체 화면이 동작한다.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { CloudRain, Sparkles } from 'lucide-react';
import type { TravelMode, Weather } from '@/lib/types';
import { useNodes } from '@/lib/ui/useNodes';
import { useRoute } from '@/lib/ui/useRoute';
import { MAPPED_NODE_COUNT, WALK_NODE_COUNT } from '@/lib/ui/coords';
import { cn } from '@/lib/ui/cn';

import { SearchPanel } from '@/components/SearchPanel';
import { ModeSwitcher } from '@/components/ModeSwitcher';
import { MapView } from '@/components/MapView';
import { SummaryCard } from '@/components/SummaryCard';
import { StepList } from '@/components/StepList';
import { TimetableUpload } from '@/components/TimetableUpload';
import {
  InlineNotice,
  MapSkeleton,
  MissingCoordsBanner,
  NarrationBanner,
  StepSkeleton,
  WarningBanner,
} from '@/components/Banners';

const USING_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === '1';

export default function HomePage() {
  const { nodes, byId, status: nodesStatus, reload: reloadNodes } = useNodes();

  const [fromNodeId, setFromNodeId] = useState<string | null>(null);
  const [toNodeId, setToNodeId] = useState<string | null>(null);
  const [mode, setMode] = useState<TravelMode>('fastest');
  const [rain, setRain] = useState(false);
  const [focusNodeId, setFocusNodeId] = useState<string | null>(null);

  const weather: Weather = rain ? 'rain' : 'clear';
  const { result, view, status, error, retry } = useRoute(fromNodeId, toNodeId, mode, weather);

  // 경로가 새로 나오면 단계 선택을 초기화한다.
  useEffect(() => {
    setFocusNodeId(null);
  }, [result]);

  const swap = useCallback(() => {
    setFromNodeId(toNodeId);
    setToNodeId(fromNodeId);
  }, [fromNodeId, toNodeId]);

  const onWeatherSuggest = useCallback((w: Weather) => setRain(w === 'rain'), []);

  const fromLabel = useMemo(() => (fromNodeId ? byId.get(fromNodeId)?.label ?? null : null), [byId, fromNodeId]);
  const toLabel = useMemo(() => (toNodeId ? byId.get(toNodeId)?.label ?? null : null), [byId, toNodeId]);

  const showFirstLoadSkeleton = status === 'loading' && result === null;

  return (
    <div className="min-h-dvh">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-col gap-1 px-4 py-4 sm:px-6">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-bold tracking-tight text-slate-900 sm:text-xl">
              국민대 길찾기
            </h1>
            {USING_MOCK && (
              <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-[11px] font-bold text-amber-800">
                MOCK 데이터
              </span>
            )}
          </div>
          <p className="text-[13px] text-slate-600 sm:text-sm">
            강의실에서 강의실까지, <strong className="font-semibold text-slate-800">계단을 최소화하는</strong> 실내외 통합 경로 안내
          </p>
        </div>
      </header>

      <main id="main" className="mx-auto max-w-6xl px-4 py-4 sm:px-6 sm:py-6">
        <div className="grid gap-4 lg:grid-cols-[minmax(340px,390px)_1fr] lg:items-start">
          {/* 좌측 상단: 입력 */}
          <div className="order-1 flex flex-col gap-4 lg:col-start-1 lg:row-start-1">
            {nodesStatus === 'error' ? (
              <InlineNotice tone="error" onRetry={reloadNodes}>
                장소 목록을 불러오지 못했습니다.
              </InlineNotice>
            ) : (
              <SearchPanel
                nodes={nodes}
                nodesLoading={nodesStatus === 'loading'}
                fromNodeId={fromNodeId}
                toNodeId={toNodeId}
                onFromChange={setFromNodeId}
                onToChange={setToNodeId}
                onSwap={swap}
                onModeSuggest={setMode}
                onWeatherSuggest={onWeatherSuggest}
              />
            )}

            <div className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm">
              <ModeSwitcher
                value={mode}
                onChange={setMode}
                appliedMode={result?.appliedMode ?? null}
              />

              <label
                className={cn(
                  'flex min-h-11 cursor-pointer items-center justify-between gap-3 rounded-xl border px-3 transition',
                  rain ? 'border-cyan-400 bg-cyan-50' : 'border-slate-300 bg-white hover:bg-slate-50',
                )}
              >
                <span className="flex items-center gap-2 text-[13px] font-semibold text-slate-700">
                  <CloudRain
                    className={cn('size-4', rain ? 'text-cyan-600' : 'text-slate-400')}
                    aria-hidden="true"
                  />
                  지금 비가 와요
                </span>
                <input
                  type="checkbox"
                  checked={rain}
                  onChange={(e) => setRain(e.target.checked)}
                  className="size-5 rounded border-slate-400 text-cyan-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-cyan-500"
                />
              </label>
              <p className="-mt-1 text-[11px] text-slate-500">
                켜면 &lsquo;비 안 맞기&rsquo; 모드에서 실외 구간에 더 큰 불이익을 줍니다.
              </p>
            </div>
          </div>

          {/* 우측: 지도 + 결과 */}
          <div className="order-2 flex flex-col gap-4 lg:col-start-2 lg:row-span-2 lg:row-start-1">
            {showFirstLoadSkeleton ? (
              <MapSkeleton />
            ) : (
              <MapView
                view={view}
                mode={result?.appliedMode ?? mode}
                loading={status === 'loading'}
                focusNodeId={focusNodeId}
                fromLabel={fromLabel}
                toLabel={toLabel}
                placeholder={
                  status === 'same'
                    ? '출발지와 도착지가 같습니다.'
                    : '출발지와 도착지를 선택하면 경로가 표시됩니다.'
                }
              />
            )}

            <MissingCoordsBanner nodeIds={view.missingNodeIds} />

            {status === 'idle' && (
              <InlineNotice>
                출발지와 도착지를 선택하면 경로와 단계별 안내가 표시됩니다.
              </InlineNotice>
            )}

            {status === 'same' && (
              <InlineNotice>출발지와 도착지가 같습니다. 도착지를 다시 선택해 주세요.</InlineNotice>
            )}

            {status === 'error' && (
              <InlineNotice tone="error" onRetry={retry}>
                {error ?? '경로를 불러오지 못했습니다.'}
              </InlineNotice>
            )}

            {showFirstLoadSkeleton && <StepSkeleton />}

            {status === 'ready' && result && (
              <>
                <SummaryCard summary={result.summary} appliedMode={result.appliedMode} />
                <NarrationBanner text={result.narration} />
                <WarningBanner warnings={result.warnings} />

                <section aria-labelledby="steps-heading" className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm">
                  <h2 id="steps-heading" className="mb-2 flex items-center gap-1.5 text-sm font-semibold text-slate-700">
                    <Sparkles className="size-3.5 text-slate-400" aria-hidden="true" />
                    단계별 안내
                    <span className="font-normal text-slate-500">— 항목을 누르면 해당 층으로 이동합니다</span>
                  </h2>
                  <StepList steps={result.steps} focusNodeId={focusNodeId} onSelect={setFocusNodeId} />
                </section>
              </>
            )}
          </div>

          {/* 좌측 하단: 시간표 */}
          <div className="order-3 lg:col-start-1 lg:row-start-2">
            <TimetableUpload
              nodes={nodes}
              nodesLoading={nodesStatus === 'loading'}
              onPickDestination={(nodeId) => setToNodeId(nodeId)}
            />
          </div>
        </div>

        <footer className="mt-8 border-t border-slate-200 pt-4 text-[12px] text-slate-500">
          <p>
            실외 보행로 <strong className="font-semibold text-slate-700">{WALK_NODE_COUNT}개 지점</strong>은
            OpenStreetMap 실측 데이터, 건물·강의실 <strong className="font-semibold text-slate-700">{MAPPED_NODE_COUNT}개 지점</strong>은
            직접 매핑했습니다. 건물 층간 연결과 엘리베이터 정보는 어떤 지도 서비스에도 없는 데이터로,
            크라우드소싱으로 확장할 수 있습니다.
          </p>
          <p className="mt-1">
            좌표를 추가하려면{' '}
            <Link href="/dev/coords" className="font-semibold text-slate-700 underline">
              /dev/coords
            </Link>{' '}
            에서 지도를 클릭해 찍으세요.
          </p>
        </footer>
      </main>
    </div>
  );
}
