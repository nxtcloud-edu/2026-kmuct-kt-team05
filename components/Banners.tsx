'use client';

/**
 * 내레이션 배너 / 경고 배너 / 인라인 메시지.
 *
 * narration 은 LLM 결과라 없을 수 있다(null). 없으면 배너를 아예 렌더하지 않는다.
 * warnings 는 엔진이 대체 경로를 쓴 경우 등에 채워진다.
 */

import Link from 'next/link';
import { Info, RotateCcw, Sparkles } from 'lucide-react';
import { cn } from '@/lib/ui/cn';

export function NarrationBanner({ text }: { text: string | null | undefined }) {
  if (!text) return null;
  return (
    <div className="flex items-start gap-2.5 rounded-2xl border border-blue-200 bg-blue-50 p-3.5">
      <Sparkles className="mt-0.5 size-4 shrink-0 text-blue-600" aria-hidden="true" />
      <p className="text-[14px] font-medium leading-relaxed text-blue-900">{text}</p>
    </div>
  );
}

export function WarningBanner({ warnings }: { warnings: string[] }) {
  if (warnings.length === 0) return null;
  return (
    <div role="status" className="rounded-2xl border border-amber-300 bg-amber-50 p-3.5">
      <ul className="flex flex-col gap-1.5">
        {warnings.map((w, i) => (
          <li key={`${i}-${w}`} className="flex items-start gap-2.5">
            <Info className="mt-0.5 size-4 shrink-0 text-amber-600" aria-hidden="true" />
            <span className="text-[13px] font-medium leading-relaxed text-amber-900">{w}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** 개발 중에만 보이는 좌표 누락 경고 — 데모 빌드에서는 렌더되지 않는다. */
export function MissingCoordsBanner({ nodeIds }: { nodeIds: string[] }) {
  if (process.env.NODE_ENV === 'production' || nodeIds.length === 0) return null;
  return (
    <div className="rounded-2xl border border-dashed border-rose-300 bg-rose-50 p-3">
      <p className="text-[13px] font-semibold text-rose-800">
        좌표 누락 {nodeIds.length}개 — 지도에서 건너뛰었습니다 (개발 중에만 표시)
      </p>
      <p className="mt-1 break-all font-mono text-[11px] leading-relaxed text-rose-700">
        {nodeIds.join(', ')}
      </p>
      <p className="mt-1.5 text-[11px] text-rose-700">
        <Link href="/dev/coords" className="font-semibold underline">
          /dev/coords
        </Link>{' '}
        에서 좌표를 찍고 data/coords.json 에 붙여 넣으세요.
      </p>
    </div>
  );
}

export function InlineNotice({
  children,
  tone = 'neutral',
  onRetry,
}: {
  children: React.ReactNode;
  tone?: 'neutral' | 'error';
  onRetry?: () => void;
}) {
  return (
    <div
      className={cn(
        'flex flex-col gap-2.5 rounded-2xl border p-4 sm:flex-row sm:items-center sm:justify-between',
        tone === 'error' ? 'border-rose-300 bg-rose-50' : 'border-slate-200 bg-slate-50',
      )}
    >
      <p
        className={cn(
          'text-sm font-medium',
          tone === 'error' ? 'text-rose-800' : 'text-slate-600',
        )}
      >
        {children}
      </p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex min-h-11 shrink-0 items-center justify-center gap-1.5 rounded-xl bg-slate-900 px-4 text-sm font-semibold text-white transition hover:bg-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-slate-900"
        >
          <RotateCcw className="size-4" aria-hidden="true" />
          다시 시도
        </button>
      )}
    </div>
  );
}

export function MapSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      <div className="flex gap-1.5">
        <span className="h-11 w-24 animate-pulse rounded-full bg-slate-200" />
        <span className="h-11 w-24 animate-pulse rounded-full bg-slate-200" />
        <span className="h-11 w-20 animate-pulse rounded-full bg-slate-200" />
      </div>
      <div
        className="animate-pulse rounded-2xl bg-slate-200"
        style={{ aspectRatio: '800 / 500' }}
      />
    </div>
  );
}

export function StepSkeleton() {
  return (
    <div className="flex flex-col gap-2" aria-hidden="true">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="flex items-start gap-3 rounded-xl p-2.5">
          <span className="size-9 shrink-0 animate-pulse rounded-lg bg-slate-200" />
          <span className="flex w-full flex-col gap-1.5">
            <span className="h-4 w-4/5 animate-pulse rounded bg-slate-200" />
            <span className="h-3 w-2/5 animate-pulse rounded bg-slate-100" />
          </span>
        </div>
      ))}
    </div>
  );
}
