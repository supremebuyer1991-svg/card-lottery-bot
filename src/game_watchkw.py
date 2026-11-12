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


def update(settings, fetch=None, sleep=time.sleep):
    """1日1回、言葉ごとに楽天ブックスのおもちゃを探し直す。戻り値：state"""
    st = load_json(STATE, {})
    kws = settings.get("watch_keywords") or []
    t = now()
    if not kws or (st.get("at") and parse_dt(st["at"]) and (t - parse_dt(st["at"])).total_seconds() < 20 * 3600):
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
    if calls:
        st = {"at": t.isoformat(), "items": items}
        save_json(STATE, st)
        log(f"見張りの言葉：楽天ブックスを{calls}回見て {len(items)}件")
    return st


def watch_items(settings, have_codes=()):
    """watch.json に足す分（すでに見張っている楽天の商品は除く）"""
    import game_premium
    import gamecats
    cats = gamecats.by_id(False)
    ex = set(settings.get("x_exclude_games") or [])
    out = []
    for code, v in (load_json(STATE, {}).get("items") or {}).items():
        if code in have_codes:
            continue
        g = v.get("game") or ""
        out.append({"k": "kw" + code, "n": v["n"][:40], "g": False, "rk": code, "asin": "",
                    "nopost": g in ex,
                    "hot": game_premium.premium_match(v["n"], settings) is not None,
                    "neg": game_premium.below_teika(v["n"], settings),
                    "tag": ((cats.get(g) or {}).get("hashtags") or "").split()[:1]})
    return out
