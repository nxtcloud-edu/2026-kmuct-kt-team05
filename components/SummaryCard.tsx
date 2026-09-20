'use client';

/**
 * 경로 요약 배지.
 * 경로가 갱신되면 aria-live 로 한 문장 요약을 읽어준다.
 */

import { Accessibility, Clock, CloudRain, MoveVertical, Ruler } from 'lucide-react';
import type { RouteSummary, TravelMode } from '@/lib/types';
import { TRAVEL_MODE_LABEL } from '@/lib/types';
import {
  formatDistance,
  formatDuration,
  formatSlope,
  MODE_STYLE,
  STEEP_SLOPE_THRESHOLD,
} from '@/lib/ui/theme';
import { StepIconGlyph } from '@/lib/ui/icons';
import { cn } from '@/lib/ui/cn';

interface SummaryCardProps {
  summary: RouteSummary;
  appliedMode: TravelMode;
}

function Badge({
  children,
  tone = 'neutral',
}: {
  children: React.ReactNode;
  tone?: 'neutral' | 'good' | 'warn' | 'stairs';
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[13px] font-semibold',
        tone === 'neutral' && 'bg-slate-100 text-slate-700',
        tone === 'good' && 'bg-emerald-100 text-emerald-800',
        tone === 'warn' && 'bg-amber-100 text-amber-800',
        tone === 'stairs' && 'bg-violet-100 text-violet-800',
      )}
    >
      {children}
    </span>
  );
}

export function SummaryCard({ summary, appliedMode }: SummaryCardProps) {
  const totalStairs = summary.stairsUp + summary.stairsDown;
  const steep = summary.maxSlope >= STEEP_SLOPE_THRESHOLD;

  const spoken = [
    `${TRAVEL_MODE_LABEL[appliedMode]} 경로.`,
    `${formatDistance(summary.distanceM)}, 약 ${formatDuration(summary.durationMin)}.`,
    totalStairs === 0
      ? '계단 없음.'
      : `계단 오르기 ${summary.stairsUp}칸, 내려가기 ${summary.stairsDown}칸.`,
    summary.elevatorCount > 0 ? `엘리베이터 ${summary.elevatorCount}회.` : '',
    summary.outdoorM > 0 ? `실외 ${formatDistance(summary.outdoorM)}.` : '실외 구간 없음.',
    steep ? `최대 경사 ${formatSlope(summary.maxSlope)}, 급경사 포함.` : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-3.5 shadow-sm">
      {/* 스크린리더용 요약 — 경로가 바뀔 때마다 읽힌다 */}
      <p className="sr-only" aria-live="polite">
        {spoken}
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <Badge>
          <Ruler className="size-3.5" aria-hidden="true" />
          {formatDistance(summary.distanceM)}
        </Badge>

        <Badge>
          <Clock className="size-3.5" aria-hidden="true" />
          약 {formatDuration(summary.durationMin)}
        </Badge>

        {totalStairs === 0 ? (
          <Badge tone="good">
            <Accessibility className="size-3.5" aria-hidden="true" />
            계단 0칸
          </Badge>
        ) : (
          <Badge tone="stairs">
            <StepIconGlyph icon="stairs_up" className="size-3.5" />
            계단 ↑{summary.stairsUp} ↓{summary.stairsDown}
          </Badge>
        )}

        {summary.elevatorCount > 0 && (
          <Badge tone="good">
            <MoveVertical className="size-3.5" aria-hidden="true" />
            엘리베이터 {summary.elevatorCount}회
          </Badge>
        )}

        <Badge tone={summary.outdoorM === 0 ? 'good' : 'neutral'}>
          <CloudRain className="size-3.5" aria-hidden="true" />
          실외 {formatDistance(summary.outdoorM)}
        </Badge>

        {steep && (
          <Badge tone="warn">
            경사 {formatSlope(summary.maxSlope)} 구간 포함
          </Badge>
        )}
      </div>

      {summary.barrierFree && (
        <p
          className={cn(
            'mt-3 flex items-center gap-2 rounded-xl bg-emerald-50 px-3 py-2.5 text-[13px] font-semibold',
            MODE_STYLE.barrier_free.accent,
          )}
        >
          <Accessibility className="size-4 shrink-0" aria-hidden="true" />
          휠체어·유모차·캐리어로도 이동할 수 있는 무장애 경로입니다.
        </p>
      )}
    </div>
  );
}
