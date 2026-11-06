"""海外向けページのチャート用：韓国版・台湾（繁体字）版のBOXの値段を、公式のAPIで1日1回記録する（11/7）
- 韓国版・台湾版とも：eBayの公式 Browse API（App ID/Cert ID が必要）→ 韓国語版・繁体字版BOXの出品価格（ドル）
  （NAVERショッピングの検索APIは 2026/7/31 で終了していて代わりもないため、韓国版もeBayで取る）
「今の値段」しか取れないので、毎日の値を souba.json に足していく（rec["kr"]・rec["tw"]：どちらもドル）。
規約で自動取得を禁止しているサイト（KREAM・蝦皮・露天など）は使わない。
"""
import os
import re
import statistics
import time
from datetime import datetime, timedelta, timezone

import requests

from common import load_json, save_json, log

JST = timezone(timedelta(hours=9))


def _clean(s):
    return re.sub(r"<[^>]+>", "", s or "")


def _norm(s):
    return re.sub(r"[\s\-・·]", "", (s or "").lower())


def _pick(prices):
    """出品のうち安いほう5件の真ん中（1件だけ極端に安い・高い出品に引っぱられないように）"""
    ps = sorted(p for p in prices if p > 0)
    if len(ps) < 2:
        return None
    lo = ps[:5]
    return round(statistics.median(lo), 2)


_EBAY_TOKEN = {}


def _ebay_token(sess):
    aid, cert = os.environ.get("EBAY_APP_ID"), os.environ.get("EBAY_CERT_ID")
    if not (aid and cert):
        return None
    if _EBAY_TOKEN.get("exp", 0) > time.time() + 60:
        return _EBAY_TOKEN["v"]
    r = sess.post("https://api.ebay.com/identity/v1/oauth2/token", auth=(aid, cert), timeout=20,
                  data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"})
    r.raise_for_status()
    j = r.json()
    _EBAY_TOKEN.update(v=j["access_token"], exp=time.time() + int(j.get("expires_in") or 7200))
    return _EBAY_TOKEN["v"]


def ebay_local(sess, code, lang, name_en=""):
    """eBayで韓国語版（lang="kr"）・繁体字版（lang="tw"）のBOXの出品価格（ドル）"""
    tok = _ebay_token(sess)
    if not (tok and code):
        return None
    c = code.upper()
    if lang == "tw":
        q, must, code_re = f"pokemon {c}F booster box chinese", r"chinese|中文|繁", rf"\b{re.escape(c)}F?\b"
        bad = r"japanese|korean|english|simplified|\bCSV"
    else:
        q, must, code_re = f"pokemon korean {name_en or c} booster box", r"korean|한글|한국", rf"\b{re.escape(c)}\b|{re.escape(name_en)}" if name_en else rf"\b{re.escape(c)}\b"
        bad = r"japanese|chinese|english|\bjp\b"
    r = sess.get("https://api.ebay.com/buy/browse/v1/item_summary/search", timeout=20,
                 params={"q": q, "limit": 50, "filter": "buyingOptions:{FIXED_PRICE},conditions:{NEW}"},
                 headers={"Authorization": f"Bearer {tok}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"})
    r.raise_for_status()
    out = []
    for it in r.json().get("itemSummaries") or []:
        t = it.get("title") or ""
        if not re.search(code_re, t, re.I) or not re.search(must, t, re.I) or not re.search(r"box", t, re.I):
            continue
        if re.search(bad, t, re.I) or re.search(r"case|pack only|single pack|sleeve|\b\d+\s*box(es)?\b|empty", t, re.I):
            continue
        try:
            out.append(float((it.get("price") or {}).get("value") or 0))
        except ValueError:
            pass
    return _pick(out)


def update_local_prices(settings, sess=None):
    """1日1回：韓国版・台湾版の値段を記録する（キーがなければ何もしない）"""
    has_tw = has_kr = bool(os.environ.get("EBAY_APP_ID") and os.environ.get("EBAY_CERT_ID"))
    if not (has_kr or has_tw):
        return
    data = load_json("souba.json", {})
    today = datetime.now(JST).date().isoformat()
    if data.get("local_checked") == today:
        return
    import intl
    sess = sess or requests.Session()
    sess.headers.update({"User-Agent": "tcg-chusen-bot/1.0 (+https://tcg-chusen.com)"})
    n_kr = n_tw = 0
    for key, rec in (data.get("items") or {}).items():
        g, x = key.split("|", 1)
        if g != "pokemon":
            continue
        code, en, _ctp, zh, ko = intl.set_info(g, x)
        if has_kr and ko and code:
            try:
                v = ebay_local(sess, code, "kr", en)
                if v:
                    rec["kr"] = {**(rec.get("kr") or {}), today: v}
                    n_kr += 1
            except Exception as e:
                log(f"韓国版の相場（eBay）: {x} 取得失敗 {e}")
            time.sleep(0.3)
        if has_tw and zh and code:
            try:
                v = ebay_local(sess, code, "tw")
                if v:
                    rec["tw"] = {**(rec.get("tw") or {}), today: v}
                    n_tw += 1
            except Exception as e:
                log(f"台湾版の相場（eBay）: {x} 取得失敗 {e}")
            time.sleep(0.3)
        for f in ("kr", "tw"):  # 400日より前は捨てる
            if rec.get(f):
                cut = (datetime.now(JST).date() - timedelta(days=400)).isoformat()
                rec[f] = {d: v for d, v in rec[f].items() if d >= cut}
    data["local_checked"] = today
    save_json("souba.json", data)
    log(f"韓国版・台湾版の相場: 韓国 {n_kr}件・台湾 {n_tw}件")
