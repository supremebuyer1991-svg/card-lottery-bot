"""ゲームのX速報：初回は記録だけ・上限・間隔・まとめ・文字数"""
import os, sys, tempfile, pathlib, json, datetime as dt
os.environ["SITE"] = "game"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))
import common
tmp = pathlib.Path(tempfile.mkdtemp())
common.STATE_DIR = tmp
import game_xpost as gx
import game_premium   # 「定価以上で売れる商品」の判定はテスト用に固定（アシュタロン・PS5 新色・HG ガンダム）
game_premium.premium_match = lambda n, s=None: ({} if any(w in (n or "") for w in ("アシュタロン", "PS5 新色", "HG ガンダム", "HG アシュタロン")) else None)
J = dt.timezone(dt.timedelta(hours=9))
T = dt.datetime(2026, 11, 9, 12, 0, tzinfo=J)
gx.now = lambda: T
common.now = lambda: T
def w(name, d): (tmp / name).write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
def r(name): return json.loads((tmp / name).read_text(encoding="utf-8"))
def it(p, **k):
    d = dict(status="listed", kind="lottery", game="ps5", store="ヨドバシ", product=p, end="2026-11-10T09:00+09:00", found_at=(T - dt.timedelta(hours=1)).isoformat())
    d.update(k); return d
S = {"x_speed_post": True, "x_speed_per_day": 2, "x_speed_gap_min": 20, "dry_run": False}
sent = []
send = lambda text, mid: sent.append((text, mid)) or str(len(sent))
img = lambda i: "M1"
w("lotteries.json", {"old": it("古いの")})
gx.post_speed(S, send, img)
assert sent == [] and r("xpost.json")["seen"] == ["old"]                     # 初回は記録だけ
lots = {"old": it("古いの"), "a": it("PS5 Pro"), "b": it("発売日", kind="release"), "c": it("締切不明", end=None),
        "d": it("終わった", end="2026-11-09T10:00+09:00"), "e": it("昔見つけた", found_at="2026-11-01T10:00+09:00")}
w("lotteries.json", lots)
gx.post_speed(S, send, img)
assert len(sent) == 1 and "PS5 Pro" in sent[0][0] and sent[0][1] == "M1" and "http" not in sent[0][0]
assert "#PS5" in sent[0][0] and sent[0][0].count("#") <= 2, sent[0][0]
gx.post_speed(S, send, img); assert len(sent) == 1                            # 同じものは二度出さない
lots.update(f=it("Switch 2 マリオカート セット", game="switch2", store="ゲオ"), g=it("HG アシュタロン", game="gunpla", store="プレバン", kind="preorder"))
w("lotteries.json", lots)
gx.post_speed(S, send, img); assert len(sent) == 1                            # 20分たっていない
T = T + dt.timedelta(minutes=30); gx.now = lambda: T
gx.post_speed(S, send, img)
assert len(sent) == 2 and "2件" in sent[1][0] and "#PS5" not in sent[1][0], sent[1][0]   # まとめて1本
assert gx.x_len(sent[1][0]) <= 280
lots["h"] = it("もう1件"); w("lotteries.json", lots)
T = T + dt.timedelta(minutes=30); gx.now = lambda: T
gx.post_speed(S, send, img); assert len(sent) == 2                            # 1日の上限
gx.post_speed(dict(S, x_speed_post=False), send, img); assert len(sent) == 2
long = [it("とても長い商品名" * 8, store="とても長いお店の名前") for _ in range(6)]
assert gx.x_len(gx.compose(long)) <= 280 and gx.x_len(gx.compose(long[:1])) <= 280
t1 = gx.compose([it("PS5 Pro")], link="https://www.amazon.co.jp/dp/B0TEST1234?tag=g-22")
assert "Amazonの商品ページ👉 https://www.amazon.co.jp/dp/B0TEST1234?tag=g-22" in t1 and "プロフ" not in t1
t2 = gx.compose([it("A"), it("B")], link="https://www.amazon.co.jp/dp/B0TEST1234?tag=g-22")
assert "http" not in t2                                                       # まとめ投稿にはリンクを付けない
# 急がないもの（締切が先）は予約投稿の待ち行列へ。ホビーの速報は1日の上限あり
st = r("xpost.json"); st["posts"] = []; w("xpost.json", st)
T = T + dt.timedelta(days=1); gx.now = lambda: T
lots.update(q1=it("先の抽選", end="2026-11-20T23:59+09:00", found_at=T.isoformat()))
w("lotteries.json", lots); n0 = len(sent)
gx.post_speed(S, send, img)
assert len(sent) == n0 and "q1" in r("xpost.json")["queue"]
assert gx.is_urgent(it("再入荷", kind="restock", end=None), T, {}) and not gx.is_urgent(it("先", end="2026-11-30T00:00+09:00"), T, {})
assert gx.is_game(it("x", game="ps5")) and not gx.is_game(it("x", game="gunpla"))
print(t1); print("---"); print(sent[0][0]); print("---"); print(sent[1][0])
print("XPOST OK")
