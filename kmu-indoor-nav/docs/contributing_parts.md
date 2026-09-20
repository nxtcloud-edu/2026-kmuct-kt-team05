# 파트 나눠 작업하고 합치기

여러 사람이 다른 건물·실외를 동시에 만들 때의 규약이다.

## 핵심 원칙

**같은 파일을 두 사람이 고치지 않는다.** 그래프를 단일 JSON 한 개로 두면
팀원 A가 공학관, B가 실외를 작업할 때 매번 git 충돌이 난다.
그래서 파트 단위로 파일을 나누고 **빌드 시점에 병합**한다.

```
data/parts/mirae.json        ← 이태곤 소유
data/parts/gonghak.json      ← 담당자 B 소유
data/parts/outdoor.json      ← 담당자 C 소유
data/links/outdoor-mirae.json  ← 파트를 잇는 연결만
        ↓  python scripts/merge_graphs.py
data/published/campus_v1.json  ← 산출물. 직접 편집 금지
```

병합 산출물은 `.gitignore` 대상이다. 커밋하는 것은 **파트 파일과 연결 파일뿐**이다.
그래야 서로 다른 파트를 동시에 머지해도 충돌이 없다.

## 시작하는 방법

```bash
# 1) 템플릿 복사
cp data/parts/_TEMPLATE.json data/parts/gonghak.json

# 2) part 블록 수정  (파일명과 id 가 같아야 한다)
#    "part": {"id": "gonghak", "namespace": "gonghak/", "kind": "building", "owner": "이름"}

# 3) 작업하면서 계속 검사
python scripts/merge_graphs.py --check

# 4) 통과하면 병합 + 검증 + 경로 확인
python scripts/merge_graphs.py
python scripts/validate_graph.py data/published/campus_v1.json
python scripts/route_cli.py --graph data/published/campus_v1.json --from 352 --to 338
```

이미 단일 그래프를 만들어 둔 경우에는 변환기를 쓴다.

```bash
python scripts/to_part.py data/demo/my_graph.json gonghak building "담당자이름"
```

## 규칙 1 — ID 네임스페이스

파트 안의 모든 id 는 `<part-id>/` 로 시작한다. 병합기가 강제한다.

```
gonghak.json  →  gonghak/F3/352, gonghak/F3/door/352, gonghak/ev/1
outdoor.json  →  outdoor/n/1024, outdoor/e/88
```

`building_id` 처럼 네임스페이스 루트 자체(`gonghak`)를 가리키는 것은 허용된다.

도면 좌표공간도 자기 네임스페이스여야 한다.

```json
"plan_point": {"coordinate_space": "plan:gonghak/F3", "x_px": 500, "y_px": 300}
```

이 규칙 덕분에 두 사람이 우연히 같은 id 를 써서 서로를 덮어쓰는 일이 구조적으로 불가능하다.

## 규칙 2 — 파트 간 연결은 links 에만

실외 보행로와 건물 출입구를 잇는 엣지를 파트 파일에 쓰면, 양쪽 담당자가
같은 파일을 고쳐야 해서 충돌이 난다. 그래서 별도 파일로 뺀다.

```bash
cp data/links/_TEMPLATE.json data/links/outdoor-mirae.json
```

```json
{
  "links": [{
    "id": "link/outdoor-mirae-entrance1",
    "from_node": "outdoor/n/1024",
    "to_node": "mirae/F1/entrance/1",
    "kind": "entrance",
    "...": "나머지 필드는 템플릿 참고"
  }]
}
```

병합기가 검사하는 것

- 양쪽 노드가 실제로 존재하는가
- 양끝이 서로 다른 파트인가 (같은 파트면 파트 파일에 쓰라고 거부한다)
- id 가 다른 어떤 것과도 겹치지 않는가

**양방향 통행이면 `/rev` 엣지를 직접 하나 더 쓴다.** 자동 생성하지 않는다.
출입 제한이나 일방향 동선이 있을 수 있기 때문이다.

## 규칙 3 — 출입구 노드를 미리 만들어 둔다

실외 담당자가 건물에 붙이려면 붙일 지점이 있어야 한다.
건물 담당자는 `entrance_inside` 노드를 만들고 **어느 층과 만나는지** 명시한다.

```json
{
  "id": "gonghak/F1/entrance/1",
  "kind": "entrance_inside",
  "floor_id": "gonghak/F1",
  "name": "주 출입구(실내측)",
  "notes": ["실외 파트와 이을 지점"]
}
```

국민대는 경사 캠퍼스라 **한 건물이 여러 층에서 지면과 만난다.**
출입구마다 만나는 층이 다를 수 있으니 출입구를 층별로 따로 만든다.
이게 배리어프리 경로의 핵심이다 — 계단 대신 다른 층 출입구로 들어가면 되는 경우가 있다.

## 규칙 4 — unknown 을 0 이나 false 로 바꾸지 않는다

```json
"clear_width_m": {"value": null, "verification": "unknown"}
```

모르는 값은 `unknown` 으로 둔다. 0 이나 `false` 로 채우면 라우터가
"폭 0m 통로" 또는 "문턱 없음"으로 잘못 판단한다.
`unknown` 자체가 정보다 — 휠체어 경로 요청 시 `insufficient_verified_data` 와
함께 어느 구간을 조사해야 하는지 알려준다.

근거 수준은 5단계다.

```
unknown → drawing_inferred → drawing_read → official_document → field_measured
```

휠체어 접근성 판정에는 `field_measured` 가 필요하다.

## 규칙 5 — 축척을 모르면 거리를 쓰지 않는다

```json
"scale_m_per_px": {"value": null, "verification": "unknown"}
```

축척이 `unknown` 인 층의 엣지에 길이를 채우면 `validate_graph.py` 가
치명적 오류로 막는다. 다른 층의 축척을 복사해서 쓰지 않는다.
도면마다 원점·축척이 다를 수 있다 (미래관 2층 도면은 3층과 원점이 약 51px 어긋난다).

## git 작업 흐름

```bash
# 파트마다 브랜치를 따로 만든다
git checkout -b feat/gonghak-indoor

# 자기 파일만 스테이징한다
git add data/parts/gonghak.json data/raw/gonghak/

# 커밋 후 PR
git push -u origin feat/gonghak-indoor
gh pr create --base main --title "feat(gonghak): 공학관 실내 그래프"
```

PR 을 올리기 전에 반드시 통과시킨다.

```bash
python scripts/merge_graphs.py --check
python tests/test_merge_parts.py
python scripts/validate_graph.py data/published/campus_v1.json
```

머지 순서는 상관없다. 파트 파일이 서로 겹치지 않으므로 git 이 자동 병합한다.
`data/links/` 만 여러 사람이 같은 파일을 건드릴 수 있으니, **연결 파일도
파트 조합별로 쪼갠다** (`outdoor-mirae.json`, `outdoor-gonghak.json`).

## 충돌이 났을 때

| 증상 | 원인 | 해결 |
|---|---|---|
| `파일명과 part.id 가 다릅니다` | 템플릿 복사 후 `part.id` 를 안 고쳤다 | 파일명과 `part.id` 를 맞춘다 |
| `네임스페이스 중복` | 두 파트가 같은 `namespace` 를 쓴다 | 한쪽을 고유한 값으로 |
| `id 충돌` | 같은 id 를 두 파일이 쓴다 | 네임스페이스 규칙을 다시 확인 |
| `로 시작해야 함` | 남의 네임스페이스를 침범했다 | 자기 접두어로 바꾼다 |
| `어느 파트에도 없는 노드` | 상대 파트가 아직 그 노드를 안 만들었다 | 상대 PR 이 머지된 뒤 연결한다 |
| `같은 파트 내부 연결` | links 에 자기 파트 내부 엣지를 썼다 | 파트 파일로 옮긴다 |
| `축척 unknown 인 층의 엣지에 길이가 채워져 있음` | 축척 없이 거리를 넣었다 | 축척을 산출하거나 길이를 `unknown` 으로 |

## 파트를 나누는 기준

| kind | 범위 | 좌표 |
|---|---|---|
| `building` | 건물 1개 전층 | 도면 픽셀 (`plan:<part>/<floor>`) |
| `outdoor` | 실외 보행로 | 지리 좌표 (`geo_point`) |
| `area` | 광장·주차장 등 | 둘 중 적합한 쪽 |

건물 하나를 여러 명이 나누려면 층이 아니라 **동(wing)** 으로 나누는 게 낫다.
층으로 나누면 엘리베이터·계단이 양쪽에 걸쳐 연결 선언이 복잡해진다.

## 현재 상태

```
data/parts/mirae.json    건물   층 8  장소 171  노드 567  엣지 1600  승강기 1
```

`python scripts/merge_graphs.py` 로 `campus_v1.json` 생성 확인,
`validate_graph.py` 치명적 0건, `tests/test_merge_parts.py` 10/10 통과.
