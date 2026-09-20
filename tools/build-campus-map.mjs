/**
 * ============================================================
 *  campus.svg + walk-network.json 생성기
 * ============================================================
 *  실행: node tools/build-campus-map.mjs
 *
 *  무엇을 하는가
 *   1. Overpass API 에서 국민대 캠퍼스의 건물 폴리곤 / 보행로 / 계단 / 운동장을 받아온다
 *   2. 위경도를 등거리 원통도법으로 SVG 좌표(1000x700)로 투영한다
 *   3. 보행로를 "걸어갈 수 있는 그래프"로 만들고, 건물 간 최단경로를 미리 계산한다
 *      → data/walk-network.json  (경로가 직선이 아니라 실제 인도를 따라가게 하는 핵심)
 *      → 계단 회피 경로도 따로 계산한다 (계단최소 / 무장애 모드용)
 *   4. data/campus-facts.json (사람이 적은 층간 연결·엘리베이터 제보)을 읽어 지도에 얹는다
 *   5. public/maps/campus.svg 를 다시 그린다
 *
 *  데이터 출처: © OpenStreetMap contributors, ODbL
 *  층간 연결 / 엘리베이터 / 경사는 OSM 에 없다 → data/campus-facts.json 에서 온다.
 * ============================================================
 */

import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

/* ------------------------------------------------------------
 * 투영 설정 — 바꾸면 data/coords.json 의 기존 좌표가 전부 어긋난다
 * ---------------------------------------------------------- */
const VIEW = { width: 1000, height: 700 };
const BOUNDS = { lonMin: 126.9929, lonMax: 126.9999, latMin: 37.60922, latMax: 37.61311 };

const M_PER_DEG_LON = 111320 * Math.cos((37.611 * Math.PI) / 180);
const METERS_PER_UNIT_X = ((BOUNDS.lonMax - BOUNDS.lonMin) * M_PER_DEG_LON) / VIEW.width;

const project = ({ lat, lon }) => ({
  x: ((lon - BOUNDS.lonMin) / (BOUNDS.lonMax - BOUNDS.lonMin)) * VIEW.width,
  y: ((BOUNDS.latMax - lat) / (BOUNDS.latMax - BOUNDS.latMin)) * VIEW.height,
});

const round = (n) => Math.round(n * 10) / 10;

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

const floorLabel = (n) => (n < 0 ? `B${-n}` : `${n}F`);

/* ------------------------------------------------------------
 * 국민대 건물 화이트리스트 (bbox 안에 인근 빌라/고교가 섞여 있어서)
 * ---------------------------------------------------------- */
const KMU_BUILDINGS = {
  성곡도서관: { slug: 'library', short: '성곡도서관', kind: 'facility' },
  '글로벌 센터': { slug: 'global', short: '글로벌센터', kind: 'academic' },
  북악관: { slug: 'bukak', short: '북악관', kind: 'academic' },
  조형관: { slug: 'johyung', short: '조형관', kind: 'academic' },
  산학협력관: { slug: 'iprc', short: '산학협력관', kind: 'academic' },
  공학관: { slug: 'engineering', short: '공학관', kind: 'academic' },
  본부관: { slug: 'hq', short: '본부관', kind: 'admin' },
  과학관: { slug: 'science', short: '과학관', kind: 'academic' },
  경상관: { slug: 'econ', short: '경상관', kind: 'academic' },
  법학관: { slug: 'law', short: '법학관', kind: 'academic' },
  국제관: { slug: 'intl', short: '국제관', kind: 'academic' },
  체육관: { slug: 'gym', short: '체육관', kind: 'facility' },
  콘서트홀: { slug: 'concert', short: '콘서트홀', kind: 'facility' },
  경영관: { slug: 'biz', short: '경영관', kind: 'academic' },
  종합복지관: { slug: 'welfare', short: '복지관', kind: 'facility' },
  예술관: { slug: 'art', short: '예술관', kind: 'academic' },
  미래관: { slug: 'mirae', short: '미래관', kind: 'academic' },
  평생교육실기관: { slug: 'lifelong', short: '평생교육실기관', kind: 'academic' },
  생활관: { slug: 'dorm', short: '생활관', kind: 'dorm' },
  '생활관 D': { slug: 'dorm_d', short: '생활관D', kind: 'dorm' },
  영빈관: { slug: 'guest', short: '영빈관', kind: 'facility' },
};

const FILL = {
  academic: '#ffffff',
  admin: '#fefce8',
  facility: '#f1f5f9',
  dorm: '#f5f3ff',
};

const LABEL_OFFSET = {
  조형관: { dx: 34, dy: -16 },
  북악관: { dx: -12, dy: -12 },
  본부관: { dx: 10, dy: 12 },
  국제관: { dx: -6, dy: 10 },
  콘서트홀: { dx: -4, dy: 22 },
  경상관: { dx: -8, dy: -6 },
  공학관: { dx: 6, dy: 4 },
  산학협력관: { dx: -20, dy: 18 },
  '글로벌 센터': { dx: 0, dy: -10 },
  성곡도서관: { dx: 0, dy: 6 },
  영빈관: { dx: 22, dy: 10 },
  '생활관 D': { dx: 26, dy: -8 },
  법학관: { dx: 14, dy: 8 },
  체육관: { dx: 2, dy: 6 },
};

/* ------------------------------------------------------------
 * Overpass
 * ---------------------------------------------------------- */
const BBOX = '37.6086,126.9922,37.6136,127.0002';

const WALK_HIGHWAYS = [
  'footway',
  'path',
  'steps',
  'pedestrian',
  'service',
  'living_street',
  'residential',
  'track',
  'corridor',
];

const QUERY = `[out:json][timeout:90];
(
  nwr["building"]["name"](${BBOX});
  way["highway"](${BBOX});
  nwr["leisure"~"^(pitch|track|stadium|sports_centre)$"](${BBOX});
);
out geom;`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * Overpass 응답 캐시.
 * 공용 서버가 자주 504/429 를 내기 때문에 한 번 받으면 파일로 남긴다.
 * 최신 데이터를 다시 받으려면: KMU_REFRESH=1 node tools/build-campus-map.mjs
 */
const CACHE_PATH = resolve(ROOT, 'tools/osm-cache.json');

async function overpass() {
  if (process.env.KMU_REFRESH !== '1') {
    try {
      const cached = JSON.parse(readFileSync(CACHE_PATH, 'utf8'));
      if (Array.isArray(cached.elements) && cached.elements.length > 0) {
        console.log(`[overpass] 캐시 사용 (elements ${cached.elements.length}) — 갱신은 KMU_REFRESH=1`);
        return cached;
      }
    } catch {
      /* 캐시 없음 → 네트워크로 */
    }
  }

  const endpoints = [
    'https://overpass-api.de/api/interpreter',
    'https://overpass.kumi.systems/api/interpreter',
    'https://overpass.private.coffee/api/interpreter',
  ];

  let lastError;
  for (let attempt = 1; attempt <= 4; attempt += 1) {
    for (const base of endpoints) {
      try {
        const res = await fetch(`${base}?data=${encodeURIComponent(QUERY)}`, {
          headers: { Accept: 'application/json', 'User-Agent': 'kmu-wayfinder/0.1 (hackathon)' },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!Array.isArray(json.elements) || json.elements.length === 0) {
          throw new Error('elements 가 비어 있음');
        }
        console.log(`[overpass] ${base} OK (elements ${json.elements.length})`);
        writeFileSync(CACHE_PATH, `${JSON.stringify(json)}\n`, 'utf8');
        return json;
      } catch (e) {
        lastError = e;
        console.warn(`[overpass] ${base} 실패: ${e.message}`);
      }
    }
    if (attempt < 4) {
      const wait = attempt * 10000;
      console.warn(`[overpass] ${wait / 1000}초 대기 후 재시도 (${attempt}/3)`);
      await sleep(wait);
    }
  }
  throw lastError;
}

/* ------------------------------------------------------------
 * 멀티폴리곤 조각 이어붙이기 (미래관이 4개 way 로 쪼개져 있다)
 * ---------------------------------------------------------- */
function stitchRings(parts) {
  const remaining = parts.map((p) => [...p]);
  const rings = [];
  const key = (p) => `${p.lat.toFixed(7)},${p.lon.toFixed(7)}`;

  while (remaining.length > 0) {
    let ring = remaining.shift();
    let extended = true;
    while (extended) {
      extended = false;
      for (let i = 0; i < remaining.length; i += 1) {
        const seg = remaining[i];
        const rs = key(ring[0]);
        const re = key(ring[ring.length - 1]);
        const ss = key(seg[0]);
        const se = key(seg[seg.length - 1]);
        if (re === ss) ring = ring.concat(seg.slice(1));
        else if (re === se) ring = ring.concat([...seg].reverse().slice(1));
        else if (rs === se) ring = seg.slice(0, -1).concat(ring);
        else if (rs === ss) ring = [...seg].reverse().slice(0, -1).concat(ring);
        else continue;
        remaining.splice(i, 1);
        extended = true;
        break;
      }
    }
    rings.push(ring);
  }
  return rings;
}

function centroid(points) {
  let area = 0;
  let cx = 0;
  let cy = 0;
  for (let i = 0; i < points.length; i += 1) {
    const a = points[i];
    const b = points[(i + 1) % points.length];
    const cross = a.x * b.y - b.x * a.y;
    area += cross;
    cx += (a.x + b.x) * cross;
    cy += (a.y + b.y) * cross;
  }
  if (Math.abs(area) < 1e-9) {
    return {
      x: points.reduce((s, p) => s + p.x, 0) / points.length,
      y: points.reduce((s, p) => s + p.y, 0) / points.length,
    };
  }
  area *= 0.5;
  return { x: cx / (6 * area), y: cy / (6 * area) };
}

const toPath = (pts) =>
  `${pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${round(p.x)} ${round(p.y)}`).join(' ')} Z`;
const toPolyline = (pts) =>
  pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${round(p.x)} ${round(p.y)}`).join(' ');
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/* ============================================================
 * 1) 데이터 수집
 * ========================================================== */
const data = await overpass();

const buildings = [];
const roads = [];
const stepWays = [];
const fields = [];

/** OSM 노드 id → 위경도 */
const nodeLL = new Map();
/** OSM 노드 id → [{to, dist, steps, stepCount}] */
const adj = new Map();

function addEdge(a, b, dist, steps, stepCount) {
  if (!adj.has(a)) adj.set(a, []);
  if (!adj.has(b)) adj.set(b, []);
  adj.get(a).push({ to: b, dist, steps, stepCount });
  adj.get(b).push({ to: a, dist, steps, stepCount });
}

for (const el of data.elements) {
  const tags = el.tags ?? {};
  const name = tags.name;

  if (tags.building) {
    if (!name || !KMU_BUILDINGS[name]) continue;
    const meta = KMU_BUILDINGS[name];
    let rings;
    if (el.type === 'relation') {
      const outers = (el.members ?? [])
        .filter((m) => m.role === 'outer' && Array.isArray(m.geometry))
        .map((m) => m.geometry);
      rings = stitchRings(outers);
    } else {
      rings = [el.geometry ?? []];
    }
    const projected = rings.map((r) => r.filter(Boolean).map(project)).filter((r) => r.length >= 3);
    if (projected.length === 0) continue;
    const biggest = projected.reduce((a, b) => (b.length > a.length ? b : a));
    buildings.push({
      name,
      ...meta,
      levels: tags['building:levels'] ? Number(tags['building:levels']) : null,
      rings: projected,
      center: centroid(biggest),
    });
    continue;
  }

  if (tags.leisure && Array.isArray(el.geometry) && el.geometry.length >= 3) {
    const pts = el.geometry.map(project);
    const inside = pts.some((p) => p.x > 0 && p.x < VIEW.width && p.y > 0 && p.y < VIEW.height);
    if (inside) fields.push({ pts, name: name ?? null, center: centroid(pts) });
    continue;
  }

  if (tags.highway && Array.isArray(el.geometry)) {
    const pts = el.geometry.map(project);
    const visible = pts.some(
      (p) => p.x > -40 && p.x < VIEW.width + 40 && p.y > -40 && p.y < VIEW.height + 40,
    );
    if (visible && pts.length >= 2) {
      const bucket = tags.highway === 'steps' ? stepWays : roads;
      bucket.push({ pts, highway: tags.highway, name: name ?? null });
    }

    // 보행 그래프 구성
    if (!WALK_HIGHWAYS.includes(tags.highway)) continue;
    const ids = el.nodes;
    const geom = el.geometry;
    if (!Array.isArray(ids) || !Array.isArray(geom) || ids.length !== geom.length) continue;

    const isSteps = tags.highway === 'steps';
    const declared = Number(tags.step_count);
    const perEdgeSteps =
      isSteps && Number.isFinite(declared) && declared > 0 ? declared / (ids.length - 1) : 0;

    for (let i = 0; i < ids.length; i += 1) nodeLL.set(ids[i], geom[i]);
    for (let i = 1; i < ids.length; i += 1) {
      const d = haversine(geom[i - 1], geom[i]);
      if (d === 0) continue;
      addEdge(ids[i - 1], ids[i], d, isSteps, perEdgeSteps);
    }
  }
}

buildings.sort((a, b) => a.center.y - b.center.y);
if (buildings.length === 0) throw new Error('건물을 하나도 못 받았습니다.');

/* ============================================================
 * 2) 보행 네트워크 정리 — 뷰박스 주변으로 자르고 최대 연결요소만 남긴다
 * ========================================================== */
const MARGIN = 70;
const keep = new Set();
for (const [id, ll] of nodeLL) {
  const p = project(ll);
  if (p.x >= -MARGIN && p.x <= VIEW.width + MARGIN && p.y >= -MARGIN && p.y <= VIEW.height + MARGIN) {
    keep.add(id);
  }
}

/** 잘라낸 뒤의 인접 리스트 */
const graph = new Map();
for (const id of keep) {
  const edges = (adj.get(id) ?? []).filter((e) => keep.has(e.to));
  graph.set(id, edges);
}

// 최대 연결요소
function largestComponent() {
  const seen = new Set();
  let best = new Set();
  for (const start of graph.keys()) {
    if (seen.has(start)) continue;
    const comp = new Set([start]);
    const stack = [start];
    seen.add(start);
    while (stack.length) {
      const cur = stack.pop();
      for (const e of graph.get(cur) ?? []) {
        if (comp.has(e.to)) continue;
        comp.add(e.to);
        seen.add(e.to);
        stack.push(e.to);
      }
    }
    if (comp.size > best.size) best = comp;
  }
  return best;
}

const component = largestComponent();
for (const id of [...graph.keys()]) if (!component.has(id)) graph.delete(id);
for (const [id, edges] of graph) graph.set(id, edges.filter((e) => component.has(e.to)));

console.log(`보행 네트워크: 노드 ${graph.size}개`);
if (graph.size < 20) throw new Error('보행 네트워크가 너무 작습니다. WALK_HIGHWAYS 를 확인하세요.');

/* --- 건물별 접속 노드: 무게중심에서 가장 가까운 네트워크 노드 --- */
const nodeXY = new Map();
for (const id of graph.keys()) nodeXY.set(id, project(nodeLL.get(id)));

for (const b of buildings) {
  let bestId = null;
  let bestD = Infinity;
  for (const [id, p] of nodeXY) {
    const d = (p.x - b.center.x) ** 2 + (p.y - b.center.y) ** 2;
    if (d < bestD) {
      bestD = d;
      bestId = id;
    }
  }
  b.accessNode = bestId;
  b.accessDistUnits = round(Math.sqrt(bestD));
}

/* ============================================================
 * 3) 최단경로 미리 계산 (일반 / 계단 회피)
 * ========================================================== */
function dijkstra(sourceId, { avoidSteps }) {
  const dist = new Map([[sourceId, 0]]);
  const prev = new Map();
  const visited = new Set();
  // 노드 수가 수백 개라 단순 선형 탐색으로 충분하다
  const pending = new Set([sourceId]);

  while (pending.size) {
    let cur = null;
    let curD = Infinity;
    for (const id of pending) {
      const d = dist.get(id) ?? Infinity;
      if (d < curD) {
        curD = d;
        cur = id;
      }
    }
    if (cur === null) break;
    pending.delete(cur);
    visited.add(cur);

    for (const e of graph.get(cur) ?? []) {
      if (avoidSteps && e.steps) continue;
      if (visited.has(e.to)) continue;
      const nd = curD + e.dist;
      if (nd < (dist.get(e.to) ?? Infinity)) {
        dist.set(e.to, nd);
        prev.set(e.to, cur);
        pending.add(e.to);
      }
    }
  }
  return { dist, prev };
}

function tracePath(prev, sourceId, targetId) {
  const out = [targetId];
  let cur = targetId;
  while (cur !== sourceId) {
    const p = prev.get(cur);
    if (p === undefined) return null;
    out.push(p);
    cur = p;
  }
  return out.reverse();
}

function measure(pathIds) {
  let d = 0;
  let stepEdges = 0;
  let stepCount = 0;
  /** 계단 구간의 위치. i 는 pathIds[i] → pathIds[i+1] 엣지를 뜻한다. */
  const sx = [];
  for (let i = 1; i < pathIds.length; i += 1) {
    const e = (graph.get(pathIds[i - 1]) ?? []).find((x) => x.to === pathIds[i]);
    if (!e) continue;
    d += e.dist;
    if (e.steps) {
      stepEdges += 1;
      stepCount += e.stepCount;
      sx.push(i - 1);
    }
  }
  return { d: Math.round(d), st: stepEdges, stc: Math.round(stepCount), sx };
}

/* --- 경로에 등장하는 노드만 골라 인덱스를 부여한다 (파일 크기 절약) --- */
const usedNodes = new Set();
const rawPaths = new Map();

const routable = buildings.filter((b) => b.accessNode);

for (const from of routable) {
  const normal = dijkstra(from.accessNode, { avoidSteps: false });
  const flat = dijkstra(from.accessNode, { avoidSteps: true });

  for (const to of routable) {
    if (to.slug === from.slug) continue;
    const key = [`out_${from.slug}`, `out_${to.slug}`].sort().join('|');
    if (rawPaths.has(key)) continue;

    const fastIds = tracePath(normal.prev, from.accessNode, to.accessNode);
    if (!fastIds) continue;
    const flatIds = tracePath(flat.prev, from.accessNode, to.accessNode);

    const entry = {
      a: `out_${from.slug}`,
      b: `out_${to.slug}`,
      fast: { ids: fastIds, ...measure(fastIds) },
      flat: flatIds ? { ids: flatIds, ...measure(flatIds) } : null,
    };
    rawPaths.set(key, entry);
    fastIds.forEach((id) => usedNodes.add(id));
    flatIds?.forEach((id) => usedNodes.add(id));
  }
}

const nodeList = [...usedNodes];
const nodeIndex = new Map(nodeList.map((id, i) => [id, i]));

const walkNetwork = {
  _readme: [
    'tools/build-campus-map.mjs 가 생성한 파일입니다. 직접 수정하지 마세요.',
    'OSM 보행로(footway/path/steps/service 등)로 만든 실제 도보 네트워크입니다.',
    'nodes: 인덱스 → campus.svg 좌표 [x, y]. 경로에서의 노드 ID 는 "w<인덱스>" 입니다.',
    'paths["A|B"].fast = 최단 경로, .flat = 계단을 전혀 쓰지 않는 경로(없으면 null)',
    'd = 거리(m), st = 통과한 계단 구간 수, stc = OSM step_count 합계(0이면 미상)',
    'sx = 계단 구간의 위치. 값 i 는 n[i] → n[i+1] 구간이 계단이라는 뜻.',
    '출처: © OpenStreetMap contributors (ODbL)',
  ],
  viewBox: VIEW,
  nodes: nodeList.map((id) => {
    const p = nodeXY.get(id);
    return [round(p.x), round(p.y)];
  }),
  access: Object.fromEntries(routable.map((b) => [`out_${b.slug}`, nodeIndex.get(b.accessNode)])),
  /** 건물 무게중심 → 접속 보행로 노드까지의 거리(m). 경로 총거리에 더해야 한다. */
  accessDistM: Object.fromEntries(
    routable.map((b) => [
      `out_${b.slug}`,
      Math.round((b.accessDistUnits ?? 0) * METERS_PER_UNIT_X),
    ]),
  ),
  paths: Object.fromEntries(
    [...rawPaths.entries()].map(([key, v]) => [
      key,
      {
        a: v.a,
        b: v.b,
        fast: {
          n: v.fast.ids.map((id) => nodeIndex.get(id)),
          d: v.fast.d,
          st: v.fast.st,
          stc: v.fast.stc,
          sx: v.fast.sx,
        },
        flat: v.flat
          ? { n: v.flat.ids.map((id) => nodeIndex.get(id)), d: v.flat.d, st: 0, stc: 0, sx: [] }
          : null,
      },
    ]),
  ),
};

mkdirSync(resolve(ROOT, 'data'), { recursive: true });
// 참고용. 실제 경로 탐색은 tools/build-graph.mjs 가 만드는 data/campus-graph.json 을 쓴다.
// 이 파일은 "건물쌍별 최단/계단회피 거리"를 눈으로 확인할 때만 쓴다. 앱은 import 하지 않는다.
writeFileSync(
  resolve(ROOT, 'tools/walk-pairs.generated.json'),
  `${JSON.stringify(walkNetwork)}\n`,
  'utf8',
);

/* ============================================================
 * 4) 제보 정보(campus-facts.json) 읽기
 * ========================================================== */
let facts = { elevators: [], connections: [], groundEntries: [] };
try {
  facts = JSON.parse(readFileSync(resolve(ROOT, 'data/campus-facts.json'), 'utf8'));
} catch (e) {
  console.warn(`[facts] data/campus-facts.json 을 읽지 못했습니다: ${e.message}`);
}

const byName = new Map(buildings.map((b) => [b.name, b]));

/** 건물별 엘리베이터 집계 */
const evByBuilding = new Map();
for (const ev of facts.elevators ?? []) {
  if (!byName.has(ev.building)) {
    console.warn(`[facts] 알 수 없는 건물: ${ev.building} (엘리베이터 ${ev.id})`);
    continue;
  }
  const cur = evByBuilding.get(ev.building) ?? { count: 0, min: Infinity, max: -Infinity, uncertain: false };
  cur.count += ev.count ?? 1;
  for (const f of ev.servesFloors ?? []) {
    cur.min = Math.min(cur.min, f);
    cur.max = Math.max(cur.max, f);
  }
  cur.uncertain = cur.uncertain || Boolean(ev.uncertain);
  evByBuilding.set(ev.building, cur);
}

/* ============================================================
 * 5) SVG 조립
 * ========================================================== */
const metersPerUnitX = METERS_PER_UNIT_X;
const scaleBarMeters = 100;
const scaleBarUnits = scaleBarMeters / metersPerUnitX;

const fieldLayer = fields
  .map(
    (f) =>
      `    <path d="${toPath(f.pts)}" fill="#dcece0" stroke="#bcd3c0" stroke-width="1.5" />`,
  )
  .join('\n');

const fieldLabels = fields
  .filter((f) => f.name)
  .map(
    (f) =>
      `    <text x="${round(f.center.x)}" y="${round(
        f.center.y,
      )}" font-size="11.5" font-weight="600" fill="#5f7a63" text-anchor="middle">${esc(f.name)}</text>`,
  )
  .join('\n');

const roadLayer = roads
  .map((r) => {
    const thin = ['footway', 'path', 'pedestrian', 'corridor'].includes(r.highway);
    return `    <path d="${toPolyline(r.pts)}" fill="none" stroke="#dde4ec" stroke-width="${
      thin ? 7 : 13
    }" stroke-linecap="round" stroke-linejoin="round" />`;
  })
  .join('\n');

const roadCenterLine = roads
  .filter((r) => !['footway', 'path', 'pedestrian', 'corridor'].includes(r.highway))
  .map(
    (r) =>
      `    <path d="${toPolyline(
        r.pts,
      )}" fill="none" stroke="#f4f7fa" stroke-width="2.5" stroke-dasharray="9 11" stroke-linecap="round" />`,
  )
  .join('\n');

const stepsLayer = stepWays
  .map(
    (s) =>
      `    <path d="${toPolyline(
        s.pts,
      )}" fill="none" stroke="#a78bfa" stroke-width="7" stroke-linecap="round" />
    <path d="${toPolyline(
      s.pts,
    )}" fill="none" stroke="#ffffff" stroke-width="7" stroke-dasharray="1.5 4" stroke-linecap="butt" />`,
  )
  .join('\n');

const buildingLayer = buildings
  .map(
    (b) =>
      `    <path id="bld-${b.slug}" d="${b.rings
        .map(toPath)
        .join(' ')}" fill="${FILL[b.kind]}" stroke="#8fa0b4" stroke-width="2" stroke-linejoin="round" />`,
  )
  .join('\n');

/**
 * 층 목록을 짧은 라벨로.
 *  연속이고 3개 이상 → "1F~4F", 그 외 → "1F·5F"
 *  0층이 없으므로 B1(-1) 다음은 1F(1) 을 연속으로 취급한다.
 */
function labelForFloors(floors) {
  const sorted = [...floors].sort((a, b) => a - b);
  const isNext = (prev, cur) => cur === prev + 1 || (prev === -1 && cur === 1);
  const contiguous = sorted.every((f, i) => i === 0 || isNext(sorted[i - 1], f));
  if (sorted.length > 2 && contiguous) {
    return `${floorLabel(sorted[0])}~${floorLabel(sorted[sorted.length - 1])}`;
  }
  return sorted.map(floorLabel).join('·');
}

/* --- 건물 간 연결선 --- */
const connectionLayer = (facts.connections ?? [])
  .map((c) => {
    const A = byName.get(c.a?.building);
    const B = byName.get(c.b?.building);
    if (!A || !B) {
      console.warn(`[facts] 연결선을 그릴 수 없음: ${c.id} (${c.a?.building} ↔ ${c.b?.building})`);
      return null;
    }
    const mx = (A.center.x + B.center.x) / 2;
    const my = (A.center.y + B.center.y) / 2;

    const aFloors = c.a.floors ?? [];
    const bFloors = c.b.floors ?? [];
    let label;
    if (c.pairing === 'same_floor') {
      label = labelForFloors(aFloors);
    } else {
      label = `${floorLabel(aFloors[0])} ↔ ${floorLabel(bFloors[0])}`;
    }
    if (c.uncertain) label += ' ?';

    const stroke = c.uncertain ? '#f59e0b' : '#059669';
    const w = Math.max(44, label.length * 6.6 + 14);

    return `    <g>
      <path d="M${round(A.center.x)} ${round(A.center.y)} L${round(B.center.x)} ${round(
      B.center.y,
    )}" fill="none" stroke="${stroke}" stroke-width="6" stroke-linecap="round" opacity="0.42" />
      <rect x="${round(mx - w / 2)}" y="${round(
      my - 9,
    )}" width="${round(w)}" height="18" rx="9" fill="#ffffff" fill-opacity="0.94" stroke="${stroke}" stroke-width="1.5" />
      <text x="${round(mx)}" y="${round(
      my + 4.5,
    )}" font-size="10.5" font-weight="700" fill="${stroke}" text-anchor="middle">${esc(label)}</text>
    </g>`;
  })
  .filter(Boolean)
  .join('\n');

/* --- 직접 추가한 실외 공간 (광장 등) --- */
const plazaLayer = (facts.outdoorAreas ?? [])
  .map((area) => {
    const byId = new Map((area.nodes ?? []).map((n) => [n.id, n]));
    const parts = [];

    for (const e of area.edges ?? []) {
      const a = byId.get(e.from);
      const b = byId.get(e.to);
      if (!a || !b) continue;
      const isSteps = Number(e.steps) > 0;
      const d = `M${round(a.x)} ${round(a.y)} L${round(b.x)} ${round(b.y)}`;
      if (isSteps) {
        parts.push(
          `      <path d="${d}" fill="none" stroke="#a78bfa" stroke-width="9" stroke-linecap="round" />
      <path d="${d}" fill="none" stroke="#ffffff" stroke-width="9" stroke-dasharray="1.5 4" />`,
        );
      } else {
        parts.push(
          `      <path d="${d}" fill="none" stroke="#e3e9f0" stroke-width="11" stroke-linecap="round" />`,
        );
      }
    }

    // 계단 라벨
    for (const e of area.edges ?? []) {
      if (!(Number(e.steps) > 0)) continue;
      const a = byId.get(e.from);
      const b = byId.get(e.to);
      if (!a || !b) continue;
      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      const text = `계단 ${e.steps}칸`;
      const w = text.length * 6.2 + 12;
      parts.push(`      <g>
        <rect x="${round(mx - w / 2)}" y="${round(
        my - 22,
      )}" width="${round(w)}" height="16" rx="8" fill="#f5f3ff" stroke="#a78bfa" stroke-width="1.2" />
        <text x="${round(mx)}" y="${round(
        my - 10,
      )}" font-size="9.5" font-weight="700" fill="#6d28d9" text-anchor="middle">${esc(text)}</text>
      </g>`);
    }

    // 광장 이름
    const xs = (area.nodes ?? []).map((n) => n.x);
    const ys = (area.nodes ?? []).map((n) => n.y);
    if (xs.length > 0) {
      const cx = xs.reduce((s, v) => s + v, 0) / xs.length;
      const cy = ys.reduce((s, v) => s + v, 0) / ys.length;
      parts.push(
        `      <text x="${round(cx)}" y="${round(
          cy - 30,
        )}" font-size="10.5" font-weight="700" fill="#64748b" text-anchor="middle"
              stroke="#ffffff" stroke-width="3" paint-order="stroke">자유 통행 공간</text>`,
      );
    }

    return `    <g>\n${parts.join('\n')}\n    </g>`;
  })
  .join('\n');

/* --- 동(wing) 경계선 --- */
const wingLayer = (facts.wings ?? [])
  .map((w) => {
    const b = byName.get(w.building);
    if (!b || typeof w.dividerX !== 'number') return null;
    const ys = b.rings.flat().map((p) => p.y);
    const top = Math.min(...ys) - 3;
    const bottom = Math.max(...ys) + 3;
    // 건물 이름 라벨(무게중심)과 겹치지 않게 위쪽에 붙인다
    const labelY = top + 16;
    return `    <g>
      <path d="M${round(w.dividerX)} ${round(top)} L${round(w.dividerX)} ${round(
      bottom,
    )}" stroke="#64748b" stroke-width="2" stroke-dasharray="6 5" />
      <text x="${round(w.dividerX - 8)}" y="${round(
      labelY,
    )}" font-size="10" font-weight="700" fill="#475569" text-anchor="end"
            stroke="#ffffff" stroke-width="3" paint-order="stroke">${esc(w.leftName ?? '')}</text>
      <text x="${round(w.dividerX + 8)}" y="${round(
      labelY,
    )}" font-size="10" font-weight="700" fill="#475569" text-anchor="start"
            stroke="#ffffff" stroke-width="3" paint-order="stroke">${esc(w.rightName ?? '')}</text>
    </g>`;
  })
  .filter(Boolean)
  .join('\n');

/** 건물 → 지면과 만나는 층 */
const groundByBuilding = new Map(
  (facts.groundEntries ?? []).map((g) => [g.building, g.floor]),
);

/** 작은 배지 하나를 그린다 */
function badge(x, y, text, fill, stroke, textColor) {
  const w = text.length * 5.6 + 14;
  return `      <g>
        <rect x="${round(x - w / 2)}" y="${round(y - 8.5)}" width="${round(
    w,
  )}" height="17" rx="8.5" fill="${fill}" stroke="${stroke}" stroke-width="1.2" />
        <text x="${round(x)}" y="${round(
    y + 4,
  )}" font-size="9.5" font-weight="700" fill="${textColor}" text-anchor="middle">${esc(text)}</text>
      </g>`;
}

/* --- 건물 이름 + 엘리베이터 / 지면층 배지 --- */
const labelLayer = buildings
  .map((b) => {
    const off = LABEL_OFFSET[b.name] ?? { dx: 0, dy: 0 };
    const x = round(b.center.x + off.dx);
    const y = round(b.center.y + off.dy);
    const size = b.kind === 'academic' || b.kind === 'admin' ? 14 : 12.5;

    const parts = [
      `      <text x="${x}" y="${y}" font-size="${size}" font-weight="700" fill="#33415a" text-anchor="middle"
            stroke="#ffffff" stroke-width="3.5" stroke-linejoin="round" paint-order="stroke">${esc(
              b.short,
            )}</text>`,
    ];

    let cursor = y + size - 2;

    if (b.levels) {
      cursor += 12;
      parts.push(
        `      <text x="${x}" y="${round(
          cursor,
        )}" font-size="10.5" fill="#94a3b8" text-anchor="middle">${b.levels}층</text>`,
      );
    }

    const ev = evByBuilding.get(b.name);
    if (ev) {
      cursor += 15;
      parts.push(
        badge(
          x,
          cursor,
          `EV ${ev.count}대 · ${floorLabel(ev.min)}~${floorLabel(ev.max)}`,
          '#ecfdf5',
          '#34d399',
          '#047857',
        ),
      );
    }

    const ground = groundByBuilding.get(b.name);
    if (ground !== undefined) {
      cursor += 19;
      parts.push(badge(x, cursor, `지면 = ${floorLabel(ground)}`, '#fff7ed', '#fb923c', '#c2410c'));
    }

    return `    <g>\n${parts.join('\n')}\n    </g>`;
  })
  .join('\n');

const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${VIEW.width} ${VIEW.height}" width="${VIEW.width}" height="${VIEW.height}" role="img" aria-labelledby="campusTitle campusDesc">
  <title id="campusTitle">국민대학교 캠퍼스 지도</title>
  <desc id="campusDesc">OpenStreetMap 실측 데이터로 그린 국민대학교 캠퍼스 지도입니다. ${buildings.length}개 건물의 실제 외곽선, 보행로, 계단이 표시되어 있고, 학생 제보로 확인된 건물 간 층별 연결과 엘리베이터 정보가 함께 표시됩니다. 북쪽이 위입니다.</desc>

  <rect width="${VIEW.width}" height="${VIEW.height}" fill="#eef2f7" />

  <!-- 운동장 / 체육시설 (OSM leisure) -->
  <g id="fields">
${fieldLayer}
  </g>

  <!-- 보행로 / 차로 (OSM highway) -->
  <g id="roads">
${roadLayer}
${roadCenterLine}
  </g>

  <!-- 계단 (OSM highway=steps) — 이 앱이 피해야 하는 구간 -->
  <g id="steps">
${stepsLayer}
  </g>

  <!-- 직접 추가한 실외 보행 공간 (OSM 에 없는 열린 공간 · 외부 계단) -->
  <g id="plaza" font-family="system-ui, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif">
${plazaLayer}
  </g>

  <!-- 건물 외곽선 (OSM building) -->
  <g id="buildings">
${buildingLayer}
  </g>

  <!-- 건물 간 층별 연결 (학생 제보, OSM에 없는 데이터) -->
  <g id="connections" font-family="system-ui, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif">
${connectionLayer}
  </g>

  <!-- 동(wing) 경계 -->
  <g id="wings" font-family="system-ui, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif">
${wingLayer}
  </g>

  <!-- 건물 이름 · 엘리베이터 -->
  <g id="labels" font-family="system-ui, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif">
${fieldLabels}
${labelLayer}
  </g>

  <!-- 방위 · 축척 · 출처 -->
  <g font-family="system-ui, 'Malgun Gothic', 'Apple SD Gothic Neo', sans-serif">
    <g transform="translate(${VIEW.width - 52}, 54)">
      <circle r="26" fill="#ffffff" fill-opacity="0.9" stroke="#cbd5e1" stroke-width="1.5" />
      <path d="M 0 -15 L 6 5 L 0 1 L -6 5 Z" fill="#334155" />
      <text y="-17" font-size="10" font-weight="700" fill="#334155" text-anchor="middle">N</text>
    </g>
    <g transform="translate(24, ${VIEW.height - 28})">
      <line x1="0" y1="0" x2="${round(scaleBarUnits)}" y2="0" stroke="#475569" stroke-width="3" />
      <line x1="0" y1="-5" x2="0" y2="5" stroke="#475569" stroke-width="3" />
      <line x1="${round(scaleBarUnits)}" y1="-5" x2="${round(
        scaleBarUnits,
      )}" y2="5" stroke="#475569" stroke-width="3" />
      <text x="${round(
        scaleBarUnits / 2,
      )}" y="-10" font-size="11" font-weight="600" fill="#475569" text-anchor="middle">${scaleBarMeters} m</text>
    </g>
    <text x="24" y="${
      VIEW.height - 8
    }" font-size="9.5" fill="#94a3b8">건물·보행로 © OpenStreetMap contributors (ODbL) · 층간 연결·엘리베이터는 학생 제보</text>
  </g>
</svg>
`;

mkdirSync(resolve(ROOT, 'public/maps'), { recursive: true });
writeFileSync(resolve(ROOT, 'public/maps/campus.svg'), svg, 'utf8');

/* --- 참고용 건물 좌표 --- */
const reference = {
  _readme: [
    'tools/build-campus-map.mjs 가 생성한 파일입니다. 직접 수정하지 마세요.',
    'OSM 실측 좌표를 campus.svg 의 viewBox(1000x700)로 투영한 결과입니다.',
    'accessNodeDistUnits = 건물 무게중심에서 가장 가까운 보행로 노드까지의 거리(SVG 단위).',
    '이 값이 크면 그 건물은 보행로 연결이 부실하다는 뜻이다.',
    '출처: © OpenStreetMap contributors (ODbL)',
  ],
  viewBox: VIEW,
  bounds: BOUNDS,
  metersPerUnitX: Math.round(metersPerUnitX * 1000) / 1000,
  buildings: buildings.map((b) => ({
    name: b.name,
    slug: b.slug,
    levels: b.levels,
    x: round(b.center.x),
    y: round(b.center.y),
    suggestedNodeId: `out_${b.slug}`,
    accessNodeDistUnits: b.accessDistUnits ?? null,
  })),
};

writeFileSync(
  resolve(ROOT, 'tools/campus-buildings.generated.json'),
  `${JSON.stringify(reference, null, 2)}\n`,
  'utf8',
);

/* ------------------------------------------------------------
 * 요약 출력
 * ---------------------------------------------------------- */
const pathCount = Object.keys(walkNetwork.paths).length;
const flatMissing = Object.values(walkNetwork.paths).filter((p) => !p.flat).length;

console.log('');
console.log(`건물 ${buildings.length} · 보행로/차로 ${roads.length} · 계단 ${stepWays.length} · 운동장류 ${fields.length}`);
console.log(`보행 네트워크 노드 ${graph.size} · 경로에 쓰인 노드 ${nodeList.length}`);
console.log(`건물쌍 경로 ${pathCount}개 (계단 없는 경로가 없는 쌍: ${flatMissing}개)`);
console.log(`1 SVG 단위 = ${reference.metersPerUnitX} m`);
console.log(`엘리베이터 정보 있는 건물 ${evByBuilding.size}개 · 연결선 ${(facts.connections ?? []).length}개`);
console.log('');
console.log('건물            slug          접속노드거리(단위)');
console.log('------------------------------------------------');
for (const b of reference.buildings) {
  const warn = (b.accessNodeDistUnits ?? 0) > 60 ? '  ← 보행로 연결 부실' : '';
  console.log(
    `${b.name.padEnd(14, ' ')} ${b.slug.padEnd(13, ' ')} ${String(b.accessNodeDistUnits).padStart(6)}${warn}`,
  );
}
