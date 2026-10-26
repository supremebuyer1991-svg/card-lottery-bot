"""今日の相場のテスト  python tests/test_market.py"""
import sys, tempfile, types
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import save_json, load_json, now
import market

assert market.parse_price('<script type="application/ld+json">{"@type":"Product","offers":{"@type":"AggregateOffer","lowPrice":"30000"}}</script>') == 30000
assert market.parse_price('<div>¥28,500〜 即購入可</div>') == 28500
assert market.parse_price('<div>なし</div>') is None

market.products = lambda: [{"game": "pokemon", "name": "A弾", "kind": "BOX", "url": "u1", "msrp": 5400},
                           {"game": "pokemon", "name": "B弾", "kind": "BOX", "url": "u2"},
                           {"game": "pokemon", "name": "C弾", "kind": "BOX", "url": "u3"}]
y = (now().date().fromordinal(now().date().toordinal() - 1)).isoformat()
save_json("market.json", {"prices": {y: {"A弾": 31200}}})
save_json("lotteries.json", {"x": {"series": "B弾", "product": "B弾 1BOX（7,200円税込）"}})
calls, waits = [], []
def fetch(u):
    calls.append(u)
    if u == "u2":
        return types.SimpleNamespace(status_code=403, text="")
    return types.SimpleNamespace(status_code=200, text="¥30,000〜")
n = market.update_market({"market_hour": 0}, fetch=fetch, sleep=waits.append)
assert n == 1 and calls == ["u1", "u2"] and waits == [10]   # 断られたらそこで止める・10秒あける
assert market.update_market({"market_hour": 0}, fetch=fetch, sleep=waits.append) == 0 and len(calls) == 2  # 1日1回だけ
rows, d0 = market.today_rows("pokemon")
assert rows[0][:5] == ("A弾", "BOX", 5400, 30000, -1200), rows
assert market.msrp_from_lotteries("B弾") == 7200
print("MARKET OK")
