"""BOX相場の朝・夜の更新のテスト（スニダンは偽物）  python tests/test_souba.py"""
import sys, tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import load_json, JST
import souba

PRICES = {"2026-10-27": 10000, "2026-10-28": 11000, "2026-10-29": 12000}
souba.items = lambda: [{"game": "pokemon", "series": "ポケモンカード151", "name": "ポケモンカード151 BOX", "snkr": 118914, "teika": 5800}]
souba._snkr_daily = lambda sess, aid: dict(PRICES)
souba._fx = lambda sess: None


class Sess:
    headers = {}


def at(h, m=5, day=29):
    souba.now = lambda: datetime(2026, 10, day, h, m, tzinfo=JST)


s = {"souba_hour": 7, "souba_eve_hour": 21}
nop = lambda *_: None

# 朝7時より前は読まない
at(6)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 0

# 朝：前日（10/28）までを出す
at(7)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 1
d = load_json("souba.json", {})
rec = d["items"]["pokemon|ポケモンカード151"]
sm = souba.summary(rec, "2026-10-29")
assert sm["date"] == "2026-10-28" and sm["price"] == 11000, sm
assert d["updated"].startswith("2026-10-29T07:05")
# 同じ日の昼はもう読まない
at(15)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 0

# 夜21時ごろ：今日（10/29）の21時ごろまでの値を出す
at(21)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 1
d = load_json("souba.json", {})
rec = d["items"]["pokemon|ポケモンカード151"]
sm = souba.summary(rec, "2026-10-29")
assert sm["date"] == "2026-10-29" and sm["price"] == 12000 and sm["prev"] == ("2026-10-28", 11000), sm
assert d["updated"].startswith("2026-10-29T21:05")
# 夜にもう一度は読まない
at(22)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 0

# 翌朝：また前日（10/29、1日分）までに戻る
PRICES["2026-10-29"] = 12500
PRICES["2026-10-30"] = 13000
at(7, day=30)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 1
rec = load_json("souba.json", {})["items"]["pokemon|ポケモンカード151"]
sm = souba.summary(rec, "2026-10-30")
assert sm["date"] == "2026-10-29" and sm["price"] == 12500, sm

# 夜に読めなかった商品は、今日の途中の値を出さない
at(21, day=30)
souba._snkr_daily = lambda sess, aid: (_ for _ in ()).throw(ValueError("x"))
before = load_json("souba.json", {})["updated"]
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 0
d = load_json("souba.json", {})
sm = souba.summary(d["items"]["pokemon|ポケモンカード151"], "2026-10-30")
assert sm["date"] == "2026-10-29", sm
assert d["updated"] == before  # 数字を読めなかった時は「相場の更新」を進めない

# 過去の弾：朝7時すぎから1回15件ずつ。夜の回でもその日の値は出さない
common.STATE_DIR = Path(tempfile.mkdtemp())
souba._snkr_daily = lambda sess, aid: dict(PRICES)
main = [{"game": "pokemon", "series": "151", "name": "151 BOX", "snkr": 1}]
old = [{"game": "pokemon", "series": f"old{n}", "name": f"old{n} BOX", "snkr": 100 + n, "past": True} for n in range(20)]
souba.items = lambda past=True: main + (old if past else [])
at(6, day=30)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 0
at(7, day=30)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 16  # 今の弾1件＋過去の弾15件
at(7, 35, day=30)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 5  # 残りの過去の弾5件だけ
at(8, day=30)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 0
at(21, day=30)
assert souba.update_souba(s, sess=Sess(), sleep=nop) == 1  # 夜は今の弾だけ
st = load_json("souba.json", {})["items"]
assert souba.summary(st["pokemon|151"], "2026-10-30")["date"] == "2026-10-30"
assert souba.summary(st["pokemon|old3"], "2026-10-30")["date"] == "2026-10-29" and st["pokemon|old3"]["past"]

# 400日分を残す（40日より前は1週に1日）・1か月前比・1年前比
from datetime import date, timedelta as td
d0 = date(2026, 10, 29)
hist = {(d0 - td(days=i)).isoformat(): 10000 + i for i in range(0, 500)}
th = souba._thin(hist, "2026-10-30")
assert min(th) >= (date(2026, 10, 30) - td(days=400)).isoformat()
assert all(k in th for k in [(d0 - td(days=i)).isoformat() for i in range(0, 39)])
assert len(th) < 120, len(th)
sm = souba.summary({"jp": th}, "2026-10-30")
assert sm["prev"] == ("2026-10-28", 10001)
assert sm["month"] == ("2026-09-29", 10030), sm["month"]
assert sm["year"] and "2025-10-2" in sm["year"][0] and sm["year"][0] <= "2025-10-29", sm["year"]
# 1年分のデータがない弾は1年前比なし
assert souba.summary({"jp": {k: v for k, v in th.items() if k > "2026-06-01"}}, "2026-10-30")["year"] is None
print("OK")

# ポケカのグラフに海外の線（円にした値）を重ねる
import sitegen as _sg
_pts = [("2026-10-%02d" % d, 20000 + d * 100) for d in range(1, 11)]
_us = [("2026-10-%02d" % d, 200.0 + d) for d in range(1, 11)]
_h = _sg.chart(_pts, us=_us, fx=150)
assert "stroke-dasharray" in _h and "海外（TCGplayer" in _h and ",30150" in _h, _h
assert "stroke-dasharray" not in _sg.chart(_pts)
print("chart us OK")
