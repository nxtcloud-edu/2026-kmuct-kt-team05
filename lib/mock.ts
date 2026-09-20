/**
 * ============================================================
 *  목(MOCK) 데이터 — 아직 구현되지 않은 기능의 자리 채우기
 * ============================================================
 *  경로 탐색은 더 이상 목이 아니다. lib/graph.ts 가 실제로 계산한다.
 *  여기 남은 것은 아직 만들지 않은 LLM 기능(자연어 파싱 / 시간표 OCR)의 예시 응답뿐이다.
 *
 *  .env.local 의 NEXT_PUBLIC_USE_MOCK=1 로 두면 이 값들이 쓰인다.
 * ============================================================
 */

import type { ParseResult, TimetableResult } from './types';

/**
 * 자연어 파싱 예시.
 * 노드 ID 는 data/campus-graph.json 에 실제로 존재하는 것이어야 한다.
 */
export const MOCK_PARSE: ParseResult = {
  ok: true,
  fromNodeId: 'econ_5f',
  toNodeId: 'mirae_old_1f',
  mode: 'stay_dry',
  weather: 'rain',
  confidence: 0.86,
  reply: '경상관 5층에서 미래관 1층까지, 비 안 맞는 실내 경로로 찾아볼게요.',
};

/**
 * 시간표 OCR 예시.
 * 실제 도면이 없어서 강의실 단위가 아니라 '층' 단위로 매칭한다.
 */
export const MOCK_TIMETABLE: TimetableResult = {
  ok: true,
  courses: [
    {
      title: '자료구조',
      roomLabel: '북악관 411',
      nodeId: 'bukak_4f',
      day: 'MON',
      startsAt: '09:00',
      endsAt: '10:15',
    },
    {
      title: '기초조형',
      roomLabel: '조형관 302',
      nodeId: 'johyung_1f',
      day: 'MON',
      startsAt: '10:30',
      endsAt: '11:45',
    },
  ],
  next: {
    courseIndex: 1,
    minutesUntil: 12,
    message: '다음 수업은 조형관, 12분 남았습니다. 지금 나가세요.',
  },
};
