"""
국민대학교 캠퍼스 접근성 경로안내 - 설정

좌표계: WGS84 (EPSG:4326)
캠퍼스 경계는 OSM way 173018858 (국민대학교 / Kookmin University) 의 bounding box.
"""

# --- 캠퍼스 영역 --------------------------------------------------------------
# OSM way 173018858 bbox 를 약간 여유있게 확장한 값
CAMPUS_BBOX = (37.6088, 126.9918, 37.6143, 127.0002)  # (minlat, minlon, maxlat, maxlon)

# --- 외부 서비스 --------------------------------------------------------------
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# 고도 데이터셋. 검증 단계에서는 ASTER GDEM 30m 을 사용한다.
# 교차검증 결과 srtm30m / mapzen 과 지점별 2~7m 차이. 추세는 일치하나
# 30m 격자이므로 개별 구간 경사의 절대값은 신뢰하지 않는다 (README 참고).
DEM_DATASET = "aster30m"
ELEVATION_URL = "https://api.opentopodata.org/v1/{dataset}"
ELEVATION_INTERPOLATION = "bilinear"  # 짧은 엣지에서 계단현상(blocky) 완화
ELEVATION_BATCH = 100                 # opentopodata 공개 API 한 요청당 최대 좌표 수
ELEVATION_SLEEP = 1.1                 # 초당 1회 제한 준수

USER_AGENT = "kmu-campus-accessible-nav/0.1 (capstone research)"

# --- 보행 가능 도로 종류 ------------------------------------------------------
# 캠퍼스 내부 도로는 residential/service 로 태깅된 경우가 많아 포함한다.
# primary/trunk (북악산로, 정릉로 등) 는 캠퍼스 경계 외곽 차도이므로 제외.
WALKABLE_HIGHWAYS = {
    "footway",
    "path",
    "pedestrian",
    "steps",
    "corridor",
    "living_street",
    "service",
    "residential",
    "unclassified",
    "track",
}

# --- 이동 프로파일 ------------------------------------------------------------
# w(e) = L * (1 + alpha * max(0, |grade| - grade_free) ** p) + stair_penalty
#
# p(grade_exponent) 를 왜 2 로 두는가
# ---------------------------------
# p=1 로 두면 오르막 경로에서 페널티 총합이
#     sum L*alpha*(|g|-g0) = alpha*(sum|dz| - g0*L_total)
# 가 되고, sum|dz| 는 출발/도착 고도차로 고정된 상수다. 따라서 총비용이
#     L_total*(1 - alpha*g0) + const
# 로 환원되어 경사항이 경로 선택에 영향을 주지 못한다(최단거리와 동일해).
# p=2 로 두면 페널티가 alpha*dz^2/L 형태가 되어, 같은 고도차를 더 긴 거리에
# 나눠 오르는 경로가 실제로 유리해진다. 이것이 완만한 우회로를 찾는 핵심이다.
#
# alpha 값의 근거 (고도 50m 상승, p=2 기준)
#   경로 A: 200m @ 25%   경로 B: 600m @ 8.3%
#   휠체어가 B 를 고르려면 alpha > 49 가 필요 -> 200 채택
#   노약자는 B 를 약간 선호하는 수준 -> 60
#   일반은 항상 최단거리 -> 1
#
# 설계 원칙:
#   - 계단(steps)은 OSM 의 확정 정보이므로 휠체어는 무한 비용(완전 차단).
#   - 경사(grade)는 30m DEM 추정치이므로 하드 컷오프 판정에 쓰지 않고
#     연속 페널티로만 반영한다.
PROFILES = {
    "normal": {
        "label": "일반",
        "alpha": 1.0,
        "grade_exponent": 2.0,
        "grade_free": 0.12,
        "stair_cost_per_m": 0.3,   # 계단이 오히려 지름길인 경우가 많음
        "stairs_blocked": False,
        "max_grade": None,
    },
    "elderly": {
        "label": "노약자",
        "alpha": 60.0,
        "grade_exponent": 2.0,
        "grade_free": 0.04,
        "stair_cost_per_m": 8.0,   # 가급적 회피하되 통행 자체는 가능
        "stairs_blocked": False,
        "max_grade": None,
    },
    "wheelchair": {
        "label": "휠체어",
        "alpha": 200.0,
        "grade_exponent": 2.0,
        "grade_free": 0.02,
        "stair_cost_per_m": None,  # 통행 불가
        "stairs_blocked": True,
        # 참고용 상한. 하드 차단이 아니라 리포트에서 위반 구간 표시용.
        # DEM 오차 때문에 차단 근거로는 쓰지 않는다.
        "max_grade": 0.0833,       # 1/12, 국내 경사로 기준으로 알려진 값
    },
}

# --- 고도 스무딩 --------------------------------------------------------------
# OSM 보행로 엣지의 87% 가 길이 30m 미만인데 DEM 격자는 30m 다.
# 즉 짧은 엣지의 경사는 대부분 보간 노이즈다.
# way 방향으로 이동평균을 걸어 노이즈를 줄인다. 0 이면 스무딩 없음.
SMOOTH_HALF_WINDOW_M = 20.0

# 경사 계산 시 분모의 최소값(m).
# DEM 은 30m 격자이므로 그보다 훨씬 짧은 구간의 경사는 물리적 의미가 없다.
# 1~2m 짜리 엣지에서 고도차가 나눠지면 경사가 100% 를 넘는 인공물이 생기므로
#     grade = dz / max(L, MIN_GRADE_BASELINE_M)
# 으로 감쇠시킨다. dz 자체는 그대로 두므로 누적 상승고도 집계는 영향을 받지 않는다.
MIN_GRADE_BASELINE_M = 15.0

# --- 파일 경로 ----------------------------------------------------------------
import pathlib

DATA_DIR = pathlib.Path(__file__).parent / "data"
RAW_OSM = DATA_DIR / "raw_osm.json"
ELEV_CACHE = DATA_DIR / "elevation_cache.json"
GRAPH = DATA_DIR / "graph.json"
ROUTES_GEOJSON = DATA_DIR / "routes.geojson"
GRAPH_GEOJSON = DATA_DIR / "graph.geojson"
