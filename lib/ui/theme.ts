/**
 * 모드/구간별 시각 스타일과 표시 형식 — UI 전용.
 *
 * 접근성 원칙: 경로 구분을 색상만으로 하지 않는다.
 * 색(color) + 선 스타일(dash) + 아이콘을 항상 함께 쓴다.
 */

import type { SegmentKind } from './route-view';
import type { TravelMode } from '@/lib/types';

export interface ModeStyle {
  /** 경로 선 색 */
  stroke: string;
  /** 선택된 모드 버튼 배경 */
  activeBg: string;
  /** 선택된 모드 버튼 글자색 */
  activeText: string;
  /** 요약 배지 강조색 */
  accent: string;
  /** 모드가 뭘 우선하는지 한 줄 설명 (버튼 아래 보조 텍스트 / aria-description) */
  hint: string;
}

export const MODE_STYLE: Record<TravelMode, ModeStyle> = {
  fastest: {
    stroke: '#2563eb',
    activeBg: 'bg-blue-600',
    activeText: 'text-white',
    accent: 'text-blue-700',
    hint: '거리 우선',
  },
  fewest_stairs: {
    stroke: '#7c3aed',
    activeBg: 'bg-violet-600',
    activeText: 'text-white',
    accent: 'text-violet-700',
    hint: '계단 회피',
  },
  barrier_free: {
    stroke: '#059669',
    activeBg: 'bg-emerald-600',
    activeText: 'text-white',
    accent: 'text-emerald-700',
    hint: '계단 0칸',
  },
  stay_dry: {
    stroke: '#0891b2',
    activeBg: 'bg-cyan-600',
    activeText: 'text-white',
    accent: 'text-cyan-700',
    hint: '실내 위주',
  },
};

export interface KindStyle {
  /** SVG stroke-dasharray. null 이면 실선 */
  dash: string | null;
  width: number;
  label: string;
}

/** 구간 종류별 선 모양. 색맹 사용자도 구분할 수 있도록 선 스타일을 다르게 준다. */
export const KIND_STYLE: Record<SegmentKind, KindStyle> = {
  walk: { dash: null, width: 6, label: '도보' },
  stairs: { dash: '2 9', width: 7, label: '계단' },
  elevator: { dash: '14 8', width: 7, label: '엘리베이터' },
  ramp: { dash: '18 6', width: 6, label: '경사로' },
  bridge: { dash: null, width: 9, label: '연결통로' },
};

/* ------------------------------------------------------------
 * 표시 형식
 * ---------------------------------------------------------- */

export function formatDistance(meters: number): string {
  if (!Number.isFinite(meters)) return '-';
  if (meters < 1000) return `${Math.round(meters)}m`;
  return `${(meters / 1000).toFixed(1)}km`;
}

export function formatDuration(minutes: number): string {
  if (!Number.isFinite(minutes)) return '-';
  const m = Math.max(1, Math.round(minutes));
  if (m < 60) return `${m}분`;
  const h = Math.floor(m / 60);
  return `${h}시간 ${m % 60}분`;
}

/** 0~1 경사도를 퍼센트로 */
export function formatSlope(slope: number): string {
  if (!Number.isFinite(slope)) return '-';
  return `${Math.round(slope * 100)}%`;
}

/**
 * 층 번호를 사람이 읽는 표기로.
 * 지하는 음수로 들어온다 (-1 → B1). 0층은 존재하지 않는다.
 */
export function formatFloor(floor: number): string {
  if (!Number.isFinite(floor)) return '';
  if (floor < 0) return `B${-floor}`;
  return `${floor}층`;
}

/** 건물 + 층. 실외는 '실외' */
export function formatPlace(building: string, floor: number): string {
  if (building === 'OUTDOOR') return '실외';
  return `${building} ${formatFloor(floor)}`;
}

/** 급경사 기준 — 이 값을 넘으면 경고 배지를 띄운다 */
export const STEEP_SLOPE_THRESHOLD = 0.15;
