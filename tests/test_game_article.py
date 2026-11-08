"""ゲーム側：RSSの記事を開いて本文（プレバンの商品ページ）まで読む。トレカ側（設定なし）は今まで通りタイトルだけ"""
import os, sys, tempfile, pathlib
os.environ["SITE"] = "game"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = pathlib.Path(tempfile.mkdtemp())
import collect
RSS = """<rss><channel><item><title>HG ヴァサーゴ抽選</title><link>https://news.example.jp/a/1</link><guid>g1</guid>
<pubDate>Sat, 07 Nov 2026 10:00:00 +0900</pubDate><description>要約だけ</description></item></channel></rss>"""
ART = '<html><body><p>抽選期間は11月9日15時まで。</p><a href="https://p-bandai.jp/item/item-1000259371/">商品ページ</a></body></html>'
pages = {"https://feed.example.jp/rss": RSS, "https://news.example.jp/a/1": ART}
got = []
def ext(text, game, gname, sname, url):
    got.append((text, url)); return []
src = [{"id": "t1", "name": "テスト", "type": "rss", "game": "gunpla", "url": "https://feed.example.jp/rss"}]
S = dict(common.load_settings(), rss_read_article=True, rss_article_max_per_run=5)
collect.collect(src, S, extractor=ext, fetcher=lambda u: pages[u])
assert got and "p-bandai.jp/item/item-1000259371" in got[0][0] and "11月9日15時" in got[0][0] and got[0][1] == "https://news.example.jp/a/1", got
got.clear()
common.STATE_DIR = pathlib.Path(tempfile.mkdtemp())
collect.collect(src, dict(S, rss_read_article=False), extractor=ext, fetcher=lambda u: pages[u])
assert got and "要約だけ" in got[0][0] and "p-bandai" not in got[0][0]
print("ARTICLE OK")
