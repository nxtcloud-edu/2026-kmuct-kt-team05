/* =============================================================================
 * 경로 탐색 엔진
 * =============================================================================
 * data.js 의 BUILDINGS / JUNCTIONS / EDGES 를 방향 그래프로 펼친 뒤
 * 모드별 가중치를 적용한 다익스트라로 최적 경로를 찾습니다.
 *
 * 핵심 아이디어
 *   같은 출발·도착이라도 모드에 따라 "비용"의 정의가 바뀌므로
 *   전혀 다른 경로가 나옵니다. 이게 일반 지도앱과의 차이점입니다.
 * ========================================================================== */

'use strict';

/* --- 엣지 종류별 성질 ----------------------------------------------------- */
const EDGE_KINDS = {
  road:     { indoor: false, stairsFromElev: false, climbFactor: 1.0,  waitSec: 0,  verb: '보도' },
  stairs:   { indoor: false, stairsFromElev: true,  climbFactor: 0.0,  waitSec: 0,  verb: '계단' },
  ramp:     { indoor: false, stairsFromElev: false, climbFactor: 0.7,  waitSec: 0,  verb: '경사로' },
  indoor:   { indoor: true,  stairsFromElev: false, climbFactor: 0.3,  waitSec: 0,  verb: '실내 통로' },
  bridge:   { indoor: true,  stairsFromElev: false, climbFactor: 0.3,  waitSec: 0,  verb: '연결통로' },
  elevator: { indoor: true,  stairsFromElev: false, climbFactor: 0.0,  waitSec: 35, verb: '엘리베이터' }
};

/* =============================================================================
 * 그래프 구성
 * ========================================================================== */

const Graph = (function () {

  /** id → 노드 */
  const nodes = new Map();

  /** id → 나가는 방향 엣지 배열 */
  const adj = new Map();

  /** 데이터 점검 결과 */
  const issues = [];

  function euclid(a, b) {
    return Math.hypot(a.x - b.x, a.y - b.y);
  }

  function registerNode(raw, kind) {
    if (nodes.has(raw.id)) {
      issues.push({ level: 'error', msg: `중복된 노드 id: ${raw.id}` });
      return;
    }
    nodes.set(raw.id, Object.assign({}, raw, { kind: kind }));
    adj.set(raw.id, []);
  }

  BUILDINGS.forEach(b => registerNode(b, 'building'));
  JUNCTIONS.forEach(j => registerNode(j, 'junction'));

  /**
   * 원본 엣지 하나를 양방향 두 개로 펼칩니다.
   * 오르막/내리막은 방향에 따라 비용이 다르므로 반드시 분리해야 합니다.
   */
  EDGES.forEach((raw, index) => {
    const [aId, bId, type] = raw;
    const opts = raw[3] || {};

    const a = nodes.get(aId);
    const b = nodes.get(bId);

    if (!a || !b) {
      issues.push({
        level: 'error',
        msg: `엣지 #${index}: 존재하지 않는 노드 (${!a ? aId : bId})`
      });
      return;
    }

    const kind = EDGE_KINDS[type];
    if (!kind) {
      issues.push({ level: 'error', msg: `엣지 #${index}: 알 수 없는 종류 "${type}"` });
      return;
    }

    const dist = opts.dist != null
      ? opts.dist
      : euclid(a, b) * SCALE_M_PER_PX;

    const dElev = b.elev - a.elev;

    // 계단 수: 명시값 > 고도차 역산 > 최소 1칸
    let stepCount = 0;
    if (kind.stairsFromElev) {
      stepCount = opts.stairs != null
        ? opts.stairs
        : Math.max(1, Math.round(Math.abs(dElev) / STEP_HEIGHT_M));
    } else if (opts.stairs != null) {
      stepCount = opts.stairs;
    }

    const indoor = kind.indoor || opts.covered === true;

    if (opts.needsVerify) {
      issues.push({
        level: 'warn',
        msg: `확인 필요: ${a.name} ↔ ${b.name}${opts.note ? ' — ' + opts.note : ''}`
      });
    }

    // a → b 와 b → a 를 각각 등록
    [[a, b, dElev], [b, a, -dElev]].forEach(([from, to, delta]) => {
      adj.get(from.id).push({
        from: from.id,
        to: to.id,
        type: type,
        kind: kind,
        dist: dist,
        indoor: indoor,
        climb: Math.max(0, delta),          // 올라가는 높이(m)
        drop: Math.max(0, -delta),          // 내려가는 높이(m)
        stairsUp: delta > 0 ? stepCount : 0,
        stairsDown: delta < 0 ? stepCount : 0,
        stairsFlat: delta === 0 ? stepCount : 0,
        note: opts.note || '',
        needsVerify: !!opts.needsVerify
      });
    });
  });

  return { nodes: nodes, adj: adj, issues: issues };
})();

/* =============================================================================
 * 비용 / 시간 계산
 * ========================================================================== */

/** 모드에 따른 이 엣지의 통행 비용. 통행 불가면 Infinity */
function edgeCost(edge, mode) {
  // 무장애 모드: 계단이 있는 구간은 통행 불가
  if (mode.noStairs) {
    const totalSteps = edge.stairsUp + edge.stairsDown + edge.stairsFlat;
    if (totalSteps > 0) return Infinity;
  }

  let cost = edge.dist;

  // 계단 — 올라가는 쪽이 훨씬 힘들므로 내려가는 계단은 40%만 반영
  cost += mode.stair * edge.stairsUp;
  cost += mode.stair * 0.4 * edge.stairsDown;
  cost += mode.stair * 0.4 * edge.stairsFlat;

  // 경사 — 계단으로 이미 비용을 매긴 구간은 climbFactor 0 이라 이중 계산되지 않음
  cost += mode.slope * edge.climb * edge.kind.climbFactor;

  // 비 오는 날: 실외 구간에 패널티
  if (!edge.indoor) cost += mode.outdoor * edge.dist;

  // 엘리베이터 대기시간을 "그 시간에 걸을 수 있는 거리"로 환산합니다.
  // 이렇게 해야 비용 단위(m)가 일관되고, 급한 사람이 엘리베이터를
  // 마냥 기다리지 않는 현실이 반영됩니다.
  cost += edge.kind.waitSec * WALK_SPEED_MPS;

  return cost;
}

/** 이 엣지를 실제로 통과하는 데 걸리는 시간(초) */
function edgeSeconds(edge) {
  let sec = edge.dist / WALK_SPEED_MPS;
  sec += edge.stairsUp * 0.62;
  sec += edge.stairsDown * 0.45;
  sec += edge.stairsFlat * 0.5;
  sec += edge.climb * edge.kind.climbFactor * 2.2;   // 오르막에서 느려지는 몫
  sec += edge.kind.waitSec;
  return sec;
}

/* =============================================================================
 * 다익스트라
 * ========================================================================== */

/**
 * @param {string} fromId 출발 노드 id
 * @param {string} toId   도착 노드 id
 * @param {string} modeId MODES 의 키
 * @returns {{ok:boolean, reason?:string, nodes?:string[], segments?:object[], totals?:object}}
 */
function findRoute(fromId, toId, modeId) {
  const mode = MODES[modeId];
  if (!mode) return { ok: false, reason: `알 수 없는 모드: ${modeId}` };
  if (!Graph.nodes.has(fromId)) return { ok: false, reason: `출발지를 찾을 수 없습니다: ${fromId}` };
  if (!Graph.nodes.has(toId)) return { ok: false, reason: `도착지를 찾을 수 없습니다: ${toId}` };

  if (fromId === toId) {
    return {
      ok: true, nodes: [fromId], segments: [],
      totals: emptyTotals(), mode: mode
    };
  }

  const dist = new Map();
  const prev = new Map();     // nodeId → 여기로 들어온 엣지
  const visited = new Set();

  Graph.nodes.forEach((_, id) => dist.set(id, Infinity));
  dist.set(fromId, 0);

  // 노드 수가 수십 개 수준이라 단순 선형 탐색으로 충분합니다.
  // 수천 개로 늘어나면 바이너리 힙으로 교체하세요.
  while (visited.size < Graph.nodes.size) {
    let current = null;
    let best = Infinity;
    dist.forEach((d, id) => {
      if (!visited.has(id) && d < best) { best = d; current = id; }
    });

    if (current === null) break;      // 남은 노드에 도달 불가
    if (current === toId) break;

    visited.add(current);

    Graph.adj.get(current).forEach(edge => {
      if (visited.has(edge.to)) return;
      const w = edgeCost(edge, mode);
      if (!isFinite(w)) return;       // 이 모드에서는 통행 불가
      const cand = dist.get(current) + w;
      if (cand < dist.get(edge.to)) {
        dist.set(edge.to, cand);
        prev.set(edge.to, edge);
      }
    });
  }

  if (!isFinite(dist.get(toId))) {
    return {
      ok: false,
      reason: mode.noStairs
        ? '계단을 쓰지 않는 경로가 없습니다. 이 구간은 접근성 개선이 필요한 곳입니다.'
        : '경로를 찾을 수 없습니다. 그래프 데이터에 끊긴 구간이 있는지 확인하세요.',
      accessibilityGap: !!mode.noStairs
    };
  }

  // 경로 역추적
  const segments = [];
  let cursor = toId;
  while (cursor !== fromId) {
    const edge = prev.get(cursor);
    segments.unshift(edge);
    cursor = edge.from;
  }

  const nodeIds = [fromId].concat(segments.map(s => s.to));

  return {
    ok: true,
    mode: mode,
    nodes: nodeIds,
    segments: segments,
    totals: summarize(segments)
  };
}

function emptyTotals() {
  return {
    dist: 0, seconds: 0, minutes: 0,
    stairsUp: 0, stairsDown: 0, climb: 0, drop: 0,
    indoorDist: 0, indoorRatio: 1, elevatorCount: 0, needsVerify: false
  };
}

function summarize(segments) {
  const t = emptyTotals();
  t.indoorRatio = 0;

  segments.forEach(s => {
    t.dist += s.dist;
    t.seconds += edgeSeconds(s);
    t.stairsUp += s.stairsUp;
    t.stairsDown += s.stairsDown + s.stairsFlat;
    t.climb += s.climb;
    t.drop += s.drop;
    if (s.indoor) t.indoorDist += s.dist;
    if (s.type === 'elevator') t.elevatorCount += 1;
    if (s.needsVerify) t.needsVerify = true;
  });

  t.minutes = Math.max(1, Math.round(t.seconds / 60));
  t.indoorRatio = t.dist > 0 ? t.indoorDist / t.dist : 0;
  return t;
}

/** 네 가지 모드를 모두 계산해서 비교용으로 돌려줍니다 */
function findAllRoutes(fromId, toId) {
  const out = {};
  Object.keys(MODES).forEach(id => {
    out[id] = findRoute(fromId, toId, id);
  });
  return out;
}

/* =============================================================================
 * 데이터 건강검진
 * ========================================================================== */
/*
 * 데이터를 손으로 채우다 보면 노드를 빼먹거나 오타를 내기 쉽습니다.
 * 앱을 열 때마다 아래 점검이 돌아서 문제를 바로 알려줍니다.
 */
function healthCheck() {
  const report = { errors: [], warnings: [], stats: {} };

  Graph.issues.forEach(i => {
    (i.level === 'error' ? report.errors : report.warnings).push(i.msg);
  });

  // 고립된 노드
  Graph.nodes.forEach((node, id) => {
    if (Graph.adj.get(id).length === 0) {
      report.errors.push(`${node.name}(${id}) 에 연결된 보행로가 없습니다.`);
    }
  });

  // 모드별 도달 불가 건물
  const origin = 'gate_main';
  const unreachable = {};
  Object.keys(MODES).forEach(modeId => {
    const bad = [];
    BUILDINGS.forEach(b => {
      if (b.id === origin) return;
      const r = findRoute(origin, b.id, modeId);
      if (!r.ok) bad.push(b.name);
    });
    if (bad.length) unreachable[MODES[modeId].label] = bad;
  });

  Object.keys(unreachable).forEach(label => {
    report.warnings.push(
      `[${label}] 정문에서 도달 불가: ${unreachable[label].join(', ')}`
    );
  });

  report.stats = {
    buildings: BUILDINGS.length,
    junctions: JUNCTIONS.length,
    edges: EDGES.length,
    directedEdges: Array.from(Graph.adj.values()).reduce((n, a) => n + a.length, 0),
    unverified: EDGES.filter(e => e[3] && e[3].needsVerify).length
  };
  report.unreachable = unreachable;

  return report;
}

/* --- 조회 헬퍼 ------------------------------------------------------------ */

function getNode(id) { return Graph.nodes.get(id); }

function allBuildings() {
  return BUILDINGS.slice().sort((a, b) => a.name.localeCompare(b.name, 'ko'));
}
