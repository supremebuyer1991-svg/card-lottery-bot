"""大手の抽選：予告の段階で見つけていた抽選は、受付開始の時にも速報する"""
import sys, tempfile
from pathlib import Path
from datetime import timedelta
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import now, load_settings, save_json, load_json
import xpost

t = now()
iso = lambda d: d.isoformat(timespec="minutes")
base = {"game": "onepiece", "store": "ゲオ", "series": "神の支配", "product": "神の支配 BOX", "channel": "online",
        "status": "approved", "url": "https://geo-online.co.jp/news/788"}
lots = {
    # 2日前に予告で見つけ、1時間前に受付開始 → 受付開始の速報
    "a": dict(base, key="a", found_at=iso(t - timedelta(days=2)), start=iso(t - timedelta(hours=1)), end=iso(t + timedelta(days=3))),
    # 受付開始がまだ → 出さない
    "b": dict(base, key="b", store="ジョーシン", found_at=iso(t - timedelta(days=1)), start=iso(t + timedelta(hours=2)), end=iso(t + timedelta(days=3))),
    # 受付開始が設定の日時より前（手動で投稿済み） → 出さない
    "c": dict(base, key="c", store="エディオン", found_at=iso(t - timedelta(days=2)), start=iso(t - timedelta(hours=8)), end=iso(t + timedelta(days=3))),
    # 店頭抽選 → 出さない（いつも通り）
    "d": dict(base, key="d", store="ゲオ", series="別の弾", channel="store", found_at=iso(t - timedelta(days=2)), start=iso(t - timedelta(hours=1)), end=iso(t + timedelta(days=3))),
}
save_json("lotteries.json", lots)
s = load_settings()
s.update(big_post=True, dry_run=False, site_url="https://example.com", big_start_since=iso(t - timedelta(hours=4)))


class FakeClient:
    def __init__(self): self.texts = []
    def create_tweet(self, text): self.texts.append(text)


c = FakeClient()
xpost.post_big(s, client=c)
assert len(c.texts) == 1, c.texts
assert c.texts[0].startswith("🔔受付開始") and "ゲオ" in c.texts[0] and "始まりました" in c.texts[0], c.texts[0]
xpost.post_big(s, client=c)  # 2回目は出さない
assert len(c.texts) == 1
assert "geo|onepiece|神の支配|start" in load_json("x_meta.json", {})["big_posted"]
print("BIGSTART OK")
