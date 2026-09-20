# 배포 안내

클론만 하면 바로 뜬다. 빌드 단계가 없다.

## 실행

```bash
git clone -b fix/wheelchair-routing https://github.com/nxtcloud-edu/2026-kmuct-kt-team05.git
cd 2026-kmuct-kt-team05/kmu-indoor-nav
python demo/server.py 8950
```

http://<서버주소>:8950

필요한 것은 Python 3.10 이상뿐이다. 외부 패키지도, npm 도 필요 없다.
표준 라이브러리만 쓴다.

확인:

```bash
curl -s localhost:8950/api/status?graph=campus
# {"graph_version":"campus-v1", ...}
```

## Nginx

```nginx
server {
    listen 80;
    server_name _;

    # 이 서버는 인증이 없다. 반드시 접근 제한을 걸 것.
    # allow 1.2.3.4;
    # deny all;

    location / {
        proxy_pass http://127.0.0.1:8950;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

`/proxy/3000/` 같은 하위 경로로 열면 안 된다. 지도와 API 를 절대경로(`/plan/...`,
`/api/...`)로 요청하므로 루트에 붙여야 한다.

## systemd

```ini
[Unit]
Description=KMU indoor nav demo
After=network.target

[Service]
WorkingDirectory=/home/ubuntu/2026-kmuct-kt-team05/kmu-indoor-nav
ExecStart=/usr/bin/python3 demo/server.py 8950
Restart=always
User=ubuntu

[Install]
WantedBy=multi-user.target
```

## 보안 — 먼저 읽을 것

`demo/server.py` 는 Python 표준 `http.server` 기반이고 **인증이 없다.**
프로덕션용 서버가 아니다. 그대로 열면 누구나 접근한다.

최소한 아래 중 하나를 적용할 것.

- 보안그룹에서 접속 IP 를 팀 IP 로 제한
- Nginx basic auth
- 시연 시간에만 기동

## 데이터를 바꿨다면

경로 그래프(`data/published/campus_v1.json`)는 **커밋되어 있다.** 클론 후 바로
쓰라고 그렇게 했다. 원본 데이터를 고쳤다면 다시 만들어 커밋해야 한다.

```bash
cd kmu-indoor-nav
python scripts/import_campus_part.py      # 팀원 그래프 -> 우리 파트
python scripts/merge_graphs.py            # 파트 병합
python scripts/add_stepfree_bypasses.py   # 단차 없는 우회로 추가
python scripts/validate_graph.py data/published/campus_v1.json
```

배치도 주석(EV 대수, 지면 층, 계단 단수)을 지운 사본도 커밋되어 있다.
팀원이 `public/maps/campus.svg` 를 고쳤다면 다시 만들어야 한다.

```bash
python scripts/clean_campus_svg.py
```

## 팀원 Next.js 앱

같은 저장소 루트에 있고 따로 돈다. 우리 UI 를 배포하기로 했으므로 이 앱은
띄우지 않아도 된다. 띄우려면:

```bash
npm ci && npm run build && npm run start   # :3000
```

두 앱은 포트가 다르므로 동시에 띄워도 충돌하지 않는다.

## 아는 문제

- 미래관 외 21개 건물은 건물·층 단위다. 층 안에서 걷는 안내가 없다.
- 접근성 일부는 전제값이다. 경로 응답의 `assumed_accessibility_segments` 로
  집계되고, 휠체어 경로에는 화면에 표시된다. 현장 실측으로 교체해야 한다.
  조사 항목은 `docs/data_gaps.md`.
- 미래관 28개 노드는 계단과 무관하게 고립돼 있다(골격 연결 결함).
