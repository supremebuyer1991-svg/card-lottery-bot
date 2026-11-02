"""X投稿：新着抽選の告知と、締切前リマインド"""
import os
import re
import unicodedata

from common import load_json, save_json, parse_dt, now, log

WEEK = "月火水木金土日"


def fmt_dt(s):
    dt = parse_dt(s)
    if not dt:
        return "公式で確認"
    return f"{dt.month}/{dt.day}({WEEK[dt.weekday()]}){dt:%H:%M}"


def x_len(text: str) -> int:
    """Xの文字数カウント（全角=2, URL=23）の近似"""
    n = 0
    for w in re.split(r"(\s+)", text):
        if w.startswith("http"):
            n += 23
            continue
        for ch in w:
            n += 2 if unicodedata.east_asian_width(ch) in "FWA" else 1
    return n


def public_site(settings):
    return (settings.get("site_public_url") or os.environ.get("SITE_URL") or "").rstrip("/")


def page_url(it, settings):
    own = public_site(settings)  # 自作サイト（トレカ抽選ナビ）を優先
    if own:
        from sitegen import series_path, GAME_SLUG
        if it.get("series"):
            return f"{own}/{series_path(it['game'], it['series'])}"
        return f"{own}/{GAME_SLUG[it['game']]}/"
    site = settings.get("site_url")
    if site and it.get("series"):  # 弾ごとの記事へ
        from wp import series_slug
        return f"{site.rstrip('/')}/{series_slug(it['game'], it['series'])}/"
    if site:
        return f"{site.rstrip('/')}/{settings['wp_pages'][it['game']]}/"
    return it.get("url") or it.get("source_url")


def quote_id(it, settings):
    """店舗の告知ポストを引用する（リンク無しなので安い＆一次情報が見える）"""
    if it.get("no_quote"):
        return None
    m = re.search(r"/status/(\d+)", it.get("x_post") or "")
    return m.group(1) if (m and settings.get("quote_source", True)) else None


def short_product(it):
    """投稿用の商品名。短い弾名があればそれを使い、無ければカッコ内の細かい説明を省く"""
    if it.get("series"):
        return it["series"]
    p = it.get("product") or ""
    p = re.sub(r"[（(][^）)]{8,}[）)]", "", p).strip()
    return p[:40] + ("…" if len(p) > 40 else "")


def compose(it, settings, remind=False):
    is_store = it.get("channel") == "store"
    head = "⏰締切まもなく" if remind else ("🏪店頭抽選" if is_store else "🎯抽選受付中")
    area = f"［{it['area']}］" if is_store and it.get("area") else ""
    lines = [f"【{head}】{area}{it['store']}", short_product(it), f"締切：{fmt_dt(it.get('end'))}"]
    req = []
    if it.get("id_check") is not None:
        req.append("本人確認" + ("あり" if it["id_check"] else "なし"))
    if it.get("member"):
        req.append({"card": "会員カード必要", "account": "会員登録必要", "none": "会員不要"}.get(it["member"], ""))
    if req:
        lines.append("／".join(r for r in req if r))
    if it.get("conditions"):
        lines.append(f"条件：{it['conditions']}")
    link = page_url(it, settings)
    if settings.get("post_link") and link:
        lines.append(f"▶詳細 {link}")
    elif quote_id(it, settings):
        lines.append("▼店舗の告知はこちら")
    lines.append(settings["hashtags"][it["game"]])
    text = "\n".join(lines)
    # 長ければ 条件 → 商品名 → 店舗名 の順に削る
    while x_len(text) > 280:
        cond = next((i for i, l in enumerate(lines) if l.startswith("条件：")), None)
        if cond is not None:
            lines.pop(cond)
        elif len(lines[1]) > 20:
            lines[1] = lines[1][:-11] + "…"
        elif len(lines[0]) > 20:
            lines[0] = lines[0][:-11] + "…"
        else:
            break
        text = "\n".join(lines)
    return text


def _client():
    import tweepy  # GitHub Actions側でインストール
    return tweepy.Client(
        consumer_key=os.environ["X_API_KEY"], consumer_secret=os.environ["X_API_SECRET"],
        access_token=os.environ["X_ACCESS_TOKEN"], access_token_secret=os.environ["X_ACCESS_SECRET"])


def upload_image(png):
    """画像をXにアップロードして media_id を返す（失敗したら None＝画像なしで投稿）"""
    try:
        import requests
        from requests_oauthlib import OAuth1
        auth = OAuth1(os.environ["X_API_KEY"], os.environ["X_API_SECRET"],
                      os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_SECRET"])
        r = requests.post("https://api.x.com/2/media/upload", auth=auth, timeout=60,
                          files={"media": ("post.png", png, "image/png")},
                          data={"media_category": "tweet_image", "media_type": "image/png"})
        if r.status_code < 300:
            j = r.json()
            mid = (j.get("data") or {}).get("id") or j.get("media_id_string")
            if mid:
                return str(mid)
        log(f"画像アップロード失敗(v2) {r.status_code}: {r.text[:200]}")
        import tweepy, io  # 旧方式でもう一度
        api = tweepy.API(tweepy.OAuth1UserHandler(os.environ["X_API_KEY"], os.environ["X_API_SECRET"],
                                                  os.environ["X_ACCESS_TOKEN"], os.environ["X_ACCESS_SECRET"]))
        return str(api.media_upload(filename="post.png", file=io.BytesIO(png)).media_id)
    except Exception as e:
        log(f"画像アップロード失敗: {e}")
        return None


def post_all(settings, client=None):
    lots = load_json("lotteries.json", {})
    budget = settings.get("max_posts_per_run", 3)
    dry = settings["dry_run"] or (client is None and not os.environ.get("X_API_KEY"))
    if not dry and client is None:
        client = _client()

    def send(text, quote=None):
        if dry:
            log("DRY_RUN 投稿:\n" + text + (f"\n（引用: {quote}）" if quote else ""))
            return "dry"
        try:
            res = client.create_tweet(text=text, quote_tweet_id=quote)
        except Exception as e:
            # 自動化ラベル付きアカウントは他人のポストを引用できない（403）→ 引用なしで出し直す
            if quote and "403" in str(e):
                log("引用が拒否されたため引用なしで投稿します")
                res = client.create_tweet(text=text)
            else:
                raise
        return str(res.data["id"])

    # 1) 締切が近い順に新着告知
    queue = sorted([i for i in lots.values() if i["status"] == "approved"],
                   key=lambda i: i.get("end") or "9999")
    # 2) リマインド
    limit = now().timestamp() + settings.get("remind_hours_before", 24) * 3600
    remind = [i for i in lots.values() if i["status"] == "posted" and not i.get("reminded_at")
              and now().timestamp() - parse_dt(i["posted_at"]).timestamp() >= 6 * 3600  # 告知直後は重ねない
              and parse_dt(i.get("end")) and now().timestamp() < parse_dt(i["end"]).timestamp() <= limit]

    for it, is_remind in [(i, False) for i in queue] + [(i, True) for i in remind]:
        if budget <= 0:
            break
        try:
            tid = send(compose(it, settings, remind=is_remind), quote_id(it, settings))
        except Exception as e:
            log(f"投稿失敗: {e}")
            break  # API制限などは次回に回す
        budget -= 1
        if tid == "dry":
            continue  # テストモードでは状態を変えない（本番切替後に投稿される）
        if is_remind:
            it["reminded_at"] = now().isoformat()
        else:
            it.update(status="posted", posted_at=now().isoformat(), tweet_id=tid)
    save_json("lotteries.json", lots)


def post_daily_summary(settings, client=None):
    """8時間ごと（summary_hours の各時刻以降に1回ずつ）、サイトへのリンク付きで受付中件数のまとめを投稿。
    リンク付き投稿は1件約$0.20と高いので、個別告知にはリンクを付けず、ここに集約する（1日3件）。"""
    if not (public_site(settings) or settings.get("site_url")):
        return
    hours = sorted(settings.get("summary_hours") or [])
    if not hours:  # 空＝自動まとめはオフ（手動投稿で運用。/x-draft.html の下書きを使う）
        return
    meta = load_json("x_meta.json", {})
    today = now().date().isoformat()
    done = meta.get("summary_slots", {}).get(today, [])
    due = [h for h in hours if now().hour >= h and h not in done]
    if not due:
        return
    slot = due[-1]  # 同じ日に取りこぼした枠があっても、出すのは1回だけ

    lots = load_json("lotteries.json", {})
    active = [i for i in lots.values() if i["status"] in ("approved", "posted", "listed")
              and not (parse_dt(i.get("end")) and parse_dt(i["end"]) < now())]
    if not active:
        return
    short = {"pokemon": "ポケカ", "onepiece": "ワンピースカード", "dragonball": "DBフュージョンワールド"}
    parts, tags = [], []
    for game in settings["game_names"]:
        n = sum(1 for i in active if i["game"] == game)
        if n:
            parts.append(f"{short.get(game, game)} {n}件")
            tags.append(settings["hashtags"][game].split()[0])
    soon = sum(1 for i in active if parse_dt(i.get("end")) and
               (parse_dt(i["end"]) - now()).total_seconds() < 86400)
    t = now()
    text = (f"【トレカ抽選まとめ｜{t.month}/{t.day} {t.hour}時時点】\n"
            f"受付中：{'／'.join(parts)}"
            + (f"\n⏰締切24時間以内：{soon}件" if soon else "")
            + f"\n条件・締切・店舗を一覧でチェック👇\n{public_site(settings) or settings['site_url']}/\n"
            + " ".join(tags))

    dry = settings["dry_run"] or (client is None and not os.environ.get("X_API_KEY"))
    if dry:
        log("DRY_RUN まとめ投稿:\n" + text)
        return
    if client is None:
        client = _client()
    try:
        client.create_tweet(text=text)
    except Exception as e:
        log(f"まとめ投稿失敗: {e}")
        return
    log(f"まとめ投稿OK（{slot}時の枠）")
    meta["summary_slots"] = {today: sorted(set(done) | set(h for h in hours if h <= slot))}
    save_json("x_meta.json", meta)


# ---- 大手の抽選の速報（見つけたらすぐ・リンク付き）----
# 大手＝サイトで⭐の付いたチェーン＋通販の大手。そのうち受け取りが通販（発送）のものだけ。小さいお店や店頭抽選は、まとめて「新着の抽選」で出す（Claudeの予約投稿）
BIG_ONLINE = [("pbandai", "プレミアムバンダイ", r"プレミアムバンダイ|プレバン"),
              ("rakutenbooks", "楽天ブックス", r"楽天ブックス"),
              ("sevennet", "セブンネット", r"セブンネット|セブン-?イレブン|7net"),
              ("amazon", "Amazon", r"Amazon|アマゾン"),
              ("amiami", "あみあみ", r"あみあみ|amiami"),
              ("aeon", "イオン", r"イオン|AEON"),
              ("tsutaya", "TSUTAYA", r"TSUTAYA|ツタヤ|蔦屋")]
GAME_HEAD = {"pokemon": "ポケカ", "onepiece": "ワンピースカード"}
TAGS = {"pokemon": "#ポケモンカード #ポケカ #ポケカ抽選", "onepiece": "#ワンピースカード #ワンピースカード抽選"}
FOLLOW = "🔔フォロー＆通知ONで、抽選の開始・締切のお知らせを受け取れます"


def big_chain(store):
    """大手なら (キー, 表示名)。違えば None"""
    from sitegen import CHAINS
    for slug, name, pat, big in CHAINS:
        if big and re.search(pat, store or "", re.I):
            return slug, name
    for slug, name, pat in BIG_ONLINE:
        if re.search(pat, store or "", re.I):
            return slug, name
    return None


def compose_big(name, game, series, items, settings, started=False):
    """大手の速報の文。1店なら店名と締切、複数店ならお店の数と一番早い締切。
    started=True は「予告の段階で見つけていた抽選が、受付開始になった」お知らせ"""
    from detail import lottery_path
    from sitegen import series_path
    own = public_site(settings)
    items = sorted(items, key=lambda i: i.get("end") or "9999")
    first = items[0]
    if len(items) == 1:
        where = first["store"] + (f"（{first['area']}）" if first.get("channel") == "store" and first.get("area")
                                  else "（通販・発送）" if first.get("channel") != "store" else "")
        link = f"{own}/{lottery_path(first)}" if own else first.get("url")
    else:
        areas = list(dict.fromkeys(i.get("area") for i in items if i.get("area")))
        where = f"{name} {len(items)}店舗" + (f"（{'・'.join(areas[:3])}{' ほか' if len(areas) > 3 else ''}）" if areas else "")
        link = f"{own}/{series_path(game, series)}" if own and series else f"{own}/"
    kind = "店頭抽選" if first.get("channel") == "store" else "抽選"
    head = f"🔔受付開始｜{GAME_HEAD[game]}" if started else f"🚨抽選速報｜{GAME_HEAD[game]}"
    what = f"{name}で「{series or short_product(first)}」の{kind}" + ("が始まりました" if started else "")
    lines = [head, "", what, "",
             f"📍{where}", (f"⏰{fmt_dt(first.get('end'))} 締切" + ("（早い店）" if len(items) > 1 else "") if first.get("end") else "⏰締切はお店の告知で確認"), "",
             "応募条件・方法はこちら👇", link, "", FOLLOW, "", TAGS[game]]
    return "\n".join(lines)


def post_big(settings, client=None):
    """大手の新しい抽選を、チェーン×弾ごとに1回だけ速報する。
    サイトの個別ページが公開されてから出す（見つけて20分〜3時間のもの）。同じチェーン×弾は3日間は出し直さない"""
    if not settings.get("big_post"):
        return
    from datetime import timedelta
    meta = load_json("x_meta.json", {})
    done = meta.setdefault("big_posted", {})
    t = now()
    for k in [k for k, v in done.items() if t - parse_dt(v) > timedelta(days=3)]:
        done.pop(k)
    today = t.date().isoformat()
    count = meta.setdefault("big_count", {}).get(today, 0)
    cap = settings.get("big_posts_per_day", 6)
    lots = load_json("lotteries.json", {})
    groups = {}
    for i in lots.values():
        if i.get("status") not in ("approved", "listed", "posted") or i.get("game") not in GAME_HEAD:
            continue
        f, e, st = parse_dt(i.get("found_at")), parse_dt(i.get("end")), parse_dt(i.get("start"))
        if not f or (e and e < t + timedelta(hours=1)):
            continue
        if timedelta(minutes=20) <= t - f <= timedelta(hours=3):
            kind = "new"  # 見つけたばかり
        elif (st and st - f >= timedelta(minutes=30) and timedelta(0) <= t - st <= timedelta(hours=9)
              and st >= (parse_dt(settings.get("big_start_since")) or st)):
            kind = "start"  # 予告の段階で見つけていた抽選が受付開始（夜中に始まったものも朝の回で出せるよう9時間まで）
        else:
            continue
        if i.get("channel") == "store":
            continue  # ユーザーの指示：お店ごとの店頭抽選（TSUTAYA〇〇店など）は出さない。通販（発送）だけ
        bc = big_chain(i.get("store"))
        if not bc:
            continue
        groups.setdefault((bc[0], bc[1], i["game"], i.get("series") or short_product(i), kind), []).append(i)
    dry = settings["dry_run"] or (client is None and not os.environ.get("X_API_KEY"))
    for (slug, name, game, series, kind), items in sorted(groups.items(), key=lambda kv: min(i.get("end") or "9" for i in kv[1])):
        key = f"{slug}|{game}|{series}" + ("|start" if kind == "start" else "")
        if key in done:
            continue
        if count >= cap:
            log(f"大手の速報: 今日の上限（{cap}件）に届いたので {key} は出さない")
            break
        text = compose_big(name, game, series, items, settings, started=(kind == "start"))
        if dry:
            log("DRY_RUN 大手の速報:\n" + text)
            continue
        try:
            client = client or _client()
            client.create_tweet(text=text)
        except Exception as e:
            log(f"大手の速報: 投稿失敗 {e}")
            break
        done[key] = t.isoformat()
        count += 1
        log(f"大手の速報: {key}")
    meta["big_count"] = {today: count}
    save_json("x_meta.json", meta)
