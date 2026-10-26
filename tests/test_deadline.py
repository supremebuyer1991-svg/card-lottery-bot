"""締切の調査のテスト（XもAIも偽物）  python tests/test_deadline.py"""
import sys, tempfile
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import load_settings, load_json, save_json, now
import deadline

s = load_settings()
save_json("lotteries.json", {
    "a": {"store": "古本市場 倉敷中島店", "product": "30th", "status": "listed", "end": None, "found_at": now().isoformat(),
          "url": "https://x.com/furuichi/status/111"},
    "b": {"store": "TSUTAYA", "product": "OP-17", "status": "listed", "end": None, "found_at": now().isoformat(),
          "url": "https://livepocket.jp/e/abc"},
    "a2": {"store": "古本市場 倉敷中島店", "product": "メガブレイブ", "status": "listed", "end": None, "found_at": now().isoformat(),
           "url": "https://x.com/furuichi/status/111", "deadline_checked_at": now().isoformat()},
    "c": {"store": "済み", "product": "x", "status": "listed", "end": "2026-11-01T23:59:00+09:00", "url": "https://x.com/a/status/9"},
})


class FakeX:
    def __init__(self): self.calls = []
    def get_tweets(self, ids, **kw):
        self.calls.append(ids)
        t = NS(id=111, text="抽選受付中！詳細はこちら", created_at=datetime(2026, 10, 26), attachments={"media_keys": ["m1"]},
               entities={"urls": [{"expanded_url": "https://livepocket.jp/e/xyz"}]})
        return NS(data=[t], includes={"media": [NS(media_key="m1", url="https://pbs.twimg.com/media/aaa.jpg", preview_image_url=None)]})


pages = {"https://livepocket.jp/e/xyz": "<html><body>申込期間 10/27(火) 10:00 〜 10/30(金) 21:00</body></html>",
         "https://livepocket.jp/e/abc": "<html><body>受付期間 11/1 〜 11/3 23:59</body></html>"}
seen = []
def fake_ask(text, imgs, it, posted):
    seen.append((it["store"], text, imgs, posted))
    if "10/30" in text: return {"end": "2026-10-30T21:00:00+09:00", "evidence": "申込期間"}
    if "11/3" in text: return {"end": "2026-11-03T23:59:00+09:00", "evidence": "受付期間"}
    return {"end": None}

fx = FakeX()
n = deadline.fill_deadlines(s, ask=fake_ask, fetcher=lambda u: pages[u], x_client=fx)
L = load_json("lotteries.json", {})
assert n == 3, n
assert L["a2"]["end"] == L["a"]["end"]                                                     # 同じポストの別商品にも同じ締切
assert L["a"]["end"] == "2026-10-30T21:00:00+09:00" and "応募ページ" in L["a"]["end_from"]   # ポスト→LivePocketから
assert L["a"]["apply_url"] == "https://livepocket.jp/e/xyz"
assert L["b"]["end"] == "2026-11-03T23:59:00+09:00"                                        # LivePocketのページから
assert fx.calls == [["111"]]                                                                # 締切のある抽選は調べない
assert seen[0][2] == ["https://pbs.twimg.com/media/aaa.jpg"]                                # 画像もAIへ
# 1日は調べ直さない
assert deadline.fill_deadlines(s, ask=fake_ask, fetcher=lambda u: pages[u], x_client=fx) == 0 and len(fx.calls) == 1
print("DEADLINE OK")
