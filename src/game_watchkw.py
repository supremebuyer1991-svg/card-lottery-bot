"""ゲーム・ホビー入荷速報：言葉で楽天ブックスのおもちゃ売り場を探して、見張り（worker/game-watch）に足す（11/13）

11/13 ユーザー「入荷Now、ベイブレードの速報結構来てたけどうちはないな」。
見張っていたベイブレードは買取価格の分かる13商品だけで、新しい弾・再販の商品が入っていなかった。
・1日1回、settings の watch_keywords（例：ベイブレードX）で楽天ブックス（shopCode=book）のおもちゃ（genreId 566382）を探す
・商品名にそのジャンルの言葉（categories.yaml の hints）が入り、本・カード・中古などでないものだけ
・state/game/watch_kw.json に残し、watch.json に足す（速報の決まりは見張りの側と同じ：定価の8割未満の買取の商品は出さない など）
"""
import re
import time

from common import load_json, save_json, now, parse_dt, log, job_elapsed

STATE = "watch_kw.json"
NG = re.compile(r"中古|訳あり|ジャンク|コミック|漫画|攻略|ガイド|ブック|BOOK|DVD|Blu-?ray|CD|雑誌|ムック|てれびくん|コロコロ|"
                r"カードダス|トレカ|カレンダー|ポスター|Tシャツ|シール", re.I)


BOOKS_TOTAL = ["https://openapi.rakuten.co.jp/services/api/BooksTotal/Search/20170404",
               "https://openapi.rakuten.co.jp/booksms/api/BooksTotal/Search/20170404",
               "https://app.rakuten.co.jp/services/api/BooksTotal/Search/20170404"]
_ok = {}


def books_search(q, page, settings):
    """楽天ブックス総合検索（JANが返る）。新しいAPIの場所が分からないので、候補を順に試す"""
    import os
    import requests
    site = (os.environ.get("RAKUTEN_REFERER") or os.environ.get("SITE_URL") or settings.get("site_public_url") or "").rstrip("/")
    p = {"applicationId": os.environ.get("RAKUTEN_APP_ID", "").strip(), "accessKey": os.environ.get("RAKUTEN_ACCESS_KEY", "").strip(),
         "format": "json", "formatVersion": 2, "hits": 30, "page": page, "keyword": q, "sort": "-releaseDate", "outOfStockFlag": 1}
    if settings.get("rakuten_affiliate_id"):
        pass
    h = {"accessKey": p["accessKey"], "Referer": site + "/", "Origin": site, "User-Agent": "game-nyuka/1.0"}
    err = None
    for url in ([_ok["url"]] if _ok.get("url") else BOOKS_TOTAL):
        try:
            r = requests.get(url, params=p, headers=h, timeout=15)
        except Exception as e:
            err = e
            continue
        if r.status_code == 429:
            time.sleep(2)
            r = requests.get(url, params=p, headers=h, timeout=15)
        if r.status_code == 200:
            _ok["url"] = url
            return [i.get("Item", i) for i in (r.json().get("Items") or [])]
        err = f"{r.status_code} {r.text[:120]}"
    raise RuntimeError(f"楽天ブックス総合検索 {err}")


def update(settings, fetch=None, sleep=time.sleep, books=None):
    """1日1回、言葉ごとに楽天ブックスのおもちゃを探し直す。戻り値：state"""
    st = load_json(STATE, {})
    kws = settings.get("watch_keywords") or []
    t = now()
    if not kws or ("jans" in st and st.get("at") and parse_dt(st["at"]) and (t - parse_dt(st["at"])).total_seconds() < 20 * 3600):
        return st
    if fetch is None:
        import os
        if not (os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY")):
            return st
        import game_affi
        fetch = lambda p: game_affi.http_fetch(p, settings)  # noqa: E731
    import gamecats
    hints = gamecats.hints()
    items = {}
    jans = {}
    calls = 0
    for e in kws:
        q, game = e.get("q") or "", e.get("game") or ""
        hint = hints.get(game)
        for page in range(1, int(e.get("pages", 2)) + 1):
            if job_elapsed() > float(settings.get("kaitori_until_sec", 230)) + 30:
                break
            if calls:
                sleep(1.1)   # 楽天は1秒に1回まで
            calls += 1
            try:
                rows = fetch({"keyword": q, "shopCode": "book", "genreId": e.get("genre", 566382), "hits": 30, "page": page,
                              "availability": 0, "imageFlag": 1, "sort": "-updateTimestamp"})
            except Exception as ex:
                log(f"見張りの言葉「{q}」：失敗 {ex}")
                break
            for it in rows or []:
                it = it.get("Item", it)
                name = (it.get("itemName") or "").strip()
                code = it.get("itemCode") or ""
                if not code or NG.search(name) or (hint and not hint.search(name)):
                    continue
                items[code] = {"n": name[:60], "game": game, "url": (it.get("itemUrl") or "").split("?")[0]}
            if len(rows or []) < 30:
                break
        # JANも取る（11/13 ユーザー「Amazonも」）：楽天ブックスの本・ゲームの検索はJANを返すので、
        # JANで見張りに入れると、見張りの側で楽天・Amazonの両方をJANで探す（AmazonはJANが一致するものだけ使う）
        for page in range(1, int(e.get("pages", 2)) + 1):
            if job_elapsed() > float(settings.get("kaitori_until_sec", 230)) + 30:
                break
            sleep(1.1)
            calls += 1
            try:
                rows = books_search(q, page, settings) if books is None else books(q, page)
            except Exception as ex:
                log(f"見張りの言葉「{q}」（JAN）：失敗 {ex}")
                break
            for it in rows or []:
                it = it.get("Item", it)
                name = (it.get("title") or it.get("itemName") or "").strip()
                jan = str(it.get("jan") or it.get("isbn") or "")
                if not (jan.isdigit() and len(jan) == 13) or NG.search(name) or (hint and not hint.search(name)):
                    continue
                jans[jan] = {"n": name[:60], "game": game, "url": (it.get("itemUrl") or "").split("?")[0]}
            if len(rows or []) < 30:
                break
    if calls:
        st = {"at": t.isoformat(), "items": items, "jans": jans}
        save_json(STATE, st)
        log(f"見張りの言葉：楽天ブックスを{calls}回見て {len(items)}件（JANが分かったもの {len(jans)}件）")
    return st


def watch_items(settings, have_codes=(), have_jans=()):
    """watch.json に足す分（すでに見張っている楽天の商品・JANは除く）。
    JANが分かる商品は JAN で（見張りの側で楽天・Amazonの両方を探す）、分からない商品は楽天の商品番号で"""
    import game_premium
    import gamecats
    cats = gamecats.by_id(False)
    ex = set(settings.get("x_exclude_games") or [])
    out = []
    st = load_json(STATE, {})
    by_jan = st.get("jans") or {}
    names_with_jan = {(v.get("n") or "")[:30] for v in by_jan.values()}
    for jan, v in by_jan.items():
        if jan in have_jans:
            continue
        g = v.get("game") or ""
        out.append({"k": "j" + jan, "jan": jan, "n": v["n"][:40], "g": False, "rk": "", "asin": "",
                    "nopost": g in ex,
                    "hot": game_premium.premium_match(v["n"], settings) is not None,
                    "neg": game_premium.below_teika(v["n"], settings),
                    "tag": ((cats.get(g) or {}).get("hashtags") or "").split()[:1]})
    for code, v in (st.get("items") or {}).items():
        if code in have_codes or (v.get("n") or "")[:30] in names_with_jan:   # JANで見張る商品は、楽天の商品番号では見張らない（二重にしない）
            continue
        g = v.get("game") or ""
        out.append({"k": "kw" + code, "n": v["n"][:40], "g": False, "rk": code, "asin": "",
                    "nopost": g in ex,
                    "hot": game_premium.premium_match(v["n"], settings) is not None,
                    "neg": game_premium.below_teika(v["n"], settings),
                    "tag": ((cats.get(g) or {}).get("hashtags") or "").split()[:1]})
    return out
