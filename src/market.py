"""「今日の相場」用に、スニダンの商品ページから相場（最安値）を1日1回だけ読む

・config/market.yaml の商品だけ（検索はしない）
・1日1回（market_hour 時以降の最初の実行）、1件ずつ10秒あけて、10件まで
・読めなかったらその日はあきらめる（何度もやり直さない）
・state/market.json に日付ごとの値段を残す（前日比に使う。60日より古い日は消す）
"""
import json
import re
import time
from datetime import timedelta
from pathlib import Path

import requests
import yaml

from common import ROOT, load_json, save_json, now, log

UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
      "Version/17.5 Mobile/15E148 Safari/604.1")
MAX_PAGES = 10
WAIT = 10


def products():
    p = ROOT / "config" / "market.yaml"
    if not p.exists():
        return []
    return [x for x in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("products") or [] if x.get("name")]


def parse_price(html):
    """商品ページから相場（いちばん安い出品の値段）を取り出す。見つからなければ None"""
    # 1) 機械向けの商品情報（JSON-LD の offers.lowPrice / price）
    for m in re.finditer(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', html, re.S):
        try:
            d = json.loads(m.group(1))
        except Exception:
            continue
        for e in d if isinstance(d, list) else [d]:
            o = e.get("offers") if isinstance(e, dict) else None
            for x in (o if isinstance(o, list) else [o] if o else []):
                v = x.get("lowPrice") or x.get("price")
                if v and str(v).replace(".", "").isdigit() and float(v) > 0:
                    return int(float(v))
    # 2) 画面の「¥30,000〜」のような表示
    m = re.search(r"[¥￥]\s*([0-9]{1,3}(?:,[0-9]{3})+|[0-9]{3,7})\s*[〜~]", html)
    if m:
        return int(m.group(1).replace(",", ""))
    return None


def msrp_from_lotteries(name):
    """定価が設定されていない商品は、抽選の告知の「7,200円税込」のような値段から拾う（いちばん多い値段）"""
    lots = load_json("lotteries.json", {})
    cnt = {}
    for it in lots.values():
        text = f"{it.get('series') or ''} {it.get('product') or ''} {it.get('conditions') or ''}"
        if name not in text:
            continue
        for v in re.findall(r"([0-9]{1,2},[0-9]{3}|[0-9]{4,5})円", text):
            n = int(v.replace(",", ""))
            if 1000 <= n <= 60000:
                cnt[n] = cnt.get(n, 0) + 1
    return max(cnt, key=cnt.get) if cnt else None


def update_market(settings, fetch=None, sleep=time.sleep):
    hour = settings.get("market_hour", 8)
    t = now()
    if t.hour < hour:
        return 0
    data = load_json("market.json", {})
    today = t.date().isoformat()
    if data.get("checked") == today:
        return 0  # 今日はもう見た（成功でも失敗でも1日1回）
    items = [p for p in products() if p.get("url")][:MAX_PAGES]
    data["checked"] = today
    if not items:
        save_json("market.json", data)
        return 0
    fetch = fetch or (lambda u: requests.get(u, headers={"User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9"}, timeout=30))
    day = data.setdefault("prices", {}).setdefault(today, {})
    got = 0
    for k, p in enumerate(items):
        if k:
            sleep(WAIT)
        try:
            r = fetch(p["url"])
            if getattr(r, "status_code", 200) >= 400:
                log(f"相場: {p['name']} 取得できず（{r.status_code}）→ 今日はここまで")
                break  # 断られたら続けない（アクセスしすぎない）
            price = parse_price(r.text)
        except Exception as e:
            log(f"相場: {p['name']} 取得失敗 {e} → 今日はここまで")
            break
        if price:
            day[p["name"]] = price
            got += 1
        else:
            log(f"相場: {p['name']} 値段が見つからず")
    cutoff = (t.date() - timedelta(days=60)).isoformat()
    data["prices"] = {d: v for d, v in data["prices"].items() if d >= cutoff and v}
    save_json("market.json", data)
    log(f"相場: {got}/{len(items)}件の値段を取得")
    return got


def today_rows(game=None):
    """[(商品, 種類, 定価, 今日, 前日比)] 今日の値段があるものだけ"""
    data = load_json("market.json", {})
    prices = data.get("prices") or {}
    if not prices:
        return [], None
    days = sorted(prices)
    d0 = days[-1]
    prev = prices[days[-2]] if len(days) > 1 else {}
    rows = []
    for p in products():
        if game and p.get("game") != game:
            continue
        v = prices[d0].get(p["name"])
        if not v:
            continue
        msrp = p.get("msrp") or msrp_from_lotteries(p["name"])
        diff = v - prev[p["name"]] if p["name"] in prev else None
        rows.append((p.get("label") or p["name"], p.get("kind") or "", msrp, v, diff, p.get("game")))
    return rows, d0
