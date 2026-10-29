"""主要カードの相場のテスト（スニダン・楽天は偽物）  python tests/test_souba_cards.py"""
import sys, tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import load_json, JST
import souba

cfg = {"pokemon|黒炎の支配者": [{"snkr": 1, "label": "リザードンex SAR", "num": "SV3 134/108"},
                               {"snkr": 2, "label": "リザードンex UR", "num": "SV3 139/108"}],
       "onepiece|ロマンスドーン": [{"snkr": 3, "label": "シャンクス SEC-SP (コミパラ)", "num": "OP01-120"}]}
souba.card_cfg = lambda: cfg
calls = []


class R:
    def __init__(self, j=None, text=""):
        self._j, self.text = j, text

    def raise_for_status(self):
        pass

    def json(self):
        return self._j


class Sess:
    headers = {}

    def get(self, url, timeout=30):
        calls.append(url)
        if "/apparels/" in url:
            return R(text='"productId":555')
        if "condition_code" in url:
            assert "variant_id=77" in url and "trading_card_single_nearly_unused" in url
            ts = lambda d: int(datetime(2026, 10, d, tzinfo=JST).timestamp() * 1000)
            return R({"chart": {"lines": [{"points": [{"timestamp": ts(20), "price": 30000}, {"timestamp": ts(28), "price": 35000},
                                                         {"timestamp": ts(29), "price": 36000}, {"timestamp": ts(30), "price": 1}]}]}})
        return R({"filters": {"variants": {"options": [{"id": 77, "name": "1枚"}, {"id": 78, "name": "2枚"}]}}})


souba.now = lambda: datetime(2026, 10, 30, 8, 5, tzinfo=JST)
souba.time.sleep = lambda *_: None
s = {"souba_hour": 7}
# 初めてのカードは3回（ページ・1枚の番号・状態Aの相場）。上限7回なら2枚まで
assert souba.update_cards(s, sess=Sess(), sleep=lambda *_: None, budget=7) == 2
assert len(calls) == 6
d = load_json("souba_cards.json", {})
assert d["1"]["pid"] == 555 and d["1"]["vid"] == 77 and d["1"]["day"] == "2026-10-30"
sm = souba.card_summary(d["1"], "2026-10-30")
assert sm["date"] == "2026-10-29" and sm["price"] == 36000 and sm["prev"] == ("2026-10-28", 35000) and sm["week"] == ("2026-10-20", 30000), sm
# 残りの1枚
calls.clear()
assert souba.update_cards(s, sess=Sess(), sleep=lambda *_: None, budget=7) == 1
# 同じ日はもう読まない
assert souba.update_cards(s, sess=Sess(), sleep=lambda *_: None) == 0
# 翌日は1枚1回だけ
souba.now = lambda: datetime(2026, 10, 31, 8, 5, tzinfo=JST)
calls.clear()
assert souba.update_cards(s, sess=Sess(), sleep=lambda *_: None) == 3 and len(calls) == 3

# サイトの欄
import sitegen
cs = [(c, d.get(str(c["snkr"])) or {}, souba.card_summary(load_json("souba_cards.json", {})[str(c["snkr"])], "2026-10-30")) for c in cfg["pokemon|黒炎の支配者"]]
cs[0][1]["rk"] = {"image": "https://thumbnail.image.rakuten.co.jp/x.jpg?_ex=300x300", "url": "https://hb.afl.rakuten.co.jp/hgc/abc/?pc=x"}
h = sitegen.cards_block("黒炎の支配者", cs)
assert "黒炎の支配者の主要カードの相場" in h and "¥36,000" in h and "楽天で見る" in h and "rel=\"nofollow sponsored noopener\"" in h
assert "https://jp.mercari.com/search?keyword=%E3%83%AA%E3%82%B6%E3%83%BC%E3%83%89%E3%83%B3ex%20SAR%20134/108" in h, h
assert sitegen.cards_block("x", []) == ""
print("OK")
