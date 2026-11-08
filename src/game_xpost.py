"""ゲーム・ホビー入荷速報：Xの速報（@a9994aaa）
新しい抽選・予約・再入荷を見つけたら、リンクなし＋商品写真で知らせる。毎日の決まった投稿（締切まとめ等）は
Xの予約投稿で入れるので、ここでは速報だけ。

決まりごと（11/8 Fable の調査より）：
・1日 x_speed_per_day 本まで、前の投稿から x_speed_gap_min 分以上あける（1回の実行で1本だけ。複数あれば1本にまとめる）
・リンクは、その商品のアフィリエイトのページがあるとき（1件だけの速報）だけ付ける（URL付きは1件約$0.20、なしは約$0.015）。
  付けるときは「（PR）」と書く（ステマ規制）。Amazonがあれば Amazon（定価で買えるページ）、なければ楽天。ハッシュタグは2つまで
・自動リプ・引用はしない。冒頭の言い回しは毎回変える（同じ文面のくり返しはスパム扱いされやすい）
・最初に動いたときは、それまでに載っていた分を「投稿済み」として記録するだけ（昔の分をまとめて流さない）
鍵：X_API_KEY / X_API_SECRET（トレカと同じアプリ）＋ X_GAME_ACCESS_TOKEN / X_GAME_ACCESS_SECRET（@a9994aaa）
"""
import os
import re
import unicodedata

from common import load_json, save_json, now, parse_dt, log

STATE = "xpost.json"   # state/game/xpost.json
SPEED_KINDS = ("lottery", "invite", "preorder", "restock", "first_come", "fukubukuro")
WEEK = "月火水木金土日"
OPEN1 = ["🔔速報だよ！", "🔔新着を見つけたよ！", "🔔リンリンからお知らせ！", "🔔チェックしてね！", "🔔いま入った情報だよ！"]
OPENN = ["🔔新着{n}件まとめだよ！", "🔔{n}件まとめてお知らせ！", "🔔リンリンが{n}件見つけたよ！", "🔔新しい情報が{n}件！"]
CLOSE = ["くわしくはプロフのリンクから📝", "一覧はプロフのサイトにまとめてるよ📝", "条件はプロフのリンクから確認してね📝"]


def _md(s):
    dt = parse_dt(s)
    return f"{dt.month}/{dt.day}({WEEK[dt.weekday()]}){dt:%H:%M}" if dt else ""


def _short(name, n=40):
    s = unicodedata.normalize("NFKC", name or "").strip()
    s = re.sub(r"[（(][^）)]{12,}[）)]", "", s)   # 長いカッコ書きは削る
    return s if len(s) <= n else s[:n - 1] + "…"


def _kind(it):
    import gamecats
    return gamecats.KINDS.get(it.get("kind"), "抽選")


def _tags(items):
    import gamecats
    cats = gamecats.by_id(False)
    out = []
    for it in items:
        for t in ((cats.get(it.get("game")) or {}).get("hashtags") or "").split()[:1]:
            if t not in out:
                out.append(t)
    return " ".join(out[:2])


def x_len(text):
    return sum(2 if unicodedata.east_asian_width(c) in "FWA" else 1 for c in text)


def compose(items, k=0, link=""):
    """items（1件以上）から投稿の文面。k は言い回しを変える番号。link はアフィリエイトのページ（1件のときだけ使う）"""
    tags = _tags(items)
    if len(items) == 1:
        it = items[0]
        head = OPEN1[k % len(OPEN1)]
        lines = [head, "", f"【{it.get('store') or '公式'}】{_short(it.get('product'), 60)}", f"▶{_kind(it)}"]
        st, en = parse_dt(it.get("start")), parse_dt(it.get("end"))
        if st and st > now():
            lines.append(f"▶受付開始 {_md(it['start'])}")
        if en and it.get("kind") not in ("restock", "first_come"):
            lines.append(f"▶締切 {_md(it['end'])}")
        if it.get("price"):
            lines.append(f"▶定価 {str(it['price']).replace('（税込）', '')}")
    else:
        head = OPENN[k % len(OPENN)].format(n=len(items))
        lines = [head, ""]
        for it in items[:4]:
            en = _md(it.get("end")) if it.get("kind") not in ("restock", "first_come") else ""
            lines.append(f"▶{_short(it.get('product'), 28)}（{it.get('store') or '公式'}・{_kind(it)}{'・〜' + en if en else ''}）")
        if len(items) > 4:
            lines.append(f"ほか{len(items) - 4}件")
    if link and len(items) == 1:
        lines += ["", f"{'Amazon' if 'amazon.' in link else '楽天'}の商品ページ（PR）👉 {link}"]
    else:
        lines += ["", CLOSE[k % len(CLOSE)]]
    if tags:
        lines.append(tags)
    text = "\n".join(lines)
    while x_len(re.sub(r"https?://\S+", "x" * 23, text)) > 280 and len(lines) > 4:   # 長すぎたら途中の行を削る
        lines.pop(-4 if tags else -3)
        text = "\n".join(lines)
    return text


def _norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[\s・:：/／\-ー（）()【】「」]|プレバン|プレミアムバンダイ|最新フォーマットのガンプラ|機動新世紀ガンダムx", "", s)


def candidates(lots, seen, t):
    out, names = [], set()
    for key, it in sorted(lots.items(), key=lambda kv: kv[1].get("end") or "9999"):
        if key in seen or it.get("status") not in ("approved", "listed", "posted"):
            continue
        if it.get("kind") not in SPEED_KINDS:
            continue
        en, st = parse_dt(it.get("end")), parse_dt(it.get("start"))
        if not (en or st):                 # 締切も開始日も分からない（ニュースのまとめ等）は速報しない
            continue
        if en and en <= t:
            continue
        fa = parse_dt(it.get("found_at"))
        if fa and (t - fa).total_seconds() > 36 * 3600:   # 見つけてから時間がたったものは速報にしない
            continue
        n = _norm(it.get("product"))
        if n in names:
            continue
        names.add(n)
        out.append((key, it))
    return out


def _auth():
    from requests_oauthlib import OAuth1
    return OAuth1(os.environ["X_API_KEY"], os.environ["X_API_SECRET"],
                  os.environ["X_GAME_ACCESS_TOKEN"], os.environ["X_GAME_ACCESS_SECRET"])


def _image_id(url):
    """商品写真（楽天の画像）をXに上げて media_id。失敗したら None（写真なしで投稿）"""
    if not url:
        return None
    try:
        import requests
        r = requests.get(url, timeout=20)
        if r.status_code != 200 or len(r.content) < 1000:
            return None
        ct = r.headers.get("content-type", "image/jpeg").split(";")[0]
        u = requests.post("https://api.x.com/2/media/upload", auth=_auth(), timeout=60,
                          files={"media": ("item", r.content, ct)}, data={"media_category": "tweet_image", "media_type": ct})
        if u.status_code < 300:
            j = u.json()
            return str((j.get("data") or {}).get("id") or j.get("media_id_string") or "") or None
        log(f"X速報：写真のアップロード失敗 {u.status_code}: {u.text[:150]}")
    except Exception as e:
        log(f"X速報：写真のアップロード失敗 {e}")
    return None


def _send(text, media_id=None):
    import requests
    body = {"text": text}
    if media_id:
        body["media"] = {"media_ids": [media_id]}
    r = requests.post("https://api.x.com/2/tweets", json=body, auth=_auth(), timeout=30)
    if r.status_code >= 300:
        raise RuntimeError(f"{r.status_code}: {r.text[:200]}")
    return str(r.json()["data"]["id"])


def post_speed(settings, send=None, image=None):
    """send(text, media_id)→投稿ID、image(item)→media_id（テストでは偽物を渡す）"""
    if not settings.get("x_speed_post"):
        return
    lots = load_json("lotteries.json", {})
    st = load_json(STATE, {})
    t = now()
    if "seen" not in st:   # 初回：今ある分は投稿済み扱いにして終わり
        st = {"seen": sorted(lots), "posts": []}
        save_json(STATE, st)
        log(f"X速報：初回なので、今ある{len(lots)}件は投稿済みとして記録しました（次の新着から速報します）")
        return
    seen = set(st["seen"])
    cands = candidates(lots, seen, t)
    if not cands:
        return
    posts = [p for p in st.get("posts", []) if parse_dt(p["at"]) and (t - parse_dt(p["at"])).total_seconds() < 3 * 86400]
    today = [p for p in posts if parse_dt(p["at"]).date() == t.date()]
    if len(today) >= int(settings.get("x_speed_per_day", 5)):
        log(f"X速報：今日の上限（{len(today)}本）に達したので、{len(cands)}件は次の日のまとめ投稿に回します")
        return
    if posts and (t - parse_dt(posts[-1]["at"])).total_seconds() < int(settings.get("x_speed_gap_min", 20)) * 60:
        log("X速報：前の投稿から間がないので次の回に回します")
        return
    if t.hour < 7:
        return
    items = [it for _, it in cands]
    link = ""
    if len(items) == 1 and settings.get("x_speed_link", True):
        try:
            import game_affi
            lk = game_affi.links_for(items[0], load_json(game_affi.CACHE, {}), settings)
            link = lk.get("az") or (lk.get("rk") or {}).get("u") or ""
        except Exception as e:
            log(f"X速報：リンクの用意に失敗 {e}")
    text = compose(items, k=len(posts), link=link)
    dry = settings.get("dry_run") or (send is None and not os.environ.get("X_GAME_ACCESS_TOKEN"))
    if dry:
        log("X速報（テスト・投稿しない）:\n" + text)
        return
    if send is None:
        send = _send
    if image is None:
        import game_affi
        cache, models = load_json(game_affi.CACHE, {}), game_affi._models()

        def image(it):
            return _image_id(((game_affi.links_for(it, cache, settings, models).get("rk") or {}).get("img") or "").replace("?_ex=300x300", "?_ex=600x600"))
    mid = None
    for it in items[:3]:   # 写真がある最初の商品
        mid = image(it)
        if mid:
            break
    try:
        tid = send(text, mid)
    except Exception as e:
        log(f"X速報：投稿失敗 {e}")
        return
    st["seen"] = sorted(seen | {k for k, _ in cands})
    st["posts"] = posts + [{"at": t.isoformat(), "id": tid, "keys": [k for k, _ in cands]}]
    save_json(STATE, st)
    log(f"X速報：{len(items)}件を投稿しました（今日{len(today) + 1}本目）")
