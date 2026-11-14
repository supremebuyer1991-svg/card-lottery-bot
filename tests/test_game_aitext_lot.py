"""抽選の個別ページ（/l/）にもAIの解説を作る  python tests/test_game_aitext_lot.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
import game_aitext as ga
import game_premium

game_premium._PM_CACHE["cat"] = []   # 買取の分からない商品として
common.save_json("lottery_pages.json", {
    "k1": {"path": "l/k1/", "snap": {"store": "ソニーストア", "product": "PS5 Pro", "kind": "lottery", "end": "2026-11-20T23:59:00+09:00",
                                      "conditions": "PSNアカウント連携", "channel": "online"}},
    "k2": {"path": "l/k2/", "ended": True, "snap": {"store": "X", "product": "Y"}},
})
common.save_json("content_volume.json", {"pages": {"l/k1/": [300, 200], "l/k2/": [300, 100]}})
seen = []


def fake_ai(d):
    seen.append(d)
    return "## どんな受付？\n" + "あ" * 400


st = ga.update({"content_target_chars": 1500, "aitext_per_run": 8}, ai=fake_ai)
assert list(k for k in st if k.startswith("l:")) == ["l:k1"], st.keys()      # 終わった受付は作らない
d = seen[0]
assert d["_kind"] == "lottery_page" and d["お店"] == "ソニーストア" and d["受付の種類"] == "抽選" and "条件" in d, d
ga._cache.clear()
h = ga.html_for("l:k1")
assert "<h2>どんな受付？</h2>" in h and "受付の情報" in h, h[:200]
# 2回目は作り直さない
seen.clear()
ga.update({"content_target_chars": 1500, "aitext_per_run": 8}, ai=fake_ai)
assert not [x for x in seen if x.get("_kind") == "lottery_page"]
print("AITEXT LOT OK")
