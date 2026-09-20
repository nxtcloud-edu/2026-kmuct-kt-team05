/**
 * 경로 단계 아이콘 — UI 전용.
 *
 * lucide-react 에는 "계단" 아이콘이 없어서 계단/경사로만 직접 그렸다.
 * 아이콘은 항상 장식이므로 aria-hidden 처리하고, 의미는 옆의 텍스트가 전달한다.
 */

import {
  ArrowRightLeft,
  Flag,
  Footprints,
  LogIn,
  LogOut,
  MoveVertical,
} from 'lucide-react';
import type { StepIcon } from '@/lib/types';

interface GlyphProps {
  className?: string;
}

function StairsUpGlyph({ className }: GlyphProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M3 20h4v-4h4v-4h4V8h4V4" />
      <path d="M17 4h4v4" />
    </svg>
  );
}

function StairsDownGlyph({ className }: GlyphProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M3 4v4h4v4h4v4h4v4h4" />
      <path d="M17 16v4h4" />
    </svg>
  );
}

function RampGlyph({ className }: GlyphProps) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
         strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d="M3 19h18" />
      <path d="M4 19 20 6" />
      <path d="M20 6v13" />
    </svg>
  );
}

export function StepIconGlyph({ icon, className }: { icon: StepIcon; className?: string }) {
  switch (icon) {
    case 'walk':
      return <Footprints className={className} aria-hidden="true" />;
    case 'stairs_up':
      return <StairsUpGlyph className={className} />;
    case 'stairs_down':
      return <StairsDownGlyph className={className} />;
    case 'elevator':
      return <MoveVertical className={className} aria-hidden="true" />;
    case 'ramp':
      return <RampGlyph className={className} />;
    case 'bridge':
      return <ArrowRightLeft className={className} aria-hidden="true" />;
    case 'enter':
      return <LogIn className={className} aria-hidden="true" />;
    case 'exit':
      return <LogOut className={className} aria-hidden="true" />;
    case 'arrive':
      return <Flag className={className} aria-hidden="true" />;
    default:
      return <Footprints className={className} aria-hidden="true" />;
  }
}

/** 스크린리더/툴팁용 텍스트. 아이콘 자체는 aria-hidden 이므로 이 값을 문장으로 노출한다. */
export const STEP_ICON_LABEL: Record<StepIcon, string> = {
  walk: '도보',
  stairs_up: '계단 오르기',
  stairs_down: '계단 내려가기',
  elevator: '엘리베이터',
  ramp: '경사로',
  bridge: '연결통로',
  enter: '건물 진입',
  exit: '건물 밖으로',
  arrive: '도착',
};

/** 아이콘 배경 톤 — 계단은 보라, 무장애 수단은 초록으로 일관되게 */
export const STEP_ICON_TONE: Record<StepIcon, string> = {
  walk: 'bg-slate-100 text-slate-600',
  stairs_up: 'bg-violet-100 text-violet-700',
  stairs_down: 'bg-violet-100 text-violet-700',
  elevator: 'bg-emerald-100 text-emerald-700',
  ramp: 'bg-emerald-100 text-emerald-700',
  bridge: 'bg-emerald-100 text-emerald-700',
  enter: 'bg-sky-100 text-sky-700',
  exit: 'bg-amber-100 text-amber-700',
  arrive: 'bg-rose-100 text-rose-700',
};
