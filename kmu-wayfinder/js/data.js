/* =============================================================================
 * 국민대학교 북악캠퍼스 길찾기 - 그래프 데이터
 * =============================================================================
 *
 * 좌표계
 *   캠퍼스맵 스크린샷 기준 픽셀 좌표. SVG viewBox "0 0 829 591" 과 1:1 대응.
 *   assets/campusmap.png 를 배경으로 깔면 핀 위치가 그대로 맞습니다.
 *
 * elev (고도)
 *   정문 앞을 0m 로 둔 상대 고도(m).
 *   ★ 현재 값은 "경사 캠퍼스" 지형을 반영한 추정치입니다.
 *     실측/체감으로 반드시 교정하세요. 이 값이 계단 수와 경사 패널티를
 *     자동 계산하는 근거라서, 서비스 품질이 여기서 갈립니다.
 *
 * 데이터를 고칠 때는 이 파일만 만지면 됩니다. 나머지 코드는 손댈 필요 없습니다.
 * ========================================================================== */

'use strict';

/* --- 전역 상수 ------------------------------------------------------------ */

/** 픽셀 1 = 실제 몇 m 인가 (대운동장 장축을 100m 로 가정해 역산한 값) */
const SCALE_M_PER_PX = 0.85;

/** 계단 한 칸의 높이(m). 고도차에서 계단 수를 역산할 때 사용 */
const STEP_HEIGHT_M = 0.17;

/** 평지 보행 속도(m/s) */
const WALK_SPEED_MPS = 1.33;

/* --- 건물 ---------------------------------------------------------------- */
/*
 * id       : 내부 식별자
 * name     : 표시 이름
 * aliases  : 자연어 입력에서 인식할 별칭 (줄임말, 오타, 영문)
 * x, y     : 지도 좌표
 * elev     : 상대 고도(m)  ← 추정치, 교정 대상
 * floors   : [최저층, 최고층]
 * entrance : 주 출입구가 있는 층 (경사 캠퍼스라 건물마다 다름!)
 * elevator : 엘리베이터 유무
 * depts    : 검색 도움말로 보여줄 입주 기관
 */
const BUILDINGS = [
  {
    id: 'bukak', name: '북악관', aliases: ['북악', '2호관', 'bukak'],
    x: 456, y: 150, elev: 34, floors: [1, 15], entrance: 1, elevator: true,
    depts: '글로벌인문·지역대학, 사회과학대학, 교양, 교육대학원'
  },
  {
    id: 'johyung', name: '조형관', aliases: ['조형', 'johyung'],
    x: 542, y: 164, elev: 40, floors: [1, 7], entrance: 1, elevator: true,
    depts: '조형대학, 테크노디자인전문대학원, 디자인대학원'
  },
  {
    id: 'bonbu', name: '본부관', aliases: ['본부', '1호관', '본관'],
    x: 488, y: 219, elev: 28, floors: [1, 5], entrance: 1, elevator: true,
    depts: '총장실, 학사지원팀 등 본부 부서'
  },
  {
    id: 'kyungsang', name: '경상관', aliases: ['경상', 'kyungsang'],
    x: 409, y: 250, elev: 24, floors: [1, 6], entrance: 1, elevator: true,
    depts: '경상대학 강의실·연구실'
  },
  {
    id: 'kukje', name: '국제관', aliases: ['국제', 'kukje'],
    x: 462, y: 294, elev: 20, floors: [1, 5], entrance: 1, elevator: true,
    labelDx: 13, labelDy: 4, labelAnchor: 'start',
    depts: '외국인 학생 수업'
  },
  {
    id: 'law', name: '법학관', aliases: ['법학', 'law'],
    x: 606, y: 281, elev: 30, floors: [1, 6], entrance: 1, elevator: true,
    depts: '법과대학, 법무대학원, 법률상담센터'
  },
  {
    id: 'hyungsul', name: '형설관', aliases: ['형설', 'hyungsul'],
    x: 643, y: 259, elev: 36, floors: [1, 5], entrance: 1, elevator: false,
    labelDx: 13, labelDy: -8, labelAnchor: 'start',
    depts: ''
  },
  {
    id: 'gym', name: '체육관', aliases: ['체육', '실내체육관', 'gym'],
    x: 650, y: 320, elev: 28, floors: [1, 3], entrance: 1, elevator: false,
    depts: '실내경기장 (약 1,200석)'
  },
  {
    id: 'youngbin', name: '영빈관', aliases: ['영빈', 'youngbin'],
    x: 660, y: 380, elev: 22, floors: [1, 3], entrance: 1, elevator: false,
    depts: ''
  },
  {
    id: 'science', name: '과학관', aliases: ['과학', 'science'],
    x: 742, y: 220, elev: 44, floors: [1, 6], entrance: 1, elevator: true,
    depts: '과학기술대학'
  },
  {
    id: 'concert', name: '콘서트홀', aliases: ['콘서트', 'concerthall'],
    x: 498, y: 325, elev: 14, floors: [1, 3], entrance: 1, elevator: true,
    labelDx: -14, labelDy: 20, labelAnchor: 'end',
    depts: '공연장'
  },
  {
    id: 'business', name: '경영관', aliases: ['경영', 'business'],
    x: 540, y: 356, elev: 14, floors: [1, 8], entrance: 1, elevator: true,
    depts: '경영대학, 경영대학원'
  },
  {
    id: 'welfare', name: '종합복지관', aliases: ['복지관', '복지', '학생회관'],
    x: 356, y: 409, elev: 8, floors: [1, 6], entrance: 1, elevator: true,
    depts: '건축대학, 평생교육원, 학생자치기구, 편의시설'
  },
  {
    id: 'art', name: '예술관', aliases: ['예술', 'art'],
    x: 557, y: 439, elev: 12, floors: [1, 6], entrance: 1, elevator: true,
    depts: '예술대학, 종합예술대학원'
  },
  {
    id: 'mirae', name: '미래관', aliases: ['미래', '7호관', 'mirae'],
    x: 492, y: 485, elev: 5, floors: [1, 7], entrance: 1, elevator: true,
    depts: '소프트웨어융합대학, 체육대학, 전자공학부'
  },
  {
    id: 'eng', name: '공학관', aliases: ['공학', 'eng'],
    x: 132, y: 216, elev: 30, floors: [1, 6], entrance: 1, elevator: true,
    depts: '창의공과대학, 자동차융합대학, 자동차공학전문대학원'
  },
  {
    id: 'lab', name: '공동실험연구센터', aliases: ['공동실험', '실험동', '연구센터'],
    x: 133, y: 153, elev: 34, floors: [1, 5], entrance: 1, elevator: true,
    depts: '공동 실험·연구 시설'
  },
  {
    id: 'library', name: '성곡도서관', aliases: ['도서관', '성곡', 'library'],
    x: 103, y: 98, elev: 45, floors: [1, 6], entrance: 1, elevator: true,
    labelDx: 14, labelDy: -10, labelAnchor: 'start',
    depts: '중앙도서관'
  },
  {
    id: 'global', name: '글로벌센터', aliases: ['글로벌', 'global'],
    x: 98, y: 121, elev: 42, floors: [1, 5], entrance: 1, elevator: true,
    depts: '국제교류'
  },
  {
    id: 'museum', name: '박물관', aliases: ['박물', 'museum'],
    x: 150, y: 61, elev: 50, floors: [1, 3], entrance: 1, elevator: false,
    labelDx: 13, labelDy: 4, labelAnchor: 'start',
    depts: ''
  },
  {
    id: 'dorm', name: '생활관A동', aliases: ['생활관', '기숙사', '학생기숙사', 'dorm'],
    x: 688, y: 501, elev: 18, floors: [1, 8], entrance: 1, elevator: true,
    depts: '교내 기숙사'
  },
  {
    id: 'lifelong', name: '평생교육원', aliases: ['평생교육', '평교원'],
    x: 596, y: 538, elev: 3, floors: [1, 5], entrance: 1, elevator: true,
    depts: '평생교육원'
  },
  {
    id: 'field', name: '대운동장', aliases: ['운동장', '대운동장', 'field'],
    x: 378, y: 359, elev: 10, floors: [1, 1], entrance: 1, elevator: false,
    depts: '인조잔디 운동장', outdoorOnly: true
  },
  {
    id: 'tennis', name: '테니스장', aliases: ['테니스'],
    x: 200, y: 248, elev: 26, floors: [1, 1], entrance: 1, elevator: false,
    depts: '', outdoorOnly: true
  },
  {
    id: 'basketball', name: '농구장', aliases: ['농구'],
    x: 295, y: 283, elev: 16, floors: [1, 1], entrance: 1, elevator: false,
    depts: '', outdoorOnly: true
  },
  {
    id: 'parking', name: '지하주차장', aliases: ['주차장', '주차'],
    x: 303, y: 329, elev: 12, floors: [-2, 1], entrance: 1, elevator: true,
    depts: ''
  },
  {
    id: 'gate_main', name: '정문', aliases: ['정문', '국민대입구', '메인게이트'],
    x: 470, y: 575, elev: 0, floors: [1, 1], entrance: 1, elevator: false,
    depts: '정릉로 · 국민대입구 버스정류장', outdoorOnly: true, isGate: true
  },
  {
    id: 'gate_north', name: '북문', aliases: ['북문', '후문'],
    x: 782, y: 315, elev: 40, floors: [1, 1], entrance: 1, elevator: false,
    depts: '장교동 방향', outdoorOnly: true, isGate: true
  }
];

/* --- 교차점 (건물이 아닌 보행로 분기점) ----------------------------------- */
const JUNCTIONS = [
  { id: 'j_gate',    name: '정문 광장',     x: 478, y: 540, elev: 2 },
  { id: 'j_mirae',   name: '미래관 앞',     x: 492, y: 505, elev: 6 },
  { id: 'j_art',     name: '예술관 앞',     x: 545, y: 465, elev: 11 },
  { id: 'j_welfare', name: '복지관 앞',     x: 400, y: 430, elev: 9 },
  { id: 'j_field_e', name: '운동장 동측',   x: 440, y: 370, elev: 11 },
  { id: 'j_field_w', name: '운동장 서측',   x: 330, y: 365, elev: 11 },
  { id: 'j_center',  name: '중앙 광장',     x: 470, y: 315, elev: 19 },
  { id: 'j_bonbu',   name: '본부관 앞',     x: 500, y: 250, elev: 26 },
  { id: 'j_north',   name: '북악관 앞',     x: 460, y: 180, elev: 32 },
  { id: 'j_east',    name: '법학관 앞',     x: 600, y: 300, elev: 28 },
  { id: 'j_dorm',    name: '생활관 앞',     x: 650, y: 470, elev: 19 },
  { id: 'j_eng',     name: '공학관 앞',     x: 170, y: 240, elev: 28 },
  { id: 'j_lib',     name: '도서관 진입로', x: 140, y: 135, elev: 38 }
];

/* --- 보행로 (엣지) -------------------------------------------------------- */
/*
 * 형식: [출발, 도착, 종류, 옵션?]
 *
 * 종류
 *   'road'     일반 보도 (고도차가 있으면 경사로 취급)
 *   'stairs'   계단 — 고도차에서 계단 수를 자동 계산
 *   'ramp'     경사로 (휠체어 통행 가능)
 *   'indoor'   건물 내부 통로 — 비를 안 맞음
 *   'bridge'   건물 간 연결통로 — 이 서비스의 핵심 자산!
 *   'elevator' 엘리베이터
 *
 * 옵션
 *   covered      : true  → 비를 안 맞는 외부 통로 (필로티, 캐노피)
 *   stairs       : 숫자  → 계단 수 직접 지정 (자동 계산 무시)
 *   dist         : 숫자  → 거리(m) 직접 지정 (좌표 계산 무시)
 *   note         : 문자열 → 안내문에 붙는 설명
 *   needsVerify  : true  → 아직 확인 안 된 추정 데이터
 */
const EDGES = [
  /* ---- 캠퍼스 남단: 정문 ~ 미래관 ~ 예술관 ---- */
  ['gate_main', 'j_gate',    'road'],
  ['j_gate',    'j_mirae',   'road',   { note: '완만한 오르막' }],
  ['j_mirae',   'mirae',     'road'],
  ['j_gate',    'lifelong',  'road'],
  ['lifelong',  'j_art',     'stairs', { note: '평생교육원 옆 계단' }],
  ['j_mirae',   'j_art',     'road'],
  ['j_art',     'art',       'stairs', { note: '예술관 진입 계단' }],
  ['j_art',     'business',  'stairs'],
  ['j_mirae',   'j_welfare', 'road'],

  /* ---- 복지관 ~ 대운동장 ---- */
  ['j_welfare', 'welfare',   'road'],
  ['j_welfare', 'j_field_e', 'road'],
  ['j_welfare', 'j_field_w', 'road'],
  ['j_field_w', 'field',     'road'],
  ['j_field_e', 'field',     'road'],
  ['j_field_e', 'concert',   'road'],
  ['concert',   'business',  'indoor', { needsVerify: true, note: '콘서트홀-경영관 내부 연결 (확인 필요)' }],

  /* ---- 중앙부: 경사 구간 (이 서비스의 핵심) ---- */
  ['j_field_e', 'j_center',  'stairs', { note: '운동장에서 중앙광장 올라가는 계단' }],
  ['j_center',  'kukje',     'road'],
  ['j_center',  'kyungsang', 'road'],
  ['j_center',  'j_bonbu',   'stairs'],
  ['j_bonbu',   'bonbu',     'road'],
  ['j_bonbu',   'j_north',   'stairs', { note: '본부관에서 북악관 올라가는 계단' }],
  ['j_north',   'bukak',     'road'],
  ['j_north',   'johyung',   'stairs', { note: '조형관 진입 계단' }],
  ['bukak',     'johyung',   'bridge', { needsVerify: true, note: '북악관 ↔ 조형관 연결통로 (층 확인 필요)' }],
  ['kyungsang', 'bukak',     'stairs'],

  /* ---- 동측: 법학관 ~ 형설관 ~ 체육관 ~ 과학관 ---- */
  ['j_bonbu',   'j_east',    'road'],
  ['j_east',    'law',       'road'],
  ['j_east',    'gym',       'road'],
  ['law',       'hyungsul',  'stairs', { note: '법학관 뒤 계단' }],
  ['hyungsul',  'science',   'road',   { note: '오르막' }],
  ['science',   'gate_north', 'road'],
  ['j_east',    'youngbin',  'stairs'],
  ['youngbin',  'j_dorm',    'road'],
  ['j_dorm',    'dorm',      'road'],
  ['j_dorm',    'j_art',     'road'],
  ['gym',       'science',   'stairs', { note: '체육관 옆 계단' }],

  /* ---- 서측: 공학관 ~ 도서관 ~ 박물관 ---- */
  ['j_field_w', 'parking',   'road'],
  ['parking',   'basketball', 'road'],
  ['basketball', 'j_eng',    'stairs', { note: '농구장에서 공학관 올라가는 계단' }],
  ['j_eng',     'eng',       'road'],
  ['j_eng',     'tennis',    'road'],
  ['eng',       'lab',       'bridge', { needsVerify: true, note: '공학관 ↔ 공동실험연구센터 연결 (확인 필요)' }],
  ['j_eng',     'j_lib',     'stairs', { note: '도서관 오르는 계단 (악명 높은 구간)' }],
  ['j_lib',     'library',   'road'],
  ['j_lib',     'global',    'road'],
  ['library',   'global',    'indoor', { needsVerify: true, note: '도서관 ↔ 글로벌센터 내부 연결 (확인 필요)' }],
  ['library',   'museum',    'stairs'],
  ['j_eng',     'j_center',  'road',   { dist: 330, note: '캠퍼스 횡단 보도' }],

  /* ---- 무장애 우회로 (엘리베이터 / 경사로) ---- */
  /* ★ 아래는 "이런 게 있으면 좋겠다" 수준의 추정입니다.
     실제로 어떤 경로가 휠체어 통행 가능한지 확인해서 고쳐주세요. */
  ['j_field_e', 'concert',   'ramp',   { needsVerify: true, note: '콘서트홀 측 경사로' }],
  ['concert',   'j_center',  'elevator', { needsVerify: true, note: '콘서트홀 엘리베이터로 중앙광장 레벨 진입 (확인 필요)' }],
  ['j_center',  'bonbu',     'ramp',   { needsVerify: true, note: '본부관 측 경사로' }],
  ['bonbu',     'bukak',     'elevator', { needsVerify: true, note: '본부관-북악관 엘리베이터 경유 (확인 필요)' }],
  ['j_art',     'art',       'ramp',   { needsVerify: true, note: '예술관 측면 경사로 (확인 필요)' }],
  ['gym',       'science',   'elevator', { needsVerify: true, note: '체육관 엘리베이터로 과학관 레벨 진입 (확인 필요)' }],
  ['j_eng',     'j_lib',     'elevator', { needsVerify: true, note: '도서관 진입 리프트 (확인 필요)' }]
];

/* --- 강의실 코드 해석 규칙 ------------------------------------------------ */
/*
 * "북악관 411호" → 북악관 4층
 * 3자리면 앞 1자리, 4자리면 앞 1~2자리를 층으로 해석합니다.
 * 건물마다 규칙이 다르면 여기에 예외를 추가하세요.
 */
const ROOM_FLOOR_EXCEPTIONS = {
  // 예: bukak: (code) => Number(String(code).slice(0, 2))
};

/* --- 이동 모드 ------------------------------------------------------------ */
/*
 * stair    : 계단 한 칸당 추가 비용
 * slope    : 오르막 1m당 추가 비용
 * outdoor  : 실외 구간 1m당 추가 비용 (비 오는 날)
 * noStairs : true 면 계단 구간을 아예 통행 불가로 처리
 */
const MODES = {
  fastest: {
    id: 'fastest', label: '최단시간', icon: '⚡',
    desc: '거리 위주. 계단도 감수합니다.',
    stair: 0.2, slope: 0.8, outdoor: 0, noStairs: false
  },
  fewStairs: {
    id: 'fewStairs', label: '계단 최소', icon: '🦵',
    desc: '계단을 최대한 피해서 돌아갑니다.',
    stair: 7.0, slope: 4.0, outdoor: 0, noStairs: false
  },
  accessible: {
    id: 'accessible', label: '무장애', icon: '♿',
    desc: '계단 없는 경로만. 휠체어·부상·캐리어.',
    stair: 0, slope: 9.0, outdoor: 0, noStairs: true
  },
  sheltered: {
    id: 'sheltered', label: '비 안 맞기', icon: '🌧️',
    desc: '실내·지붕 있는 구간을 우선합니다.',
    stair: 1.2, slope: 1.5, outdoor: 1.4, noStairs: false
  }
};
