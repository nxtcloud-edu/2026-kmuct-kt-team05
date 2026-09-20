'use client';

/**
 * 경로 안내 단계 리스트.
 *
 * 접근성:
 *  - 순서가 있는 안내이므로 <ol> 사용
 *  - 항목은 버튼 → 키보드로 선택 가능, 선택 시 지도가 해당 층으로 이동
 *  - 아이콘은 aria-hidden, 의미는 STEP_ICON_LABEL 텍스트로 전달
 */

import type { RouteStep } from '@/lib/types';
import { STEP_ICON_LABEL, STEP_ICON_TONE, StepIconGlyph } from '@/lib/ui/icons';
import { formatDistance, formatPlace } from '@/lib/ui/theme';
import { cn } from '@/lib/ui/cn';

interface StepListProps {
  steps: RouteStep[];
  focusNodeId: string | null;
  onSelect: (nodeId: string) => void;
}

export function StepList({ steps, focusNodeId, onSelect }: StepListProps) {
  if (steps.length === 0) {
    return (
      <p className="rounded-xl bg-slate-50 px-3 py-4 text-sm text-slate-500">
        안내할 단계가 없습니다.
      </p>
    );
  }

  return (
    <ol className="flex flex-col gap-1.5">
      {steps.map((step) => {
        const active = step.focusNodeId === focusNodeId;
        return (
          <li key={`${step.index}-${step.focusNodeId}`}>
            <button
              type="button"
              onClick={() => onSelect(step.focusNodeId)}
              aria-current={active ? 'step' : undefined}
              className={cn(
                'flex w-full items-start gap-3 rounded-xl border p-2.5 text-left transition',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:ring-blue-500',
                active
                  ? 'border-slate-900 bg-slate-50 shadow-sm'
                  : 'border-transparent hover:border-slate-200 hover:bg-slate-50',
              )}
            >
              <span
                className={cn(
                  'grid size-9 shrink-0 place-items-center rounded-lg',
                  STEP_ICON_TONE[step.icon],
                )}
              >
                <StepIconGlyph icon={step.icon} className="size-[18px]" />
              </span>

              <span className="flex min-w-0 flex-col gap-0.5">
                <span className="text-[15px] font-medium leading-snug text-slate-900">
                  {step.text}
                </span>
                <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-slate-500">
                  <span className="font-semibold text-slate-600">{STEP_ICON_LABEL[step.icon]}</span>
                  <span aria-hidden="true">·</span>
                  <span>{formatPlace(step.building, step.floor)}</span>
                  {step.distanceM > 0 && (
                    <>
                      <span aria-hidden="true">·</span>
                      <span>{formatDistance(step.distanceM)}</span>
                    </>
                  )}
                </span>
              </span>
            </button>
          </li>
        );
      })}
    </ol>
  );
}
