"""ネットワークなしで一連の流れを確認するテスト（AIと取得はダミー）"""
import sys, shutil, tempfile
from pathlib import Path
from datetime import timedelta

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
from common import now, load_settings, load_json
from extract import _parse
from collect import collect
from approve import approve
from xpost import post_all, compose, x_len
from wp import render

tmp = Path(tempfile.mkdtemp())
common.STATE_DIR = tmp

s = load_settings()
s["auto_approve"], s["dry_run"], s["site_url"] = True, False, "https://example.com"

end = (now() + timedelta(hours=10)).isoformat(timespec="minutes")
end2 = (now() + timedelta(days=5)).isoformat(timespec="minutes")
past = (now() - timedelta(days=1)).isoformat(timespec="minutes")

def fake_extract(text, game, gname, sname, url):
    items = [
        {"store": "ヨドバシ.com", "product": "拡張パック テスト弾 BOX", "end": end,
         "conditions": "ゴールドポイントカード会員", "url": "https://example.com/a", "confidence": 0.9},
        {"store": "セブンネット", "product": "テスト弾 BOX", "end": end2, "url": None, "confidence": 0.95},
        {"store": "謎の店", "product": "不明商品", "end": None, "confidence": 0.3},
        {"store": "終了店", "product": "古い弾", "end": past, "confidence": 0.9},
    ]
    for it in items:
        it.update(game=game, source=sname, source_url=url, url=it.get("url") or url)
    return items

src = [{"id": "t", "game": "pokemon", "name": "テスト", "type": "html", "url": "https://example.com"}]
html = "<html><body><p>抽選のお知らせ</p><a href='/lot'>抽選はこちら</a></body></html>"

common.save_json("seen.json", {"t": "x"})  # 初回扱いにしない（初回の挙動は下で別に確認）
new = collect(src, s, extractor=fake_extract, fetcher=lambda u: html)
assert len(new) == 3, new                       # 締切済みは除外
assert collect(src, s, extractor=fake_extract, fetcher=lambda u: html) == []  # 変化なし→再抽出しない

approve(s)
lots = load_json("lotteries.json", {})
st = sorted(i["status"] for i in lots.values())
assert st == ["approved", "approved", "pending"], st   # 自信度不足は承認待ち

class FakeClient:
    def __init__(self):
        self.sent, self.quotes = [], []
    def create_tweet(self, text, quote_tweet_id=None):
        self.sent.append(text); self.quotes.append(quote_tweet_id)
        class R: data = {"id": len(self.sent)}
        return R()

c = FakeClient()
post_all(s, client=c)
assert len(c.sent) == 2
assert "ヨドバシ" in c.sent[0]                  # 締切が近い順
post_all(s, client=c)
assert len(c.sent) == 2                          # 告知直後はリマインドしない
lots = load_json("lotteries.json", {})
for i in lots.values():                          # 告知から7時間経過したことにする
    if i.get("posted_at"):
        i["posted_at"] = (now() - timedelta(hours=7)).isoformat()
common.save_json("lotteries.json", lots)
post_all(s, client=c)
assert len(c.sent) == 3 and "締切まもなく" in c.sent[2], c.sent
post_all(s, client=c)
assert len(c.sent) == 3                          # 二重リマインドしない
for t in c.sent:
    assert x_len(t) <= 280, (x_len(t), t)

long = {"game": "pokemon", "store": "店" * 30, "product": "長い商品名" * 20, "end": end,
        "conditions": "条件" * 40, "url": "https://example.com"}
assert x_len(compose(long, s)) <= 280

page = render("pokemon", s, load_json("lotteries.json", {}))
assert "プロモーション" in page and "ヨドバシ" in page and "締切間近" in page

assert _parse('前置き [{"store":"A","product":"B"},{"store":"x"}] 後') == [{"store": "A", "product": "B"}]
assert _parse("該当なし") == []

# ---- Xからの収集 ----
from types import SimpleNamespace as NS
from fetch_x import build_query
import xpost
for f in ("seen.json", "lotteries.json"):
    (tmp / f).unlink()

class FakeX:
    calls = []
    def search_recent_tweets(self, **kw):
        self.calls.append(kw)
        if kw.get("since_id"):
            return NS(data=[], includes={})
        t = NS(id=1850000000000000001, author_id=7, created_at="2026-10-26T06:00:00Z",
               text="【抽選販売】ポケカ新弾BOX 11/2 23:59まで受付", entities={"urls": [{"expanded_url": "https://shop.example/lot"}]})
        return NS(data=[t], includes={"users": [NS(id=7, username="shop_example", name="テスト店")]})

def fake_x_extract(text, game, gname, sname, url):
    assert "@shop_example" in text and "https://shop.example/lot" in text and "/status/" in text
    return [{"store": "テスト店", "product": "ポケカ新弾BOX", "end": end2, "confidence": 0.9,
             "x_post": "https://x.com/shop_example/status/1850000000000000001",
             "game": game, "source": sname, "source_url": url, "url": "https://shop.example/lot"}]

xsrc = [{"id": "xs", "game": "pokemon", "name": "X", "type": "x", "keywords": "ポケカ 抽選"},
        {"id": "xe", "game": "pokemon", "name": "X空", "type": "x", "accounts": [], "keywords": "抽選"},
        {"id": "xd", "game": "pokemon", "name": "無効", "type": "x", "enabled": False, "keywords": "抽選"}]
fx = FakeX()
common.save_json("seen.json", {"xs": None})
assert len(collect(xsrc, s, extractor=fake_x_extract, x_client=fx)) == 1
assert len(fx.calls) == 1                                    # 空アカウント・無効ソースは呼ばない
assert "-当選" in fx.calls[0]["query"] and "has:links" in fx.calls[0]["query"]
collect(xsrc, s, extractor=fake_x_extract, x_client=fx)
assert fx.calls[1]["since_id"] == "1850000000000000001"     # 前回以降だけ取得
assert "from:ONEPIECE_tcg" in build_query({"accounts": ["@ONEPIECE_tcg"], "keywords": "抽選"})

approve(s)
c2 = FakeClient()
post_all(s, client=c2)
assert c2.quotes == ["1850000000000000001"] and "店舗の告知" in c2.sent[0]
assert "http" not in c2.sent[0]                              # 個別告知はリンク無し（安い）

# 1日1回のまとめ投稿
import common as cm
xpost.now = lambda: cm.now().replace(hour=21)
c3 = FakeClient()
xpost.post_daily_summary(s, client=c3); xpost.post_daily_summary(s, client=c3)
assert len(c3.sent) == 1 and "https://example.com/pokeca-lottery/" in c3.sent[0], c3.sent
print("\n--- X由来の投稿サンプル ---\n" + c2.sent[0] + "\n\n--- まとめ投稿 ---\n" + c3.sent[0])

print("\n--- 投稿サンプル ---\n" + c.sent[0] + "\n\n" + c.sent[2])
for f in ("seen.json", "lotteries.json"):
    (tmp / f).unlink(missing_ok=True)
tmp.mkdir(exist_ok=True)
first = collect(src, s, extractor=fake_extract, fetcher=lambda u: html)
assert first and all(i["status"] == "listed" for i in first)   # 初回はXに流さない
print("\nALL OK")
