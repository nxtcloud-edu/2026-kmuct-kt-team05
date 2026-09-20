# 국민대 길찾기 — 통합 저장소

두 프로젝트가 한 저장소에 공존한다. 서로 다른 범위를 담당하고, 아직 **데이터가
연결되어 있지는 않다** (아래 「다음 단계」 참고).

```
/                    실외 + 캠퍼스 전역 길찾기        Next.js + TypeScript   담당 jihun335
kmu-indoor-nav/      미래관 실내 상세 길찾기          Python                 담당 taegon6
```

## 1. 루트 — 캠퍼스 전역 (Next.js)

```bash
npm install
npm run dev        # http://localhost:3000
npm run typecheck  # 통과 확인됨
npm run build      # 통과 확인됨 (7 페이지)
```

| 항목 | 내용 |
|---|---|
| 그래프 | `data/campus-graph.json` v0.4.0-r3 |
| 규모 | 건물 21개 · 노드 232개 · 엣지 504개 |
| 노드 구성 | 실외 145 · 분기점 76 · 출입구 11 |
| 건물별 노드 | 북악관 16, 미래관 15, 산학협력관 6, 공학관 6, 경영관 6, 종합복지관 6, 예술관 6, 경상관 5, 국제관 5, 콘서트홀 5, 성곡도서관 1 |
| 지도 | `public/maps/campus.svg` + 북악관 1F/4F, 조형관 1F/3F |
| 엔진 | `lib/graph.ts`, `lib/cost.ts` |
| 빌더 | `tools/build-graph.mjs`, `tools/build-campus-map.mjs` |
| 고도 | `baseElevation` + `assumptions` 로 경사 반영 |
| API | `app/api/route`, `app/api/nodes` |

강점: 캠퍼스 전역을 덮고, 실외 경사를 다루며, 사용자 화면이 완성되어 있다.

## 2. kmu-indoor-nav — 미래관 실내 (Python)

```bash
cd kmu-indoor-nav
python scripts/build_from_navmap.py          # 층별 지도 -> 그래프
python demo/server.py 8900                   # http://127.0.0.1:8900
python tests/test_routing_synthetic.py       # 29개
python tests/test_mirae_real_graph.py        # 18개
python tests/test_merge_parts.py             # 10개
```

| 항목 | 내용 |
|---|---|
| 그래프 | `data/demo/mirae_nav_v1.json` |
| 규모 | 미래관 8개 층(지하1층~7층) · 호실 180개 · 노드 813개 · 엣지 2,344개 |
| 승강기 | 샤프트 4개 (주 샤프트는 1~7층 정차) |
| 도달성 | 호실 180개 중 179개 |
| 엔진 | `backend/app/routing/` (Dijkstra, 시간/선호 분리) |
| 의존성 | `requests`, `Pillow` 만 |

강점: 한 건물의 실내를 문 단위까지 상세히 다루고, 접근성 근거 추적
(`unknown` 보존, 5단계 검증 수준)과 파트 분할 병합 구조를 갖췄다.

## 3. 겹치는 부분

두 프로젝트 모두 **경로 탐색 엔진**을 가지고 있다.

| | 루트 (TS) | kmu-indoor-nav (Python) |
|---|---|---|
| 범위 | 캠퍼스 전역 실외 + 출입구 | 미래관 실내 전층 |
| 미래관 노드 | 15개 (출입구·분기점 수준) | 813개 (호실 문 단위) |
| 좌표 | 지리 좌표 + SVG | 층별 지도 픽셀 좌표 |
| 경사 | 실외 고도 반영 | 실내라 해당 없음 |
| 접근성 | 비용 가중 | 하드 제약 + 근거 수준 추적 |

미래관에 대해 두 그래프가 **동시에 존재한다.** 루트 쪽은 15개 노드로 개략,
실내 쪽은 813개 노드로 상세하다. 지금은 서로 참조하지 않는다.

## 4. 다음 단계 — 실제로 연결하려면

권장 구성은 **루트 앱이 제품, 실내 그래프가 상세 데이터 공급원**이다.

**(1) 좌표계 정합** — 실내 그래프는 층별 지도 픽셀 좌표만 갖는다
(`plan:mirae/F3`). 루트 앱은 지리 좌표를 쓴다. 미래관 출입구 노드를 기준점으로
삼아 변환을 구해야 한다. 실내 쪽에 이미 출입구 노드가 8개 있다
(`entrance_inside`).

**(2) 스키마 변환** — 실내 그래프를 루트 앱의 노드/엣지 형식으로 내보내는
변환기가 필요하다. 실내 쪽 스키마가 더 풍부하므로(근거 수준, 방향별 경사,
운영시간) 손실 없이 줄이려면 매핑 표를 먼저 합의해야 한다.

**(3) 연결 지점 선언** — 실내 쪽에 이미 파트 분할 병합 구조가 있다
(`kmu-indoor-nav/docs/contributing_parts.md`). 루트 앱의 미래관 출입구 노드와
실내 그래프의 `entrance_inside` 노드를 `data/links/` 형식으로 이으면 된다.
국민대는 경사 캠퍼스라 **한 건물이 여러 층에서 지면과 만나므로** 출입구마다
만나는 층을 명시해야 한다.

**(4) 엔진 하나 고르기** — 두 엔진을 유지하면 「계단 없이」 같은 조건의 해석이
갈릴 수 있다. 사용자에게 보이는 경로는 한쪽에서만 계산하는 편이 안전하다.

가장 작은 검증 단위: **미래관 출입구 1개소를 두 그래프에서 잇고,
「정문에서 미래관 338호까지」가 끝까지 나오는지 확인한다.**

## 5. 검증 상태 (통합 시점)

```
루트 (Next.js)
  npm install       372 packages, 22초
  npm run typecheck  exit=0
  npm run build      exit=0, 7 페이지

kmu-indoor-nav (Python)
  test_routing_synthetic  29/29
  test_mirae_real_graph   18/18
  test_merge_parts        10/10
  validate_graph          치명적 0건
  merge_graphs            exit=0
  route 202->730          ok  99.3m  2층 -> 7층
```

## 6. 병합 이력 참고

- 팀원 브랜치 `feat/kmu-wayfinder-engine` 은 독립 히스토리로 만들어져
  `--allow-unrelated-histories` 로 병합했다. 충돌 0건.
- `18acdfa` 에서 `kmu-wayfinder/` 디렉터리(125개 파일)가 삭제되었다.
  기존 정적 사이트와 그 하위에 있던 실내 프로젝트가 함께 지워졌으므로,
  실내 프로젝트는 최상위 `kmu-indoor-nav/` 로 위치를 옮겨 다시 넣었다.
  삭제된 정적 사이트는 되살리지 않았다 (Next.js 앱이 이를 대체).
