"""楽天市場の商品検索API（2026-07-01版）で、弾ごとの商品画像とアフィリエイトリンクを取ってくる。

・必要なもの（GitHub の Secrets）：RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY
・楽天アフィリエイトID：config/settings.yaml の rakuten_affiliate_id（公開されるIDなのでファイルでOK）
・結果は state/rakuten.json に保存。1つの弾は rakuten_refresh_days 日ごとに取り直す（APIの使いすぎ防止）
・楽天の新API は Referer ヘッダーが必須。アプリ登録時の「許可するWebサイト」と同じサイトURLを送る
"""
import os
import re
import time
import unicodedata

import requests

from common import load_json, save_json, now, parse_dt, log

ENDPOINT = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/20260701"
# 画像に使いたくない商品（オリパ・中古・バラ売り・サプライ等）
NG_WORDS = ("オリパ", "オリジナルパック", "中古", "シングル", "バラ", "ばら", "1パック", "5パック", "10パック", "15パック", "スリーブ", "ローダー", "ケース",
            "ファイル", "プレイマット", "福袋", "くじ", "まとめ売り", "空箱", "未開封品 ※")


def _norm(s):
    return re.sub(r"[\s「」『』()（）・×xX【】\[\]/／&＆+＋-]", "", unicodedata.normalize("NFKC", s or "")).lower()


def _score(item, series, game_name):
    """商品名がどれだけ弾に合っているか。合わなければ None"""
    name = item.get("itemName") or ""
    if any(w in name for w in NG_WORDS):
        return None
    if not item.get("mediumImageUrls"):
        return None
    n, s = _norm(name), _norm(series)
    if s not in n:
        return None
    sc = 0
    if _norm(game_name)[:4] in n or "ポケモンカード" in name or "ワンピースカード" in name or "フュージョンワールド" in name:
        sc += 2
    if "box" in n or "ボックス" in name:
        sc += 2
    if "シュリンク" in name or "新品" in name or "未開封" in name:
        sc += 1
    if "予約" in name:
        sc += 1
    return sc


def _first_image(item):
    imgs = item.get("mediumImageUrls") or []
    u = imgs[0] if imgs else ""
    if isinstance(u, dict):  # formatVersion=1 の形
        u = u.get("imageUrl", "")
    # 標準の128px → 300px に（楽天の画像サーバーの機能）
    return re.sub(r"\?_ex=\d+x\d+", "", u) + "?_ex=300x300" if u else ""


def item_link(url, aff):
    """商品ページURLを、自分の楽天アフィリエイトIDのリンクで包む（楽天アフィリエイトの公式の形式）。
    APIが返す affiliateUrl の中身（pc=商品ページ）を取り出して使う"""
    from urllib.parse import urlparse, parse_qs, quote
    if not url:
        return ""
    if "hb.afl.rakuten.co.jp" in url:
        url = (parse_qs(urlparse(url).query).get("pc") or [url])[0]
    return f"https://hb.afl.rakuten.co.jp/hgc/{aff}/?pc={quote(url, safe='')}&m={quote(url, safe='')}" if aff else url


def search(keyword, settings, session=None):
    app, key = os.environ.get("RAKUTEN_APP_ID", "").strip(), os.environ.get("RAKUTEN_ACCESS_KEY", "").strip()
    site = (os.environ.get("SITE_URL") or settings.get("site_public_url") or "").rstrip("/")
    params = {"applicationId": app, "keyword": keyword, "format": "json", "formatVersion": 2,
              "hits": 20, "imageFlag": 1, "availability": 1, "sort": "standard"}
    aff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or settings.get("rakuten_affiliate_id") or "").strip()
    if aff:
        params["affiliateId"] = aff
    headers = {"accessKey": key, "Referer": site + "/", "Origin": site, "User-Agent": "toreca-chusen-navi/1.0"}
    r = (session or requests).get(ENDPOINT, params=params, headers=headers, timeout=20)
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200:
        # エラーの形が2種類ある（error/error_description と errors[].errorCode）
        err = data.get("error_description") or data.get("error") or data.get("errors") or r.text[:200]
        raise RuntimeError(f"楽天API {r.status_code}: {err}")
    return data.get("Items") or []


def update(settings, series_by_game, session=None, sleep=1.1):
    """series_by_game: {game: [弾名, ...]}（件数が多い順）。state/rakuten.json を更新して返す"""
    cache = load_json("rakuten.json", {})
    if not (os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY")):
        return cache
    days = settings.get("rakuten_refresh_days", 3)
    budget = settings.get("rakuten_max_calls_per_run", 8)
    for game, series in series_by_game.items():
        gname = settings["game_names"][game]
        for x in series:
            if budget <= 0:
                break
            k = f"{game}|{x}"
            c = cache.get(k)
            if c and parse_dt(c.get("fetched_at")) and (now() - parse_dt(c["fetched_at"])).days < days:
                continue
            budget -= 1
            alias = (settings.get("rakuten_aliases") or {}).get(x) or x  # 楽天での商品名が違う弾は別名で探す
            try:
                items = search(f"{gname} {alias}", settings, session)
            except Exception as e:
                log(f"楽天: {x} 取得失敗 {e}")
                if "401" in str(e) or "403" in str(e):
                    return cache  # 鍵の設定ミス。無駄に叩かない
                continue
            best = None
            for it in items:
                sc = _score(it, alias, gname)
                if sc is not None and (best is None or sc > best[0]):
                    best = (sc, it)
            if best:
                it = best[1]
                aff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or settings.get("rakuten_affiliate_id") or "").strip()
                cache[k] = {"image": _first_image(it), "url": item_link(it.get("itemUrl") or it.get("affiliateUrl"), aff),
                            "name": it.get("itemName"), "price": it.get("itemPrice"), "shop": it.get("shopName"),
                            "fetched_at": now().isoformat()}
                log(f"楽天: {x} → {it.get('itemName', '')[:40]}")
            else:
                cache[k] = {"image": "", "url": "", "fetched_at": now().isoformat()}  # 見つからない弾も記録（毎回探さない）
                log(f"楽天: {x} 該当なし")
            time.sleep(sleep)
    save_json("rakuten.json", cache)
    return cache
