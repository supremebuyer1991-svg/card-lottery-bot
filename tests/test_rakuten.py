"""楽天の商品画像取得のテスト（ネットにはつながない）  python tests/test_rakuten.py"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common

tmp = Path(tempfile.mkdtemp())
common.STATE_DIR = tmp
import rakuten
from common import load_settings, load_json

s = load_settings()
s["rakuten_affiliate_id"] = "aaaa.bbbb"
os.environ["SITE_URL"] = "https://toreca-chusen-navi.pages.dev"


class Resp:
    def __init__(self, code, data):
        self.status_code, self._d, self.headers, self.text = code, data, {"content-type": "application/json"}, str(data)

    def json(self):
        return self._d


class FakeSession:
    def __init__(self, items, code=200):
        self.items, self.code, self.calls = items, code, []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append((url, params, headers))
        if self.code != 200:
            return Resp(self.code, {"errors": [{"errorCode": "REQUEST_CONTEXT_BODY_HTTP_REFERRER_MISSING"}]})
        return Resp(200, {"Items": self.items})


# キー未登録なら何もしない
os.environ.pop("RAKUTEN_APP_ID", None); os.environ.pop("RAKUTEN_ACCESS_KEY", None)
fs = FakeSession([])
assert rakuten.update(s, {"pokemon": ["テスト弾"]}, session=fs, sleep=0) == {} and fs.calls == []

os.environ["RAKUTEN_APP_ID"] = "uuid-app"; os.environ["RAKUTEN_ACCESS_KEY"] = "pk_test"
items = [
    {"itemName": "【オリパ】テスト弾 1口", "mediumImageUrls": ["https://img/x1.jpg?_ex=128x128"], "affiliateUrl": "https://a/1"},
    {"itemName": "ポケモンカードゲーム 拡張パック テスト弾 スリーブ", "mediumImageUrls": ["https://img/x2.jpg"], "affiliateUrl": "https://a/2"},
    {"itemName": "ポケモンカードゲーム 拡張パック「テスト弾」 BOX シュリンク付き 新品", "mediumImageUrls": ["https://img/ok.jpg?_ex=128x128"],
     "affiliateUrl": "https://a/ok", "itemPrice": 5940, "shopName": "テスト店"},
    {"itemName": "ポケモンカードゲーム 別の弾 BOX", "mediumImageUrls": ["https://img/x3.jpg"], "affiliateUrl": "https://a/3"},
]
fs = FakeSession(items)
c = rakuten.update(s, {"pokemon": ["テスト弾", "存在しない弾"]}, session=fs, sleep=0)
url, params, headers = fs.calls[0]
assert url.startswith("https://openapi.rakuten.co.jp/") and params["applicationId"] == "uuid-app"
assert headers["accessKey"] == "pk_test" and headers["Referer"] == "https://toreca-chusen-navi.pages.dev/"
assert params["affiliateId"] == "aaaa.bbbb" and "ポケモンカード テスト弾" == params["keyword"]
r = c["pokemon|テスト弾"]
assert r["url"] == "https://a/ok" and r["image"] == "https://img/ok.jpg?_ex=300x300", r   # オリパ・サプライ・別の弾は選ばない
assert c["pokemon|存在しない弾"]["image"] == ""                                            # 見つからない弾も記録
assert load_json("rakuten.json", {})["pokemon|テスト弾"]["url"] == "https://a/ok"

# 取り直し期間内はAPIを呼ばない
fs2 = FakeSession(items)
rakuten.update(s, {"pokemon": ["テスト弾"]}, session=fs2, sleep=0)
assert fs2.calls == []

# 1回の上限
s2 = dict(s, rakuten_max_calls_per_run=2)
fs3 = FakeSession([])
rakuten.update(s2, {"onepiece": ["A", "B", "C", "D"]}, session=fs3, sleep=0)
assert len(fs3.calls) == 2

# 鍵の設定ミス（403）なら、その回はそれ以上呼ばない
fs4 = FakeSession([], code=403)
rakuten.update(s, {"dragonball": ["X", "Y", "Z"]}, session=fs4, sleep=0)
assert len(fs4.calls) == 1

print("RAKUTEN ALL OK")
