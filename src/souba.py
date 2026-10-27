"""サイトに載せるBOXの相場を1日1回だけ読む（config/souba.yaml の商品だけ）

・スニダン：その日の「1個」の取引の平均（スニダンの相場グラフと同じ数字）。日本時間の日付ごと
・TCGplayer：アメリカの取引の相場（marketPrice・ドル）。アメリカ時間の日付ごと
・1件ずつ間をあけて読む。断られたら（403など）その日はあきらめる
・state/souba.json に日付ごとの値段を残す（60日分）
"""
import re
import time
from datetime import datetime, timedelta, timezone

import requests
import yaml

from common import ROOT, load_json, save_json, now, log

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
JST = timezone(timedelta(hours=9))
WAIT = 3
KEEP_DAYS = 60


def items():
    p = ROOT / "config" / "souba.yaml"
    d = yaml.safe_load(p.read_text(encoding="utf-8")) if p.exists() else {}
    out = []
    for g, lst in ((d or {}).get("items") or {}).items():
        for x in lst or []:
            out.append(dict(x, game=g))
    # 公式サイト・スニダンの検索から自動で見つけた新しい弾
    have = {(i["game"], i["series"]) for i in out}
    for k, aid in (load_json("newsets.json", {}).get("snkr") or {}).items():
        g, x = k.split("|", 1)
        if (g, x) not in have:
            out.append({"game": g, "series": x, "name": f"{x} BOX", "snkr": aid, "teika": _teika(g, x)})
    return out


def _teika(g, x):
    """自動で見つけた弾の定価（BOX）。希望小売価格の「1BOX（30パック）6,000円」から。分からなければ None"""
    try:
        import newsets
        p = (newsets.merged_info().get(g) or {}).get(x, {}).get("price") or ""
    except Exception:
        return None
    m = re.search(r"1BOX[^0-9]*\d*[^0-9]*?([\d,]{4,})円", p)
    return int(m.group(1).replace(",", "")) if m else None


def _snkr_daily(sess, aid):
    """スニダンの商品番号 → {日付(YYYY-MM-DD): その日の1個の取引の平均}"""
    h = sess.get(f"https://snkrdunk.com/apparels/{aid}", timeout=30)
    h.raise_for_status()
    m = re.search(r'\\?"productId\\?":(\d+)', h.text)
    if not m:
        raise ValueError("productId が見つからない")
    pid = m.group(1)
    j = sess.get(f"https://snkrdunk.com/v3/products/{pid}/trading-history?range=all", timeout=30)
    j.raise_for_status()
    j = j.json()
    opt = next((o for o in ((j.get("filters") or {}).get("variants") or {}).get("options") or []
                if re.match(r"^1(個|パック|BOX|ボックス)", o.get("name") or "")), None)
    if opt:
        time.sleep(1)
        r = sess.get(f"https://snkrdunk.com/v3/products/{pid}/trading-history?range=all&variant_id={opt['id']}", timeout=30)
        r.raise_for_status()
        j = r.json()
    day = {}
    for p in (((j.get("chart") or {}).get("lines") or [{}])[0].get("points") or []):
        ts = p.get("timestamp")
        if ts is None or p.get("price") is None:
            continue
        ts = ts / 1000 if ts > 1e11 else ts
        day[datetime.fromtimestamp(ts, JST).date().isoformat()] = int(p["price"])
    return day


def _tcg_daily(sess, tid):
    """TCGplayerの商品番号 → {アメリカの日付: marketPrice(ドル)}。いちばん新しい日はまだ途中なので外す"""
    r = sess.get(f"https://infinite-api.tcgplayer.com/price/history/{tid}?range=month", timeout=30)
    r.raise_for_status()
    res = r.json().get("result") or []
    out = {}
    for d in res[1:]:
        v = (d.get("variants") or [{}])[0].get("marketPrice")
        if d.get("date") and v not in (None, ""):
            out[d["date"][:10]] = round(float(v), 2)
    return out


def _fx(sess):
    try:
        return round(float(sess.get("https://open.er-api.com/v6/latest/USD", timeout=20).json()["rates"]["JPY"]), 1)
    except Exception:
        return None


def update_souba(settings, sess=None, sleep=time.sleep, force=False):
    hour = settings.get("souba_hour", 7)
    t = now()
    data = load_json("souba.json", {})
    today = t.date().isoformat()
    if not force and (t.hour < hour or data.get("checked") == today):
        return 0
    data["checked"] = today
    sess = sess or requests.Session()
    sess.headers.update({"User-Agent": UA, "Accept-Language": "ja-JP,ja;q=0.9"})
    store = data.setdefault("items", {})
    got = blocked = 0
    for k, it in enumerate(items()):
        key = f"{it['game']}|{it['series']}"
        rec = store.setdefault(key, {})
        rec.update(name=it["name"], game=it["game"], series=it["series"], teika=it.get("teika"), snkr=it.get("snkr"))
        if it.get("snkr") and not blocked:
            if k:
                sleep(WAIT)
            try:
                rec["jp"] = {**(rec.get("jp") or {}), **_snkr_daily(sess, it["snkr"])}
                got += 1
            except requests.HTTPError as e:
                log(f"相場（スニダン）: {it['name']} 取得できず {e} → 今日はここまで")
                blocked = 1  # 断られたら続けない
            except Exception as e:
                log(f"相場（スニダン）: {it['name']} 取得失敗 {e}")
        if it.get("tcg"):
            try:
                rec["us"] = {**(rec.get("us") or {}), **_tcg_daily(sess, it["tcg"])}
            except Exception as e:
                log(f"相場（TCGplayer）: {it['name']} 取得失敗 {e}")
        cut = (t.date() - timedelta(days=KEEP_DAYS)).isoformat()
        for f in ("jp", "us"):
            if rec.get(f):
                rec[f] = {d: v for d, v in sorted(rec[f].items()) if d >= cut}
    fx = _fx(sess)
    if fx:
        data["fx"] = fx
    data["updated"] = t.isoformat()
    save_json("souba.json", data)
    log(f"相場: スニダン {got}/{sum(1 for i in items() if i.get('snkr'))}件" + (f"・1ドル={fx}円" if fx else ""))
    return got


def summary(rec, today=None):
    """サイトに出す数字：いちばん新しい日の相場・その前の日との差・7日前との差・定価との差・30日分の点"""
    jp = sorted((rec.get("jp") or {}).items())
    if not jp:
        return None
    today = today or now().date().isoformat()
    # 今日の分はまだ途中なので、昨日までの値を使う
    done = [x for x in jp if x[0] < today] or jp
    d0, v0 = done[-1]
    prev = done[-2] if len(done) > 1 else None
    wk = next((x for x in reversed(done) if x[0] <= (datetime.fromisoformat(d0) - timedelta(days=7)).date().isoformat()), None)
    pts = [(d, v) for d, v in done if d >= (datetime.fromisoformat(d0) - timedelta(days=30)).date().isoformat()]
    us = sorted((rec.get("us") or {}).items())
    out = {"date": d0, "price": v0, "teika": rec.get("teika"),
           "prev": prev, "week": wk, "points": pts, "snkr": rec.get("snkr")}
    if len(us) >= 1:
        out["us"] = us[-1]
        out["us_prev"] = us[-2] if len(us) > 1 else None
    return out
