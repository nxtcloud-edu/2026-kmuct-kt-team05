# PNG 헤더에서 가로/세로 크기를 읽습니다. (외부 라이브러리 불필요)
import struct, pathlib, sys

p = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "assets/campusmap.png")
data = p.read_bytes()

if data[:8] != b"\x89PNG\r\n\x1a\n":
    out = f"PNG 형식이 아닙니다: {p}"
else:
    w, h = struct.unpack(">II", data[16:24])
    out = f"{p.name}: {w} x {h} px  ({len(data)//1024} KB)  비율 {w/h:.4f}\n" \
          f"현재 코드 좌표계: 829 x 591  비율 {829/591:.4f}"

pathlib.Path("tools/_imgsize.txt").write_text(out, encoding="utf-8")
print("ok")
