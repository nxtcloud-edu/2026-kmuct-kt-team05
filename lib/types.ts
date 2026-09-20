/**
 * ============================================================
 *  KMU WAYFINDER — 공유 계약 (SHARED CONTRACT)
 * ============================================================
 *  이 파일은 UI 담당자와 엔진/데이터 담당자가 함께 쓰는 유일한 공유 파일입니다.
 *
 *  규칙 (반드시 지킬 것)
 *  1. 10:00 이후 이 파일은 "동결(frozen)"됩니다.
 *  2. 수정이 필요하면 혼자 고치지 말고 팀 전체에 먼저 알리고 합의 후 수정합니다.
 *  3. UI는 여기 정의된 타입만 믿고 화면을 만듭니다. 엔진 내부 구현은 모릅니다.
 *  4. 엔진은 여기 정의된 모양 그대로 응답합니다. 필드를 임의로 빼거나 이름을 바꾸지 않습니다.
 * ============================================================
 */

/* ------------------------------------------------------------
 * 1. 이동 모드 — 제품의 핵심. 같은 출발/도착에서 모드만 바꾸면 경로가 달라진다.
 * ---------------------------------------------------------- */

export type TravelMode =
  | 'fastest'        // 최단시간
  | 'fewest_stairs'  // 계단 최소
  | 'barrier_free'   // 무장애 (계단 0, 엘리베이터/경사로만)
  | 'stay_dry';      // 비 안 맞기 (실내 위주)

export const TRAVEL_MODES: TravelMode[] = [
  'fastest',
  'fewest_stairs',
  'barrier_free',
  'stay_dry',
];

/** UI가 버튼 라벨로 그대로 쓸 수 있는 한국어 표기 */
export const TRAVEL_MODE_LABEL: Record<TravelMode, string> = {
  fastest: '최단시간',
  fewest_stairs: '계단 최소',
  barrier_free: '무장애',
  stay_dry: '비 안 맞기',
};

export type Weather = 'clear' | 'rain';

/* ------------------------------------------------------------
 * 2. 그래프 데이터 (엔진/데이터 담당 소유: data/campus-graph.json)
 * ---------------------------------------------------------- */

export type NodeKind =
  | 'room'      // 강의실/사무실 — 검색 대상
  | 'junction'  // 복도 분기점
  | 'stairs'    // 계단 출입구
  | 'elevator'  // 엘리베이터
  | 'ramp'      // 경사로
  | 'entrance'  // 건물 출입구 (실내↔실외 경계)
  | 'bridge'    // 건물 간 연결통로 (이 앱의 핵심 자산)
  | 'outdoor';  // 실외 보행 지점

export interface CampusNode {
  /** 고유 ID. 규칙: {건물영문}_{층}f_{식별자}  예) bukak_4f_411, bukak_4f_bridge */
  id: string;
  /** 건물 한글명. 실외 노드는 'OUTDOOR' */
  building: string;
  /** 층. 실외 노드는 0 */
  floor: number;
  /** 사용자에게 보여줄 이름. 예) '북악관 411호' */
  label: string;
  kind: NodeKind;
  /** 검색창/드롭다운에 노출할지 여부. 복도 분기점 등은 false */
  searchable: boolean;
  /** 검색 보조 키워드. 예) ['411', '북악411', 'bukak411'] */
  aliases?: string[];
  /**
   * 좌표는 여기에 넣지 않습니다.
   * SVG 픽셀 좌표는 UI 담당이 data/coords.json 에서 소유합니다. (사유: 문서 하단 참고)
   */
}

export interface CampusEdge {
  from: string;
  to: string;
  /** 실제 이동 거리(미터). 대략값이어도 됨 */
  distance: number;
  /** from→to 방향으로 올라가는 계단 수 (없으면 0) */
  stairsUp: number;
  /** from→to 방향으로 내려가는 계단 수 (없으면 0) */
  stairsDown: number;
  /** 경사도 0(평지) ~ 1(급경사). 국민대 특성상 이 값이 제품의 차별점 */
  slope: number;
  /** 실내 구간인지 */
  indoor: boolean;
  /** 엘리베이터 이용 구간인지 */
  elevator: boolean;
  /** 양방향 통행 가능 여부. false면 from→to 만 가능 */
  bidirectional: boolean;
  /** 야간/주말 폐쇄 등 메모 (선택) */
  note?: string;
}

export interface Building {
  /** 영문 슬러그. 예) 'bukak' */
  id: string;
  /** 한글명. 예) '북악관' */
  name: string;
  /** 보유 층 목록. 예) [1,2,3,4,5] */
  floors: number[];
}

export interface CampusGraph {
  /** 데이터 버전. 데이터 갱신 시 올려주면 UI가 캐시를 버릴 수 있음 */
  version: string;
  buildings: Building[];
  nodes: CampusNode[];
  edges: CampusEdge[];
}

/* ------------------------------------------------------------
 * 3. 좌표 데이터 (UI 담당 소유: data/coords.json)
 *    엔진은 이 파일을 절대 읽지 않습니다. 거리는 edge.distance 로만 계산합니다.
 * ---------------------------------------------------------- */

export interface NodeCoord {
  /** 이 노드를 그릴 SVG 경로. 예) '/maps/bukak-4f.svg' 또는 '/maps/campus.svg' */
  svg: string;
  /** 해당 SVG viewBox 기준 픽셀 좌표 */
  x: number;
  y: number;
}

/** key = CampusNode.id */
export type CoordMap = Record<string, NodeCoord>;

/* ------------------------------------------------------------
 * 4. 경로 요청/응답 — UI와 엔진이 만나는 지점
 * ---------------------------------------------------------- */

export interface RouteRequest {
  fromNodeId: string;
  toNodeId: string;
  mode: TravelMode;
  /** 'rain'이면 stay_dry 가중치가 강해짐. 미지정 시 엔진이 'clear'로 처리 */
  weather?: Weather;
}

export interface RouteSummary {
  distanceM: number;
  durationMin: number;
  stairsUp: number;
  stairsDown: number;
  elevatorCount: number;
  /** 경로 중 최대 경사도 0~1 */
  maxSlope: number;
  /** 실외 노출 거리(미터). '비 안 맞기' 모드 효과를 UI가 숫자로 보여줄 때 사용 */
  outdoorM: number;
  /** 계단이 0이고 모든 층 이동이 엘리베이터/경사로인 경우 true */
  barrierFree: boolean;
}

/**
 * 지도 렌더링 단위.
 * 같은 (건물, 층) 안에서 이어지는 노드들을 하나의 세그먼트로 묶어서 줍니다.
 * UI는 세그먼트 = 지도 한 장(한 층) 으로 보고, nodeIds를 coords.json으로 좌표 변환해 폴리라인을 그립니다.
 */
export interface RouteSegment {
  /** 건물 한글명 또는 'OUTDOOR' */
  building: string;
  /** 층. 실외는 0 */
  floor: number;
  /** 이 세그먼트를 지나는 노드 순서 (2개 이상) */
  nodeIds: string[];
  /** 이 세그먼트의 이동 수단 */
  kind: 'walk' | 'stairs' | 'elevator' | 'ramp' | 'bridge';
  distanceM: number;
}

export type StepIcon =
  | 'walk'
  | 'stairs_up'
  | 'stairs_down'
  | 'elevator'
  | 'ramp'
  | 'bridge'
  | 'enter'
  | 'exit'
  | 'arrive';

/** 우측 패널에 리스트로 뿌릴 안내 단계 */
export interface RouteStep {
  index: number;
  icon: StepIcon;
  /** 사람이 읽는 안내 문장. 예) '북악관 4층에서 연결통로로 건너갑니다 (계단 없음)' */
  text: string;
  distanceM: number;
  building: string;
  floor: number;
  /** 이 단계를 탭하면 UI가 지도에서 포커스할 노드 */
  focusNodeId: string;
}

export interface RouteResult {
  ok: true;
  request: RouteRequest;
  summary: RouteSummary;
  segments: RouteSegment[];
  steps: RouteStep[];
  /** LLM이 만든 전체 경로 내레이션 한두 문장. LLM 실패 시 null (UI는 없어도 동작해야 함) */
  narration: string | null;
  /** 예: '무장애 경로를 찾지 못해 계단 최소 경로로 대체했습니다' */
  warnings: string[];
  /** 엔진이 실제로 적용한 모드. 요청과 다를 수 있음(대체 경로) */
  appliedMode: TravelMode;
}

/* ------------------------------------------------------------
 * 5. 자연어 파싱 (LLM)
 * ---------------------------------------------------------- */

export interface NodeSummary {
  id: string;
  label: string;
  building: string;
  floor: number;
  aliases: string[];
}

export interface ParseRequest {
  /** 예) '나 지금 북악관인데 다음 수업 조형관 가야 해, 비 안 맞고 싶어' */
  text: string;
  /** 사용자가 이미 출발지를 선택해둔 경우 힌트로 전달 */
  currentNodeId?: string;
}

export interface ParseResult {
  ok: true;
  fromNodeId: string | null;
  toNodeId: string | null;
  mode: TravelMode | null;
  weather: Weather | null;
  /** 0~1. 0.6 미만이면 UI가 사용자에게 확인을 받는 편이 좋음 */
  confidence: number;
  /** 사용자에게 보여줄 한 줄 응답. 예) '북악관 411호에서 조형관 302호까지 실내 경로로 찾아볼게요' */
  reply: string;
  /** 애매할 때 후보 제시 → UI가 선택 칩으로 보여줌 */
  candidates?: { field: 'from' | 'to'; nodes: NodeSummary[] }[];
}

/* ------------------------------------------------------------
 * 6. 시간표 이미지 (OCR / Vision)
 * ---------------------------------------------------------- */

export interface TimetableCourse {
  title: string;
  /** OCR로 읽은 원문. 예) '북악관 411' */
  roomLabel: string;
  /** 그래프 노드로 매칭 성공 시 ID, 실패 시 null */
  nodeId: string | null;
  /** 'MON' | 'TUE' | ... */
  day: string;
  /** 'HH:mm' */
  startsAt: string;
  endsAt: string;
}

export interface TimetableResult {
  ok: true;
  courses: TimetableCourse[];
  /** 지금 시각 기준 다음 수업. 없으면 null */
  next: {
    courseIndex: number;
    minutesUntil: number;
    /** 예) '다음 수업까지 12분. 지금 나가세요.' */
    message: string;
  } | null;
}

/* ------------------------------------------------------------
 * 7. 공통 에러 봉투 — 모든 API는 성공 시 ok:true, 실패 시 ok:false
 * ---------------------------------------------------------- */

export type ApiErrorCode =
  | 'BAD_REQUEST'
  | 'NODE_NOT_FOUND'
  | 'NO_ROUTE'          // 그래프상 연결 없음
  | 'NO_BARRIER_FREE'   // 무장애 경로 없음
  | 'LLM_UNAVAILABLE'
  | 'OCR_FAILED'
  | 'INTERNAL';

export interface ApiFailure {
  ok: false;
  error: {
    code: ApiErrorCode;
    /** 사용자에게 그대로 보여줄 수 있는 한국어 메시지 */
    message: string;
  };
}

export type ApiResult<T> = T | ApiFailure;

export type RouteResponse = ApiResult<RouteResult>;
export type ParseResponse = ApiResult<ParseResult>;
export type TimetableResponse = ApiResult<TimetableResult>;
export type NodesResponse = ApiResult<{
  ok: true;
  version: string;
  buildings: Building[];
  nodes: NodeSummary[];
}>;

/** 좁히기 헬퍼 */
export function isFailure<T>(r: ApiResult<T>): r is ApiFailure {
  return (r as ApiFailure).ok === false;
}

/* ------------------------------------------------------------
 * 8. API 엔드포인트 — 문자열 하드코딩 금지, 여기서만 참조
 * ---------------------------------------------------------- */

export const API = {
  /** GET  → NodesResponse (검색 드롭다운 채우기) */
  nodes: '/api/nodes',
  /** POST RouteRequest → RouteResponse */
  route: '/api/route',
  /** POST ParseRequest → ParseResponse */
  parse: '/api/parse',
  /** POST multipart/form-data (field name: 'image') → TimetableResponse */
  timetable: '/api/timetable',
} as const;

/* ============================================================
 * 왜 좌표(x, y)를 그래프가 아니라 UI가 소유하나?
 *
 * SVG 픽셀 좌표는 UI가 그린 지도 그림에 100% 의존합니다.
 * 그래프 담당이 좌표를 적으면, UI가 지도를 다시 그리는 순간 전부 틀어집니다.
 * 그래서 엔진은 "노드 순서"만 돌려주고, 좌표 변환은 UI가 담당합니다.
 * 덕분에 두 사람이 같은 파일을 건드릴 일이 없어집니다. (= 머지 충돌 0)
 * ========================================================== */
