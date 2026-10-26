"""ネット／店頭の振り分けテスト（AIは偽物）  python tests/test_classify.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
import classify as _cl
_cl.load_overrides = lambda: {}  # 実際の決まりファイルは使わない
from classify import classify
from common import save_json, load_json, load_settings

s = load_settings()
save_json("lotteries.json", {
    "a": {"store": "カードラボ岐阜店", "product": "30th BOX 購入権", "channel": "online", "area": None, "status": "listed"},
    "b": {"store": "Amazon", "product": "BOX", "channel": "online", "area": None, "status": "listed"},
    "c": {"store": "シーガル名取店", "product": "BOX", "channel": "store", "area": None, "status": "listed"},
    "d": {"store": "終了した店", "product": "BOX", "channel": "online", "status": "closed"},
})
calls = []
def fake(rows):
    calls.append(rows)
    assert "終了した店" not in rows
    return [{"id": 0, "channel": "store", "area": "岐阜県"}, {"id": 1, "channel": "online", "area": None},
            {"id": 2, "channel": "store", "area": "宮城県"}]
assert classify(s, ask=fake) == 3
L = load_json("lotteries.json", {})
assert L["a"]["channel"] == "store" and L["a"]["area"] == "岐阜県"
assert L["b"]["channel"] == "online" and L["c"]["area"] == "宮城県"
# 判定済みは二度と聞かない
assert classify(s, ask=fake) == 0 and len(calls) == 1
# 内容が変わったら判定し直す
L["b"]["product"] = "BOX（店頭受け取り）"; save_json("lotteries.json", L)
classify(s, ask=lambda r: [{"id": 0, "channel": "store", "area": None}])
assert load_json("lotteries.json", {})["b"]["channel"] == "store"
# 人が確認した決まり（config/channel_overrides.yaml）がAIより優先される
import classify as cl
cl.load_overrides = lambda: {"TierOne 浜松店": "store"}
save_json("lotteries.json", {"t": {"store": "TierOne 浜松店", "product": "OP-17", "channel": "online", "status": "listed"}})
cl.classify(s, ask=lambda r: [{"id": 0, "channel": "online", "area": "静岡県"}])
L = load_json("lotteries.json", {})
assert L["t"]["channel"] == "store" and L["t"]["area"] == "静岡県", L
print("CLASSIFY ALL OK")
