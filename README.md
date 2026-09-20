# 국민대 길찾기 — 통합

```
/                    캠퍼스 전역 길찾기 (Next.js + TS)   담당 jihun335
kmu-indoor-nav/      미래관 실내 데이터 생성 (Python)     담당 taegon6
```

**미래관은 실내 그래프를 기준으로 쓰고, 실외와 다른 건물은 팀원 그래프를 쓴다.**
두 데이터가 실제로 이어져 있어서, 캠퍼스 어디서든 미래관 호실까지 경로가 나온다.

## 실행

```bash
npm install
npm run dev        # http://localhost:3000
```

## 규모

| | 통합 전 | 통합 후 |
|---|---|---|
| campus-graph 노드 | 232 | **1,030** |
| campus-graph 엣지 | 504 | **1,611** |
| 미래관 노드 | 15 (층 단위) | **813 (호실 문 단위)** |
| 검색 가능 | 96 | **279** (미래관 호실 180 포함) |
| 지도 | 캠퍼스 + 북악관 2층 + 조형관 2층 | + **미래관 8개 층** |

## 동작 확인 (통합 시점)

```
                                     거리   시간  계단 EV  BF   지도 전환
미래관 앞 광장 -> 338호  barrier_free  124m   3분   0   1   O   campus -> mirae-4f -> mirae-3f
종합복지관 1층 -> 338호  barrier_free  119m   3분   0   1   O   campus -> mirae-3f
북악관 1층 -> 338호      fastest       396m   7분   0   0   X   campus -> mirae-4f -> mirae-3f
실외 보행로 -> 730호     barrier_free  168m   3분   0   1   O   campus -> mirae-1f -> mirae-7f
202호 -> 730호          fastest        99m   2분   0   1   O   mirae-2f -> mirae-7f
338호 -> 337호          fastest         26m   1분   0   0   O   mirae-3f
```

단계 안내 예시 (미래관 앞 광장 → 338호, `barrier_free`)

```
0. [enter]     미래관 4층 으로 들어갑니다.            12m
1. [walk]      미래관 4층 복도를 따라 84m 이동합니다.  84m
2. [elevator]  미래관 엘리베이터로 4층 → 3층 이동합니다.
3. [walk]      미래관 3층 복도를 따라 28m 이동합니다.  28m
4. [arrive]    미래관 338호 에 도착했습니다.
```

경사 캠퍼스라 미래관은 **4층에서 지면과 만난다.** 광장에서 들어가면 4층이고,
338호까지 엘리베이터로 내려간다. 이 동작이 데이터에 반영되어 있다.

## 어떻게 이어져 있나

`kmu-indoor-nav/scripts/export_to_campus_graph.py` 가 실내 그래프를 팀원 앱
형식으로 변환해 아래 4개를 갱신한다.

| 대상 | 내용 |
|---|---|
| `data/campus-graph.json` | 미래관 15노드 → 813노드 교체 |
| `data/graph-coords.json` | 미래관 노드 813개 좌표 기록 |
| `public/maps/mirae-*.png` | 층 도면 8장 복사 |
| `lib/ui/maps.ts` | `MAP_REGISTRY` 에 미래관 8개 층 등록 |

```bash
cd kmu-indoor-nav
python scripts/build_from_navmap.py            # 도면 -> 실내 그래프
python scripts/export_to_campus_graph.py --check  # 미리보기
python scripts/export_to_campus_graph.py          # 적용 (백업 생성)
cd .. && npm run typecheck && npm run build
```

**좌표 변환이 필요 없다.** 팀원 앱은 배경을 `<img>` 로 깔고 오버레이 `<svg>` 의
viewBox 를 이미지 크기에 맞추므로, 실내 그래프의 도면 픽셀 좌표가 그대로
화면 좌표가 된다.

**외부 연결을 보존한다.** 팀원의 미래관 층 노드는 외부 연결 9개를 들고 있었다
(종합복지관 1~4층, 예술관 B2, 실외 3곳). 이를 각 층의 대표 노드로 9/9 재부착한다.
우선순위는 출입구 → 엘리베이터 → 복도.

## 검증

```
npm run typecheck        exit=0
npm run build            exit=0 (7 페이지)
좌표 없는 노드            0 / 1,030
미등록 지도 참조           0
미래관 좌표 누락           0 / 813

kmu-indoor-nav
  test_routing_synthetic  29/29
  test_mirae_real_graph   18/18
  test_merge_parts        10/10
  validate_graph          치명적 0건
```

## 각 프로젝트 요약

### 루트 — 캠퍼스 전역 (Next.js)

실외 보행로는 OpenStreetMap, 층간 연결·엘리베이터·고도는 `data/campus-facts.json`.
엔진은 `lib/graph.ts` (다익스트라, 순수 함수라 서버·브라우저 양쪽에서 동작).
이동 방식 4종: `fastest`, `fewest_stairs`, `barrier_free`, `stay_dry`.

### kmu-indoor-nav — 미래관 실내 (Python)

층별 지도에서 복도망을 자동 추출한다. 상세 내용은 `kmu-indoor-nav/README.md`.

- 색상 규약(민트=복도, 파랑=엘리베이터, 주황=계단, 초록=출입구)으로 분류
- 복도와 방은 **형태로 구분** (층마다 색조가 달라 색으로는 불가능)
- Zhang-Suen 세선화 → 복도 중심선 → 분기점/문 노드
- 문은 호실 이름표에서 가장 가까운 복도 셀, 연결선은 복도 내 BFS 경로
- 승강기는 층간 위치 클러스터링으로 샤프트 구분 (4개)
- 미래관 8개 층 · 호실 180개 · 노드 813 · 엣지 2,344

의존성은 `requests`, `Pillow` 뿐이다.

## 남은 것

- **엔진이 둘이다.** 제품 경로는 루트 TS 엔진이 계산한다. Python 엔진은 실내
  데이터 생성·검증용으로 남는다. 접근성 조건 해석이 다르므로(Python 쪽은
  미확인 속성을 하드 제약으로 차단, TS 쪽은 비용 가중) 판정이 갈릴 수 있다.
- **미래관 외 건물은 여전히 층 단위**다. 같은 파이프라인으로 확장할 수 있다.
- **현장 미검증.** 문턱·유효폭·경사·승강기 정차층은 추정값이다.
  조사 항목은 `kmu-indoor-nav/docs/data_gaps.md` 에 대상 ID 별로 정리했다.
- 미래관 도면은 AI 로 단순화한 시안이라 호실명·벽 위치에 오류가 있을 수 있다.

## 병합 이력

- 팀원 브랜치 `feat/kmu-wayfinder-engine` 은 독립 히스토리로 만들어져
  `--allow-unrelated-histories` 로 병합했다. 충돌 0건.
- `18acdfa` 에서 `kmu-wayfinder/` 125개 파일이 삭제되었다(정적 사이트 + 그 하위
  실내 프로젝트). Next.js 앱이 정적 사이트를 대체하므로 되살리지 않고,
  실내 프로젝트만 최상위 `kmu-indoor-nav/` 로 옮겨 넣었다.