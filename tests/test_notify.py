"""新着のお知らせ（Discord）のテスト  python tests/test_notify.py"""
import sys, tempfile
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import JST, load_json
import notify

T = datetime(2026, 10, 28, 21, 0, tzinfo=JST)
sent = []
notify._send = lambda url, text: sent.append(text) or True

lots = {
    "a": {"game": "pokemon", "store": "A店", "series": "30th CELEBRATION", "end": "2026-10-30T23:59:00+09:00", "status": "approved"},
    "old": {"game": "pokemon", "store": "B店", "series": "30th CELEBRATION", "end": "2026-10-27T23:59:00+09:00", "status": "approved"},
}
# 1回目：いま載っている分は送らず、開始のお知らせだけ
assert notify.run("https://x", lots, "https://tcg-chusen.com", T) == 0
assert len(sent) == 1 and "始めました" in sent[0], sent

# 新着が2件（ポケカ・ワンピース）＋承認待ち・締切切れ・別ゲームは送らない
lots.update({
    "n1": {"game": "pokemon", "store": "C店", "series": "ストームエメラルダ", "end": "2026-10-31T23:59:00+09:00", "status": "listed"},
    "n2": {"game": "pokemon", "store": "D店", "series": "30th CELEBRATION", "end": "2026-10-29T12:00:00+09:00", "status": "approved"},
    "n3": {"game": "onepiece", "store": "E店", "series": "ヒロインズエディション vol.2", "end": None, "status": "approved"},
    "p": {"game": "pokemon", "store": "F店", "series": "x", "end": None, "status": "pending"},
    "d": {"game": "dragonball", "store": "G店", "series": "x", "end": None, "status": "approved"},
})
sent.clear()
assert notify.run("https://x", lots, "https://tcg-chusen.com", T) == 2
poke = next(x for x in sent if "ポケカの抽選" in x)
op = next(x for x in sent if "ワンピースカードの抽選" in x)
assert poke.index("D店") < poke.index("C店"), poke  # 締切が早い順
assert "10/29(木) 12:00まで" in poke and "https://tcg-chusen.com/pokeka/" in poke and "#ポケカ #ポケカ抽選" in poke
assert "締切は応募ページで確認" in op and "https://tcg-chusen.com/onepiece/" in op and "#ワンピースカード抽選" in op
assert "F店" not in poke and "A店" not in poke

# 2回目は送らない／締切が後から分かって別のキーで入っても同じ店・同じ商品なら送らない
lots["n3b"] = dict(lots["n3"], end="2026-11-01T23:59:00+09:00")
sent.clear()
assert notify.run("https://x", lots, "https://tcg-chusen.com", T) == 0 and not sent

# 承認待ちが承認されたら、その回で届く
lots["p"]["status"] = "approved"
assert notify.run("https://x", lots, "https://tcg-chusen.com", T) == 1 and "F店" in sent[0]

# たくさん見つかったら10店ずつに分けて、1回3通まで（残りは次の回）
for n in range(35):
    lots[f"m{n}"] = {"game": "pokemon", "store": f"店{n:02d}", "series": "30th CELEBRATION", "end": "2026-11-05T23:59:00+09:00", "status": "approved"}
sent.clear()
assert notify.run("https://x", lots, "https://tcg-chusen.com", T) == 3
assert all(x.count("\n・") == 10 for x in sent)
sent.clear()
assert notify.run("https://x", lots, "https://tcg-chusen.com", T) == 1 and sent[0].count("\n・") == 5

# ウェブフック未登録なら何もしない
assert notify.run("", lots, "https://tcg-chusen.com", T) == 0
assert load_json("notify.json", {}).get("started")
print("NOTIFY OK")

# ゲームの区分がまちがっていそうなもの（ポケカにヒロインズ）は送らない
lots["w"] = {"game": "pokemon", "store": "H店", "series": "Heroines Edition vol.2", "end": None, "status": "approved"}
lots["w2"] = {"game": "onepiece", "store": "I店", "series": "30th CELEBRATION", "end": None, "status": "approved"}
sent.clear()
assert notify.run("https://x", lots, "https://tcg-chusen.com", T) == 0 and not sent
print("NOTIFY WRONG-GAME OK")
