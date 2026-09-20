"""selftest.html 을 Edge 헤드리스로 실행해 결과를 tools/_result.txt 에 저장합니다.

사용법:
    py tools/runtest.py          # 로직 회귀 테스트
    py tools/runtest.py app      # index.html 이 오류 없이 뜨는지 확인

Node 가 없는 환경을 위해 브라우저를 테스트 러너로 씁니다.
PowerShell 파이프를 거치지 않으므로 한글이 깨지지 않습니다.
"""

import subprocess, re, html, pathlib, sys, tempfile

EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def find_browser() -> str:
    for path in EDGE_CANDIDATES:
        if pathlib.Path(path).exists():
            return path
    raise SystemExit("Edge 나 Chrome 을 찾을 수 없습니다. EDGE_CANDIDATES 에 경로를 추가하세요.")


def dump_dom(page: pathlib.Path) -> tuple[str, str]:
    browser = find_browser()
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.run(
            [
                browser,
                "--headless=new",
                "--disable-gpu",
                "--no-first-run",
                "--no-default-browser-check",
                "--allow-file-access-from-files",
                f"--user-data-dir={profile}",
                "--virtual-time-budget=8000",
                "--dump-dom",
                page.as_uri(),
            ],
            capture_output=True,
            timeout=180,
        )
    return (
        proc.stdout.decode("utf-8", errors="replace"),
        proc.stderr.decode("utf-8", errors="replace"),
    )


def console_errors(stderr: str) -> list[str]:
    keys = ("SyntaxError", "ReferenceError", "TypeError",
            "Uncaught", "is not defined", "is not a function")
    return [l for l in stderr.splitlines() if any(k in l for k in keys)]


def run_selftest() -> str:
    dom, stderr = dump_dom(HERE / "selftest.html")
    m = re.search(r'<pre id="out">(.*?)</pre>', dom, re.S)

    lines = []
    if m:
        lines.append(html.unescape(m.group(1)))
    else:
        lines.append(f"결과 블록을 찾지 못했습니다. DOM 길이 {len(dom)}")
        lines.append(dom[:2000])

    errs = console_errors(stderr)
    lines.append("")
    lines.append(f"콘솔 오류: {'없음' if not errs else str(len(errs)) + '건'}")
    lines.extend("  " + e for e in errs[:20])
    return "\n".join(lines)


def run_app_check() -> str:
    dom, stderr = dump_dom(ROOT / "index.html")
    lines = [f"DOM 길이 {len(dom)}", ""]

    def grab(pattern, label, closing):
        m = re.search(pattern % closing, dom, re.S)
        val = re.sub(r"<[^>]+>", "", html.unescape(m.group(1))).strip() if m else ""
        lines.append(f"{label}: {val or '(빈값)'}")

    grab(r'id="result-mode"[^>]*>(.*?)</%s>', "선택된 모드", "span")
    grab(r'id="result-summary"[^>]*>(.*?)</%s>', "경로 요약", "strong")
    grab(r'id="result-sentence"[^>]*>(.*?)</%s>', "안내 문장", "p")
    grab(r'id="health-badge"[^>]*>(.*?)</%s>', "데이터 점검 배지", "span")

    steps = re.search(r'id="step-list"[^>]*>(.*?)</ol>', dom, re.S)
    lines.append(f"안내 단계 수: {len(re.findall(r'<li', steps.group(1))) if steps else 0}")
    lines.append(f"지도 건물 노드: {len(re.findall(r'class=.map-node', dom))}")
    lines.append(f"모드 버튼: {len(re.findall(r'class=.mode-btn', dom))}")

    card = re.search(r'id="result-card"([^>]*)>', dom)
    lines.append("결과 카드: " + ("표시됨(정상)" if card and "hidden" not in card.group(1) else "숨김 ← 확인 필요"))

    errs = console_errors(stderr)
    lines.append("")
    lines.append(f"콘솔 오류: {'없음' if not errs else str(len(errs)) + '건'}")
    lines.extend("  " + e for e in errs[:20])
    return "\n".join(lines)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    report = run_app_check() if mode == "app" else run_selftest()

    out = HERE / "_result.txt"
    out.write_text(report, encoding="utf-8")

    # 콘솔 인코딩이 한글을 못 받는 환경도 있으므로 파일이 정본입니다.
    print(f"결과를 {out} 에 저장했습니다.")
    try:
        print(report)
    except UnicodeEncodeError:
        print("(콘솔 인코딩 문제로 출력 생략 — 파일을 확인하세요)")
