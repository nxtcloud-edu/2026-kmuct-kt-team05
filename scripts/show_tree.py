"""저장소 트리 요약 (충돌 점검용)."""
import json
import pathlib
import sys

p = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "data/work/repotree.json")
d = json.loads(p.read_text(encoding="utf-8"))
tree = d.get("tree", [])
print(f"총 {len(tree)}개 항목")
for t in sorted(tree, key=lambda x: x["path"]):
    size = t.get("size", "")
    print(f"  {t['type']:4} {str(size):>8}  {t['path']}")
