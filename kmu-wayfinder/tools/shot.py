"""앱을 헤드리스로 띄워 화면을 PNG 로 저장합니다. 지도 정렬을 눈으로 확인할 때 씁니다.

사용법:
    py tools/shot.py                 # 전체 화면
    py tools/shot.py map             # 지도만 (viewBox 전체)
"""

import subprocess, pathlib, sys, tempfile, textwrap

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
]

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent

mode = sys.argv[1] if len(sys.argv) > 1 else "full"


def browser():
    for p in EDGE_CANDIDATES:
        if pathlib.Path(p).exists():
            return p
    raise SystemExit("브라우저를 찾을 수 없습니다.")


if mode == "map":
    # 지도만 크게 보기 위한 임시 페이지.
    # assets/ 와 js/ 상대경로가 맞아야 하므로 프로젝트 루트에 만듭니다.
    page = ROOT / "_shot_map.html"
    route = sys.argv[2] if len(sys.argv) > 2 else "gate_main,bukak,fastest"
    a, b, m = route.split(",")
    page.write_text(textwrap.dedent(f"""\
        <!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
        <style>
          html,body{{margin:0;background:#fff}}
          #map{{display:block;width:1648px;height:1222px}}
        </style></head><body>
        <svg id="map"></svg>
        <script src="js/data.js"></script>
        <script src="js/graph.js"></script>
        <script src="js/parse.js"></script>
        <script src="js/render.js"></script>
        <script>
          MapView.init({{ svg: document.getElementById('map'), onSelect: function(){{}} }});
          var r = findRoute('{a}','{b}','{m}');
          MapView.setEndpoints('{a}','{b}');
          MapView.showRoute(r);
        </script>
        </body></html>
    """), encoding="utf-8")
    size = "1648,1222"
    out = HERE / "_shot_map.png"
else:
    page = ROOT / "index.html"
    size = "1500,1400"
    out = HERE / "_shot_app.png"

with tempfile.TemporaryDirectory() as profile:
    subprocess.run(
        [browser(), "--headless=new", "--disable-gpu", "--no-first-run",
         "--no-default-browser-check", "--allow-file-access-from-files",
         "--hide-scrollbars", f"--user-data-dir={profile}",
         f"--window-size={size}", "--virtual-time-budget=9000",
         f"--screenshot={out}", page.as_uri()],
        capture_output=True, timeout=180,
    )

print("SAVED" if out.exists() else "FAILED", out)
