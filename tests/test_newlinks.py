"""主催者ページ（新しい抽選ページだけ読む）のテスト  python tests/test_newlinks.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import load_json
import collect

ORG = "https://livepocket.jp/p/hpmzs"
pages = {ORG: '<a href="/e/aaa">ポケモンカード スペシャルデッキセットMEGA</a><a href="/e/bbb">ホロビートカードゲーム</a>'
              '<a href="/e/ccc">ワンピースカードゲーム Heroines</a>',
         "https://livepocket.jp/e/aaa": "<p>抽選 A</p>", "https://livepocket.jp/e/ccc": "<p>抽選 C</p>"}
read = []
def ext(text, *a, **k):
    read.append(text)
    return []
src = [{"id": "lp", "game": "auto", "name": "LP", "type": "html_newlinks", "url": ORG,
        "link_keywords": ["ポケモンカード", "ワンピース"]}]
S = {"game_names": {"pokemon": "ポケカ", "onepiece": "ワンピースカード"}}
collect.collect(src, S, extractor=ext, fetcher=lambda u: pages[u])
n1 = sum(t.count("抽選 ") for t in read)
assert n1 == 2 and not any("ホロビート" in t for t in read), read
read.clear()
pages["https://livepocket.jp/e/aaa"] = "<p>抽選 A 残り1日</p>"   # 中身が変わっても読み直さない
collect.collect(src, S, extractor=ext, fetcher=lambda u: pages[u])
assert not read, read
print("NEWLINKS OK")
