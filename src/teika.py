"""定価で買える通販の見張り（楽天市場）

・BOXの定価が分かっている弾（発売1年以内・発売前）を、楽天で安い順に検索する
・在庫あり・BOX・定価の110%以下の商品だけを「定価くらいで買える」として残す（送料は含まない）
・1回の実行で teika_calls_per_run 件まで。同じ弾は teika_refresh_minutes 分ごとに見直す
・結果は state/teika.json（弾ごとの今の候補と、初めて見つけた時刻）。サイトの /teika/ と弾のページ、Xの予約作業が読む
"""
import re
import time
from datetime import timedelta

from common import load_json, save_json, now, parse_dt, log, normalize

GAME_WORD = {"pokemon": "ポケモンカード", "onepiece": "ワンピースカード"}
NG = ("オリパ", "オリジナルパック", "中古", "開封済", "シングル", "バラ", "ばら", "1パック", "パック販売", "カートン", "スリーブ", "ローダー",
      "ケース", "ファイル", "プレイマット", "福袋", "くじ", "まとめ売り", "空箱", "英語版", "海外版", "中国語", "韓国語", "Chinese", "Korean",
      "シュリンクなし", "シュリンク無", "訳あり", "箱つぶれ", "箱潰れ", "傷あり", "ジャンク", "抽選", "応募券", "サプライ", "デッキケース",
      "グミ", "食玩", "キャンディ", "ウエハース", "チップス", "ガム", "菓子", "ラムネ", "チョコ", "ふりかけ", "カレー", "ソーセージ")


def targets(settings):
    """[(game, 弾名, 定価)]：souba.yaml の定価 ＋ 弾の基本情報の「1BOX（〇パック）〇円」"""
    from sitegen import _ser_cfg
    import souba
    out = {}
    for it in souba.items():
        if it.get("teika") and it["game"] in GAME_WORD:
            out[(it["game"], it["series"])] = int(it["teika"])
    d0 = (now() - timedelta(days=365)).date().isoformat()
    for g, m in (_ser_cfg()["info"] or {}).items():
        if g not in GAME_WORD:
            continue
        for x, inf in (m or {}).items():
            if str(inf.get("release") or "") < d0:
                continue
            p = re.search(r"1BOX[^0-9]*\d*[^0-9]*?([\d,]{4,})円", inf.get("price") or "")
            if p and (g, x) not in out:
                out[(g, x)] = int(p.group(1).replace(",", ""))
    rel = {(g, x): str(inf.get("release") or "") for g, m in (_ser_cfg()["info"] or {}).items() for x, inf in (m or {}).items()}
    keep = [(g, x, t) for (g, x), t in out.items() if rel.get((g, x), "9999") >= d0 or (g, x) not in rel]
    return keep


def _words(settings, series):
    """楽天での呼び名（rakuten_aliases）があればそれを使う。商品名に全部の言葉が入っていること"""
    al = (settings.get("rakuten_aliases") or {}).get(series) or series
    return [normalize(w).replace(" ", "") for w in re.split(r"[\s・]+", al) if w]


def _ok(item, series, teika, words):
    name = item.get("itemName") or ""
    if any(w in name for w in NG):
        return False
    n = normalize(name).replace(" ", "")
    if not all(w in n for w in words):
        return False
    v2 = "vol2" in n.replace(".", "")
    if v2 != ("vol2" in normalize(series).replace(".", "").replace(" ", "")):
        return False  # vol.2 と vol.1 を取り違えない
    if not re.search(r"デッキ|セット", series) and not re.search(r"box|ボックス", name, re.I):
        return False  # パックの弾はBOXだけ（デッキ・セットはBOXと書かれないことがある）
    price = int(item.get("itemPrice") or 0)
    return teika * 0.6 <= price <= teika * settings_ratio()


_RATIO = {"v": 1.10}


def settings_ratio():
    return _RATIO["v"]


def update(settings, session=None, sleep=1.1, search=None):
    import os
    if not (os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY")) and search is None:
        return {}
    from rakuten import search as rsearch, item_link
    search = search or rsearch
    _RATIO["v"] = float(settings.get("teika_ratio", 1.10))
    aff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or settings.get("rakuten_affiliate_id") or "").strip()
    data = load_json("teika.json", {})
    items = data.setdefault("items", {})
    refresh = settings.get("teika_refresh_minutes", 120) * 60
    budget = settings.get("teika_calls_per_run", 4)
    t = now()
    tg = sorted(targets(settings), key=lambda x: (items.get(f"{x[0]}|{x[1]}") or {}).get("checked") or "")
    for g, x, teika in tg:
        key = f"{g}|{x}"
        rec = items.setdefault(key, {"game": g, "series": x})
        last = parse_dt(rec.get("checked"))
        if last and (t - last).total_seconds() < refresh:
            continue
        if budget <= 0:
            break
        budget -= 1
        try:
            al = (settings.get("rakuten_aliases") or {}).get(x) or x
            res = search(f"{GAME_WORD[g]} {al}" + ("" if re.search(r"デッキ|セット|BOX", x) else " BOX"), dict(settings, _sort="+itemPrice"), session)
        except Exception as e:
            log(f"定価の見張り: {x} 取得失敗 {e}")
            if "401" in str(e) or "403" in str(e):
                break
            continue
        rec.update(checked=t.isoformat(), teika=teika)
        old = {h["url_raw"]: h for h in rec.get("hits") or []}
        hits = []
        for it in res:
            if not _ok(it, x, teika, _words(settings, x)):
                continue
            u = it.get("itemUrl") or ""
            hits.append({"name": (it.get("itemName") or "")[:80], "price": int(it["itemPrice"]), "shop": it.get("shopName") or "",
                         "url": item_link(u, aff), "url_raw": u,
                         "postage": bool(it.get("postageFlag") == 0),  # 0＝送料込み
                         "first_seen": (old.get(u) or {}).get("first_seen") or t.isoformat()})
        hits.sort(key=lambda h: h["price"])
        rec["hits"] = hits[:5]
        if hits:
            log(f"定価の見張り: {x}（定価{teika:,}円）→ {len(hits)}件 最安 {hits[0]['price']:,}円 {hits[0]['shop']}")
        time.sleep(sleep)
    data["updated"] = t.isoformat()
    # 対象から外れた弾は消す
    keys = {f"{g}|{x}" for g, x, _ in tg}
    data["items"] = {k: v for k, v in items.items() if k in keys}
    save_json("teika.json", data)
    return data


def current(max_age_hours=6):
    """サイトに出す今の候補（見直してから max_age_hours 以内のものだけ）"""
    data = load_json("teika.json", {})
    t = now()
    out = []
    for k, rec in (data.get("items") or {}).items():
        c = parse_dt(rec.get("checked"))
        hits = [h for h in rec.get("hits") or [] if not any(w in (h.get("name") or "") for w in NG)]
        if not c or (t - c).total_seconds() > max_age_hours * 3600 or not hits:
            continue
        out.append(dict(rec, hits=hits))
    return out
