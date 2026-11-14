"""商品ページに商品の事実（メーカー公式など）を足す  python tests/test_game_facts.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
import game_facts as gf
import game_premium

# 答えの確かめ方
seen = {"https://www.takaratomy.co.jp/products/beyblade/ux10/"}
ok = gf.check({"found": True, "src": "https://www.takaratomy.co.jp/products/beyblade/ux10/?x=1", "official": True,
               "facts": ["2025年3月発売", "対象年齢6歳以上", "大人気のセット", " ランチャー同梱 "]}, seen)
assert ok and ok[0] == ["2025年3月発売", "対象年齢6歳以上", "ランチャー同梱"] and ok[3] is True and ok[4] is None, ok   # 宣伝の言葉は外す
ok2 = gf.check({"found": True, "src": "https://www.takaratomy.co.jp/products/beyblade/ux10/", "official": True, "msrp": "5,700", "facts": ["a", "b"]}, seen)
assert ok2[4] == 5700
ok3 = gf.check({"found": True, "src": "https://www.takaratomy.co.jp/products/beyblade/ux10/", "official": False, "msrp": 5700, "facts": ["a", "b"]}, seen)
assert ok3[4] is None   # 公式でないページの値段は希望小売価格として使わない
# 前に取った分（msrp が無い）は要点の文から読む
assert gf.msrp_of({"official": True, "facts": ["価格は税込5,700円と表示されている"]}) == 5700
assert gf.msrp_of({"official": False, "facts": ["価格は税込5,700円"]}) is None
assert gf.msrp_of({"official": True, "msrp": None, "facts": ["価格は税込5,700円"]}) is None   # 新しく取って無かったもの
assert gf.msrp_of({"official": True, "facts": ["メーカー希望小売価格 6,600円（税込）"]}) == 6600
assert gf.check({"found": True, "src": "https://made-up.example/x", "facts": ["a", "b"]}, seen) is None   # 見ていないURLは使わない
assert gf.check({"found": False}, seen) is None
assert gf.check({"found": True, "src": "https://jp.mercari.com/item/1", "facts": ["a", "b"]}, {"https://jp.mercari.com/item/1"}) is None

# 取ってきて保存・ページの欄
cat = [{"jan": "4904810939542", "name": "BEYBLADE X UX-10", "names": []}, {"jan": "4904810000000", "name": "見つからない商品", "names": []}]
game_premium.catalog = lambda s, w=None: cat


def call(name, jan, names):
    if jan == "4904810000000":
        return {"found": False}, set()
    return {"found": True, "src": "https://www.takaratomy.co.jp/products/beyblade/ux10/", "src_title": "UX-10", "official": True,
            "facts": ["2025年3月発売", "対象年齢6歳以上"]}, seen


n = gf.update({"product_facts_per_run": 4}, call=call)
assert n == 1, n
st = common.load_json(gf.STATE, {})
assert st["4904810939542"]["facts"] == ["2025年3月発売", "対象年齢6歳以上"] and st["4904810000000"]["facts"] == []
assert gf.update({"product_facts_per_run": 4}, call=call) == 0   # 取ったもの・探して無かったものは、しばらく探し直さない
gf._cache.clear()
h = gf.html_for("4904810939542", "BEYBLADE X UX-10")
assert "商品の特徴" in h and "メーカー公式" in h and "takaratomy" in h, h
assert gf.html_for("4904810000000", "x") == ""
print("FACTS OK")
