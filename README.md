# 미래관 실내 내비게이션 (indoor)

국민대 미래관의 **실내 경로 안내** 구현. 층별 지도에서 복도·문·엘리베이터·계단
그래프를 추출하고, 한국어 음성/텍스트 요청을 구조화해 계단 회피·휠체어 조건을
반영한 경로를 계산한다. 모바일 우선 UI.

같은 폴더의 상위 프로젝트(`../index.html`, `../js/`)는 실외 캠퍼스맵 기반
브라우저 전용 구현이고, 이 폴더는 **Python 백엔드 + 실내 층별 지도** 기반으로
별개 구성이다.

## 지금 되는 것

| 항목 | 상태 |
|---|---|
| 층 | 8개 (지하1층 ~ 7층) |
| 등록 호실 | 171개 |
| 그래프 | 노드 1,477 · 엣지 4,484 · **연결요소 1개** |
| 엘리베이터 / 계단 | 1대(8개 층 정차) / 층간 연결 |
| 같은 층 / 층간 경로 | O |
| 「계단 없이」 | O |
| 휠체어 조건 | O |
| 한국어 음성 입력 | O (브라우저 Web Speech API, ko-KR) |
| 모바일 UI | O (핀치 줌, 하단 시트, 경로 자동 맞춤) |
| 실외 연결 | X (출입구 노드까지) |

경로 예시

```
338→337  3층 내         28.7m   24s  계단0  EV0
338→449  3→4층 빠르게   64.6m   78s  계단1  EV0   ← 1개층은 계단이 빠름
338→449  3→4층 계단없이 133.0m 146s  계단0  EV1   ← 조건 바꾸면 엘리베이터 우회
202→730  2→7층         173.3m 192s  계단0  EV1
338→620  3→6층 휠체어   134.0m 213s  계단0  EV1
```

## 실행

```bash
# 그래프 생성 (층별 지도에서 추출)
python scripts/build_from_navmap.py

# 검증
python scripts/validate_graph.py data/demo/mirae_nav_v1.json
python scripts/diagnose_indoor.py data/demo/mirae_nav_v1.json
python tests/test_routing_synthetic.py       # 29개
python tests/test_mirae_real_graph.py        # 18개

# 데모 서버
python demo/server.py 8855
#    -> http://127.0.0.1:8855   (음성은 Chrome/Edge)

# CLI
python scripts/route_cli.py --graph data/demo/mirae_nav_v1.json --from 202 --to 730
python scripts/route_cli.py --graph data/demo/mirae_nav_v1.json --from 338 --to 620 --wheelchair
```

의존성은 `requests` 와 `Pillow` 뿐이다. 나머지는 표준 라이브러리.

원본 공식 도면까지 다루려면 `python scripts/collect_floorplans.py` 를 먼저 실행한다
(저장소에 원본 이미지는 포함하지 않았다. 아래 「원본 자료」 참고).

## 층별 지도에서 그래프를 뽑는 방법

`data/raw/navmaps/nav_*.png` 는 원본 도면을 단순화한 층별 지도다.
**원본 도면과 좌표계가 다르다** — 정합을 시도했으나 적중률이 0.0~0.65로 실패했다
(`scripts/analyze_navmap.py`, 결과는 `data/curated/navmap_registration.json`).

그래서 정합을 포기하고 **지도 자체를 데이터 소스로** 썼다. 같은 이미지에서
그래프를 뽑으므로 경로가 화면과 정확히 정렬된다.

지도의 색상 규약을 이용한다.

```
민트 rgb(221,244,233) → 이동 공간      파랑 → 엘리베이터
주황 → 계단                            초록 → 출입구
회색(지하1층) → 주차/차량 동선
```

파이프라인 (`scripts/build_from_navmap.py`)

1. **6px 셀 격자 색상 분류** → 통행 마스크
2. **모폴로지 닫힘(반경 2셀)** — 민트 통행면 위에 호실번호·아이콘·벽선을 덧그려서
   원본 마스크가 조각나 있다(3층 44조각, 최대 60%). 닫힘 후 1조각(97%)으로 복구
3. **Zhang-Suen 세선화** → 복도 중심선 골격
4. **잔가지 제거** — 넓은 개방공간에서 생기는 spur 제거 (9셀 미만)
5. **골격 추적** — 분기점/끝점을 노드로, 사이 경로를 폴리라인 엣지로
6. **시설 부착** — 색 덩어리 중심을 **최대 골격 요소**에만 부착.
   작은 고립 조각에 붙이면 그 시설이 경로에서 단절된다 (이 처리 전 연결요소 89개 → 후 1개)
7. **호실 부착** — 지도 OCR(Windows.Media.Ocr, ko) 라벨을 최근접 골격점에 문 노드로

축척은 건물 장변을 원본 도면 치수선 값(그리드축 ①~⑰ = 139.55 m)으로 잡아
층별로 산출한다 (74.1~90.1 mm/px).

## 원본 도면 판독 (참고 자산)

`data/published/mirae_indoor_v1.json` 은 원본 공식 도면을 직접 판독해 만든
검증 기준 그래프다(3층 338/337호, 2층 202호). 추정값이 없다.

원본 도면에는 **계단·엘리베이터를 가리키는 텍스트가 없고 기호 범례도 없어서**
픽셀 분석으로 구조를 읽었다.

- **축척** — 그리드축 ①(x=139.0px) → ⑯(x=1412.0px) = 1273.0px 가 128,350mm
  → 100.83 mm/px. 수직 H→A 로 99.03 mm/px 교차검증. 부분구간 13개 모두 99~102 범위.
  채택 **0.1008 m/px (±2%)**
- **층 구조** — 가로 벽선 픽셀 탐지(`scripts/find_walls.py`). 3~7층이 같은 프레임
  (벽선 y = 333 / 361 / 558 / 592 층마다 일치). 북측 복도 센터라인 348(폭 2.5m),
  남측 576(폭 3.1m)
- **문** — 이 도면은 **벽선이 문 위치에서도 끊기지 않고** 문이 실내쪽 호선(arc)으로만
  표현된다. '벽 빈틈' 방식이 실패해 호선 검출로 전환(`scripts/detect_doors.py`).
  위치를 미리 아는 338/337호 문으로 교정
- **338/337 사이 코어는 화장실** — 9배 확대에서 대변기 칸과 중앙 세면대를 확인.
  계단/승강기가 아니므로 통과 동선으로 쓰지 않는다
- **층간 좌표 공유 금지** — 2층 도면은 3층과 원점이 약 51px 어긋난다
  (동일 픽셀 영역의 코어 위치 비교로 확인)

## 설계에서 신경 쓴 것

**「계단 없이」와 「휠체어 접근성」은 다른 조건이다.**
전자는 계단 엣지를 제거하면 끝이고, 후자는 폭·문턱·방향별 경사에 근거가 있어야 한다.
검증 기준 그래프(`data/published/`)로 휠체어 경로를 요청하면
`insufficient_verified_data` 를 돌려주고 어느 구간이 미확인인지 알려준다.

**하드 제약은 탐색 전에 엣지를 제거한다.** 큰 벌점으로 대체하지 않는다.
`no_stairs=true` 면 경로가 없더라도 계단을 자동 허용하지 않는다.

**시간과 선호를 분리한다.** `estimated_time_s` 는 속도·대기 모델에서 나오고
`preference_cost` 는 별도다. 거리 비용의 이름만 초로 바꾼 것이 아니다.

**엘리베이터 대기시간은 1회만 붙는다.** 출발층→도착층을 직접 승차 엣지 하나로
모델링하므로 층을 연쇄로 이어 대기가 중복되는 구조가 애초에 없다.

**unknown 을 0 이나 false 로 바꾸지 않는다.** 모든 접근성 속성은 값과 근거 수준을
함께 갖는다(`unknown` / `drawing_inferred` / `drawing_read` / `official_document` /
`field_measured`).

**탐색은 Dijkstra(h=0)** 를 정확도 기준으로 쓴다. A* 는 모든 엣지에 대한 허용 하한을
증명하고 Dijkstra 비용과 비교한 뒤에만 도입한다.

## 모바일 UI

- 지도가 화면 전체. 경로를 찾으면 **경로 범위에 자동 맞춤 줌**(패딩 12%)
- `devicePixelRatio` 반영, 최대 14배 확대. 확대하면 호실 번호 라벨 표시
- 한 손가락 드래그 이동 / 두 손가락 핀치 줌 (Pointer Events)
- 하단 시트를 드래그로 접기·펼치기 (96px ↔ 88vh)
- 층 선택은 오른쪽 세로 스택. 경로가 지나는 층은 테두리 강조
- 경로선은 흰 테두리 + 파란 본선 2중 렌더
- 단계 안내에 아이콘(🛗 🪜 🚪)과 완료 버튼
- 820px 이상에서는 오른쪽 400px 사이드바로 전환

## 층 표기 불일치 (미해결)

공식 페이지의 탭 이름과 도면 내부 인쇄 표기가 2건 어긋난다.

| 웹 탭 | 파일 | 도면 내부 표기 |
|---|---|---|
| 지하 2층-① | Mirae_B2_1.png | **지상 1층** |
| 지하 2층-② | Mirae_B2_2.png | **지상 2층** |

호실 번호도 각각 1xx / 2xx 계열이어서 도면 내부 표기를 뒷받침한다.
원인을 단정하지 않고 `source_tab_label` / `source_filename` /
`drawing_floor_label` / `canonical_floor_id` 를 각각 다른 필드에 저장했다.
검증 기준 그래프에서 `canonical_floor_id` 는 `null` 이다.
자세한 내용은 `docs/floor_mapping.md`.

## 데이터 상태

| 그래프 | 내용 | 용도 |
|---|---|---|
| `data/demo/mirae_nav_v1.json` | 8개 층 171개 호실, 층별 지도에서 추출 | **시연 기본** |
| `data/demo/mirae_full_v1.json` | 2~7층 45개 호실, 원본 도면 자동추출 | 비교용 |
| `data/published/mirae_indoor_v1.json` | 3층 338/337 + 2층 202, 도면 판독 근거만 | 검증 기준 |

시연용 그래프의 문턱·경사·승강기 규격은 **일반 규격 추정값**이다. 현장 실측이 아니다.
현장에서 확인해야 할 항목은 `docs/data_gaps.md` 에 대상 ID 별로 정리했다.
가장 작은 검증 사이클은 **338/337 문 4개소의 유효폭·문턱 실측**이며, 그것만으로
같은 층 휠체어 경로가 `insufficient_verified_data` → `ok` 로 바뀐다
(`tests/test_mirae_real_graph.py::test_hypothetical_survey_would_make_wheelchair_route_ok`
가 이를 확인한다).

## 구조

```
indoor/
  backend/app/
    models/schema.py      근거 동반 스키마 (Attr, Verification)
    graph/dataset.py      방향 다중그래프 + 구조 검증
    routing/policy.py     하드 제약 / 시간모델 / 선호비용
    routing/engine.py     Dijkstra, 상태 5종, 단계 안내 생성
    intent/parse.py       한국어 요청 -> 구조화 의도 (규칙 기반)
  demo/
    server.py             표준 라이브러리 HTTP 서버 (그래프 3종 동시 로드)
    index.html            모바일 우선 UI
  scripts/
    build_from_navmap.py  층별 지도 -> 그래프 (색상/세선화/골격추적)
    analyze_navmap.py     지도 색상 팔레트 + 원본과의 정합 시도/검증
    collect_floorplans.py 공식 원본 도면 수집 (URL/해시/크기 기록)
    crop_plan.py          판독용 확대·좌표격자 사본
    ocr_win.ps1           Windows.Media.Ocr 텍스트+좌표 추출
    find_walls.py         가로 벽선 / 복도 밴드 탐지
    detect_doors.py       호선 기반 문 검출
    probe_wall.py         벽 개구부 / 픽셀 덤프
    extract_floor.py      원본 도면 층 단위 자동 추출
    build_indoor.py       3층 수동 작도분 -> 검증 기준 그래프
    build_mirae_full.py   원본 도면 기반 전층 그래프
    validate_graph.py     스키마 + 토폴로지 + 근거 검증
    diagnose_indoor.py    연결성 진단
    check_mask.py         통행 마스크 연결성 점검
    route_cli.py          CLI 경로 출력
  tools/editor/           지도 위 노드/엣지 수동 편집기 (JSON 내보내기)
  tests/                  합성 29개 + 실도면 18개
  docs/                   기준 감사 / 원본 목록 / 층 매핑 / 데이터 갭
  data/
    raw/navmaps/          층별 지도 8장
    sources/manifest.json 공식 도면 8장의 URL·SHA-256·크기·판독 상태
    published/ demo/      그래프
```

## 원본 자료

- 공과대학 건물지도: https://engineering.kookmin.ac.kr/engineering/etc/engineering-floor-guide.do
- 북악캠퍼스 안내 (미래관 = S2): https://www.kookmin.ac.kr/user/unIntr/campusGuide/bukakCampusGuide/index.do

공식 평면도 8장의 URL·해시·크기·수집 시각은 `data/sources/manifest.json` 에 있다.
개정일은 도면에 표기가 없어 `null` 이다(HTTP `Last-Modified` 는 서버 파일 시각이므로
개정일로 쓰지 않았다). **이용 조건이 `unknown` 이라 원본 이미지는 저장소에 포함하지 않았다.**
필요하면 `scripts/collect_floorplans.py` 로 수집하고 manifest 의 SHA-256 으로 검증한다.

`data/raw/navmaps/` 의 층별 지도는 원본 도면을 바탕으로 만든 단순화 시각화 시안이다.
AI 로 재렌더링한 것이라 호실명·문·계단·엘리베이터 위치에 오류가 있을 수 있고,
운영 데이터로 쓰기 전에 원본 도면과 현장 조사로 대조해야 한다.

## 한계

- 실외 구간 미등록. 정문에서 미래관까지 경로를 만들지 않았다
- 층별 지도는 단순화 시안이므로 벽·문 위치가 실제와 다를 수 있다
- 호실명은 지도 OCR 결과이며 현장 확인 전이다 (`status: drawing_candidate`)
- 지리 좌표 정합 미수행. 도면/지도 픽셀 좌표만 쓴다
- 실내 자동 측위 없음. 층 선택과 단계 완료 확인 방식 (실내 GPS 로 층을 확정하지 않는다)
- 소요시간은 가정값 기반 추정이다. 확정 도착시간이 아니다
- 엘리베이터 정차층·규격은 추정값이다. 현장 확인 필요
