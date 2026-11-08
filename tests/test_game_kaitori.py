"""買取店の買取価格：店ごとに読み、全店でいちばん高い店を出す"""
import os, sys, tempfile, pathlib
os.environ["SITE"] = "game"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = pathlib.Path(tempfile.mkdtemp())
import game_kaitori as gk
gk.stores = lambda: [{"name": "A店", "urls": ["https://a.example/game"]}, {"name": "B店", "urls": ["https://b.example/game"]}]
pages = {"https://a.example/game": "<p>A</p>", "https://b.example/game": "<p>B</p>"}
ais = {"A": [["Nintendo Switch 2 Proコントローラー ゼルダの伝説 40周年 アニバーサリーエディション", "4902370554564", 13000]],
       "B": [["Switch2 Proコントローラー ゼルダの伝説 40周年", None, 13800], ["PS5 Pro CFI-7100", None, 200000]]}
st = gk.update({"kaitori_stores_per_run": 5}, fetch=lambda u: pages[u], ai=lambda text: ais[text.strip()[0]])
z = {"product": "Nintendo Switch 2 Proコントローラー ゼルダの伝説 40周年 アニバーサリーエディション", "price": "12,980円"}
b = gk.best_for(z, st)
assert b == (13000, "A店") or b == (13800, "B店"), b
assert gk.best_for(dict(z, jan="4902370554564"), st)[0] >= 13000
assert gk.label(z, (13800, "B店")) == "最高買取 13,800円（B店・定価比 +6%）・プレ値"
assert gk.best_for({"product": "HG ガンダム"}, st) is None
n = len([1 for _ in st]); gk.update({"kaitori_stores_per_run": 5}, fetch=lambda u: 1 / 0, ai=None)   # 1日1回：読み直さない
print("KAITORI OK")
