"""本文の中に応募ページのURLを書き込むテスト  python tests/test_fetch_links.py"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from fetch import html_to_text

h = ('<p>' + 'あ' * 20000 + '</p><p>フルコンプ（8店舗）応募は<a href="https://livepocket.jp/e/x425p">フルコンプ</a>から</p>'
     '<p>SHIBUYA TSUTAYA <a href="https://cloud-pass.jp/pr/abc">こちら</a></p><a href="/archives/1">前の記事</a>')
t = html_to_text(h, "https://nyuka-now.com/a")
i = t.index("フルコンプ（8店舗）")
assert "https://livepocket.jp/e/x425p" in t[i:i + 80]      # 店の文のすぐそばにURL（長い記事で切れても残る）
assert "https://cloud-pass.jp/pr/abc" in t
assert "archives/1" not in t.split("[関連リンク]")[0]       # ふつうのリンクは本文に書き込まない
print("FETCH LINKS OK")
