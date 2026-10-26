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
              "hits": 30 if settings.get("_sort") else 20, "imageFlag": 1, "availability": 1,
              "sort": settings.get("_sort") or "standard", "page": settings.get("_page") or 1}
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


# ---- サプライの最安値（ジャンルごと・1日1回） ----
# ジャンル: (検索語のリスト（{g}=ゲーム名）, 商品名の頭にあるべき語)
SUPPLY = {  # ジャンル: (検索語, 商品名に入っているべき語)。検索語はジャンル名だけ（ゲーム名は付けない）
    "スリーブ": ("スリーブ", ("スリーブ",)),
    "ローダー": ("ローダー", ("ローダー",)),
    "デッキケース": ("デッキケース", ("デッキケース",)),
    "ストレージ": ("ストレージ", ("ストレージ",)),
}
# カード用ではないとはっきり分かる物だけ除く（スマホ・PC・服・腕カバーなど）と、中古・オリパなど
SUPPLY_NG = ("中古", "ジャンク", "訳あり", "オリパ", "福袋",
             "スマホ", "スマートフォン", "iPhone", "アイフォン", "Android", "Galaxy", "Xperia", "AQUOS", "Pixel",
             "PC", "パソコン", "ノート", "MacBook", "Mac", "タブレット", "iPad", "Surface", "Kindle", "インチ",
             "アームカバー", "アームスリーブ", "腕", "袖", "シャツ", "ニット", "ブラウス", "ワンピース 半袖", "レディース", "メンズ",
             "コンプレッション", "サポーター", "インナー", "肘", "膝", "日焼け", "UV手袋", "冷感",
             "ワイン", "ボトル", "カップ", "スリーブ缶", "レコード", "LP", "ストレージ容量", "SSD", "HDD", "USB", "microSD", "GB", "TB",
             "ソファ", "クッション", "収納ボックス 衣類", "フィルムスリーブ", "ネガ")
CARD_NO = re.compile(r"\b[A-Z]{1,3}\d{2}-\d{3}\b|\b(SR|SEC|SAR|UR|AR|RR)\b")


def _head(name, n=28):
    """商品名の頭の部分（【】などの宣伝文句を除く）"""
    s = re.sub(r"[【\[［〔(（＼][^】\]］〕)）／]{0,40}[】\]］〕)）／]", " ", name or "")
    return re.sub(r"\s+", " ", s).strip()[:n]


def supply_ok(name, must):
    if not any(w in (name or "") for w in must):
        return False
    if any(w in (name or "") for w in SUPPLY_NG) or CARD_NO.search(name or ""):
        return False
    return True


def search_link(q, aff):
    """楽天の検索結果（安い順）への自分のアフィリエイトリンク"""
    from urllib.parse import quote
    return item_link(f"https://search.rakuten.co.jp/search/mall/{quote(q)}/?s=2", aff)


def supply_prices(settings, games, session=None, sleep=1.1):
    """state/rakuten_prices.json を更新して返す。{"スリーブ": {"price", "url", "name", "fetched_at"}}（全ゲーム共通）
    楽天で「ジャンル名」だけを検索し、商品名にジャンル名が入っている物の最安値（送料別）"""
    cache = load_json("rakuten_prices.json", {})
    if not (os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY")):
        return cache
    aff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or settings.get("rakuten_affiliate_id") or "").strip()
    budget = settings.get("rakuten_price_calls_per_run", 20)
    for genre, (word, must) in SUPPLY.items():
        c = cache.get(genre)
        if c and parse_dt(c.get("fetched_at")) and (now() - parse_dt(c["fetched_at"])).total_seconds() < 20 * 3600:
            continue  # 1日1回
        if budget < 3:
            break
        cands, failed = [], False
        for page in (1, 2, 3):
            budget -= 1
            try:
                items = search(word, dict(settings, _sort="+itemPrice", _page=page), session)
            except Exception as e:
                log(f"楽天価格: {genre} 取得失敗 {e}")
                if "401" in str(e) or "403" in str(e):
                    return cache
                failed = True
                break
            cands += [(int(it["itemPrice"]), it.get("itemName"), it.get("itemUrl"))
                      for it in items if supply_ok(it.get("itemName"), must) and int(it.get("itemPrice") or 0) > 0]
            time.sleep(sleep)
            if cands or len(items) < 30:
                break  # 安い順なので、見つかったらそれ以上は見なくてよい
        if failed and not cands:
            continue
        cands.sort()
        best = cands[0] if cands else None
        cache[genre] = {"price": best[0] if best else None, "name": best[1] if best else None,
                        "url": search_link(word, aff), "item_url": item_link(best[2], aff) if best and best[2] else None,
                        "fetched_at": now().isoformat(), "top": [f"¥{p} {n[:50]}" for p, n, _ in cands[:5]]}
        log(f"楽天価格: {genre} → " + (f"¥{best[0]} {best[1][:40]}" if best else "なし"))
    save_json("rakuten_prices.json", cache)
    return cache
