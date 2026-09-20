# 국민대 길찾기

음성이나 텍스트로 목적지를 말하면 경로를 안내한다. 일반 사용자에게는 빠른 길,
휠체어 사용자에게는 계단 없는 길을 준다.

## 지금 되는 것

```
                     미래관              그 외 건물
장소                 호실 180개          건물+층 (예: 종합복지관 1층)
노드                 813개 (문 단위)     6~16개 (층 단위)
층 안에서 걷는 안내    "복도 28m"          없음
지도                 층별 도면 8장        캠퍼스 배치도 위 마커
```

미래관만 실제 실내 내비게이션이다. 나머지 21개 건물은 건물·층 단위 이동 안내다.
경로 자체는 캠퍼스 어디서든 미래관 호실까지 이어진다.

```
북악관 1층 → 미래관 338호      421m  5.8분  단계 14개
종합복지관 1층 → 미래관 338호   133m  1.9분  단계  4개
미래관 202호 → 730호            99m  2.4분  엘리베이터 1회
```

## 구성

경로 계산은 Python 엔진 하나가 전부 담당한다. 데이터는 파트로 나눠 관리하고
병합해서 쓴다.

```
kmu-indoor-nav/
  data/parts/campus.json          실외 + 미래관 외 건물   217노드   860엣지
  data/parts/mirae.json           미래관 실내 (문 단위)   813노드  2344엣지
  data/links/campus-mirae.json    두 파트를 잇는 연결      18엣지
        │
        │  scripts/merge_graphs.py
        ▼
  data/published/campus_v1.json   1030노드  3222엣지  (생성물, 커밋 안 함)
```

`data/parts/campus.json` 은 팀원이 만든 캠퍼스 그래프(`data/campus-graph.json`)를
`scripts/import_campus_part.py` 로 들여온 것이다. 미래관 15개 층 노드는 버리고
우리 실내 그래프 813노드로 대체하되, 거기 붙어 있던 외부 연결 9개는 층별
대표 노드로 재부착했다.

## 실행

```bash
cd kmu-indoor-nav

# 1) 팀원 그래프를 파트로 들여오기
python scripts/import_campus_part.py

# 2) 파트 병합
python scripts/merge_graphs.py

# 3) 검증
python scripts/validate_graph.py data/published/campus_v1.json

# 4) 실행
python demo/server.py 8930     # http://127.0.0.1:8930
```

`?graph=nav` 를 붙이면 미래관만 담긴 그래프로 볼 수 있다.

데모 서버는 로컬 전용이며 인증이 없다. 외부에 노출하지 말 것.

## 근거 수준을 파트가 선언한다

휠체어 경로 판정에 요구하는 최소 근거를 파트마다 다르게 선언한다.

```
mirae   field_measured     현장 실측을 요구한다 (기존 정책)
campus  drawing_inferred   OSM + 학생 제보. 현장 실측이 아니다
```

실내 기준을 실외에 그대로 적용하면 실외 전체가 휠체어 경로에서 빠진다.
그래서 파트 단위로 낮춰 선언하되, 정책 쪽에 절대 하한
(`Constraints.absolute_min_verification`)을 둬서 데이터가 정책을 무력화하지
못하게 했다. 파트가 무엇을 선언해도 `unknown` 은 통행 가능이 되지 않는다.

## 층 단위 건물을 지나는 비용을 보정했다

팀원 그래프는 건물 한 층을 노드 하나로 모델한다. 그러면 건물에 들어온 지점과
나가는 지점이 같은 노드라서 **건물을 가로질러도 거리가 0** 이다. 그대로 두면
건물 관통이 밖으로 돌아가는 것보다 싸져서, 라우터가 건물 여러 개를 뚫고 가는
경로를 고른다.

```
보정 전   북악관 → 콘서트홀 → 경영관 → 경영관B1 → 예술관 → 예술관B1
          → 예술관B2 → 미래관2층      349.7m   건물 4개 관통
보정 후   북악관 → 실외 166m → 경영관 통과 → 실외 → 미래관4층
          → 복도 86m → 계단 → 3층      441.7m   건물 1개 통과
```

새 숫자를 만들지 않고 팀원 assumptions 의 `elevatorAccessM`(22m, '출입구에서
엘리베이터까지 걷는 거리')을 쓴다. 건물에 닿는 통과성 엣지마다 절반을 물린다.

```
들어가서 멈춤   11m
통과           22m
```

추정값이므로 해당 엣지는 `length_is_assumed` 로 표시되고, 경로 응답의
`assumed_length_segments` / `assumed_length_m` 에 집계된다. 현재 3222개 중
188개가 가정 길이다. 건물별 실내 그래프가 생기면 이 허용치는 빼야 한다.

## 경로 상태가 4가지다

```
ok                       조건을 만족하고 근거도 있다
candidate_unverified     경로는 있지만 접근성 근거가 없는 구간을 지난다
insufficient_verified_data   근거 없는 구간을 빼면 경로가 없다
no_route_under_constraints   조건 자체를 만족하는 경로가 없다
```

`candidate_unverified` 는 호출부가 `allow_unverified_as_candidate` 로 명시
요청할 때만 나온다. UI 의 `후보까지 보기` 토글이 이것이며, 화면에
`접근성 미확인` 배지와 조사 대상 구간 수가 함께 뜬다. `ok` 와 섞이지 않는다.

## 확인된 한계

**북악관은 휠체어로 빠져나갈 수 없다.** 건물에서 나오는 출구 자체는 계단이
없지만, 바로 밖 보행로가 계단으로 막혀 있다. 계단을 제외하면 북악관 1층에서
도달 가능한 노드가 1002개에서 17개로 줄고, 미래관 785개는 0개가 된다.
등록된 데이터상 사실이며 현장에서 확인해야 한다.

**현장 미검증.** 문턱·유효폭·경사·승강기 정차층은 도면 판독이나 추정값이다.
조사 대상은 `docs/data_gaps.md` 에 ID별로 정리했다.

**미래관 1층 102호는 휠체어로 도달할 수 없다.** 복도 연결 일부가 벽을 지나는
구간도 남아 있다 (골격 연결 단계에서 생김).

## 팀원 Next.js 앱

저장소 루트의 Next.js 앱에도 미래관 실내 데이터가 들어가 있다
(`scripts/export_to_campus_graph.py` 가 생성). 다만 경로 계산과 화면은
위의 Python 엔진과 `demo/` 를 쓴다.

```bash
python kmu-indoor-nav/scripts/export_to_campus_graph.py
npm run dev
```

변환은 항상 `data/campus-graph.base.json` (팀원 원본 스냅샷)을 기준으로 한다.
변환 결과를 다시 입력으로 쓰면 재부착한 외부 연결이 내부 엣지로 오인되어
삭제된다. 두 번 실행해도 결과가 같다.

## 테스트

```bash
cd kmu-indoor-nav
python -m pytest tests/ -q
```

```
test_routing_synthetic   29    합성 그래프로 정책·제약 검증
test_mirae_real_graph    18    실제 미래관 그래프
test_merge_parts         10    파트 병합 규칙
```

## 다른 건물 확장

`scripts/build_from_navmap.py` 에 층별 도면 이미지를 넣으면 미래관과 같은
수준(호실 단위, 복도 안내)으로 만들 수 있다. 색상 분류 → 복도/호실 분리 →
골격화 → 그래프 생성까지 자동이다. 필요한 것은 도면뿐이다.
