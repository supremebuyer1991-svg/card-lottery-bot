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
    "old_closed": {"status": "closed", "end": iso(40), "closed_at": iso(35), "store": "e", "product": "p"},
})
approve.approve(s)
L = load_json("lotteries.json", {})
assert L["past"]["status"] == "closed"                 # 締切が過ぎた
assert L["noend_old"]["status"] == "closed"            # 締切不明のまま10日
assert L["noend_new"]["status"] == "listed"            # 締切不明でもまだ新しい
assert L["live"]["status"] == "listed"
assert "old_closed" not in L                           # 終了から30日でデータから削除
print("EXPIRE OK")
