/* =============================================================================
 * 앱 조립
 * =============================================================================
 * UI 이벤트 → 경로 계산 → 지도/패널 갱신 흐름을 담당합니다.
 * ========================================================================== */

'use strict';

const App = (function () {

  const state = {
    fromId: 'gate_main',
    toId: 'bukak',
    modeId: 'fastest',
    routes: null,
    context: {},
    nextPick: 'from'      // 지도 클릭 시 출발/도착 중 어디를 채울지
  };

  const $ = id => document.getElementById(id);

  /* ======================================================================
   * 초기화
   * =================================================================== */

  function init() {
    buildSelects();
    buildModeButtons();
    buildLegend();
    bindEvents();
    restoreApiSettings();

    MapView.init({
      svg: $('map'),
      onSelect: onMapSelect
    });

    runHealthCheck();
    syncInputs();
    search();
  }

  /* --- 출발/도착 드롭다운 ---------------------------------------------- */

  function buildSelects() {
    const list = allBuildings();

    // 강의가 있는 건물과 부대시설을 그룹으로 나눠서 고르기 쉽게
    const academic = list.filter(b => !b.outdoorOnly);
    const facility = list.filter(b => b.outdoorOnly);

    [['sel-from', 'fromId'], ['sel-to', 'toId']].forEach(([elId, key]) => {
      const sel = $(elId);
      sel.innerHTML = '';

      appendGroup(sel, '건물', academic);
      appendGroup(sel, '출입구 · 시설', facility);

      sel.value = state[key];
      sel.addEventListener('change', () => {
        state[key] = sel.value;
        search();
      });
    });
  }

  function appendGroup(sel, label, items) {
    if (!items.length) return;
    const g = document.createElement('optgroup');
    g.label = label;
    items.forEach(b => {
      const o = document.createElement('option');
      o.value = b.id;
      o.textContent = b.name;
      g.appendChild(o);
    });
    sel.appendChild(g);
  }

  /* --- 모드 버튼 -------------------------------------------------------- */

  function buildModeButtons() {
    const wrap = $('mode-buttons');
    wrap.innerHTML = '';

    Object.keys(MODES).forEach(id => {
      const mode = MODES[id];
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'mode-btn';
      btn.setAttribute('role', 'radio');
      btn.setAttribute('aria-checked', String(id === state.modeId));
      btn.dataset.mode = id;
      btn.innerHTML = `<span class="ico" aria-hidden="true">${mode.icon}</span><span>${mode.label}</span>`;
      btn.addEventListener('click', () => {
        state.modeId = id;
        syncModeButtons();
        search();
      });
      wrap.appendChild(btn);
    });

    syncModeButtons();
  }

  function syncModeButtons() {
    Array.prototype.forEach.call(
      document.querySelectorAll('.mode-btn'),
      btn => btn.setAttribute('aria-checked', String(btn.dataset.mode === state.modeId))
    );
    $('mode-desc').textContent = MODES[state.modeId].desc;
  }

  /* --- 범례 ------------------------------------------------------------- */

  function buildLegend() {
    const wrap = $('legend-types');
    wrap.innerHTML = '';
    const shown = ['road', 'stairs', 'ramp', 'bridge', 'elevator'];
    shown.forEach(type => {
      const s = MapView.SEG_STYLE[type];
      const span = document.createElement('span');
      span.className = 'legend-item';
      span.innerHTML =
        `<i style="border-top-color:${s.color};${s.dash ? 'border-top-style:dashed;' : ''}"></i>${s.label}`;
      wrap.appendChild(span);
    });
  }

  /* --- 이벤트 ----------------------------------------------------------- */

  function bindEvents() {
    $('btn-search').addEventListener('click', handleNaturalLanguage);
    $('nl-input').addEventListener('keydown', e => {
      if (e.key === 'Enter') { e.preventDefault(); handleNaturalLanguage(); }
    });

    Array.prototype.forEach.call(document.querySelectorAll('.chip'), chip => {
      chip.addEventListener('click', () => {
        $('nl-input').value = chip.dataset.q;
        handleNaturalLanguage();
      });
    });

    $('btn-swap').addEventListener('click', () => {
      const t = state.fromId;
      state.fromId = state.toId;
      state.toId = t;
      state.context = {};
      syncInputs();
      search();
    });

    $('btn-zoom-in').addEventListener('click', () => MapView.zoomBy(0.8));
    $('btn-zoom-out').addEventListener('click', () => MapView.zoomBy(1.25));
    $('btn-zoom-reset').addEventListener('click', () => MapView.resetZoom());
    $('btn-zoom-fit').addEventListener('click', () => {
      if (state.routes) MapView.fitRoute(state.routes[state.modeId]);
    });

    $('btn-health').addEventListener('click', () => {
      const panel = $('health-panel');
      const open = panel.hidden;
      panel.hidden = !open;
      $('btn-health').setAttribute('aria-expanded', String(open));
    });

    $('class-time').addEventListener('change', updateLeaveAdvice);
    $('btn-now').addEventListener('click', () => {
      const d = new Date(Date.now() + 30 * 60000);
      $('class-time').value =
        String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
      updateLeaveAdvice();
    });

    $('btn-save-key').addEventListener('click', saveApiSettings);
    $('btn-clear-key').addEventListener('click', clearApiSettings);
    $('btn-polish').addEventListener('click', polishNarration);
  }

  /* --- 지도 클릭 -------------------------------------------------------- */

  function onMapSelect(id) {
    if (state.nextPick === 'from') {
      state.fromId = id;
      state.nextPick = 'to';
    } else {
      state.toId = id;
      state.nextPick = 'from';
    }
    state.context = {};
    syncInputs();
    search();
  }

  function syncInputs() {
    $('sel-from').value = state.fromId;
    $('sel-to').value = state.toId || '';
    MapView.setEndpoints(state.fromId, state.toId);
  }

  /* ======================================================================
   * 자연어 입력 처리
   * =================================================================== */

  async function handleNaturalLanguage() {
    const text = $('nl-input').value.trim();
    const notes = $('nl-notes');

    if (!text) {
      notes.textContent = '';
      return;
    }

    // 1단계: 규칙 기반 파서 (항상 동작)
    const parsed = parseQuery(text, {
      fromId: state.fromId,
      toId: state.toId,
      modeId: state.modeId
    });

    let applied = parsed;
    let via = '규칙 파서';

    // 2단계: 자신이 없고 키가 있으면 LLM 으로 보강
    if (!parsed.confident && LLM.available()) {
      notes.textContent = 'AI 로 문장을 해석하고 있습니다…';
      try {
        const ai = await LLM.extractIntent(text);
        if (ai && ai.toId && getNode(ai.toId)) {
          applied = {
            fromId: (ai.fromId && getNode(ai.fromId)) ? ai.fromId : parsed.fromId,
            toId: ai.toId,
            modeId: MODES[ai.modeId] ? ai.modeId : parsed.modeId,
            fromPlace: ai.fromRoom ? { room: ai.fromRoom } : parsed.fromPlace,
            toPlace: ai.toRoom ? { room: ai.toRoom } : parsed.toPlace,
            notes: ['AI 가 문장을 해석했습니다.']
          };
          via = 'AI';
        }
      } catch (err) {
        // AI 가 실패해도 규칙 파서 결과로 계속 진행합니다.
        applied.notes.push('AI 해석 실패: ' + err.message + ' (규칙 파서 결과로 진행)');
      }
    }

    if (!applied.toId) {
      notes.textContent = '도착지를 알아듣지 못했습니다. 건물 이름을 넣어보세요.';
      return;
    }

    state.fromId = applied.fromId;
    state.toId = applied.toId;
    state.modeId = applied.modeId;
    state.context = {
      fromFloor: applied.fromPlace && applied.fromPlace.floor,
      toFloor: applied.toPlace && applied.toPlace.floor,
      toRoom: applied.toPlace && applied.toPlace.room
    };

    syncInputs();
    syncModeButtons();
    search();

    const msgs = applied.notes.slice();
    msgs.unshift(`[${via}] ${getNode(state.fromId).name} → ${getNode(state.toId).name}`);
    notes.textContent = msgs.join(' ');
  }

  /* ======================================================================
   * 경로 계산 + 표시
   * =================================================================== */

  function search() {
    if (!state.toId) return;

    const routes = findAllRoutes(state.fromId, state.toId);
    state.routes = routes;

    const route = routes[state.modeId];

    if (!route.ok) {
      showError(
        route.accessibilityGap ? '무장애 경로가 없습니다' : '경로를 찾지 못했습니다',
        route.reason
      );
      MapView.clearRoute();
      renderCompare(routes);
      return;
    }

    hideError();
    MapView.showRoute(route);
    MapView.fitRoute(route);
    renderResult(route);
    renderCompare(routes);
    updateLeaveAdvice();
  }

  function renderResult(route) {
    const card = $('result-card');
    card.hidden = false;

    const n = narrate(route, state.context);

    $('result-mode').textContent = `${route.mode.icon} ${route.mode.label}`;
    $('result-summary').textContent = n.summary;
    $('result-sentence').textContent = n.sentence;

    const list = $('step-list');
    list.innerHTML = '';
    n.steps.forEach(step => {
      const li = document.createElement('li');
      const ico = document.createElement('span');
      ico.className = 'ico';
      ico.setAttribute('aria-hidden', 'true');
      ico.textContent = step.icon;

      const body = document.createElement('span');
      body.textContent = step.text;
      if (step.detail) {
        const d = document.createElement('span');
        d.className = 'detail';
        d.textContent = step.detail;
        body.appendChild(d);
      }

      li.appendChild(ico);
      li.appendChild(body);
      list.appendChild(li);
    });

    $('verify-warn').hidden = !route.totals.needsVerify;
    $('btn-polish').hidden = !LLM.available();
  }

  function renderCompare(routes) {
    const card = $('compare-card');
    const list = $('compare-list');
    const items = modeInsights(routes, state.modeId);

    list.innerHTML = '';
    if (!items.length) {
      card.hidden = true;
      return;
    }

    card.hidden = false;
    items.forEach(item => {
      const li = document.createElement('li');
      li.className = item.level;
      li.textContent = item.text;
      list.appendChild(li);
    });
  }

  function showError(title, body) {
    $('result-card').hidden = true;
    const card = $('error-card');
    card.hidden = false;
    $('error-title').textContent = title;
    $('error-body').textContent = body || '';
  }

  function hideError() { $('error-card').hidden = true; }

  /* --- 출발 시각 안내 --------------------------------------------------- */

  function updateLeaveAdvice() {
    const el = $('leave-advice');
    const time = $('class-time').value;
    const route = state.routes && state.routes[state.modeId];

    if (!time || !route || !route.ok) {
      el.textContent = '';
      el.className = 'advice';
      return;
    }

    const advice = leaveAdvice(route, time);
    if (!advice) {
      el.textContent = '';
      el.className = 'advice';
      return;
    }
    el.textContent = advice.text;
    el.className = 'advice ' + advice.level;
  }

  /* ======================================================================
   * AI 보조 기능
   * =================================================================== */

  function restoreApiSettings() {
    $('api-key').value = LLM.getKey();
    $('api-endpoint').value = LLM.getEndpoint();
    $('api-status').textContent = LLM.available()
      ? 'AI 기능이 켜져 있습니다.'
      : 'AI 없이 동작 중입니다. (길찾기는 정상)';
  }

  function saveApiSettings() {
    LLM.setKey($('api-key').value.trim());
    LLM.setEndpoint($('api-endpoint').value.trim());
    restoreApiSettings();
    if (state.routes && state.routes[state.modeId].ok) {
      $('btn-polish').hidden = !LLM.available();
    }
  }

  function clearApiSettings() {
    LLM.setKey('');
    $('api-key').value = '';
    restoreApiSettings();
    $('btn-polish').hidden = true;
  }

  async function polishNarration() {
    const route = state.routes && state.routes[state.modeId];
    if (!route || !route.ok) return;

    const btn = $('btn-polish');
    const target = $('result-sentence');
    const original = target.textContent;

    btn.disabled = true;
    btn.textContent = '다듬는 중…';

    try {
      const n = narrate(route, state.context);
      const text = await LLM.polishNarration(route, n.steps, state.context);
      target.textContent = text.trim();
    } catch (err) {
      target.textContent = original;
      $('nl-notes').textContent = 'AI 다듬기 실패: ' + err.message;
    } finally {
      btn.disabled = false;
      btn.textContent = 'AI로 안내문 다듬기';
    }
  }

  /* ======================================================================
   * 데이터 건강검진
   * =================================================================== */

  function runHealthCheck() {
    const report = healthCheck();
    const badge = $('health-badge');
    const s = report.stats;

    const problems = report.errors.length;
    badge.textContent = problems ? String(problems) : (report.warnings.length ? String(report.warnings.length) : 'OK');
    badge.className = 'badge ' + (problems ? 'alert' : (report.warnings.length ? 'warn' : 'ok'));

    $('health-stats').innerHTML =
      `<span>건물 <strong>${s.buildings}</strong></span>` +
      `<span>교차점 <strong>${s.junctions}</strong></span>` +
      `<span>보행로 <strong>${s.edges}</strong></span>` +
      `<span>방향 엣지 <strong>${s.directedEdges}</strong></span>` +
      `<span>미확인 <strong>${s.unverified}</strong></span>`;

    $('health-errors').innerHTML = report.errors.length
      ? `<h4>오류 ${report.errors.length}건</h4><ul>` +
        report.errors.map(e => `<li>${escapeHtml(e)}</li>`).join('') + '</ul>'
      : '';

    $('health-warnings').innerHTML = report.warnings.length
      ? `<h4>확인 필요 ${report.warnings.length}건</h4><ul>` +
        report.warnings.map(w => `<li>${escapeHtml(w)}</li>`).join('') + '</ul>'
      : '';

    if (report.errors.length) {
      $('health-panel').hidden = false;
      $('btn-health').setAttribute('aria-expanded', 'true');
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    })[c]);
  }

  return { init: init, state: state };
})();

document.addEventListener('DOMContentLoaded', App.init);
