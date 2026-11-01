"""LivePocket常連店：抽選ページからお店のページを覚え、常連店のお店ページから知らない抽選だけを拾う"""
import sys, tempfile
from pathlib import Path
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
from common import now, load_settings, load_json, save_json

common.STATE_DIR = Path(tempfile.mkdtemp())
import lpshops
from collect import collect

EVENT = '<html><a href="/p/shopA">泉大津店</a><a href="https://livepocket.jp/p/shopA">泉大津店</a></html>'
ORG = ('<html><a href="/e/old1">【泉大津店】ポケカ抽選 旧</a>'
       '<a href="/e/new9">【泉大津店】ポケモンカード 新弾 抽選</a>'
       '<a href="/e/zzz">【泉大津店】ゲーム機 抽選</a></html>')
calls = []


def fetcher(url):
    calls.append(url)
    if "/p/shopA" in url:
        return ORG
    if "/e/new9" in url:
        return "【泉大津店】ポケモンカード 新弾 抽選 受付中"
    return EVENT


end = (now() + timedelta(days=3)).isoformat(timespec="minutes")
lots = {
    "a": {"store": "泉大津店", "url": "https://livepocket.jp/e/old1?x=1", "found_at": "2026-10-01", "status": "closed"},
    "b": {"store": "泉大津店", "url": "https://livepocket.jp/e/old2", "found_at": "2026-10-02", "status": "closed"},
    "c": {"store": "別の店", "url": "https://livepocket.jp/e/solo", "found_at": "2026-10-03", "status": "closed"},
    "d": {"store": "Amazon", "url": "https://amazon.co.jp/x", "status": "closed"},
}
save_json("lotteries.json", lots)

# 1) 抽選ページからお店を覚える（上限ずつ）
lpshops.learn(lots, fetcher=fetcher, limit=2)
db = load_json("lp_shops.json", {})
assert len(db["events"]) == 2, db
lpshops.learn(lots, fetcher=fetcher, limit=8)
db = load_json("lp_shops.json", {})
assert set(db["events"]) == {"old1", "old2", "solo"}, db
assert sorted(db["shops"]["https://livepocket.jp/p/shopA"]["events"]) == ["old1", "old2", "solo"]
n_calls = len(calls)
lpshops.learn(lots, fetcher=fetcher)  # もう全部覚えた → アクセスしない
assert len(calls) == n_calls

# ほかの処理で読んだページからも覚える
lpshops.record("https://livepocket.jp/e/xyz", '<a href="/p/shopB">B店</a>', "B店")
assert load_json("lp_shops.json", {})["events"]["xyz"] == "https://livepocket.jp/p/shopB"

# 2) 2回以上の店だけ、間隔をあけて見る
s = load_settings()
srcs = lpshops.sources(s, lots, [])
assert [x["url"] for x in srcs] == ["https://livepocket.jp/p/shopA"], srcs
assert "https://livepocket.jp/e/old1" in srcs[0]["skip_urls"]
assert lpshops.sources(s, lots, []) == []  # 直後はお休み
assert lpshops.sources(s, lots, [{"url": "https://livepocket.jp/p/shopA"}]) == []  # すでに情報元にある店は除く

# 3) お店ページから、知らない抽選（カードのもの）だけAIへ
seen_texts = []


def fake_extract(text, game, gname, sname, url):
    seen_texts.append(url)
    return [{"store": "泉大津店", "product": "新弾 BOX", "game": "pokemon", "end": end, "url": url, "confidence": 0.9}]


s["auto_approve"], s["dry_run"] = True, True
new = collect(srcs, s, extractor=fake_extract, fetcher=fetcher)
assert seen_texts == ["https://livepocket.jp/e/new9"], seen_texts  # 旧（既知）とゲーム機は読まない
assert len(new) == 1 and new[0]["status"] == "new", new  # 初めて見る店でも新着扱い
print("LPSHOPS OK")
