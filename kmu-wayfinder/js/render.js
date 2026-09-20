/* =============================================================================
 * SVG 지도 렌더러
 * =============================================================================
 * 실제 지도 API 를 쓰지 않습니다. 캠퍼스맵 좌표 위에 직접 그리기 때문에
 *   - 외부 의존성 0, 오프라인에서도 동작
 *   - 층·실내 통로처럼 지도 API 에 없는 정보를 자유롭게 표현
 * 배경에 실제 지도를 깔고 싶으면 assets/campusmap.png 를 넣으세요.
 * 없으면 추상 베이스맵으로 자동 대체됩니다.
 * ========================================================================== */

'use strict';

const SVG_NS = 'http://www.w3.org/2000/svg';

/** 구간 종류별 표시 스타일 */
const SEG_STYLE = {
  road:     { color: '#2563eb', dash: null,    label: '보도' },
  stairs:   { color: '#dc2626', dash: '1 7',   label: '계단' },
  ramp:     { color: '#059669', dash: null,    label: '경사로' },
  indoor:   { color: '#7c3aed', dash: '10 5',  label: '실내' },
  bridge:   { color: '#7c3aed', dash: '10 5',  label: '연결통로' },
  elevator: { color: '#c026d3', dash: '2 4',   label: '엘리베이터' }
};

const MapView = (function () {

  // 배경 지도(assets/campusmap.png)의 실제 픽셀 크기와 일치시켜야
  // 건물 핀이 지도 위 제자리에 찍힙니다.
  const VIEW_W = 824;
  const VIEW_H = 611;

  let svg = null;
  let layers = {};
  let onSelect = null;
  let nodeEls = new Map();
  let endpoints = { from: null, to: null };
  let hasBackground = false;

  /* --- DOM 헬퍼 ---------------------------------------------------------- */

  function el(tag, attrs, parent) {
    const node = document.createElementNS(SVG_NS, tag);
    if (attrs) {
      Object.keys(attrs).forEach(k => {
        if (attrs[k] == null) return;
        node.setAttribute(k, attrs[k]);
      });
    }
    if (parent) parent.appendChild(node);
    return node;
  }

  function clear(node) {
    while (node && node.firstChild) node.removeChild(node.firstChild);
  }

  /* --- 고도 → 색 (경사 캠퍼스를 눈으로 보여주는 장치) -------------------- */

  const elevRange = (function () {
    const all = BUILDINGS.concat(JUNCTIONS).map(n => n.elev);
    return { min: Math.min.apply(null, all), max: Math.max.apply(null, all) };
  })();

  function elevColor(elev) {
    const t = (elev - elevRange.min) / Math.max(1, elevRange.max - elevRange.min);
    // 낮은 곳 = 연한 청록, 높은 곳 = 진한 갈색 (등고선 느낌)
    const r = Math.round(120 + t * 105);
    const g = Math.round(190 - t * 90);
    const b = Math.round(180 - t * 130);
    return `rgb(${r},${g},${b})`;
  }

  /* --- 초기화 ----------------------------------------------------------- */

  function init(options) {
    svg = options.svg;
    onSelect = options.onSelect || function () {};

    svg.setAttribute('viewBox', `0 0 ${VIEW_W} ${VIEW_H}`);
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', '국민대학교 북악캠퍼스 지도와 경로');
    clear(svg);

    defs();

    // 레이어 순서가 곧 z-order 입니다.
    layers.bg      = el('g', { id: 'layer-bg' }, svg);
    layers.terrain = el('g', { id: 'layer-terrain' }, svg);
    layers.edges   = el('g', { id: 'layer-edges' }, svg);
    layers.route   = el('g', { id: 'layer-route' }, svg);
    layers.nodes   = el('g', { id: 'layer-nodes' }, svg);
    layers.labels  = el('g', { id: 'layer-labels' }, svg);
    layers.markers = el('g', { id: 'layer-markers' }, svg);

    loadBackground();
    renderBase();
    bindZoom();
  }

  function defs() {
    const d = el('defs', null, svg);

    // 경로 글로우
    const f = el('filter', { id: 'route-glow', x: '-30%', y: '-30%', width: '160%', height: '160%' }, d);
    el('feGaussianBlur', { stdDeviation: '3', result: 'blur' }, f);
    const merge = el('feMerge', null, f);
    el('feMergeNode', { in: 'blur' }, merge);
    el('feMergeNode', { in: 'SourceGraphic' }, merge);

    // 출발/도착 화살표
    const marker = el('marker', {
      id: 'arrow', viewBox: '0 0 10 10', refX: '8', refY: '5',
      markerWidth: '5', markerHeight: '5', orient: 'auto-start-reverse'
    }, d);
    el('path', { d: 'M 0 0 L 10 5 L 0 10 z', fill: '#111827' }, marker);
  }

  /** 실제 지도 스크린샷이 있으면 배경으로 깔고, 없으면 추상 베이스맵 */
  function loadBackground() {
    const probe = new Image();
    probe.onload = function () {
      // 흰 바탕을 먼저 깔고 그 위에 흑백으로 눌러 얹습니다.
      // 지도 자체의 라벨·핀이 우리 경로와 색으로 경쟁하지 않게 하려는 것입니다.
      el('rect', { x: 0, y: 0, width: VIEW_W, height: VIEW_H, fill: '#ffffff' }, layers.bg);
      el('image', {
        href: 'assets/campusmap.png',
        x: 0, y: 0, width: VIEW_W, height: VIEW_H,
        opacity: 0.42,
        filter: 'grayscale(1)',
        preserveAspectRatio: 'none'
      }, layers.bg);

      // 실제 지도가 깔리면 추상 지형 덩어리는 오히려 지저분해지므로 끕니다.
      // 고도 정보는 건물 점 색깔로 계속 표현됩니다.
      hasBackground = true;
      clear(layers.terrain);
    };
    probe.onerror = function () {
      drawAbstractBase();
    };
    probe.src = 'assets/campusmap.png';
  }

  /** 지도 이미지가 없을 때의 대체 베이스맵 */
  function drawAbstractBase() {
    el('rect', { x: 0, y: 0, width: VIEW_W, height: VIEW_H, fill: '#f8fafc' }, layers.bg);

    // 정릉로 (캠퍼스 남쪽 간선도로)
    el('path', {
      d: 'M 0 330 Q 220 370 420 470 T 829 560',
      stroke: '#fde68a', 'stroke-width': 26, fill: 'none', 'stroke-linecap': 'round'
    }, layers.bg);
    el('text', { x: 300, y: 470, fill: '#a16207', 'font-size': 11, transform: 'rotate(14 300 470)' }, layers.bg)
      .textContent = '정릉로';

    // 대운동장
    el('ellipse', { cx: 400, cy: 355, rx: 78, ry: 40, fill: '#bbf7d0', stroke: '#86efac' }, layers.bg);

    // 북악산 사면 느낌의 등고선
    [
      'M 60 60 Q 300 30 560 70 T 829 130',
      'M 40 130 Q 300 110 580 150 T 829 210',
      'M 30 210 Q 280 200 560 240 T 829 300'
    ].forEach(d => {
      el('path', { d: d, stroke: '#e2e8f0', 'stroke-width': 1.5, fill: 'none', 'stroke-dasharray': '4 6' }, layers.bg);
    });
  }

  /* --- 베이스: 보행로 + 건물 ------------------------------------------- */

  function renderBase() {
    clear(layers.terrain);
    clear(layers.edges);
    clear(layers.nodes);
    clear(layers.labels);
    nodeEls.clear();

    if (!hasBackground) drawTerrainHints();
    drawAllEdges();
    drawAllNodes();
  }

  /** 고도를 반투명 원으로 깔아서 "어디가 높은지" 한눈에 보이게 */
  function drawTerrainHints() {
    BUILDINGS.concat(JUNCTIONS).forEach(n => {
      el('circle', {
        cx: n.x, cy: n.y, r: 42,
        fill: elevColor(n.elev), opacity: 0.16
      }, layers.terrain);
    });
  }

  /** 전체 보행로 네트워크를 흐리게 표시 (데이터가 있다는 신뢰감) */
  function drawAllEdges() {
    EDGES.forEach(raw => {
      const a = getNode(raw[0]);
      const b = getNode(raw[1]);
      if (!a || !b) return;
      const style = SEG_STYLE[raw[2]] || SEG_STYLE.road;
      el('line', {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        stroke: style.color, 'stroke-width': 2, opacity: 0.18,
        'stroke-dasharray': style.dash
      }, layers.edges);
    });
  }

  function drawAllNodes() {
    // 교차점은 작은 점으로
    JUNCTIONS.forEach(j => {
      el('circle', {
        cx: j.x, cy: j.y, r: 3,
        fill: '#94a3b8', opacity: 0.7
      }, layers.nodes);
    });

    BUILDINGS.forEach(b => {
      const isFacility = !!b.outdoorOnly && !b.isGate;
      const g = el('g', {
        class: 'map-node' + (isFacility ? ' is-facility' : ''),
        tabindex: '0',
        role: 'button',
        'aria-label': `${b.name}. 클릭하면 출발지 또는 도착지로 지정합니다.`
      }, layers.nodes);

      // 클릭 판정을 넉넉하게
      el('circle', { cx: b.x, cy: b.y, r: 16, fill: 'transparent' }, g);

      const r = b.isGate ? 8 : (isFacility ? 5 : 9);
      const dot = el('circle', {
        cx: b.x, cy: b.y, r: r,
        fill: b.isGate ? '#111827' : elevColor(b.elev),
        stroke: '#ffffff', 'stroke-width': 2.5
      }, g);

      if (b.elevator) {
        el('circle', { cx: b.x + r + 3, cy: b.y - r - 1, r: 3, fill: '#c026d3', stroke: '#fff', 'stroke-width': 1 }, g)
          .setAttribute('aria-hidden', 'true');
      }

      // 건물이 몰려 있는 곳은 data.js 의 labelDx / labelDy 로 라벨을 비켜 놓습니다.
      const label = el('text', {
        x: b.x + (b.labelDx || 0),
        y: b.y + (b.labelDy != null ? b.labelDy : (isFacility ? 15 : 22)),
        'text-anchor': b.labelAnchor || 'middle',
        class: 'map-label' + (isFacility ? ' is-facility' : '')
      }, layers.labels);
      label.textContent = b.name;

      const title = el('title', null, g);
      title.textContent = `${b.name} · 고도 ${b.elev}m${b.depts ? '\n' + b.depts : ''}`;

      g.addEventListener('click', () => onSelect(b.id));
      g.addEventListener('keydown', e => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(b.id); }
      });

      nodeEls.set(b.id, { group: g, dot: dot, label: label });
    });
  }

  /* --- 경로 표시 -------------------------------------------------------- */

  function showRoute(route) {
    clear(layers.route);
    clear(layers.markers);

    if (!route || !route.ok || !route.segments.length) {
      paintEndpoints();
      return;
    }

    // 1) 두꺼운 흰 바탕선 — 배경 위에서도 경로가 또렷하게 보이도록
    const pts = route.nodes.map(id => {
      const n = getNode(id);
      return `${n.x},${n.y}`;
    }).join(' ');

    el('polyline', {
      points: pts, fill: 'none',
      stroke: '#ffffff', 'stroke-width': 11,
      'stroke-linejoin': 'round', 'stroke-linecap': 'round',
      opacity: 0.95
    }, layers.route);

    // 2) 구간별 색칠 — 계단/실내/엘리베이터가 시각적으로 구분됨
    route.segments.forEach((seg, i) => {
      const a = getNode(seg.from);
      const b = getNode(seg.to);
      const style = SEG_STYLE[seg.type] || SEG_STYLE.road;

      const line = el('line', {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        stroke: style.color, 'stroke-width': 5.5,
        'stroke-linecap': 'round',
        'stroke-dasharray': style.dash,
        filter: 'url(#route-glow)'
      }, layers.route);

      const t = el('title', null, line);
      t.textContent = `${i + 1}. ${a.name} → ${b.name} · ${style.label} ${Math.round(seg.dist)}m`
        + (seg.stairsUp ? ` · 계단 ${seg.stairsUp}칸 오름` : '')
        + (seg.stairsDown ? ` · 계단 ${seg.stairsDown}칸 내림` : '');

      // 진행 방향 애니메이션
      if (!style.dash) {
        line.setAttribute('stroke-dasharray', '14 10');
        const anim = el('animate', {
          attributeName: 'stroke-dashoffset',
          from: '24', to: '0', dur: '1s', repeatCount: 'indefinite'
        }, line);
        void anim;
      }
    });

    paintEndpoints();
  }

  function clearRoute() {
    clear(layers.route);
    paintEndpoints();
  }

  function setEndpoints(fromId, toId) {
    endpoints = { from: fromId, to: toId };
    paintEndpoints();
  }

  function paintEndpoints() {
    clear(layers.markers);

    nodeEls.forEach(ref => ref.group.classList.remove('is-start', 'is-goal'));

    [['from', '출발', '#16a34a'], ['to', '도착', '#dc2626']].forEach(([key, text, color]) => {
      const id = endpoints[key];
      if (!id) return;
      const n = getNode(id);
      if (!n) return;

      const ref = nodeEls.get(id);
      if (ref) ref.group.classList.add(key === 'from' ? 'is-start' : 'is-goal');

      const g = el('g', null, layers.markers);
      el('circle', {
        cx: n.x, cy: n.y, r: 15,
        fill: 'none', stroke: color, 'stroke-width': 3
      }, g);

      const bx = n.x - 17;
      const by = n.y - 34;
      el('rect', { x: bx, y: by, width: 34, height: 17, rx: 4, fill: color }, g);
      const label = el('text', {
        x: n.x, y: by + 12.5, 'text-anchor': 'middle',
        fill: '#fff', 'font-size': 11, 'font-weight': '700'
      }, g);
      label.textContent = text;
    });
  }

  /* --- 확대/축소 -------------------------------------------------------- */

  let zoom = { x: 0, y: 0, w: VIEW_W, h: VIEW_H };

  function applyZoom() {
    svg.setAttribute('viewBox', `${zoom.x} ${zoom.y} ${zoom.w} ${zoom.h}`);
  }

  function zoomBy(factor, cx, cy) {
    const nw = Math.min(VIEW_W, Math.max(VIEW_W * 0.25, zoom.w * factor));
    const nh = nw * (VIEW_H / VIEW_W);
    const ax = cx == null ? zoom.x + zoom.w / 2 : cx;
    const ay = cy == null ? zoom.y + zoom.h / 2 : cy;

    zoom.x = ax - (ax - zoom.x) * (nw / zoom.w);
    zoom.y = ay - (ay - zoom.y) * (nh / zoom.h);
    zoom.w = nw;
    zoom.h = nh;

    // 경계 밖으로 나가지 않도록
    zoom.x = Math.max(0, Math.min(VIEW_W - zoom.w, zoom.x));
    zoom.y = Math.max(0, Math.min(VIEW_H - zoom.h, zoom.y));
    applyZoom();
  }

  function resetZoom() {
    zoom = { x: 0, y: 0, w: VIEW_W, h: VIEW_H };
    applyZoom();
  }

  /** 경로가 화면에 꽉 차도록 맞춥니다 */
  function fitRoute(route) {
    if (!route || !route.ok || route.nodes.length < 2) return resetZoom();

    const ns = route.nodes.map(getNode);
    const pad = 70;
    const minX = Math.min.apply(null, ns.map(n => n.x)) - pad;
    const maxX = Math.max.apply(null, ns.map(n => n.x)) + pad;
    const minY = Math.min.apply(null, ns.map(n => n.y)) - pad;
    const maxY = Math.max.apply(null, ns.map(n => n.y)) + pad;

    let w = Math.max(maxX - minX, (maxY - minY) * (VIEW_W / VIEW_H));
    w = Math.min(w, VIEW_W);
    const h = w * (VIEW_H / VIEW_W);

    zoom.w = w;
    zoom.h = h;
    zoom.x = Math.max(0, Math.min(VIEW_W - w, (minX + maxX) / 2 - w / 2));
    zoom.y = Math.max(0, Math.min(VIEW_H - h, (minY + maxY) / 2 - h / 2));
    applyZoom();
  }

  function bindZoom() {
    svg.addEventListener('wheel', e => {
      e.preventDefault();
      const pt = clientToView(e.clientX, e.clientY);
      zoomBy(e.deltaY > 0 ? 1.15 : 0.87, pt.x, pt.y);
    }, { passive: false });

    let dragging = false;
    let last = null;

    svg.addEventListener('pointerdown', e => {
      if (e.target.closest('.map-node')) return;   // 건물 클릭은 선택 동작
      dragging = true;
      last = { x: e.clientX, y: e.clientY };
      svg.style.cursor = 'grabbing';
    });
    window.addEventListener('pointerup', () => {
      dragging = false;
      svg.style.cursor = '';
    });
    window.addEventListener('pointermove', e => {
      if (!dragging) return;
      const rect = svg.getBoundingClientRect();
      const kx = zoom.w / rect.width;
      const ky = zoom.h / rect.height;
      zoom.x = Math.max(0, Math.min(VIEW_W - zoom.w, zoom.x - (e.clientX - last.x) * kx));
      zoom.y = Math.max(0, Math.min(VIEW_H - zoom.h, zoom.y - (e.clientY - last.y) * ky));
      last = { x: e.clientX, y: e.clientY };
      applyZoom();
    });
  }

  function clientToView(clientX, clientY) {
    const rect = svg.getBoundingClientRect();
    return {
      x: zoom.x + ((clientX - rect.left) / rect.width) * zoom.w,
      y: zoom.y + ((clientY - rect.top) / rect.height) * zoom.h
    };
  }

  return {
    init: init,
    renderBase: renderBase,
    showRoute: showRoute,
    clearRoute: clearRoute,
    setEndpoints: setEndpoints,
    zoomBy: zoomBy,
    resetZoom: resetZoom,
    fitRoute: fitRoute,
    SEG_STYLE: SEG_STYLE
  };
})();
