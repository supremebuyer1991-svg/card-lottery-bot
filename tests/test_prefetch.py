"""一覧ページの先読み：別々のサイトは同時に、同じサイトは1件ずつ。失敗はそのまま伝える"""
import sys, time, threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from collect import prefetch

active, peak_same = {}, {"n": 0}
lock = threading.Lock()


def fake(url):
    host = url.split("/")[2]
    with lock:
        active[host] = active.get(host, 0) + 1
        peak_same["n"] = max(peak_same["n"], active[host])
    time.sleep(0.3)
    with lock:
        active[host] -= 1
    if "bad" in url:
        raise RuntimeError("403")
    return "body:" + url


urls = ["https://a.com/1", "https://a.com/2", "https://b.com/1", "https://c.com/bad", "https://d.com/1"]
t = time.time()
res = prefetch(urls, fake)
took = time.time() - t
assert peak_same["n"] == 1, "同じサイトに同時アクセスしている"
assert took < 0.9, f"並行になっていない {took:.2f}s"  # 順番なら1.5秒
assert res["https://a.com/2"] == ("ok", "body:https://a.com/2")
assert res["https://c.com/bad"][0] == "err"
assert prefetch([], fake) == {}
print("PREFETCH OK")
