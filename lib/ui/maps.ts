/**
 * SVG 지도 레지스트리 — UI 전용.
 *
 * coords.json 의 `svg` 필드 값이 곧 이 레지스트리의 키다.
 * 오버레이 <svg> 의 viewBox 를 배경 이미지와 정확히 같게 맞추기 위해 크기를 여기서 관리한다.
 */

export interface MapMeta {
  /** public/ 기준 경로. coords.json 의 svg 값과 동일 */
  src: string;
  /** viewBox 너비 */
  width: number;
  /** viewBox 높이 */
  height: number;
  /** 층 탭에 표시할 라벨 */
  label: string;
  /** 좁은 화면용 짧은 라벨 */
  short: string;
  kind: 'outdoor' | 'floor';
}

/** 규약: 캠퍼스 전체 지도 1000x700, 층별 도면 800x500 */
export const CAMPUS_VIEWBOX = { width: 1000, height: 700 } as const;
export const FLOOR_VIEWBOX = { width: 800, height: 500 } as const;

export const MAP_REGISTRY: Record<string, MapMeta> = {
  '/maps/campus.svg': {
    src: '/maps/campus.svg',
    ...CAMPUS_VIEWBOX,
    label: '캠퍼스 (실외)',
    short: '실외',
    kind: 'outdoor',
  },
  '/maps/bukak-1f.svg': {
    src: '/maps/bukak-1f.svg',
    ...FLOOR_VIEWBOX,
    label: '북악관 1F',
    short: '북악 1F',
    kind: 'floor',
  },
  '/maps/bukak-4f.svg': {
    src: '/maps/bukak-4f.svg',
    ...FLOOR_VIEWBOX,
    label: '북악관 4F',
    short: '북악 4F',
    kind: 'floor',
  },
  '/maps/johyung-1f.svg': {
    src: '/maps/johyung-1f.svg',
    ...FLOOR_VIEWBOX,
    label: '조형관 1F',
    short: '조형 1F',
    kind: 'floor',
  },
  '/maps/johyung-3f.svg': {
    src: '/maps/johyung-3f.svg',
    ...FLOOR_VIEWBOX,
    label: '조형관 3F',
    short: '조형 3F',
    kind: 'floor',
  },
  // --- 미래관 (kmu-indoor-nav 생성) ---
  '/maps/mirae-b1.png': {
    src: '/maps/mirae-b1.png',
    width: 1991,
    height: 790,
    label: '미래관 B1',
    short: '미래 B1',
    kind: 'floor',
  },
  '/maps/mirae-1f.png': {
    src: '/maps/mirae-1f.png',
    width: 1672,
    height: 941,
    label: '미래관 1F',
    short: '미래 1F',
    kind: 'floor',
  },
  '/maps/mirae-2f.png': {
    src: '/maps/mirae-2f.png',
    width: 1672,
    height: 941,
    label: '미래관 2F',
    short: '미래 2F',
    kind: 'floor',
  },
  '/maps/mirae-3f.png': {
    src: '/maps/mirae-3f.png',
    width: 1672,
    height: 941,
    label: '미래관 3F',
    short: '미래 3F',
    kind: 'floor',
  },
  '/maps/mirae-4f.png': {
    src: '/maps/mirae-4f.png',
    width: 1672,
    height: 941,
    label: '미래관 4F',
    short: '미래 4F',
    kind: 'floor',
  },
  '/maps/mirae-5f.png': {
    src: '/maps/mirae-5f.png',
    width: 1672,
    height: 941,
    label: '미래관 5F',
    short: '미래 5F',
    kind: 'floor',
  },
  '/maps/mirae-6f.png': {
    src: '/maps/mirae-6f.png',
    width: 1672,
    height: 941,
    label: '미래관 6F',
    short: '미래 6F',
    kind: 'floor',
  },
  '/maps/mirae-7f.png': {
    src: '/maps/mirae-7f.png',
    width: 1672,
    height: 941,
    label: '미래관 7F',
    short: '미래 7F',
    kind: 'floor',
  },
};

/** 레지스트리에 없는 SVG 가 coords.json 에 등장해도 앱이 죽지 않게 한다. */
export function getMapMeta(src: string): MapMeta {
  const known = MAP_REGISTRY[src];
  if (known) return known;

  const fileName = src.split('/').pop() ?? src;
  const guessLabel = fileName.replace(/\.svg$/i, '');
  return {
    src,
    ...FLOOR_VIEWBOX,
    label: guessLabel,
    short: guessLabel,
    kind: 'floor',
  };
}

export const ALL_MAPS: MapMeta[] = Object.values(MAP_REGISTRY);
