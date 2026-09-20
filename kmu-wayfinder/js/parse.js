/* =============================================================================
 * 자연어 입력 해석 + 경로 내레이션
 * =============================================================================
 * 두 겹 구조입니다.
 *   1) 규칙 기반 파서 — 오프라인에서 항상 동작. 데모의 안전망.
 *   2) LLM 보강      — 있으면 더 자유로운 문장을 알아듣고, 안내문도 매끄러워짐.
 *
 * 발표 중 API 가 죽어도 1번이 받쳐주므로 데모가 깨지지 않습니다.
 * ========================================================================== */

'use strict';

/* =============================================================================
 * 장소 해석
 * ========================================================================== */

/** 별칭 → 건물 id 색인. 긴 이름을 먼저 매칭해야 "북악관"이 "북악"보다 우선됩니다. */
const PLACE_INDEX = (function () {
  const entries = [];
  BUILDINGS.forEach(b => {
    entries.push({ key: b.name, id: b.id });
    (b.aliases || []).forEach(a => entries.push({ key: a, id: b.id }));
  });
  entries.sort((a, b) => b.key.length - a.key.length);
  return entries;
})();

/**
 * "북악관 411호" 같은 표현에서 건물과 층을 뽑아냅니다.
 * @returns {{id:string, name:string, floor:number|null, room:string|null, matched:string}|null}
 */
function resolvePlace(text) {
  if (!text) return null;
  const s = String(text).trim();

  for (let i = 0; i < PLACE_INDEX.length; i++) {
    const entry = PLACE_INDEX[i];
    const pos = s.toLowerCase().indexOf(entry.key.toLowerCase());
    if (pos === -1) continue;

    const building = getNode(entry.id);
    const after = s.slice(pos + entry.key.length);
    const roomMatch = after.match(/^\s*(\d{3,4})\s*(호|호실)?/);

    let floor = null;
    let room = null;
    if (roomMatch) {
      room = roomMatch[1];
      floor = roomToFloor(entry.id, room);
    }

    return {
      id: entry.id,
      name: building.name,
      floor: floor,
      room: room,
      matched: entry.key
    };
  }
  return null;
}

/** 강의실 번호를 층으로 변환 */
function roomToFloor(buildingId, code) {
  const exception = ROOM_FLOOR_EXCEPTIONS[buildingId];
  if (exception) return exception(code);

  const str = String(code);
  const floor = str.length >= 4
    ? Number(str.slice(0, 2))     // 1103호 → 11층
    : Number(str.slice(0, 1));    // 411호  → 4층

  const b = getNode(buildingId);
  if (b && b.floors && (floor < b.floors[0] || floor > b.floors[1])) {
    return null;                  // 층수 범위를 벗어나면 신뢰하지 않음
  }
  return floor;
}

/** 문장에서 장소를 등장 순서대로 전부 찾습니다 */
function resolveAllPlaces(text) {
  if (!text) return [];
  const s = String(text);
  const found = [];
  const taken = [];   // 이미 소비한 문자 구간

  PLACE_INDEX.forEach(entry => {
    let searchFrom = 0;
    for (;;) {
      const pos = s.toLowerCase().indexOf(entry.key.toLowerCase(), searchFrom);
      if (pos === -1) break;
      const end = pos + entry.key.length;

      const overlaps = taken.some(r => pos < r.end && end > r.start);
      if (!overlaps) {
        taken.push({ start: pos, end: end });
        const place = resolvePlace(s.slice(pos));
        if (place) found.push({ pos: pos, place: place });
      }
      searchFrom = end;
    }
  });

  found.sort((a, b) => a.pos - b.pos);
  return found.map(f => f.place);
}

/* =============================================================================
 * 모드 추론
 * ========================================================================== */

const MODE_KEYWORDS = [
  // 우선순위가 높은 것부터. 무장애가 가장 강한 제약이라 먼저 봅니다.
  { mode: 'accessible', words: ['휠체어', '유모차', '목발', '깁스', '부상', '다쳤', '다리를', '무장애', '배리어프리', '계단 없', '계단없', '캐리어', '짐이', '이삿'] },
  { mode: 'sheltered',  words: ['비가', '비 오', '비와', '비 와', '우산', '젖', '장마', '소나기', '눈이', '실내로', '실내만'] },
  { mode: 'fewStairs',  words: ['계단', '힘들', '숨차', '헉헉', '오르막', '언덕', '편한', '편하게', '덜 힘'] },
  { mode: 'fastest',    words: ['빨리', '급해', '급함', '지각', '늦었', '최단', '빠른', '서둘'] }
];

function inferMode(text) {
  if (!text) return null;
  const s = String(text);
  for (let i = 0; i < MODE_KEYWORDS.length; i++) {
    const rule = MODE_KEYWORDS[i];
    for (let j = 0; j < rule.words.length; j++) {
      if (s.indexOf(rule.words[j]) !== -1) {
        return { mode: rule.mode, trigger: rule.words[j] };
      }
    }
  }
  return null;
}

/* =============================================================================
 * 질의 전체 파싱
 * ========================================================================== */

/**
 * @param {string} text 사용자가 입력한 문장
 * @param {object} fallback { fromId, toId, modeId } 현재 UI 상태
 * @returns {{fromId, toId, modeId, fromPlace, toPlace, notes:string[], confident:boolean}}
 */
function parseQuery(text, fallback) {
  fallback = fallback || {};
  const notes = [];
  const places = resolveAllPlaces(text);
  const modeHit = inferMode(text);

  let fromPlace = null;
  let toPlace = null;

  // "A에서 B" / "A부터 B까지" / "A → B" 같은 방향 표현을 우선 확인
  const arrow = String(text || '').match(
    /(.+?)\s*(?:에서|부터|➡|->|→|=>)\s*(.+)/
  );

  if (arrow) {
    fromPlace = resolvePlace(arrow[1]);
    toPlace = resolvePlace(arrow[2]);
  }

  // 방향 표현이 없으면 등장 순서로 판단
  if (!fromPlace || !toPlace) {
    if (places.length >= 2) {
      fromPlace = fromPlace || places[0];
      toPlace = toPlace || places[places.length - 1];
    } else if (places.length === 1) {
      // 하나만 말했으면 목적지로 봅니다. "조형관 가는 길" 같은 경우.
      toPlace = places[0];
      notes.push('출발지를 못 찾아서 현재 선택된 출발지를 그대로 씁니다.');
    }
  }

  const fromId = (fromPlace && fromPlace.id) || fallback.fromId || 'gate_main';
  const toId = (toPlace && toPlace.id) || fallback.toId || null;
  const modeId = (modeHit && modeHit.mode) || fallback.modeId || 'fastest';

  if (modeHit) {
    notes.push(`"${modeHit.trigger}" 를 보고 ${MODES[modeHit.mode].label} 모드로 잡았습니다.`);
  }
  if (fromId === toId && toId) {
    notes.push('출발지와 도착지가 같습니다.');
  }

  return {
    fromId: fromId,
    toId: toId,
    modeId: modeId,
    fromPlace: fromPlace,
    toPlace: toPlace,
    notes: notes,
    confident: !!(toPlace)
  };
}

/* =============================================================================
 * 경로 내레이션
 * ========================================================================== */

/**
 * 연속된 같은 종류 구간을 묶어서 사람이 읽기 좋은 단계 목록으로 만듭니다.
 * @returns {{steps:Array, summary:string, sentence:string}}
 */
function narrate(route, context) {
  context = context || {};
  if (!route || !route.ok) {
    return { steps: [], summary: '', sentence: route ? route.reason : '' };
  }

  const fromNode = getNode(route.nodes[0]);
  const toNode = getNode(route.nodes[route.nodes.length - 1]);
  const steps = [];

  // 출발
  steps.push({
    icon: '🚩',
    text: `${fromNode.name}${context.fromFloor ? ' ' + context.fromFloor + '층' : ''}에서 출발`,
    detail: ''
  });

  // 같은 종류의 연속 구간을 하나로 합치기
  const groups = [];
  route.segments.forEach(seg => {
    const last = groups[groups.length - 1];
    const sameKind = last
      && last.type === seg.type
      && (seg.stairsUp > 0) === (last.stairsUp > 0)
      && (seg.stairsDown > 0) === (last.stairsDown > 0);

    if (sameKind) {
      last.dist += seg.dist;
      last.stairsUp += seg.stairsUp;
      last.stairsDown += seg.stairsDown;
      last.climb += seg.climb;
      last.drop += seg.drop;
      last.to = seg.to;
      if (seg.note && last.notes.indexOf(seg.note) === -1) last.notes.push(seg.note);
    } else {
      groups.push({
        type: seg.type, from: seg.from, to: seg.to,
        dist: seg.dist, stairsUp: seg.stairsUp, stairsDown: seg.stairsDown,
        climb: seg.climb, drop: seg.drop,
        notes: seg.note ? [seg.note] : []
      });
    }
  });

  groups.forEach(g => {
    const dest = getNode(g.to);
    const m = Math.round(g.dist);
    let icon = '🚶';
    let text = '';

    switch (g.type) {
      case 'stairs':
        if (g.stairsUp > 0) {
          icon = '🪜';
          text = `계단 약 ${g.stairsUp}칸을 올라 ${dest.name} 쪽으로`;
        } else {
          icon = '🪜';
          text = `계단 약 ${g.stairsDown}칸을 내려 ${dest.name} 쪽으로`;
        }
        break;
      case 'bridge':
        icon = '🌉';
        text = `연결통로로 ${dest.name}으로 건너가기 (실내, 계단 없음)`;
        break;
      case 'indoor':
        icon = '🏢';
        text = `건물 안을 통과해 ${dest.name}으로 (${m}m, 비 안 맞음)`;
        break;
      case 'elevator':
        icon = '🛗';
        text = `엘리베이터로 ${dest.name} 레벨까지 이동`;
        break;
      case 'ramp':
        icon = '♿';
        text = `경사로로 ${dest.name}까지 ${m}m`;
        break;
      default:
        icon = g.climb > 4 ? '⛰️' : '🚶';
        text = g.climb > 4
          ? `오르막 보도를 ${m}m 올라 ${dest.name}까지`
          : (g.drop > 4
            ? `내리막 보도를 ${m}m 내려 ${dest.name}까지`
            : `보도를 ${m}m 걸어 ${dest.name}까지`);
    }

    steps.push({ icon: icon, text: text, detail: g.notes.join(' / ') });
  });

  // 목적지 층까지 올라가기
  if (context.toFloor && context.toFloor > 1) {
    const b = getNode(toNode.id);
    steps.push({
      icon: b.elevator ? '🛗' : '🪜',
      text: b.elevator
        ? `엘리베이터로 ${context.toFloor}층${context.toRoom ? ' ' + context.toRoom + '호' : ''}`
        : `계단으로 ${context.toFloor}층${context.toRoom ? ' ' + context.toRoom + '호' : ''} (이 건물은 엘리베이터 정보가 없습니다)`,
      detail: ''
    });
  }

  steps.push({
    icon: '🏁',
    text: `${toNode.name}${context.toFloor ? ' ' + context.toFloor + '층' : ''}${context.toRoom ? ' ' + context.toRoom + '호' : ''} 도착`,
    detail: ''
  });

  const t = route.totals;
  const bits = [
    `${t.minutes}분`,
    `${Math.round(t.dist)}m`
  ];
  if (t.stairsUp) bits.push(`오르는 계단 ${t.stairsUp}칸`);
  if (t.stairsDown) bits.push(`내리는 계단 ${t.stairsDown}칸`);
  if (t.climb >= 3) bits.push(`누적 상승 ${Math.round(t.climb)}m`);
  if (t.elevatorCount) bits.push(`엘리베이터 ${t.elevatorCount}회`);

  const summary = bits.join(' · ');

  const sentence = `${fromNode.name}에서 ${toNode.name}까지 ${route.mode.label} 경로로 `
    + `약 ${t.minutes}분 걸립니다. ${t.stairsUp ? `계단은 ${t.stairsUp}칸 올라가야 하고, ` : '올라가는 계단은 없습니다. '}`
    + `실내 구간 비중은 ${Math.round(t.indoorRatio * 100)}% 입니다.`;

  return { steps: steps, summary: summary, sentence: sentence };
}

/* =============================================================================
 * 모드 비교 인사이트  ← 데모의 하이라이트
 * ========================================================================== */

/**
 * 현재 모드와 다른 모드를 비교해서 "이렇게 바꾸면 이만큼 달라진다"를 뽑아냅니다.
 */
function modeInsights(routes, currentModeId) {
  const cur = routes[currentModeId];
  if (!cur || !cur.ok) return [];

  const out = [];

  Object.keys(MODES).forEach(id => {
    if (id === currentModeId) return;
    const other = routes[id];
    const label = MODES[id].label;

    if (!other || !other.ok) {
      if (other && other.accessibilityGap) {
        out.push({
          level: 'alert',
          text: `${label}: 경로 없음. 계단을 피할 방법이 없는 구간입니다.`
        });
      }
      return;
    }

    const dStairs = other.totals.stairsUp - cur.totals.stairsUp;
    const dMin = other.totals.minutes - cur.totals.minutes;

    // 의미 있는 차이만 보여줍니다
    if (dStairs === 0 && dMin === 0) return;

    const parts = [];
    if (dStairs !== 0) {
      parts.push(`계단 ${cur.totals.stairsUp} → ${other.totals.stairsUp}칸`);
    }
    if (dMin !== 0) {
      parts.push(`시간 ${cur.totals.minutes} → ${other.totals.minutes}분`);
    }
    if (Math.abs(other.totals.indoorRatio - cur.totals.indoorRatio) > 0.15) {
      parts.push(`실내 ${Math.round(cur.totals.indoorRatio * 100)} → ${Math.round(other.totals.indoorRatio * 100)}%`);
    }

    out.push({
      level: dStairs < 0 ? 'good' : 'info',
      text: `${label}: ${parts.join(', ')}`
    });
  });

  return out;
}

/* =============================================================================
 * 다음 수업까지 남은 시간
 * ========================================================================== */

/**
 * "지금 나가야 하나?" 판단용. 수업 시작 시각(HH:MM)과 소요 시간을 비교합니다.
 */
function leaveAdvice(route, classTimeStr, now) {
  if (!route || !route.ok || !classTimeStr) return null;

  const m = String(classTimeStr).match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;

  now = now || new Date();
  const target = new Date(now);
  target.setHours(Number(m[1]), Number(m[2]), 0, 0);

  const minutesLeft = Math.round((target - now) / 60000);
  const needed = route.totals.minutes;
  const slack = minutesLeft - needed;

  if (minutesLeft < 0) {
    return { level: 'alert', text: `${classTimeStr} 수업은 이미 시작했습니다. 이동에 ${needed}분 걸립니다.` };
  }
  if (slack < 0) {
    return { level: 'alert', text: `지금 출발해도 ${Math.abs(slack)}분 늦습니다. 이동 ${needed}분 / 남은 시간 ${minutesLeft}분.` };
  }
  if (slack <= 3) {
    return { level: 'warn', text: `지금 바로 출발하세요. 이동 ${needed}분, 여유 ${slack}분.` };
  }
  return { level: 'good', text: `${slack - 0}분 여유가 있습니다. ${slack <= 10 ? '슬슬 나가면 됩니다.' : `${slack - 3}분 뒤에 나가도 됩니다.`} 이동 ${needed}분.` };
}

/* =============================================================================
 * LLM 보강 (선택)
 * ========================================================================== */
/*
 * ⚠️ 보안 주의
 *   아래 구현은 브라우저에서 직접 API 를 호출하므로 API 키가 클라이언트에
 *   노출됩니다. 해커톤 데모용으로만 쓰고, 실제 서비스로 만들 거라면
 *   반드시 서버(또는 서버리스 함수)를 두고 키를 거기에 보관하세요.
 *   키는 localStorage 에만 저장하며 코드에 하드코딩하지 않습니다.
 */
const LLM = (function () {
  const KEY_STORAGE = 'kmu_wayfinder_api_key';
  const ENDPOINT_STORAGE = 'kmu_wayfinder_api_endpoint';

  const DEFAULT_ENDPOINT = 'https://api.openai.com/v1/chat/completions';
  const DEFAULT_MODEL = 'gpt-4o-mini';

  function getKey() { return localStorage.getItem(KEY_STORAGE) || ''; }
  function setKey(v) {
    if (v) localStorage.setItem(KEY_STORAGE, v);
    else localStorage.removeItem(KEY_STORAGE);
  }
  function getEndpoint() { return localStorage.getItem(ENDPOINT_STORAGE) || DEFAULT_ENDPOINT; }
  function setEndpoint(v) {
    if (v) localStorage.setItem(ENDPOINT_STORAGE, v);
    else localStorage.removeItem(ENDPOINT_STORAGE);
  }
  function available() { return !!getKey(); }

  async function chat(messages, options) {
    options = options || {};
    if (!available()) throw new Error('API 키가 설정되지 않았습니다.');

    const res = await fetch(getEndpoint(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + getKey()
      },
      body: JSON.stringify({
        model: options.model || DEFAULT_MODEL,
        messages: messages,
        temperature: options.temperature != null ? options.temperature : 0.3,
        max_tokens: options.maxTokens || 400
      })
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`API 오류 ${res.status}: ${body.slice(0, 200)}`);
    }
    const json = await res.json();
    return json.choices[0].message.content;
  }

  /** 규칙 파서가 자신 없을 때만 호출해서 출발/도착/모드를 뽑아냅니다 */
  async function extractIntent(text) {
    const names = BUILDINGS.map(b => `${b.id}=${b.name}`).join(', ');
    const content = await chat([
      {
        role: 'system',
        content:
          '국민대 캠퍼스 길찾기 앱의 입력 해석기다. 사용자 문장에서 출발지, 도착지, 이동 모드를 뽑아 ' +
          'JSON 만 출력하라. 설명 금지.\n' +
          `건물 목록(id=이름): ${names}\n` +
          '모드: fastest(최단시간), fewStairs(계단최소), accessible(무장애/휠체어), sheltered(비안맞기)\n' +
          '형식: {"fromId":string|null,"toId":string|null,"modeId":string,"fromRoom":string|null,"toRoom":string|null}'
      },
      { role: 'user', content: text }
    ], { temperature: 0 });

    const match = content.match(/\{[\s\S]*\}/);
    if (!match) throw new Error('JSON 을 찾을 수 없습니다: ' + content.slice(0, 120));
    return JSON.parse(match[0]);
  }

  /** 딱딱한 단계 목록을 자연스러운 안내 문장으로 다시 씁니다 */
  async function polishNarration(route, steps, context) {
    const raw = steps.map((s, i) => `${i + 1}. ${s.text}${s.detail ? ' (' + s.detail + ')' : ''}`).join('\n');
    return chat([
      {
        role: 'system',
        content:
          '너는 국민대 캠퍼스 길안내 도우미다. 주어진 경로 단계를 자연스러운 한국어 3~4문장으로 ' +
          '다시 써라. 경사와 계단 정보를 반드시 살리고, 숫자를 바꾸지 마라. ' +
          '없는 장소나 시설을 새로 만들지 마라. 친근하지만 간결하게.'
      },
      {
        role: 'user',
        content:
          `모드: ${route.mode.label}\n` +
          `총 ${route.totals.minutes}분, ${Math.round(route.totals.dist)}m, ` +
          `오르는 계단 ${route.totals.stairsUp}칸, 누적 상승 ${Math.round(route.totals.climb)}m\n\n` +
          `단계:\n${raw}`
      }
    ], { temperature: 0.4, maxTokens: 320 });
  }

  return {
    available: available,
    getKey: getKey, setKey: setKey,
    getEndpoint: getEndpoint, setEndpoint: setEndpoint,
    chat: chat,
    extractIntent: extractIntent,
    polishNarration: polishNarration
  };
})();
