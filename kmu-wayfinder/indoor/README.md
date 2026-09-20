# 미래관 실내 내비게이션 (indoor)

국민대 미래관의 **실내 경로 안내** 구현. 공개 평면도를 픽셀 분석으로 읽어
층별 복도·문 그래프를 만들고, 한국어 음성/텍스트 요청을 구조화해
계단 회피·휠체어 조건을 반영한 경로를 계산한다.

같은 폴더의 상위 프로젝트(`../index.html`, `../js/`)는 실외 캠퍼스맵 기반
브라우저 전용 구현이고, 이 폴더는 **Python 백엔드 + 실내 평면도** 기반으로
별개 구성이다.

## 지금 되는 것

| 항목 | 상태 |
|---|---|
| 층 | 6개 (2층 ~ 7층) |
| 등록 호실 | 45개 |
| 그래프 | 노드 161 · 엣지 388 · 엘리베이터 1대 · 계단 1개소 |
| 같은 층 경로 | O |
| 층간 경로 (엘리베이터/계단) | O |
| 「계단 없이」 | O |
| 휠체어 조건 | O |
| 한국어 음성 입력 | O (브라우저 Web Speech API, ko-KR) |
| 실외 연결 | X (미등록) |

경로 예시

```
338→337  3층 내        10.7m   14s  계단0  EV0
202→730  2→7층         34.9m   93s  계단0  EV1
338→449  3→4층 빠르게  52.3m   70s  계단1  EV0   ← 1개층은 계단이 빠름
338→449  3→4층 계단없이 35.1m   73s  계단0  EV1   ← 조건 바꾸면 엘리베이터로 우회
338→620  3→6층 휠체어  16.6m   82s  계단0  EV1
```

## 실행

```bash
# 1) 공개 평면도 수집 (저장소에는 원본을 포함하지 않음)
python scripts/collect_floorplans.py

# 2) 그래프 생성
python scripts/extract_floor.py --all        # 3~7층 자동 추출
python scripts/build_indoor.py               # 3층 수동 작도분 (발행 그래프)
python scripts/build_mirae_full.py           # 전층 통합 그래프

# 3) 검증
python scripts/validate_graph.py data/demo/mirae_full_v1.json
python tests/test_routing_synthetic.py       # 29개
python tests/test_mirae_real_graph.py        # 18개

# 4) 데모 서버
python demo/server.py 8844
#    -> http://127.0.0.1:8844   (음성은 Chrome/Edge 에서 동작)

# CLI 로도 확인 가능
python scripts/route_cli.py --graph data/demo/mirae_full_v1.json --from 202 --to 730
python scripts/route_cli.py --graph data/demo/mirae_full_v1.json --from 338 --to 620 --wheelchair
```

의존성은 `requests` 와 `Pillow` 뿐이다. 나머지는 표준 라이브러리.

## 도면을 어떻게 읽었나

미래관 평면도에는 **계단·엘리베이터를 가리키는 텍스트가 전혀 없고 기호 범례도 없다.**
그래서 픽셀 분석으로 구조를 추출했다.

**축척** — 도면 자체의 통줄 치수선에서 산출.
그리드축 ①(x=139.0px) → ⑯(x=1412.0px) = 1273.0px 가 128,350mm → **100.83 mm/px**.
수직 H(y=253.5) → A(y=759.4) = 505.9px 가 50,100mm → 99.03 mm/px.
부분구간 13개가 모두 99~102 범위. 채택값 **0.1008 m/px (±2%)**.

**층 구조** — `scripts/find_walls.py` 로 각 y 행의 어두운 픽셀 비율을 재서 가로 벽선을 찾았다.
3~7층이 같은 도면 프레임을 쓴다 (벽선 y = 333 / 361 / 558 / 592 가 층마다 일치).

```
북측 실열   y 252..333
북측 복도   y 336..360   센터라인 348   폭 2.5m
중앙 실열   y 363..558
남측 복도   y 561..591   센터라인 576   폭 3.1m
남측 실열   y 594..676
```

**문** — 이 도면은 **벽선이 문 위치에서도 끊기지 않고**, 문은 실내쪽 호선(arc)으로만
표현된다. 처음에 '벽의 빈틈'으로 찾다가 실패했고, 벽에 인접한 호선 패턴을 찾는
방식으로 바꿨다 (`scripts/detect_doors.py`). 위치를 미리 아는 338호·337호 문으로
교정한 뒤 나머지 층에 적용했다.

**호실 매칭** — Windows 내장 OCR(`Windows.Media.Ocr`, ko)로 호실 번호와 좌표를 뽑아
(`scripts/ocr_win.ps1`) 같은 실열·x 근접으로 문과 매칭했다.
5층 남측 벽에서 문 67개가 검출된 건 해칭 오검출이라 자동으로 버렸다(벽당 20개 초과 시 폐기).

**남북 복도 연결** — 중앙 실열에서 세로로 벽이 없는 x 구간을 찾아 통로로 연결했다.

## 설계에서 신경 쓴 것

**「계단 없이」와 「휠체어 접근성」은 다른 조건이다.**
전자는 계단 엣지를 제거하면 끝이고, 후자는 폭·문턱·방향별 경사에 근거가 있어야 한다.
`data/published/mirae_indoor_v1.json`(현장 미검증 발행본)으로 휠체어 경로를 요청하면
`insufficient_verified_data` 를 돌려주고 어느 구간이 미확인인지 알려준다.

**하드 제약은 탐색 전에 엣지를 제거한다.** 큰 벌점으로 대체하지 않는다.
`no_stairs=true` 면 경로가 없더라도 계단을 자동 허용하지 않는다.

**시간과 선호를 분리한다.** `estimated_time_s` 는 속도·대기 모델에서 나오고
`preference_cost` 는 별도다. 거리 비용의 이름만 초로 바꾼 것이 아니다.

**엘리베이터 대기시간은 1회만 붙는다.** 출발층→도착층을 직접 승차 엣지 하나로
모델링하므로 층을 연쇄로 이어 대기가 중복되는 구조가 애초에 없다.
2→7층 = 대기 25 + 승하차 10 + 층당 5×5 = 60초, 층별로 쪼개면 아니다.

**unknown 을 0 이나 false 로 바꾸지 않는다.** 모든 접근성 속성은 값과 근거 수준을
함께 갖는다(`unknown` / `drawing_inferred` / `drawing_read` / `official_document` /
`field_measured`). 도면 판독만으로는 휠체어 접근성을 확정하지 않는다.

**층간 좌표를 공유하지 않는다.** 2층 도면(`Mirae_B2_2.png`)은 3층과 원점이 약 51px
어긋난다(동일 픽셀 영역의 코어 위치 비교로 확인). 스키마가 `plan:<floor_id>` 좌표공간
불일치를 예외로 막는다.

**탐색은 Dijkstra(h=0)** 를 정확도 기준으로 쓴다. A* 는 모든 엣지에 대한 허용 하한을
증명하고 Dijkstra 비용과 비교한 뒤에만 도입한다. 소형 그래프에서 완전탐색 최소비용과
일치하는지 테스트로 확인한다.

## 층 표기 불일치 (미해결)

공식 페이지의 탭 이름과 도면 내부 인쇄 표기가 2건 어긋난다.

| 웹 탭 | 파일 | 도면 내부 표기 |
|---|---|---|
| 지하 2층-① | Mirae_B2_1.png | **지상 1층** |
| 지하 2층-② | Mirae_B2_2.png | **지상 2층** |

호실 번호도 각각 1xx / 2xx 계열이어서 도면 내부 표기를 뒷받침한다.
원인을 단정하지 않고 `source_tab_label` / `source_filename` /
`drawing_floor_label` / `canonical_floor_id` 를 각각 다른 필드에 저장했다.
`canonical_floor_id` 는 현장 층 표지 확인 전까지 `null` 이다.
자세한 내용은 `docs/floor_mapping.md`.

## 데이터 상태

| 그래프 | 내용 | 용도 |
|---|---|---|
| `data/published/mirae_indoor_v1.json` | 3층 338/337 + 2층 202, 도면 판독 근거만 | 검증 기준. 가정값 없음 |
| `data/demo/mirae_full_v1.json` | 2~7층 45개 호실 + 엘리베이터/계단 | 시연용 |

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
    server.py             표준 라이브러리 HTTP 서버
    index.html            도면 위 경로 표시 + 음성 입력 + 단계 안내
  scripts/
    collect_floorplans.py 공개 도면 수집 (URL/해시/크기 기록)
    crop_plan.py          판독용 확대·좌표격자 사본
    ocr_win.ps1           Windows.Media.Ocr 텍스트+좌표 추출
    find_walls.py         가로 벽선 / 복도 밴드 탐지
    detect_doors.py       호선 기반 문 검출
    probe_wall.py         벽 개구부 / 픽셀 덤프
    extract_floor.py      층 단위 자동 추출
    build_indoor.py       3층 수동 작도분 -> 발행 그래프
    build_mirae_full.py   전층 통합 그래프 조립
    validate_graph.py     스키마 + 토폴로지 + 근거 검증
    route_cli.py          CLI 경로 출력
  tools/editor/           도면 위 노드/엣지 수동 편집기 (JSON 내보내기)
  tests/                  합성 29개 + 실도면 18개
  docs/                   기준 감사 / 원본 목록 / 층 매핑 / 데이터 갭
  data/
    sources/manifest.json 도면 8장의 URL·SHA-256·크기·판독 상태
    published/            검증 기준 그래프
    demo/                 시연용 그래프
```

## 원본 자료

- 공과대학 건물지도: https://engineering.kookmin.ac.kr/engineering/etc/engineering-floor-guide.do
- 북악캠퍼스 안내 (미래관 = S2): https://www.kookmin.ac.kr/user/unIntr/campusGuide/bukakCampusGuide/index.do

평면도 8장의 URL·해시·크기·수집 시각은 `data/sources/manifest.json` 에 있다.
개정일은 도면에 표기가 없어 `null` 이다(HTTP `Last-Modified` 는 서버 파일 시각이므로
개정일로 쓰지 않았다). 이용 조건은 `unknown` 이라 원본 이미지를 저장소에 포함하지 않았다.

## 한계

- 실외 구간 미등록. 정문에서 미래관까지 경로를 만들지 않았다(확인된 외부 지점이 없어 가상 통로를 만들지 않음).
- 1층(`Mirae_B2_1.png`)과 지하 1층 주차장은 그래프에 없다. 1층은 OCR 인식률이 낮고, 지하 1층은 차량 동선이라 보행로 변환이 필요하다.
- 호실 매칭률이 층마다 다르다(3층 16개 / 5층 4개). 편집기로 수동 보정하면 늘어난다.
- 지리 좌표 정합 미수행. 도면 픽셀 좌표만 쓴다.
- 실내 자동 측위 없음. 층 선택과 단계 완료 확인 방식이다(실내 GPS 로 층을 확정하지 않는다).
- 소요시간은 가정값 기반 추정이다. 확정 도착시간이 아니다.
