"""Xから抽選告知ポストを拾う（API従量課金：返ってきたポスト1件ごとに課金）
費用を抑える工夫:
  - since_id で前回以降の新着だけ取る（同じポストに二度課金しない）
  - クエリで「当選報告」「外れ」等の雑談を除外し、リンク付きの告知だけに絞る
  - 1日の読み取り件数に上限（settings.x_read_budget_per_day）
"""
import os
import time

from common import load_json, save_json, now, log


def _client():
    import tweepy
    return tweepy.Client(bearer_token=os.environ["X_BEARER_TOKEN"])


PEAK_TYPES = ("拡張パック", "ブースター", "ハイクラス")  # 抽選がどっと増える主力商品（構築デッキなどは対象外）


def peak_set(settings, day=None):
    """新弾（拡張パック・ブースターパック）の発売日の数日前〜発売日なら、その弾の名前を返す（Xの上限を上げる日）"""
    from datetime import date, timedelta
    day = day or now().date()
    before = settings.get("x_peak_days_before", 7)
    sets = []
    for g, v in (load_json("newsets.json", {}).get("series") or {}).items():
        sets += list(v.items())
    for g, v in (settings.get("series_info") or {}).items():
        sets += list((v or {}).items())
    for name, info in sets:
        if not isinstance(info, dict) or not any(t in str(info.get("type") or "") for t in PEAK_TYPES):
            continue
        try:
            rel = date.fromisoformat(str(info.get("release") or "")[:10])
        except ValueError:
            continue
        if rel - timedelta(days=before) <= day <= rel:
            return name
    return None


def daily_limit(settings) -> int:
    today = now().date().isoformat()
    by_date = (settings.get("x_read_budget_by_date") or {}).get(today)
    if by_date:
        return by_date
    base = settings.get("x_read_budget_per_day", 300)
    peak = settings.get("x_read_budget_peak")
    if peak and peak > base and peak_set(settings):
        return peak  # 新弾の発売前は抽選が多いので、上限を上げてしっかり拾う
    return base


def budget_left(settings) -> int:
    u = load_json("x_usage.json", {})
    used = u.get(now().date().isoformat(), 0)
    return max(0, daily_limit(settings) - used)


def _spend(n):
    u = load_json("x_usage.json", {})
    d = now().date().isoformat()
    u = {d: u.get(d, 0) + n}  # 今日の分だけ残す
    save_json("x_usage.json", u)


def _notify_limit(settings):
    """上限に届いたら、その日1回だけGitHubのIssueで知らせる（増やすかどうかはユーザーと相談）"""
    meta = load_json("x_meta.json", {})
    today = now().date().isoformat()
    if meta.get("budget_notified") == today:
        return
    meta["budget_notified"] = today
    save_json("x_meta.json", meta)
    limit = daily_limit(settings)
    log(f"Xの読み取りが今日の上限（{limit}件）に達しました")
    try:
        from approve import _gh
        _gh("POST", "/issues", json={
            "title": f"【相談】Xの読み取りが今日の上限（{limit}件）に達しました（{now():%m/%d %H:%M}）",
            "body": (f"今日（{today}）のXの読み取りが上限の{limit}件に届いたので、今日はこれ以降Xからの抽選の収集を止めています。\n\n"
                     "増やす場合は、Claudeに「今日は○件まで増やして」と伝えてください（1件 約0.005ドル。100件増やすと約0.5ドル）。\n"
                     "そのままでよければ、このIssueは閉じてください（明日の0時に上限は元に戻ります）。")})
    except Exception as e:
        log(f"上限のお知らせ失敗: {e}")


def _own_account():
    """自分のXアカウント（settings の x_account。トレカ抽選ナビは pokepi_tcg）"""
    try:
        from common import load_settings
        a = (load_settings().get("x_account") or "").strip().lstrip("@")
    except Exception:
        a = ""
    return a or ("pokepi_tcg" if __import__("common").SITE == "tcg" else "")


def build_query(src) -> str:
    """sources.yaml の x 設定からXの検索クエリを作る"""
    parts = []
    if src.get("accounts"):
        parts.append("(" + " OR ".join(f"from:{a.lstrip('@')}" for a in src["accounts"]) + ")")
    if src.get("keywords"):
        parts.append(src["keywords"])
    parts.append("-is:retweet -is:reply lang:ja")
    own = _own_account()
    if own:
        parts.append(f"-from:{own}")  # 自分のアカウント（トレカ抽選ナビ）のポストは拾わない
    if not src.get("accounts"):
        # 一般ユーザーの雑談を除外して告知だけに寄せる
        parts.append(("has:links " if src.get("require_links", True) else "")
                     + "-当選 -当たった -外れ -落選 -転売 -買取 -譲 -求")
    return " ".join(parts)


def search(src, settings, since_id=None, client=None):
    """戻り値: (テキストのリスト[(text, post_url)], 最新ID)"""
    if "accounts" in src and not src["accounts"]:
        return [], since_id  # アカウント未設定
    left = budget_left(settings)
    if left < 10:
        log(f"X読み取り上限に達したためスキップ: {src['id']}")
        _notify_limit(settings)
        return [], since_id
    if not os.environ.get("X_BEARER_TOKEN") and client is None:
        log("X_BEARER_TOKEN 未設定のためXの収集はスキップ")
        return [], since_id
    client = client or _client()
    # Xの検索は直近7日しか見られない。前回のIDが7日より古いと 400 になるので使わない
    if since_id:
        try:
            ms = (int(since_id) >> 22) + 1288834974657
            if time.time() * 1000 - ms > 6.8 * 86400e3:
                log(f"X {src['id']}: 前回のIDが7日より古いので最初から取り直し")
                since_id = None
        except ValueError:
            since_id = None
    kw = dict(query=build_query(src),
              max_results=max(10, min(src.get("max_results", 20), left, 100)),
              expansions=["author_id"], tweet_fields=["created_at", "entities"],
              user_fields=["username", "name"])
    try:
        res = client.search_recent_tweets(since_id=since_id, **kw)
    except Exception as e:
        if since_id and "since_id" in str(e):
            log(f"X {src['id']}: since_id が使えないので外して取り直し")
            since_id = None
            res = client.search_recent_tweets(**kw)
        else:
            raise
    tweets = res.data or []
    _spend(len(tweets))
    users = {u.id: u for u in (res.includes or {}).get("users", [])}
    out, newest = [], since_id
    for t in tweets:
        u = users.get(t.author_id)
        uname = u.username if u else "i"
        url = f"https://x.com/{uname}/status/{t.id}"
        links = [e.get("expanded_url") for e in (t.entities or {}).get("urls", []) if e.get("expanded_url")]
        text = (f"投稿者: {u.name if u else ''} (@{uname})\n日時: {t.created_at}\n"
                f"{t.text}\nリンク: {' '.join(links) or 'なし'}\nポストURL: {url}")
        out.append((text, url))
        if newest is None or int(t.id) > int(newest):
            newest = str(t.id)
    log(f"X {src['id']}: {len(tweets)}件取得（本日残り {budget_left(settings)}件）")
    return out, newest
