/**
 * ============================================================
 *  비용 함수 — 이 제품의 핵심
 * ============================================================
 *  같은 출발/도착인데 모드만 바꾸면 경로가 눈에 보이게 달라져야 한다.
 *  그래서 가중치를 "약간" 주지 않고 세게 준다.
 *
 *  단위는 전부 '미터 환산 비용'이다. 도보 1m = 비용 1.
 *  예) 계단 1칸에 12를 주면 "계단 1칸 = 12m 더 걷기"와 같다는 뜻.
 * ============================================================
 */

import type { TravelMode, Weather } from './types';

export interface EdgeLike {
  distance: number;
  /** 이 방향으로 올라가는 계단 칸수 */
  stairsUp: number;
  /** 이 방향으로 내려가는 계단 칸수 */
  stairsDown: number;
  /** 0(평지) ~ 1(급경사) */
  slope: number;
  indoor: boolean;
  elevator: boolean;
}

interface ModeWeights {
  /** 계단 1칸 오를 때 추가 비용(m 환산) */
  stairUp: number;
  /** 계단 1칸 내려갈 때 추가 비용 */
  stairDown: number;
  /** slope × distance 에 곱하는 계수 */
  slope: number;
  /** 실외 1m 당 추가 비용 (맑음) */
  outdoorClear: number;
  /** 실외 1m 당 추가 비용 (비) */
  outdoorRain: number;
  /** 엘리베이터 1회 대기·탑승 비용 */
  elevatorWait: number;
  /** true 면 계단이 있는 엣지를 아예 쓰지 않는다 (하드 제약) */
  forbidStairs: boolean;
}

export const MODE_WEIGHTS: Record<TravelMode, ModeWeights> = {
  // 최단시간: 계단을 거의 안 가린다. 오르막만 조금 싫어한다.
  fastest: {
    stairUp: 0.6,
    stairDown: 0.25,
    slope: 2,
    outdoorClear: 0,
    outdoorRain: 0.2,
    elevatorWait: 35,
    forbidStairs: false,
  },

  // 계단 최소: 계단 1칸이 12m 걷기와 맞먹는다. 엘리베이터는 싸게 해준다.
  fewest_stairs: {
    stairUp: 12,
    stairDown: 7,
    slope: 5,
    outdoorClear: 0,
    outdoorRain: 0.2,
    elevatorWait: 18,
    forbidStairs: false,
  },

  // 무장애: 계단은 아예 금지. 급경사도 강하게 회피한다.
  barrier_free: {
    stairUp: 0,
    stairDown: 0,
    slope: 40,
    outdoorClear: 0,
    outdoorRain: 0.2,
    elevatorWait: 12,
    forbidStairs: true,
  },

  // 비 안 맞기: 실외 1m 마다 벌점. 비가 오면 훨씬 세게.
  stay_dry: {
    stairUp: 1.5,
    stairDown: 0.8,
    slope: 2,
    outdoorClear: 1.5,
    outdoorRain: 9,
    elevatorWait: 25,
    forbidStairs: false,
  },
};

/** 이 엣지를 이 모드에서 쓸 수 있는가 (하드 제약) */
export function isEdgeAllowed(edge: EdgeLike, mode: TravelMode): boolean {
  const w = MODE_WEIGHTS[mode];
  if (w.forbidStairs && (edge.stairsUp > 0 || edge.stairsDown > 0)) return false;
  return true;
}

/**
 * 엣지 통과 비용.
 *   cost = 거리
 *        + 계단칸수 × 계단벌점
 *        + 경사 × 거리 × 경사벌점
 *        + (실외면) 거리 × 실외벌점
 *        + (엘리베이터면) 대기비용
 */
export function edgeCost(edge: EdgeLike, mode: TravelMode, weather: Weather): number {
  const w = MODE_WEIGHTS[mode];

  let cost = edge.distance;
  cost += edge.stairsUp * w.stairUp;
  cost += edge.stairsDown * w.stairDown;
  cost += edge.slope * edge.distance * w.slope;

  if (!edge.indoor) {
    cost += edge.distance * (weather === 'rain' ? w.outdoorRain : w.outdoorClear);
  }
  if (edge.elevator) {
    cost += w.elevatorWait;
  }

  return cost;
}

/* ------------------------------------------------------------
 * 소요시간 추정
 * ---------------------------------------------------------- */
export const WALK_SPEED_M_PER_S = 1.3;
export const SECONDS_PER_STEP = 1.2;
export const SECONDS_PER_ELEVATOR = 35;
/** 경사 100% 구간은 평지보다 이 배수만큼 느려진다고 본다 */
export const SLOPE_TIME_FACTOR = 1.8;

export function estimateSeconds(params: {
  distanceM: number;
  outdoorM: number;
  stairsUp: number;
  stairsDown: number;
  elevatorCount: number;
  slopeWeightedM: number;
}): number {
  const flatSeconds = params.distanceM / WALK_SPEED_M_PER_S;
  const slopeSeconds = (params.slopeWeightedM / WALK_SPEED_M_PER_S) * SLOPE_TIME_FACTOR;
  const stairSeconds = (params.stairsUp + params.stairsDown * 0.7) * SECONDS_PER_STEP;
  const elevatorSeconds = params.elevatorCount * SECONDS_PER_ELEVATOR;
  return flatSeconds + slopeSeconds + stairSeconds + elevatorSeconds;
}
