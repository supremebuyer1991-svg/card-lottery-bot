"""定価以上で売れる商品：JANでまとめる・定価比・1週間前比・ページ"""
import os, sys, tempfile, pathlib, json, datetime as dt
os.environ["SITE"] = "game"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import common
d = pathlib.Path(tempfile.mkdtemp()); common.STATE_DIR = d
import game_premium as gp
J = dt.timezone(dt.timedelta(hours=9))
gp.now = lambda: dt.datetime(2026, 11, 20, 10, 0, tzinfo=J)
w = lambda n, x: (d / n).write_text(json.dumps(x, ensure_ascii=False), encoding="utf-8")
w("kaitori_multi.json", {
  "A店": {"at": "x", "items": [["Nintendo Switch 2 Proコントローラー ゼルダの伝説 40周年 アニバーサリーエディション", "4902370554564", 13000], ["Switch 2 本体", "4902370552683", 50000]]},
  "B店": {"at": "x", "items": [["Nintendo Switch 2 Proコントローラー ゼルダの伝説 40周年 アニバーサリーエディション （スタンド付き）", None, 13800]]},
  "C店": {"at": "x", "items": [["ゼルダ プロコン", "4902370554564", 12500]]}})
w("lotteries.json", {})
calls = []
def fetch(p):
    calls.append(p["keyword"])
    return [{"itemPrice": 12980 if p["keyword"] == "4902370554564" else 59980, "itemUrl": "https://item.rakuten.co.jp/book/1/", "itemName": "【新品】Switch 2 Proコントローラー ゼルダの伝説 40周年", "mediumImageUrls": []}]
w("premium_hist.json", {"4902370554564": {"2026-11-12": 12000, "2026-10-20": 11000}})
g = gp.update({}, fetch=fetch, sleep=lambda s: None)
assert g["4902370554564"]["max"] == 13800 and g["4902370554564"]["store"] == "B店"      # JANの無い店も商品名で寄せる
assert set(calls) == {"4902370554564", "4902370552683"}
L = gp.premium_list({})
assert [x["jan"] for x in L] == ["4902370554564"]                                         # 定価より安い本体は出ない
x = L[0]
assert x["w1"] == 12000 and x["m1"] == 11000 and x["teika"] == 12980
assert "+1,800円" in gp._chg(x["max"], x["w1"])
svg = gp.chart_svg({"2026-11-12": 12000, "2026-11-20": 13800}, 12980)
assert "<polyline" in svg and "定価 12,980円" in svg
import sitegen_game
out = pathlib.Path(tempfile.mkdtemp())
sitegen_game.build(common.load_settings(), out_dir=out)
p = (out / "premium/4902370554564/index.html").read_text(encoding="utf-8")
assert "最高買取" in p and "13,800円" in p and "1週間前比" in p and "1か月前比" in p and "<svg class=\"chart\"" in p and "楽天で見る" in p and "メルカリで探す" in p
assert "定価以上で売れる" in (out / "index.html").read_text(encoding="utf-8") and "/premium/4902370554564/" in (out / "sitemap.xml").read_text(encoding="utf-8")
assert (out / "souba/index.html").exists() and (out / "premium/4902370552683/index.html").exists()          # 定価より安い商品も相場ページは作る
assert "<h2>商品情報</h2>" in p and "JANコード" in p and ("定価（税込）" in p or "楽天ブックスの販売価格（税込）" in p) and "定価 12,980円" not in p   # 楽天ブックスの値段しか分からない商品は「定価」と書かない（11/14）
print("PREMIUM OK")
# 抽選・発売日の商品（買取相場に無いもの）にも商品ページ。発売前は相場「予測不能」、フォローの案内
w("lotteries.json", {"r1": {"key": "r1", "status": "listed", "kind": "release", "game": "ps5", "store": "SIE", "product": "PS5 新色 テスト", "end": "2099-01-01T00:00+09:00", "price": "55,000円", "url": "https://x", "found_at": "2026-11-08T10:00+09:00"}})
out2 = pathlib.Path(tempfile.mkdtemp())
sitegen_game.build(common.load_settings(), out_dir=out2)
ip = [f for f in (out2 / "item").rglob("index.html")]
assert len(ip) == 1, ip
t = ip[0].read_text(encoding="utf-8")
assert "予測不能（発売前）" in t and "定期的にチェック" in t and "intent/follow?screen_name=a9994aaa" in t and "55,000円" in t
assert "この商品をメルカリで見る" in t and "status=sold_out" in t and "この商品をメルカリで見る" in p
print("ITEM PAGES OK")


def test_split_subgenres():
    import game_premium as gp
    rules = [{"name": "周辺機器", "re": "ケース"}, {"name": "コントローラー", "re": "コントローラー"}, {"name": "本体", "re": "^Nintendo Switch 2"}, {"name": "ゲームソフト"}]
    ps = [{"name": "Nintendo Switch 2 キャリングケース"}, {"name": "Nintendo Switch 2 BEE-S"}, {"name": "マリオカート ワールド"}, {"name": "Nintendo Switch 2 Proコントローラー"}]
    gs = gp.split_subgenres(ps, rules)
    assert [n for n, _ in gs] == ["本体", "コントローラー", "ゲームソフト", "周辺機器"]
    assert gs[3][1][0]["name"].endswith("ケース")
    h = gp.cat_products_html([dict(p, url="/x/", jan="1") for p in ps], "Switch 2", rules, has_list=True)
    assert 'href="#sg1"' in h and 'href="#list"' in h and 'id="sg4"' in h
    assert "sgmenu" not in gp.cat_products_html([dict(ps[0], url="/x/", jan="1")], "Switch 2", rules)
