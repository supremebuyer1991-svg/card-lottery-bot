import sys, os, types, tempfile, shutil
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import common
common.STATE_DIR = __import__("pathlib").Path(tempfile.mkdtemp())
import xtrend
from common import load_json, save_json

class T:
    def __init__(s, i): s.id = 100 + i; s.text = f"話題{i}"; s.author_id = 1; s.public_metrics = {"like_count": i, "retweet_count": 1}
class C:
    def search_recent_tweets(s, **k):
        assert "relevancy" == k["sort_order"]
        return types.SimpleNamespace(data=[T(i) for i in range(8)], includes={"users": [types.SimpleNamespace(id=1, username="u")]})
def ask(posts, n):
    assert posts[0]["likes"] == 7  # 反応の多い順
    return [{"type": "解説", "topic": "高騰", "text": "テスト本文 #ポケカ", "basis": "根拠", "src": [0, 99]},
            {"type": "相場", "topic": "x", "text": "リンク http://a", "src": []}]
save_json("x_usage.json", {})
save_json("x_trends.json", {})
s = {"trend_hours": [0], "trend_reads": 10, "x_read_budget_per_day": 1000}
xtrend.update_trends(s, client=C(), ask=ask)
d = load_json("x_trends.json", {})
assert len(d["items"]) == 1 and d["items"][0]["src"] == ["https://x.com/u/status/107"], d
xtrend.update_trends(s, client=C(), ask=lambda *a: 1 / 0)  # 同じ枠は2回やらない
print("ok")
