"""入荷Nowの記事を直接読むテスト  python tests/test_nyukanow.py"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import nyukanow

html = (Path(__file__).parent / "fixtures" / "nyukanow_sample.html").read_text(encoding="utf-8")
now = datetime(2026, 10, 30, 15, 0, tzinfo=timezone(timedelta(hours=9)))
got = [it for _, _, it in nyukanow.items(html, "https://nyuka-now.com/archives/159770", now=now)]
stores = [i["store"] for i in got]
assert stores == ["お宝創庫", "お宝創庫", "楽天ブックス", "TSUTAYA"], stores   # 終了のお店・締切が過ぎた表・先着販売は読まない。商品ごとに1件
o, o2, r, t = got
assert t["channel"] == "store" and t["url"] == "https://cloud-pass.jp/pr/885c"   # 「（店舗）」は店頭抽選・「応募ページ」の欄のリンクも読む
assert o["end"].startswith("2026-11-01T23:45") and o["start"].startswith("2026-10-29T12:00")
assert o["channel"] == "store" and o["id_check"] is True and o["member"] and "購入履歴" in o["tags"]
assert o["buy"].startswith("11/5") and o["url"].startswith("https://www.otakarasouko.com/")
assert o["series"] == "ストームエメラルダ" and o2["series"] == "30th CELEBRATION"
assert not o.get("conditions")                                   # 入荷Nowの条件の文はそのまま使わない
assert r["url"] == "https://books.rakuten.co.jp/event/x/" and r["channel"] == "online"   # アフィリエイトを外す
assert r["end"].startswith("2026-11-03T23:59") and r["confidence"] >= 0.7
assert nyukanow.unwrap("https://ad2.trafficgate.net/t/r/1") is None
assert nyukanow.unwrap("https://www.amazon.co.jp/dp/B0?m=1&tag=nnowapp-22") == "https://www.amazon.co.jp/dp/B0?m=1"
print("NYUKANOW OK")
