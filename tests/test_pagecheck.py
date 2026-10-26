"""応募ページの受付終了チェックのテスト  python tests/test_pagecheck.py"""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import common
common.STATE_DIR = Path(tempfile.mkdtemp())
from common import save_json, load_json, now
import pagecheck

save_json("lotteries.json", {
    "form": {"status": "listed", "store": "a", "product": "p", "url": "https://docs.google.com/forms/x"},
    "shop": {"status": "listed", "store": "b", "product": "p", "url": "https://shop.example/item1"},
    "open": {"status": "listed", "store": "c", "product": "p", "url": "https://shop.example/item2"},
    "x": {"status": "listed", "store": "d", "product": "p", "url": "https://x.com/a/status/1"},
})
pages = {"https://docs.google.com/forms/x": "<p>このフォームは回答を受け付けていません</p>",
         "https://shop.example/item1": "<p>メニュー：販売終了品を含む</p><p>在庫あり カートに入れる</p>",
         "https://shop.example/item2": "<p>受付中 応募する</p>"}
asked = []
def ask(text, it):
    asked.append(it["store"])
    return {"status": "ended", "evidence": "回答を受け付けていません"} if "回答" in text else {"status": "open"}
n = pagecheck.check_pages({}, ask=ask, fetcher=lambda u: pages[u])
L = load_json("lotteries.json", {})
assert n == 1 and L["form"]["status"] == "closed"     # フォームが閉じている → 終了
assert L["shop"]["status"] == "listed"                # メニューの「販売終了品」だけ → AIが受付中と判断
assert L["open"]["status"] == "listed" and "c" not in asked   # 終わりの言葉が無ければAIを呼ばない
assert "d" not in asked and not L["x"].get("page_checked_at")  # Xのポストは対象外
assert pagecheck.check_pages({}, ask=ask, fetcher=lambda u: pages[u]) == 0  # 同じ日は見に行かない
print("PAGECHECK OK")
