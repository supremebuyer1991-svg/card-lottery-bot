"""Xの予約投稿の計画：ゲーム優先・リンク付き・時刻・文字数"""
import os, sys, tempfile, pathlib, datetime as dt
os.environ["SITE"] = "game"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = pathlib.Path(tempfile.mkdtemp())
import game_xplan as xp, game_xpost as gx
import game_premium   # 「定価以上で売れる商品」の判定はテスト用に固定（アシュタロン・PS5 新色・HG ガンダム）
game_premium.premium_match = lambda n, s=None: ({} if any(w in (n or "") for w in ("アシュタロン", "PS5 新色", "HG ガンダム", "HG アシュタロン")) else None)
J = dt.timezone(dt.timedelta(hours=9))
T = dt.datetime(2026, 11, 14, 22, 30, tzinfo=J)   # 土曜の夜 → 日曜の計画
def it(p, **k):
    d = dict(status="listed", kind="lottery", game="ps5", store="ヨドバシ", product=p, end="2026-11-20T23:59+09:00"); d.update(k); return d
lots = {"a": it("PS5 Pro 抽選"), "b": it("HG ガンダム", game="gunpla", store="プレバン"), "c": it("Switch 2 セット", game="switch2"),
        "d": it("今日締切のPS5", end="2026-11-15T23:59+09:00"), "e": it("朝締切", end="2026-11-15T12:00+09:00", game="gunpla"),
        "r": it("HG アシュタロン", kind="release", game="gunpla", end="2026-11-18T23:59+09:00"),
        "r2": it("PS5 新色", kind="release", end="2026-11-19T23:59+09:00")}
st = {"seen": [], "queue": {"b": "2026-11-14T10:00+09:00", "a": "2026-11-14T11:00+09:00", "c": "2026-11-14T12:00+09:00"}}
plan = xp.build(lots, {}, "https://game-nyuka.com", T, st)
slots = [(p["at"][11:16], p["slot"]) for p in plan]
assert slots == [("07:30", "今日の締切"), ("10:30", "ピックアップ"), ("12:30", "新着まとめ"), ("17:00", "ピックアップ"), ("20:30", "今夜締切"), ("21:00", "来週の発売")], slots
pk = [p for p in plan if p["slot"] == "ピックアップ"]
assert "HG" not in pk[0]["text"] and "HG" not in pk[1]["text"]                      # ピックアップはゲームを優先
assert "https://game-nyuka.com/l/" in pk[0]["text"]                                   # リンク付き
assert "HG ガンダム" in [p for p in plan if p["slot"] == "新着まとめ"][0]["text"]      # ホビーはまとめの中に
assert "朝締切" not in [p for p in plan if p["slot"] == "今夜締切"][0]["text"]
wk = [p for p in plan if p["slot"] == "来週の発売"][0]["text"]
assert wk.index("PS5 新色") > wk.index("HG アシュタロン")                              # 日付順
for p in plan:
    assert xp._xlen(p["text"]) <= 280, p
assert st["planned"] == {"b": "2026-11-15", "a": "2026-11-15", "c": "2026-11-15"}
plan2 = xp.build(lots, {}, "https://game-nyuka.com", T, st)                           # 作り直しても同じ
assert [p["text"] for p in plan2] == [p["text"] for p in plan]
for p in plan: print(p["at"][11:16], p["slot"]); print(p["text"]); print("-")
st2 = {"seen": [], "queue": {}}
plan3 = xp.build(lots, {}, "https://game-nyuka.com", T, st2)
pk3 = [p["text"] for p in plan3 if p["slot"] == "ピックアップ"]
assert len(pk3) == 2 and all("HG" not in x for x in pk3), pk3                      # 新着が無くても、ゲームの受付中・発売で埋める
assert xp.build(lots, {}, "https://game-nyuka.com", T, st2) and [p["text"] for p in xp.build(lots, {}, "https://game-nyuka.com", T, st2)] == [p["text"] for p in plan3]
assert game_premium.worth_posting({"kind": "release", "product": "ふつうの商品"}) is False and game_premium.worth_posting({"kind": "lottery", "product": "ふつうの商品"}) is True
print("XPLAN OK")
