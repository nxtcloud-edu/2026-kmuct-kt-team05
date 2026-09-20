/**
 * ============================================================
 *  campus-graph.json 생성기 — 경로 탐색용 그래프
 * ============================================================
 *  실행: node tools/build-graph.mjs
 *  전제: tools/osm-cache.json 이 있어야 한다 (tools/build-campus-map.mjs 가 만든다)
 *
 *  입력
 *   - tools/osm-cache.json                    OSM 원본 (건물 / 보행로 / 계단)
 *   - data/campus-facts.json                  학생 제보 (층간 연결 · 엘리베이터 · 고도 · 광장)
 *   - tools/campus-buildings.generated.json   건물 무게중심 좌표
 *
 *  출력
 *   - data/campus-graph.json    lib/types.ts 의 CampusGraph 형태
 *   - data/graph-coords.json    모든 그래프 노드의 SVG 좌표
 *
 *  실외 지형 고도는 '보간'해서 얻는다
 *   1. 제보로 알아낸 건물 지면층 고도 + 정문 + 광장 노드를 앵커로 박는다
 *   2. 보행 네트워크 위에서 라플라스 평활(이웃 평균 반복)로 나머지 노드 고도를 채운다
 *   3. 각 실외 엣지의 경사 = |고도차| / 수평거리
 *
 *  노드 ID 규칙
 *   w<OSM노드ID>        OSM 보행로 노드
 *   p_<광장>_<노드>     직접 추가한 실외 노드 (data/campus-facts.json 의 outdoorAreas)
 *   <건물slug>_<층>     건물 층 노드 (예: mirae_old_1f, art_b2, bukak_16f)
 * ============================================================
 */

import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const read = (p) => JSON.parse(readFileSync(resolve(ROOT, p), 'utf8'));

const osm = read('tools/osm-cache.json');
const facts = read('data/campus-facts.json');
const buildingRef = read('tools/campus-buildings.generated.json');

/* ------------------------------------------------------------
 * 투영 — build-campus-map.mjs 와 반드시 같아야 한다
 * ---------------------------------------------------------- */
const VIEW = buildingRef.viewBox;
const BOUNDS = buildingRef.bounds;
const M_PER_DEG_LON = 111320 * Math.cos((37.611 * Math.PI) / 180);
const METERS_PER_UNIT = ((BOUNDS.lonMax - BOUNDS.lonMin) * M_PER_DEG_LON) / VIEW.width;

const project = ({ lat, lon }) => ({
  x: ((lon - BOUNDS.lonMin) / (BOUNDS.lonMax - BOUNDS.lonMin)) * VIEW.width,
  y: ((BOUNDS.latMax - lat) / (BOUNDS.latMax - BOUNDS.latMin)) * VIEW.height,
});

const round1 = (n) => Math.round(n * 10) / 10;
const round2 = (n) => Math.round(n * 100) / 100;

function haversine(a, b) {
  const R = 6371000;
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad;
  const h =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

/* ------------------------------------------------------------
 * 층 표기 유틸 (0층은 존재하지 않는다)
 * ---------------------------------------------------------- */
const floorIndex = (f) => (f > 0 ? f : f + 1);
const floorLabel = (f) => (f < 0 ? `B${-f}` : `${f}층`);
const floorToken = (f) => (f < 0 ? `b${-f}` : `${f}f`);

const FLOOR_HEIGHT_M = facts.elevation?.floorHeightM ?? 4.0;
const STEPS_PER_FLOOR = Math.round(FLOOR_HEIGHT_M / 0.17);

/**
 * 노드 하나가 '층 전체'를 뜻하기 때문에, 층 안에서 걸어다니는 거리를 엣지에 넣어야 한다.
 * 이 값이 너무 작으면 실내 경로가 비현실적으로 싸져서 바깥 길이 절대 선택되지 않는다.
 */
/** 계단실까지 걸어가는 거리 + 한 층 계단 자체 */
const STAIR_RUN_M = 20;
/** 엘리베이터까지 걸어가고 내려서 빠져나오는 거리 */
const ELEVATOR_ACCESS_M = 22;
/** 엘리베이터 이동 한 층당 */
const ELEVATOR_RUN_M = 2;
/** 연결통로까지 걸어가는 거리 + 통로 자체 */
const CONNECTION_M = 35;
/** 광장 등 실외 공간에서 건물 출입구까지. 출입구가 바로 앞이라 짧다. */
const PLAZA_ACCESS_M = 12;
const OUTDOOR_STEPS_FALLBACK = 18;
/** 보간 고도의 노이즈를 줄이기 위한 최소 기준거리 / 경사 상한 */
const SLOPE_MIN_RUN_M = 10;
const SLOPE_CAP = 0.35;

/* ============================================================
 * 1) 건물 · 동(wing)
 * ========================================================== */
const buildings = new Map();
for (const b of buildingRef.buildings) buildings.set(b.name, { ...b });

const wingsByBuilding = new Map();
for (const w of facts.wings ?? []) wingsByBuilding.set(w.building, w);

function floorRangeFor(buildingName, wingName) {
  const w = wingsByBuilding.get(buildingName);
  if (w && wingName && w.floorRanges?.[wingName]) return w.floorRanges[wingName];
  const fr = (facts.floorRanges ?? []).find((r) => r.building === buildingName);
  return fr ? { min: fr.min, max: fr.max } : null;
}

function wingsOf(buildingName) {
  const w = wingsByBuilding.get(buildingName);
  return w ? w.names : [null];
}

function wingSlug(buildingName, wingName) {
  if (!wingName) return null;
  return wingsByBuilding.get(buildingName)?.slugs?.[wingName] ?? wingName;
}

function indoorId(buildingName, wingName, floor) {
  const b = buildings.get(buildingName);
  if (!b) return null;
  const ws = wingSlug(buildingName, wingName);
  return ws ? `${b.slug}_${ws}_${floorToken(floor)}` : `${b.slug}_${floorToken(floor)}`;
}

function floorsOf(buildingName, wingName) {
  const range = floorRangeFor(buildingName, wingName);
  if (!range) return [];
  const out = [];
  for (let f = range.min; f <= range.max; f += 1) {
    if (f !== 0) out.push(f);
  }
  return out;
}

/* ============================================================
 * 2) 실외 보행 네트워크
 *    OSM 보행로 + campus-facts 의 outdoorAreas 를 하나로 합친다.
 *    노드 키는 문자열이다: OSM → "w<id>", 직접 추가 → "p_<area>_<node>"
 * ========================================================== */
const WALK_HIGHWAYS = new Set([
  'footway',
  'path',
  'steps',
  'pedestrian',
  'service',
  'living_street',
  'residential',
  'track',
  'corridor',
]);

/** 노드 키 → { x, y, label, manual } */
const netXY = new Map();
/** 엣지 목록 { a, b, distM, steps, stepCount, note } */
const netEdges = [];

/* --- 2-1. OSM --- */
const osmLL = new Map();
const osmEdges = [];

for (const el of osm.elements) {
  const tags = el.tags ?? {};
  if (!tags.highway || !WALK_HIGHWAYS.has(tags.highway)) continue;
  const ids = el.nodes;
  const geom = el.geometry;
  if (!Array.isArray(ids) || !Array.isArray(geom) || ids.length !== geom.length) continue;

  const isSteps = tags.highway === 'steps';
  const declared = Number(tags.step_count);
  const declaredOk = isSteps && Number.isFinite(declared) && declared > 0;
  const perEdge = declaredOk ? declared / (ids.length - 1) : isSteps ? OUTDOOR_STEPS_FALLBACK : 0;

  for (let i = 0; i < ids.length; i += 1) osmLL.set(ids[i], geom[i]);
  for (let i = 1; i < ids.length; i += 1) {
    const d = haversine(geom[i - 1], geom[i]);
    if (d <= 0) continue;
    osmEdges.push({
      a: ids[i - 1],
      b: ids[i],
      distM: d,
      steps: isSteps,
      stepCount: perEdge,
      note: isSteps ? (declaredOk ? 'OSM 계단' : 'OSM 계단 (칸수 추정)') : undefined,
    });
  }
}

/* 뷰박스 주변으로 자르고 최대 연결요소만 남긴다 */
const MARGIN = 70;
const inView = new Set();
for (const [id, ll] of osmLL) {
  const p = project(ll);
  if (p.x >= -MARGIN && p.x <= VIEW.width + MARGIN && p.y >= -MARGIN && p.y <= VIEW.height + MARGIN) {
    inView.add(id);
  }
}
let keptOsmEdges = osmEdges.filter((e) => inView.has(e.a) && inView.has(e.b));

const osmAdj = new Map();
for (const e of keptOsmEdges) {
  if (!osmAdj.has(e.a)) osmAdj.set(e.a, new Set());
  if (!osmAdj.has(e.b)) osmAdj.set(e.b, new Set());
  osmAdj.get(e.a).add(e.b);
  osmAdj.get(e.b).add(e.a);
}

function largestComponent(adj) {
  const seen = new Set();
  let best = new Set();
  for (const start of adj.keys()) {
    if (seen.has(start)) continue;
    const comp = new Set([start]);
    const stack = [start];
    seen.add(start);
    while (stack.length) {
      const cur = stack.pop();
      for (const n of adj.get(cur) ?? []) {
        if (comp.has(n)) continue;
        comp.add(n);
        seen.add(n);
        stack.push(n);
      }
    }
    if (comp.size > best.size) best = comp;
  }
  return best;
}

const osmComponent = largestComponent(osmAdj);
keptOsmEdges = keptOsmEdges.filter((e) => osmComponent.has(e.a) && osmComponent.has(e.b));

const osmKey = (id) => `w${id}`;
for (const id of osmComponent) {
  const p = project(osmLL.get(id));
  netXY.set(osmKey(id), { x: p.x, y: p.y, label: '실외 보행로', manual: false });
}
for (const e of keptOsmEdges) {
  netEdges.push({
    a: osmKey(e.a),
    b: osmKey(e.b),
    distM: e.distM,
    steps: e.steps,
    stepCount: e.stepCount,
    note: e.note,
  });
}

console.log(`OSM 보행로: 노드 ${netXY.size}, 엣지 ${netEdges.length}`);

/** OSM 노드 중 (x,y) 에 가장 가까운 것 */
function nearestOsmNode(x, y) {
  let best = null;
  let bestD = Infinity;
  for (const [key, p] of netXY) {
    if (p.manual) continue;
    const d = (p.x - x) ** 2 + (p.y - y) ** 2;
    if (d < bestD) {
      bestD = d;
      best = key;
    }
  }
  return { key: best, distUnits: Math.sqrt(bestD) };
}

/* --- 2-2. 직접 추가한 실외 공간 (광장 등) --- */
/** 노드 키 → 고도(층 단위). 명시된 것만. */
const manualElevation = new Map();
let manualNodeCount = 0;
let manualEdgeCount = 0;
/** { node, building, wing, floor } */
const buildingLinks = [];

const areaNodeKey = (areaId, nodeId) => `p_${areaId}_${nodeId}`;

for (const area of facts.outdoorAreas ?? []) {
  const declared = new Map();
  for (const n of area.nodes ?? []) {
    const key = areaNodeKey(area.id, n.id);
    netXY.set(key, { x: n.x, y: n.y, label: n.label ?? area.name, manual: true });
    declared.set(n.id, key);
    manualNodeCount += 1;
    if (typeof n.elevation === 'number') manualElevation.set(key, n.elevation);
    if (n.linkOsm) {
      const near = nearestOsmNode(n.x, n.y);
      if (near.key) {
        netEdges.push({
          a: key,
          b: near.key,
          distM: Math.max(2, near.distUnits * METERS_PER_UNIT),
          steps: false,
          stepCount: 0,
          note: `${area.name} ↔ 기존 보행로 연결`,
        });
        manualEdgeCount += 1;
      }
    }
  }

  for (const e of area.edges ?? []) {
    const a = declared.get(e.from);
    const b = declared.get(e.to);
    if (!a || !b) {
      console.warn(`[facts] outdoorAreas ${area.id}: 알 수 없는 노드 (${e.from} → ${e.to})`);
      continue;
    }
    const pa = netXY.get(a);
    const pb = netXY.get(b);
    const distM = Math.max(2, Math.hypot(pa.x - pb.x, pa.y - pb.y) * METERS_PER_UNIT);
    const steps = Number(e.steps) > 0;
    netEdges.push({
      a,
      b,
      distM,
      steps,
      stepCount: steps ? Number(e.steps) : 0,
      note: e.note ?? area.name,
    });
    manualEdgeCount += 1;
  }

  for (const link of area.buildingLinks ?? []) {
    const key = declared.get(link.node);
    if (!key) {
      console.warn(`[facts] outdoorAreas ${area.id}: buildingLinks 의 알 수 없는 노드 ${link.node}`);
      continue;
    }
    buildingLinks.push({ ...link, nodeKey: key, areaName: area.name });
  }
}

if (manualNodeCount > 0) {
  console.log(`직접 추가한 실외 노드 ${manualNodeCount}개, 엣지 ${manualEdgeCount}개`);
}

const netNodes = new Set(netXY.keys());
console.log(`실외 네트워크 합계: 노드 ${netNodes.size}, 엣지 ${netEdges.length}`);
if (netNodes.size < 20) throw new Error('실외 네트워크가 너무 작습니다.');

/** 전체 실외 네트워크에서 가장 가까운 노드 */
function nearestNetNode(x, y) {
  let best = null;
  let bestD = Infinity;
  for (const [key, p] of netXY) {
    const d = (p.x - x) ** 2 + (p.y - y) ** 2;
    if (d < bestD) {
      bestD = d;
      best = key;
    }
  }
  return { key: best, distUnits: Math.sqrt(bestD) };
}

/* ============================================================
 * 3) 실외 지형 고도 보간
 * ========================================================== */
const baseElevation = facts.elevation?.baseElevation ?? {};
const elevationOfKnown = (buildingName, floor) => {
  const base = baseElevation[buildingName];
  return base === undefined ? null : base + (floorIndex(floor) - 1);
};

const anchors = new Map();
const anchorReasons = [];
const anchorConflicts = [];

function addAnchor(nodeKey, elevation, why) {
  if (!nodeKey || elevation === null || elevation === undefined) return;
  const existing = anchors.get(nodeKey);
  if (existing !== undefined) {
    if (existing !== elevation) {
      anchorConflicts.push(
        `${nodeKey}: 이미 ${existing} 인데 ${elevation} 요청 (${why}) → 출입구 좌표를 분리해야 합니다`,
      );
    }
    return;
  }
  anchors.set(nodeKey, elevation);
  anchorReasons.push(`${nodeKey} = ${elevation} (${why})`);
}

// 3-1. 광장 등 직접 적은 고도
for (const [key, e] of manualElevation) {
  addAnchor(key, e, `광장 노드 ${netXY.get(key)?.label ?? key}`);
}

// 3-2. 명시적 앵커 (정문 등)
for (const a of facts.elevationAnchors ?? []) {
  if (typeof a.elevation !== 'number') continue;
  addAnchor(nearestNetNode(a.x, a.y).key, a.elevation, `앵커 ${a.name}`);
}

// 3-3. 지면층 고도가 알려진 건물의 출입 지점
const groundEntries = facts.groundEntries ?? [];
for (const g of groundEntries) {
  const b = buildings.get(g.building);
  if (!b) {
    console.warn(`[facts] groundEntries 의 알 수 없는 건물: ${g.building}`);
    continue;
  }
  const e = elevationOfKnown(g.building, g.floor);
  if (e === null) continue;
  addAnchor(
    nearestNetNode(g.x ?? b.x, g.y ?? b.y).key,
    e,
    `${g.building} ${floorLabel(g.floor)} 지면`,
  );
}

if (anchors.size < 2) throw new Error('고도 앵커가 2개 미만입니다.');

/* 라플라스 평활 */
const elev = new Map();
for (const key of netNodes) elev.set(key, 0);
for (const [key, v] of anchors) elev.set(key, v);

const neighbours = new Map();
for (const key of netNodes) neighbours.set(key, []);
for (const e of netEdges) {
  neighbours.get(e.a)?.push(e.b);
  neighbours.get(e.b)?.push(e.a);
}

for (let iter = 0; iter < 3000; iter += 1) {
  let maxDelta = 0;
  for (const key of netNodes) {
    if (anchors.has(key)) continue;
    const ns = neighbours.get(key);
    if (!ns || ns.length === 0) continue;
    let sum = 0;
    for (const n of ns) sum += elev.get(n);
    const next = sum / ns.length;
    maxDelta = Math.max(maxDelta, Math.abs(next - elev.get(key)));
    elev.set(key, next);
  }
  if (maxDelta < 1e-5) {
    console.log(`고도 보간 수렴: ${iter + 1}회`);
    break;
  }
}

const elevValues = [...elev.values()];
console.log(
  `고도 앵커 ${anchors.size}개 · 보간 범위 ${round2(Math.min(...elevValues))} ~ ${round2(
    Math.max(...elevValues),
  )} 층`,
);

/** baseElevation 이 없는 건물은 지형에서 역산 */
const derivedBase = {};
for (const g of groundEntries) {
  const b = buildings.get(g.building);
  if (!b || baseElevation[g.building] !== undefined || derivedBase[g.building] !== undefined) continue;
  const near = nearestNetNode(g.x ?? b.x, g.y ?? b.y);
  const terrain = elev.get(near.key);
  if (terrain === undefined) continue;
  derivedBase[g.building] = Math.round(terrain) - floorIndex(g.floor) + 1;
  console.log(
    `[고도 역산] ${g.building} baseElevation = ${derivedBase[g.building]} (지형 ${round2(
      terrain,
    )}, ${floorLabel(g.floor)} 출입구)`,
  );
}

const allBase = { ...baseElevation, ...derivedBase };

/* ============================================================
 * 4) 그래프 조립
 * ========================================================== */
const nodes = [];
const graphEdges = [];
const coords = {};
const nodeIds = new Set();

function addNode(node, x, y) {
  if (nodeIds.has(node.id)) return;
  nodeIds.add(node.id);
  nodes.push(node);
  coords[node.id] = { svg: '/maps/campus.svg', x: round1(x), y: round1(y) };
}

function addEdge(from, to, opts) {
  if (!nodeIds.has(from) || !nodeIds.has(to)) {
    console.warn(`[edge] 존재하지 않는 노드를 잇습니다: ${from} → ${to}`);
    return false;
  }
  graphEdges.push({
    from,
    to,
    distance: Math.max(1, Math.round(opts.distance)),
    stairsUp: Math.round(opts.stairsUp ?? 0),
    stairsDown: Math.round(opts.stairsDown ?? 0),
    slope: round2(opts.slope ?? 0),
    indoor: opts.indoor ?? false,
    elevator: opts.elevator ?? false,
    bidirectional: true,
    ...(opts.note ? { note: opts.note } : {}),
  });
  return true;
}

/* --- 4-1. 실외 노드 --- */
for (const [key, p] of netXY) {
  addNode(
    {
      id: key,
      building: 'OUTDOOR',
      floor: 0,
      label: p.label,
      kind: 'outdoor',
      searchable: false,
    },
    p.x,
    p.y,
  );
}

/* --- 4-2. 실외 엣지 --- */
let steepestSlope = 0;
let steepestNote = '';
/** 경사가 너무 급해서 '계단일 수밖에 없다'고 판단한 엣지 */
const impliedStairs = [];

for (const e of netEdges) {
  const riseM = (elev.get(e.b) - elev.get(e.a)) * FLOOR_HEIGHT_M;
  const rawSlope = Math.abs(riseM) / Math.max(e.distM, SLOPE_MIN_RUN_M);

  /**
   * OSM 에 계단 태그가 없어도, 고도차가 거리에 비해 너무 크면 실제로는 계단이다.
   * (예: 복지관 4층 출입구와 1층 출입구의 실외 접점이 13m 거리인데 고도차 12m)
   * 이걸 '완만한 경사'로 두면 무장애 경로가 물리적으로 불가능한 길을 타게 된다.
   */
  let steps = e.steps;
  let stepCount = e.stepCount;
  let note = e.note;
  if (!steps && rawSlope > SLOPE_CAP) {
    steps = true;
    stepCount = Math.max(1, Math.round(Math.abs(riseM) / 0.17));
    note = `경사 ${Math.round(rawSlope * 100)}% → 계단으로 판정 (OSM 미태깅, 칸수 추정)`;
    impliedStairs.push(`${e.a} → ${e.b} ${Math.round(e.distM)}m 고도차 ${round2(riseM)}m → ${stepCount}칸`);
  }

  // 계단 구간은 고도차를 '계단 칸수'로 이미 표현했다. 경사까지 매기면 이중 처벌이 된다.
  const slope = steps ? 0 : Math.min(rawSlope, SLOPE_CAP);
  if (slope > steepestSlope) {
    steepestSlope = slope;
    steepestNote = `${e.a} → ${e.b} (${Math.round(e.distM)}m, 고도차 ${round2(riseM)}m)`;
  }

  const stepTotal = steps ? Math.round(stepCount) : 0;
  addEdge(e.a, e.b, {
    distance: e.distM,
    stairsUp: riseM > 0 ? stepTotal : 0,
    stairsDown: riseM <= 0 ? stepTotal : 0,
    slope,
    indoor: false,
    note,
  });
}

/* --- 4-3. 건물 층 노드 --- */
function groundFloorOf(buildingName) {
  const hit = groundEntries.find((g) => g.building === buildingName);
  return hit ? hit.floor : 1;
}

function floorOffsetY(buildingName, floor) {
  const delta = floorIndex(floor) - floorIndex(groundFloorOf(buildingName));
  return Math.max(-38, Math.min(38, -delta * 4));
}

function wingOffsetX(buildingName, wingName) {
  const w = wingsByBuilding.get(buildingName);
  if (!w || !wingName) return 0;
  const idx = w.names.indexOf(wingName);
  if (idx < 0) return 0;
  return idx === 0 ? -34 : 34;
}

for (const [name, b] of buildings) {
  for (const wing of wingsOf(name)) {
    for (const f of floorsOf(name, wing)) {
      addNode(
        {
          id: indoorId(name, wing, f),
          building: name,
          floor: f,
          label: wing ? `${name} ${wing} ${floorLabel(f)}` : `${name} ${floorLabel(f)}`,
          kind: 'junction',
          searchable: true,
          aliases: [`${b.slug}${floorToken(f)}`, `${name}${floorLabel(f)}`],
        },
        b.x + wingOffsetX(name, wing),
        b.y + floorOffsetY(name, f),
      );
    }
  }
}

/* --- 4-4. 건물 내 계단 (인접 층) --- */
for (const [name] of buildings) {
  for (const wing of wingsOf(name)) {
    const floors = floorsOf(name, wing);
    for (let i = 1; i < floors.length; i += 1) {
      addEdge(indoorId(name, wing, floors[i - 1]), indoorId(name, wing, floors[i]), {
        distance: STAIR_RUN_M,
        stairsUp: STEPS_PER_FLOOR,
        indoor: true,
        note: `계단 (한 층 ${STEPS_PER_FLOOR}칸 추정)`,
      });
    }
  }
}

/* --- 4-5. 엘리베이터 (정차 층끼리 전부 직접 연결 → 대기 1회로 계산된다) --- */
let elevatorEdgeCount = 0;
for (const ev of facts.elevators ?? []) {
  if (!buildings.has(ev.building)) {
    console.warn(`[facts] 엘리베이터의 알 수 없는 건물: ${ev.building} (${ev.id})`);
    continue;
  }
  const served = (ev.servesFloors ?? []).filter((f) => {
    const id = indoorId(ev.building, ev.wing ?? null, f);
    return id && nodeIds.has(id);
  });
  for (let i = 0; i < served.length; i += 1) {
    for (let j = i + 1; j < served.length; j += 1) {
      const moved = Math.abs(floorIndex(served[j]) - floorIndex(served[i]));
      if (
        addEdge(
          indoorId(ev.building, ev.wing ?? null, served[i]),
          indoorId(ev.building, ev.wing ?? null, served[j]),
          {
            distance: ELEVATOR_ACCESS_M + ELEVATOR_RUN_M * moved,
            indoor: true,
            elevator: true,
            note: `${ev.id} (${ev.count}대, ${ev.location})`,
          },
        )
      ) {
        elevatorEdgeCount += 1;
      }
    }
  }
}

/* --- 4-6. 동(wing) 사이 연결 --- */
for (const w of facts.wings ?? []) {
  if (!buildings.has(w.building)) continue;
  const [left, right] = w.names;
  for (const f of w.connectedFloors ?? []) {
    const a = indoorId(w.building, left, f);
    const b = indoorId(w.building, right, f);
    if (!nodeIds.has(a) || !nodeIds.has(b)) continue;
    addEdge(a, b, { distance: 20, indoor: true, note: `${left} ↔ ${right} (${floorLabel(f)})` });
  }
}

/* --- 4-7. 건물 간 연결 --- */
let connectionEdgeCount = 0;
for (const c of facts.connections ?? []) {
  const aFloors = c.a?.floors ?? [];
  const bFloors = c.b?.floors ?? [];
  const pairs =
    c.pairing === 'same_floor'
      ? aFloors.map((f, i) => [f, bFloors[i] ?? f])
      : [[aFloors[0], bFloors[0]]];

  for (const [fa, fb] of pairs) {
    if (fa === undefined || fb === undefined) continue;
    const a = indoorId(c.a.building, c.a.wing ?? null, fa);
    const b = indoorId(c.b.building, c.b.wing ?? null, fb);
    if (!a || !b || !nodeIds.has(a) || !nodeIds.has(b)) {
      console.warn(`[facts] 연결 노드가 없습니다: ${c.id} (${a} ↔ ${b})`);
      continue;
    }
    if (addEdge(a, b, { distance: CONNECTION_M, indoor: c.indoor !== false, note: c.id })) {
      connectionEdgeCount += 1;
    }
  }
}

/* --- 4-8. 광장 ↔ 건물 층 --- */
let plazaLinkCount = 0;
for (const link of buildingLinks) {
  const indoor = indoorId(link.building, link.wing ?? null, link.floor);
  if (!indoor || !nodeIds.has(indoor)) {
    console.warn(
      `[facts] outdoorAreas buildingLinks: 층 노드가 없습니다 (${link.building} ${floorLabel(
        link.floor,
      )})`,
    );
    continue;
  }
  // 광장 노드는 건물 출입구 바로 앞에 찍은 것이다.
  // 건물 무게중심까지의 기하 거리를 쓰면 출입 비용이 과하게 커져서 바깥 길이 절대 안 뽑힌다.
  const distM = link.distanceM ?? PLAZA_ACCESS_M;
  if (
    addEdge(indoor, link.nodeKey, {
      distance: distM,
      indoor: false,
      note: `${link.areaName} 출입`,
    })
  ) {
    plazaLinkCount += 1;
  }
}

/* --- 4-9. 건물 ↔ 실외 (지면 출입구) --- */
let entryEdgeCount = 0;
for (const g of groundEntries) {
  const b = buildings.get(g.building);
  if (!b) continue;
  const indoor = indoorId(g.building, g.wing ?? null, g.floor);
  if (!indoor || !nodeIds.has(indoor)) {
    console.warn(`[facts] groundEntries 의 층 노드가 없습니다: ${g.building} ${floorLabel(g.floor)}`);
    continue;
  }
  const near = nearestNetNode(g.x ?? b.x, g.y ?? b.y);
  if (
    addEdge(indoor, near.key, {
      distance: Math.max(3, near.distUnits * METERS_PER_UNIT),
      indoor: false,
      note: `${g.to} 출입구`,
    })
  ) {
    entryEdgeCount += 1;
  }
}

/* --- 4-10. 정보 없는 건물도 최소한 접근 가능하게 ---
 * ⚠️ outdoorAreas 로 출입구를 지정한 건물은 절대 건드리면 안 된다.
 *    안 그러면 "가장 가까운 실외 노드"가 엉뚱한 높이의 길이어서
 *    1층이 5층 높이 길에 평지로 붙는 사고가 난다.
 */
const linkedBuildings = new Set(buildingLinks.map((l) => l.building));
let fallbackEntryCount = 0;
for (const [name, b] of buildings) {
  if (groundEntries.some((g) => g.building === name)) continue;
  if (linkedBuildings.has(name)) continue;
  let indoor = indoorId(name, null, 1);
  if (!indoor || !nodeIds.has(indoor)) {
    indoor = `${b.slug}_1f`;
    addNode(
      {
        id: indoor,
        building: name,
        floor: 1,
        label: `${name} 1층`,
        kind: 'entrance',
        searchable: true,
        aliases: [`${b.slug}1f`, `${name}1층`],
      },
      b.x,
      b.y,
    );
  }
  const near = nearestNetNode(b.x, b.y);
  if (
    addEdge(indoor, near.key, {
      distance: Math.max(3, near.distUnits * METERS_PER_UNIT),
      indoor: false,
      note: '출입구 위치 미확인 (건물 중심 기준)',
    })
  ) {
    fallbackEntryCount += 1;
  }
}

/* ============================================================
 * 5) 저장
 * ========================================================== */
const graph = {
  _readme: [
    'tools/build-graph.mjs 가 생성한 파일입니다. 직접 수정하지 마세요.',
    '고치려면 data/campus-facts.json 을 고치고 npm run build:graph 를 다시 돌리세요.',
    '',
    '실외 보행로·거리·계단 위치: © OpenStreetMap contributors (ODbL)',
    '층간 연결·엘리베이터·고도·광장: 학생 제보 (data/campus-facts.json)',
    `경사는 제보된 층 높이를 앵커로 보간한 추정값입니다. 층고 ${FLOOR_HEIGHT_M}m 가정.`,
  ],
  version: `0.4.0-r${facts.revision ?? 0}`,
  assumptions: {
    floorHeightM: FLOOR_HEIGHT_M,
    stepsPerFloor: STEPS_PER_FLOOR,
    stairRunM: STAIR_RUN_M,
    elevatorAccessM: ELEVATOR_ACCESS_M,
    elevatorRunM: ELEVATOR_RUN_M,
    connectionM: CONNECTION_M,
    plazaAccessM: PLAZA_ACCESS_M,
    outdoorStepsFallback: OUTDOOR_STEPS_FALLBACK,
    slopeMinRunM: SLOPE_MIN_RUN_M,
    slopeCap: SLOPE_CAP,
  },
  baseElevation: allBase,
  buildings: [...buildings.values()].map((b) => {
    const range = floorRangeFor(b.name, null);
    return {
      id: b.slug,
      name: b.name,
      floors: range
        ? Array.from({ length: range.max - range.min + 1 }, (_, i) => range.min + i).filter(
            (f) => f !== 0,
          )
        : [1],
    };
  }),
  nodes,
  edges: graphEdges,
};

writeFileSync(resolve(ROOT, 'data/campus-graph.json'), `${JSON.stringify(graph)}\n`, 'utf8');
writeFileSync(
  resolve(ROOT, 'data/graph-coords.json'),
  `${JSON.stringify({
    _readme: [
      'tools/build-graph.mjs 가 생성한 파일입니다. 직접 수정하지 마세요.',
      'campus-graph.json 의 모든 노드 → campus.svg 좌표.',
      '건물 내부 층 노드는 실제 도면이 없어서 건물 무게중심에서 층수만큼 위/아래로 밀어 놓았습니다.',
    ],
    coords,
  })}\n`,
  'utf8',
);

/* ============================================================
 * 6) 요약 + 자체 점검
 * ========================================================== */
const searchable = nodes.filter((n) => n.searchable);
const indoorEdges = graphEdges.filter((e) => e.indoor);
const stairEdges = graphEdges.filter((e) => e.stairsUp > 0 || e.stairsDown > 0);
const steepEdges = graphEdges.filter((e) => e.slope >= 0.15);

console.log('');
console.log(`노드 ${nodes.length} (검색 가능 ${searchable.length})`);
console.log(
  `엣지 ${graphEdges.length} — 실내 ${indoorEdges.length} / 계단 ${stairEdges.length} / 엘리베이터 ${elevatorEdgeCount}`,
);
console.log(
  `건물간 연결 ${connectionEdgeCount} · 광장 출입 ${plazaLinkCount} · 지면 출입 ${entryEdgeCount} · 출입구 미확인 ${fallbackEntryCount}`,
);
console.log(
  `경사 15% 이상 실외 엣지 ${steepEdges.length}개 · 최대 경사 ${Math.round(steepestSlope * 100)}%`,
);
console.log(`  최대 경사 구간: ${steepestNote}`);
if (impliedStairs.length > 0) {
  console.log('');
  console.log(`경사가 너무 급해 계단으로 판정한 실외 구간 ${impliedStairs.length}개:`);
  for (const s of impliedStairs) console.log(`  ${s}`);
}
console.log('');
console.log(`고도 앵커 ${anchorReasons.length}개:`);
for (const r of anchorReasons) console.log(`  ${r}`);
if (anchorConflicts.length > 0) {
  console.log('');
  console.log(`앵커 충돌 ${anchorConflicts.length}건:`);
  for (const c of anchorConflicts) console.log(`  ${c}`);
}

/* 연결성 점검 */
const undirected = new Map();
for (const n of nodes) undirected.set(n.id, []);
for (const e of graphEdges) {
  undirected.get(e.from)?.push(e.to);
  undirected.get(e.to)?.push(e.from);
}
const seen = new Set();
const components = [];
for (const n of nodes) {
  if (seen.has(n.id)) continue;
  const comp = [n.id];
  seen.add(n.id);
  const stack = [n.id];
  while (stack.length) {
    const cur = stack.pop();
    for (const nx of undirected.get(cur) ?? []) {
      if (seen.has(nx)) continue;
      seen.add(nx);
      comp.push(nx);
      stack.push(nx);
    }
  }
  components.push(comp);
}
const biggest = Math.max(...components.map((c) => c.length));

console.log('');
if (components.length === 1) {
  console.log('연결성: 전체 그래프가 하나로 이어져 있습니다.');
} else {
  console.log(`연결성: ${components.length}개 컴포넌트 (최대 ${biggest}개 노드)`);
  for (const c of components.filter((x) => x.length < biggest)) {
    console.log(`  고립 ${c.length}개: ${c.slice(0, 8).join(', ')}${c.length > 8 ? ' …' : ''}`);
  }
}
