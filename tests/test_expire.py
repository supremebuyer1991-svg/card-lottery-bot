"""締切切れ・締切不明の期限・古いデータの削除のテスト  python tests/test_expire.py"""
import sys, tempfile
from datetime import timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import save_json, load_json, load_settings, now
import approve

s = load_settings(); s["auto_approve"] = True
iso = lambda d: (now() - timedelta(days=d)).isoformat()
save_json("lotteries.json", {
    "past": {"status": "listed", "end": iso(1), "found_at": iso(3), "store": "a", "product": "p"},
    "noend_old": {"status": "listed", "end": None, "found_at": iso(11), "store": "b", "product": "p"},
    "noend_new": {"status": "listed", "end": None, "found_at": iso(2), "store": "c", "product": "p"},
    "live": {"status": "listed", "end": (now() + timedelta(days=2)).isoformat(), "found_at": iso(1), "store": "d", "product": "p"},
    # 投稿が2026-08-09のXの告知（情報元が載せたまま・見つけたのは昨日）→ 締切不明なら終了
    "old_post": {"status": "listed", "end": None, "found_at": iso(1), "store": "f", "product": "p",
                 "url": "https://x.com/lit_tenjin/status/2086377212266348799"},
    "old_post_with_end": {"status": "listed", "end": (now() + timedelta(days=5)).isoformat(), "found_at": iso(1), "store": "g",
                          "product": "p", "url": "https://x.com/lit_tenjin/status/2086377212266348799"},
    "index": {"status": "listed", "end": None, "found_at": iso(1), "store": "ポケモンセンターオンライン", "product": "30周年商品",
              "url": "https://www.pokemon-card.com/info/"},
    "vague": {"status": "approved", "end": (now() + timedelta(days=1)).isoformat(), "found_at": iso(0), "store": "岡南", "product": "p"},
    "vague2": {"status": "new", "end": (now() + timedelta(days=1)).isoformat(), "found_at": iso(0), "store": "北海道（店舗名不明）", "product": "p", "confidence": 1},
    "okshort": {"status": "approved", "end": (now() + timedelta(days=1)).isoformat(), "found_at": iso(0), "store": "DMM", "product": "p"},
    "old_closed": {"status": "closed", "end": iso(40), "closed_at": iso(35), "store": "e", "product": "p"},
})
approve.approve(s)
L = load_json("lotteries.json", {})
assert L["past"]["status"] == "closed"                 # 締切が過ぎた
assert L["noend_old"]["status"] == "closed"            # 締切不明のまま10日
assert L["noend_new"]["status"] == "listed"            # 締切不明でもまだ新しい
assert L["live"]["status"] == "listed"
assert L["old_post"]["status"] == "closed"            # 告知の投稿から21日以上・締切不明
assert L["old_post_with_end"]["status"] == "listed"    # 締切が分かっていればそのまま
assert L["index"]["status"] == "rejected"             # 応募先が情報元の一覧ページ → 載せない
assert L["vague"]["status"] == "pending" and L["vague2"]["status"] == "pending"   # 店名が地名だけ・不明
assert L["okshort"]["status"] == "approved"            # 短くても英字の店名はOK
assert "old_closed" not in L                           # 終了から30日でデータから削除
print("EXPIRE OK")
