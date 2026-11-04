"""楽天ブックス（楽天市場の shopCode=book）のトレカの在庫を楽天APIで確かめる（見張りの準備・手動実行）"""
import json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import requests
from rakuten import ENDPOINT
app, key = os.environ["RAKUTEN_APP_ID"].strip(), os.environ["RAKUTEN_ACCESS_KEY"].strip()
site = "https://toreca-chusen-navi.pages.dev"  # 楽天に登録してあるアドレス
H = {"accessKey": key, "Referer": site + "/", "Origin": site, "User-Agent": "toreca-chusen-navi/1.0"}
out = {}
for kw in ["ONE PIECEカードゲーム ブースターパック", "ポケモンカードゲーム 拡張パック", "ポケモンカードゲーム 強化拡張パック"]:
    for av in (0, 1):
        p = {"applicationId": app, "keyword": kw, "shopCode": "book", "format": "json", "formatVersion": 2, "hits": 30, "availability": av}
        time.sleep(1.3)
        r = requests.get(ENDPOINT, params=p, headers=H, timeout=20)
        j = r.json() if r.ok else {"err": r.status_code, "t": r.text[:300]}
        out[f"{kw}|av{av}"] = [{k: it.get(k) for k in ("itemName", "itemCode", "itemPrice", "availability", "itemUrl")} for it in (j.get("Items") or [])] if r.ok else j
        print(kw, av, r.status_code, len(out[f"{kw}|av{av}"]) if r.ok else j)
json.dump(out, open("state/rakuten_books_probe.json", "w"), ensure_ascii=False, indent=1)
