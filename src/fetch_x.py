"""Xから抽選告知ポストを拾う（API従量課金：返ってきたポスト1件ごとに課金）
費用を抑える工夫:
  - since_id で前回以降の新着だけ取る（同じポストに二度課金しない）
  - クエリで「当選報告」「外れ」等の雑談を除外し、リンク付きの告知だけに絞る
  - 1日の読み取り件数に上限（settings.x_read_budget_per_day）
"""
import os

from common import load_json, save_json, now, log


def _client():
    import tweepy
    return tweepy.Client(bearer_token=os.environ["X_BEARER_TOKEN"])


def budget_left(settings) -> int:
    u = load_json("x_usage.json", {})
    used = u.get(now().date().isoformat(), 0)
    today = now().date().isoformat()
    limit = (settings.get("x_read_budget_by_date") or {}).get(today) or settings.get("x_read_budget_per_day", 300)
    return max(0, limit - used)


def _spend(n):
    u = load_json("x_usage.json", {})
    d = now().date().isoformat()
    u = {d: u.get(d, 0) + n}  # 今日の分だけ残す
    save_json("x_usage.json", u)


def build_query(src) -> str:
    """sources.yaml の x 設定からXの検索クエリを作る"""
    parts = []
    if src.get("accounts"):
        parts.append("(" + " OR ".join(f"from:{a.lstrip('@')}" for a in src["accounts"]) + ")")
    if src.get("keywords"):
        parts.append(src["keywords"])
    parts.append("-is:retweet -is:reply lang:ja")
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
        return [], since_id
    if not os.environ.get("X_BEARER_TOKEN") and client is None:
        log("X_BEARER_TOKEN 未設定のためXの収集はスキップ")
        return [], since_id
    client = client or _client()
    res = client.search_recent_tweets(
        query=build_query(src), since_id=since_id,
        max_results=max(10, min(src.get("max_results", 20), left, 100)),
        expansions=["author_id"], tweet_fields=["created_at", "entities"],
        user_fields=["username", "name"])
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
