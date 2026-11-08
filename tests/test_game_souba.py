"""ゲームの相場：1日1回・定価比・目安・サイトのカードに出る"""
import os, sys, tempfile, pathlib, json, datetime as dt
os.environ["SITE"] = "game"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = pathlib.Path(tempfile.mkdtemp())
import game_souba as gs
J = dt.timezone(dt.timedelta(hours=9))
gs.now = lambda: dt.datetime(2026, 11, 9, 7, 20, tzinfo=J)
gs.cfg = lambda: {"ps5": {"PS5 Pro": {"snkr": 1, "teika": 100000}}, "switch2": {"Switch 2 本体": {"snkr": 2}}}
calls = []
def daily(sess, aid):
    calls.append(aid)
    return {"2026-08-01": 999999, "2026-11-07": 130000, "2026-11-08": 140000} if aid == 1 else {"2026-11-08": 60000}
st = gs.update({}, sess=object(), sleep=lambda s: None, daily=daily)
assert st["ps5|PS5 Pro"]["price"] == 140000 and st["ps5|PS5 Pro"]["avg7"] == 135000
gs.update({}, sess=object(), sleep=lambda s: None, daily=daily); assert len(calls) == 2      # 1日1回
lb = gs.for_item({"game": "ps5", "series": "PS5 Pro"})
assert lb == {"text": "スニダン相場 135,000円（定価比 +35%）", "hint": "プレ値 高め"}, lb
assert gs.for_item({"game": "switch2", "series": "Switch 2 本体"})["text"] == "スニダン相場 60,000円"   # 定価が無ければ相場だけ
assert gs.for_item({"game": "ps5", "series": "ほか"}) is None
gs.now = lambda: dt.datetime(2026, 12, 20, 7, 20, tzinfo=J)
st = gs.update({}, sess=object(), sleep=lambda s: None, daily=daily)
assert "ps5|PS5 Pro" not in st                                                             # 1か月より前の取引しかない → 出さない
print("SOUBA OK")
