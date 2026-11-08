"""応募先をニュース記事から公式ページに差し替える"""
import os, sys, tempfile, pathlib
os.environ["SITE"] = "game"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = pathlib.Path(tempfile.mkdtemp())
import official_link as ol
ART1 = '<a href="https://p-bandai.jp/item/item-1000259371/">商品ページ</a>'
ART2 = '<a href="https://p-bandai.jp/item/item-1000000001/">ザクヘッド</a><a href="https://p-bandai.jp/item/item-1000270000/">こちら</a>'
ART3 = '<p>リンクなし</p>'
pages = {"https://news.example.jp/1": ART1, "https://news.example.jp/2": ART2, "https://news.example.jp/3": ART3,
         "https://news.example.jp/4": ART1,
         "https://p-bandai.jp/item/item-1000000001/": "<title>ガシャポン ザクヘッド</title>",
         "https://p-bandai.jp/item/item-1000270000/": "<title>ROBOT魂 クィン・マンサ マーキングプラス | プレミアムバンダイ</title>"}
fetch = lambda u: pages[u]
def it(p, u, **k):
    d = dict(status="listed", store="プレミアムバンダイ", product=p, url=u, end="2099-01-01T00:00+09:00", found_at="2026-11-08T10:00+09:00"); d.update(k); return d
lots = {"a": it("HG ガンダムヴァサーゴ", "https://news.example.jp/1"),
        "b": it("ROBOT魂 クィン・マンサ ～マーキングプラス～", "https://news.example.jp/2"),
        "c": it("S.H.Figuarts 白ひげ", "https://news.example.jp/3"),
        "d": it("HG 1/144 ガンダムヴァサーゴ", "https://news.example.jp/4", end=None, found_at="2026-11-08T11:00+09:00"),
        "e": it("公式のまま", "https://p-bandai.jp/item/item-1000999999/")}
n = ol.resolve({}, lots, fetch)
assert lots["a"]["url"] == "https://p-bandai.jp/item/item-1000259371/" and lots["a"]["source_url"] == "https://news.example.jp/1"
assert lots["b"]["url"] == "https://p-bandai.jp/item/item-1000270000/", lots["b"]           # 関連記事のリンクではなく、商品名が合う方
assert lots["c"]["url"] == "https://p-bandai.jp/"                                           # 見つからなければお店の公式トップ
assert lots["d"]["status"] == "duplicate" and lots["a"]["status"] == "listed"              # 同じ公式ページ → 締切が分かる方を残す
assert lots["e"]["url"] == "https://p-bandai.jp/item/item-1000999999/" and "source_url" not in lots["e"]
assert ol.resolve({}, lots, lambda u: 1 / 0) == 0                                          # 2回目は何も開かない
print("OFFICIAL OK")
