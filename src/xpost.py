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
    return (os.environ.get("SITE_URL") or settings.get("site_public_url") or "").rstrip("/")


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


def compose(it, settings, remind=False):
    is_store = it.get("channel") == "store"
    head = "⏰締切まもなく" if remind else ("🏪店頭抽選" if is_store else "🎯抽選受付中")
    area = f"［{it['area']}］" if is_store and it.get("area") else ""
    lines = [f"【{head}】{area}{it['store']}", it["product"], f"締切：{fmt_dt(it.get('end'))}"]
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
        res = client.create_tweet(text=text, quote_tweet_id=quote)
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
    """1日1回、WPまとめページへのリンク付きでゲーム別の受付中件数を投稿（リンク付きは高いので1日1回に集約）"""
    hour = settings.get("summary_hour", 20)
    if not (public_site(settings) or settings.get("site_url")) or now().hour < hour:
        return
    meta = load_json("x_meta.json", {})
    today = now().date().isoformat()
    if meta.get("summary_date") == today:
        return
    lots = load_json("lotteries.json", {})
    dry = settings["dry_run"] or (client is None and not os.environ.get("X_API_KEY"))
    if not dry and client is None:
        client = _client()
    for game, name in settings["game_names"].items():
        active = [i for i in lots.values() if i["game"] == game and i["status"] == "posted"]
        if not active:
            continue
        soon = sum(1 for i in active if parse_dt(i.get("end")) and
                   (parse_dt(i["end"]) - now()).total_seconds() < 86400)
        text = (f"【{name}】今日時点で受付中の抽選は{len(active)}件"
                + (f"（うち締切24時間以内 {soon}件）" if soon else "") +
                f"\n応募漏れがないか一覧でチェック👇\n{page_url(active[0], settings)}\n{settings['hashtags'][game]}")
        if dry:
            log("DRY_RUN まとめ投稿:\n" + text)
        else:
            try:
                client.create_tweet(text=text)
            except Exception as e:
                log(f"まとめ投稿失敗: {e}")
    if not dry:
        meta["summary_date"] = today
        save_json("x_meta.json", meta)
