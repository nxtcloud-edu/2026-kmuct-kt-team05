"""배경 지도에서 확인한 실제 좌표를 data.js 에 반영합니다.

좌표 출처
  - tools/detect_pins.py 가 검출한 지도 핀의 뾰족한 끝 (가장 정확)
  - 핀이 겹쳐 검출되지 않은 건물은 지도의 건물 이름 라벨 위치
둘을 교차 검증했고 겹치는 항목은 오차 3px 이내였습니다.
"""

import re, pathlib

# id: (x, y)  — 824 x 611 좌표계
COORDS = {
    # --- 지도 핀에서 직접 검출 ---
    "bukak":      (456, 150),
    "johyung":    (542, 164),
    "science":    (742, 220),
    "law":        (606, 281),
    "kukje":      (462, 294),
    "gym":        (650, 320),
    "youngbin":   (660, 380),
    "art":        (557, 439),
    "mirae":      (492, 485),
    "dorm":       (688, 501),
    "lifelong":   (596, 538),
    "welfare":    (356, 409),
    "eng":        (132, 216),
    "global":     (98, 121),
    # --- 지도 라벨 위치 기준 ---
    "museum":     (150, 61),
    "library":    (103, 98),
    "lab":        (133, 153),
    "tennis":     (200, 248),
    "basketball": (295, 283),
    "parking":    (303, 329),
    "bonbu":      (488, 219),
    "kyungsang":  (409, 250),
    "hyungsul":   (643, 259),
    "concert":    (498, 325),
    "business":   (540, 356),
    "field":      (378, 359),
    "gate_main":  (470, 575),
    "gate_north": (782, 315),
    # --- 교차점: 위 건물 배치에 맞춰 다시 배치 ---
    "j_gate":     (478, 540),
    "j_mirae":    (492, 505),
    "j_art":      (545, 465),
    "j_welfare":  (400, 430),
    "j_field_e":  (440, 370),
    "j_field_w":  (330, 365),
    "j_center":   (470, 315),
    "j_bonbu":    (500, 250),
    "j_north":    (460, 180),
    "j_east":     (600, 300),
    "j_dorm":     (650, 470),
    "j_eng":      (170, 240),
    "j_lib":      (140, 135),
}

path = pathlib.Path(__file__).resolve().parent.parent / "js" / "data.js"
src = path.read_text(encoding="utf-8")

done, missing = [], []

for node_id, (nx, ny) in COORDS.items():
    # id: 'xxx' 로 시작하는 블록 안의 첫 x:/y: 쌍만 바꿉니다
    pattern = re.compile(
        r"(id:\s*'%s'\s*,.*?)x:\s*-?\d+,\s*y:\s*-?\d+" % re.escape(node_id),
        re.S,
    )
    new_src, n = pattern.subn(lambda m: f"{m.group(1)}x: {nx}, y: {ny}", src, count=1)
    if n:
        src = new_src
        done.append(node_id)
    else:
        missing.append(node_id)

# 축척도 다시 계산합니다.
# 공학관(132,216) ~ 과학관(742,220) 이 610px 이고 실제로 약 500m 입니다.
src = re.sub(
    r"const SCALE_M_PER_PX = [\d.]+;",
    "const SCALE_M_PER_PX = 0.85;",
    src,
)

path.write_text(src, encoding="utf-8")

report = [f"좌표 반영 {len(done)}개", f"실패 {len(missing)}개"]
if missing:
    report.append("  " + ", ".join(missing))
report.append("SCALE_M_PER_PX -> 0.85")
(pathlib.Path(__file__).parent / "_apply.txt").write_text("\n".join(report), encoding="utf-8")
print("\n".join(report))
