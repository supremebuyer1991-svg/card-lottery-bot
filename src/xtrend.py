"""Xで話題のポケカ・ワンピカードの話題を拾って、反応狙いの投稿文（リンクなし）をAIに下書きさせる

・trend_hours の各時刻以降に1回ずつ（1日2回まで）、Xで反応の多いポストを読む
  （ポケカ・ワンピで各 trend_reads 件。抽選の収集の分を先に残すため、読み取り残りが少ない日はやらない）
・AIが「いま何が話題か」をまとめ、解説・相場・注意喚起・神引き・共感などの投稿文を作る
・できた文は state/x_trends.json に保存し、下書きページ（/x-draft.html）の一番上に出す
  （話題への言及は事実の間違いが怖いので、自動投稿はせず、目で確認してから手動で出す）
"""
import json
import os
import re
from datetime import timedelta

import requests

from common import load_json, save_json, now, log
from extract import API_URL
from fetch_x import budget_left, _spend

MODEL = os.environ.get("TREND_MODEL", "claude-sonnet-5-5")

QUERIES = {
    "pokemon": "(ポケカ OR ポケモンカード) -is:retweet -is:reply lang:ja -抽選 -当選 -応募",
    "onepiece": "(ワンピカード OR ワンピースカード OR \"ONE PIECEカード\") -is:retweet -is:reply lang:ja -抽選 -当選 -応募",
}

PROMPT = """あなたはトレカ情報アカウント「ぽけぴ」(@pokepi_tcg)の中の人です。
下は、この24時間にXで反応が多かったポケカ・ワンピカード関連のポストです（いいね・リポスト数つき）。

これを読んで「いま何が話題か」をつかみ、ぽけぴが投稿する文を {n} 本作ってください。

投稿の型（話題に合うものを選ぶ。同じ型ばかりにしない）:
- 解説：話題の背景をわかりやすく説明（例：なぜこの弾が高いのか、販売方法の違い）
- 相場：値段の話題（高騰・暴落・定価割れ）。数字はポストに書かれている範囲だけ使い「〜くらい」と幅を持たせる
- 注意喚起：フリマの詐欺・すり替え・偽物・転売の手口など。被害を防ぐ具体的な一言を入れる
- 神引き・悲報：みんなが共感・反応しやすい話題に乗っかる
- 共感・質問：「みんなはどう？」とリプをもらいやすい形

守ること:
- リンクは入れない。特定の人のアカウント名（@〜）や、個人を特定できる情報は書かない
- ポストに書かれていないことを事実のように書かない。噂は「〜という話も」と書く
- 国籍・民族でひとくくりにして悪く言わない（「海外転売」「転売目的の大量購入」など行為として書く）
- 店舗・企業・個人を名指しで批判しない。公式発表は「公式発表によると」と書く
- 1本あたり日本語で120字以内。改行で読みやすく、絵文字は1〜2個、最後にハッシュタグを1〜2個
- 最後はできるだけ問いかけで終わり、リプやいいねをもらいやすくする

出力は次のJSONだけ:
{{"topics": [{{"type": "解説|相場|注意喚起|神引き・悲報|共感・質問", "topic": "話題を15字以内", "text": "投稿文", "basis": "元になったポストの内容を40字以内で（確認用）", "src": [元にしたポストの番号]}}]}}

--- 話題のポスト ---
{posts}
"""


def _search(client, query, n):
    res = client.search_recent_tweets(
        query=query, max_results=max(10, min(n, 100)), sort_order="relevancy",
        start_time=now() - timedelta(hours=23, minutes=50),
        expansions=["author_id"], tweet_fields=["created_at", "public_metrics"], user_fields=["username"])
    tweets = res.data or []
    _spend(len(tweets))
    users = {u.id: u.username for u in (res.includes or {}).get("users", [])}
    out = []
    for t in tweets:
        m = t.public_metrics or {}
        score = m.get("like_count", 0) + 3 * m.get("retweet_count", 0) + 2 * m.get("quote_count", 0) + m.get("reply_count", 0)
        out.append({"text": t.text, "likes": m.get("like_count", 0), "rts": m.get("retweet_count", 0),
                    "score": score, "url": f"https://x.com/{users.get(t.author_id, 'i')}/status/{t.id}"})
    return out


def _ask(posts, n):
    body = "\n\n".join(f"[{k}] ♥{p['likes']} RT{p['rts']}\n{p['text'][:400]}" for k, p in enumerate(posts))
    r = requests.post(API_URL, timeout=120, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json",
    }, json={"model": MODEL, "max_tokens": 2500,
             "messages": [{"role": "user", "content": PROMPT.format(n=n, posts=body)}]})
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API エラー {r.status_code}: {r.text[:200]}")
    raw = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\{.*\}", raw, re.S)
    return (json.loads(m.group(0)) if m else {}).get("topics", [])


def update_trends(settings, client=None, ask=None):
    hours = sorted(settings.get("trend_hours") or [])
    if not hours:
        return
    data = load_json("x_trends.json", {})
    today = now().date().isoformat()
    done = data.get("slots", {}).get(today, [])
    due = [h for h in hours if now().hour >= h and h not in done]
    if not due:
        return
    reads = settings.get("trend_reads", 30)
    if budget_left(settings) < 2 * reads + 100:  # 抽選の収集の分を先に残す
        log("話題ネタ: Xの読み取り残りが少ないのでスキップ")
        return
    if client is None:
        if not os.environ.get("X_BEARER_TOKEN") or not os.environ.get("ANTHROPIC_API_KEY"):
            return
        import tweepy
        client = tweepy.Client(bearer_token=os.environ["X_BEARER_TOKEN"])
    posts = []
    for q in QUERIES.values():
        try:
            posts += _search(client, q, reads)
        except Exception as e:
            log(f"話題ネタ: X検索失敗 {e}")
    posts = sorted(posts, key=lambda p: -p["score"])[:25]
    if len(posts) < 5:
        return
    try:
        topics = (ask or _ask)(posts, settings.get("trend_drafts", 4))
    except Exception as e:
        log(f"話題ネタ: AI失敗 {e}")
        return
    items = []
    for t in topics:
        text = (t.get("text") or "").strip()
        if not text or "http" in text:
            continue
        srcs = [posts[k]["url"] for k in (t.get("src") or []) if isinstance(k, int) and 0 <= k < len(posts)]
        items.append({"type": t.get("type", ""), "topic": t.get("topic", ""), "text": text,
                      "basis": t.get("basis", ""), "src": srcs[:3]})
    if not items:
        return
    data["generated"] = now().isoformat()
    data["items"] = items
    data["slots"] = {today: sorted(set(done) | set(h for h in hours if h <= due[-1]))}
    save_json("x_trends.json", data)
    log(f"話題ネタ: {len(items)}本の下書きを作成（{len(posts)}件のポストから）")
