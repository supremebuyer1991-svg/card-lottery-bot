"""Googleアナリティクスのタグ入れのテスト  python tests/test_ga.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import sitegen

d = Path(tempfile.mkdtemp())
(d / "a").mkdir()
(d / "index.html").write_text("<html><head><title>t</title></head><body><footer><p>x</p></footer></body></html>", encoding="utf-8")
(d / "a" / "index.html").write_text("<html><head></head><body>no footer</body></html>", encoding="utf-8")
(d / "x-draft.html").write_text("<html><head></head><body></body></html>", encoding="utf-8")

assert sitegen.inject_ga(d, "") == 0 and sitegen.inject_ga(d, "UA-123") == 0  # IDがない・形がちがう → 何もしない
assert sitegen.inject_ga(d, "G-ABC123XYZ") == 2
h = (d / "index.html").read_text(encoding="utf-8")
assert h.count("gtag/js?id=G-ABC123XYZ") == 1 and h.index("gtag/js") < h.index("</head>") and "Googleアナリティクス" in h
assert "gtag/js" in (d / "a" / "index.html").read_text(encoding="utf-8")
assert "gtag" not in (d / "x-draft.html").read_text(encoding="utf-8")  # 自分用のページは数えない
assert sitegen.inject_ga(d, "G-ABC123XYZ") == 0  # 2回入れない
print("GA OK")
