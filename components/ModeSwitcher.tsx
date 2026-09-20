'use client';

/**
 * 이동 모드 전환 — 이 제품의 핵심 UI.
 * 같은 출발/도착에서 모드만 바꾸면 경로가 눈에 보이게 달라진다.
 *
 * 접근성: role="radiogroup" + roving tabindex.
 *  - Tab 은 그룹 전체를 한 번만 통과하고,
 *  - 그룹 안에서는 ← → ↑ ↓ 로 이동하며 즉시 선택된다 (WAI-ARIA radio group 패턴)
 */

import { useRef } from 'react';
import { Accessibility, Clock, CloudRain } from 'lucide-react';
import { TRAVEL_MODES, TRAVEL_MODE_LABEL, type TravelMode } from '@/lib/types';
import { MODE_STYLE } from '@/lib/ui/theme';
import { StepIconGlyph } from '@/lib/ui/icons';
import { cn } from '@/lib/ui/cn';

function ModeGlyph({ mode, className }: { mode: TravelMode; className?: string }) {
  switch (mode) {
    case 'fastest':
      return <Clock className={className} aria-hidden="true" />;
    case 'fewest_stairs':
      return <StepIconGlyph icon="stairs_down" className={className} />;
    case 'barrier_free':
      return <Accessibility className={className} aria-hidden="true" />;
    case 'stay_dry':
      return <CloudRain className={className} aria-hidden="true" />;
    default:
      return <Clock className={className} aria-hidden="true" />;
  }
}

interface ModeSwitcherProps {
  value: TravelMode;
  onChange: (mode: TravelMode) => void;
  disabled?: boolean;
  /** 엔진이 요청과 다른 모드를 적용한 경우 표시 */
  appliedMode?: TravelMode | null;
}

export function ModeSwitcher({ value, onChange, disabled = false, appliedMode = null }: ModeSwitcherProps) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  const move = (fromIndex: number, delta: number) => {
    const next = (fromIndex + delta + TRAVEL_MODES.length) % TRAVEL_MODES.length;
    onChange(TRAVEL_MODES[next]);
    refs.current[next]?.focus();
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    switch (e.key) {
      case 'ArrowRight':
      case 'ArrowDown':
        e.preventDefault();
        move(index, 1);
        break;
      case 'ArrowLeft':
      case 'ArrowUp':
        e.preventDefault();
        move(index, -1);
        break;
      case 'Home':
        e.preventDefault();
        onChange(TRAVEL_MODES[0]);
        refs.current[0]?.focus();
        break;
      case 'End': {
        e.preventDefault();
        const last = TRAVEL_MODES.length - 1;
        onChange(TRAVEL_MODES[last]);
        refs.current[last]?.focus();
        break;
      }
      default:
        break;
    }
  };

  const substituted = appliedMode !== null && appliedMode !== value;

  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span id="mode-group-label" className="text-sm font-semibold text-slate-700">
          이동 방식
        </span>
        <span className="text-xs text-slate-500">모드를 바꾸면 경로가 달라집니다</span>
      </div>

      <div
        role="radiogroup"
        aria-labelledby="mode-group-label"
        className="grid grid-cols-2 gap-2 sm:grid-cols-4"
      >
        {TRAVEL_MODES.map((mode, index) => {
          const active = mode === value;
          const style = MODE_STYLE[mode];
          return (
            <button
              key={mode}
              ref={(el) => {
                refs.current[index] = el;
              }}
              type="button"
              role="radio"
              aria-checked={active}
              tabIndex={active ? 0 : -1}
              disabled={disabled}
              onClick={() => onChange(mode)}
              onKeyDown={(e) => onKeyDown(e, index)}
              className={cn(
                'flex min-h-11 flex-col items-center justify-center gap-0.5 rounded-xl border px-2 py-2.5 text-center transition',
                'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-blue-500',
                disabled && 'cursor-not-allowed opacity-50',
                active
                  ? cn(style.activeBg, style.activeText, 'border-transparent shadow-sm')
                  : 'border-slate-300 bg-white text-slate-700 hover:border-slate-400 hover:bg-slate-50',
              )}
            >
              <span className="flex items-center gap-1.5">
                <ModeGlyph mode={mode} className="size-4" />
                <span className="text-sm font-semibold">{TRAVEL_MODE_LABEL[mode]}</span>
              </span>
              <span className={cn('text-[11px]', active ? 'text-white/80' : 'text-slate-500')}>
                {style.hint}
              </span>
            </button>
          );
        })}
      </div>

      {substituted && appliedMode && (
        <p className="mt-2 text-xs font-medium text-amber-700">
          요청한 모드로는 경로가 없어 <strong>{TRAVEL_MODE_LABEL[appliedMode]}</strong> 경로로 안내하고 있습니다.
        </p>
      )}
    </div>
  );
}
