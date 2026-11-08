"""締切が分からない抽選の締切を、告知元から読み取って埋める

・応募先がXのポストなら、ポストの本文と画像をAIに読ませる（画像に期間が書いてある告知が多い）
・ポストにLivePocketなどの応募ページのリンクがあれば、そのページの本文も読む（LivePocketには受付期間がある）
・応募先がLivePocket・Googleフォームなどのページなら、そのページの本文を読む
・一度調べた抽選は deadline_checked_at を付け、1日は調べ直さない（費用をかけない）
・X の読み取りは1日の上限（x_read_budget_per_day）に数える
"""
import json
import os
import re

import requests

from common import load_json, save_json, now, parse_dt, log, SITE
from extract import API_URL, MODEL

DOMAIN_WORD = "トレカ" if SITE != "game" else "ゲーム機・ホビー"  # 指示文の冒頭（どの分野の告知か）

# 画像の文字（告知ポスター）を読むので、ふだんより強いモデルを使う（1つの告知につき1回だけ）
VISION_MODEL = os.environ.get("DEADLINE_MODEL", "claude-sonnet-5-5")
from fetch import get, html_to_text

ACTIVE = ("new", "pending", "approved", "posted", "listed")
PAGE_HOSTS = ("livepocket.jp", "docs.google.com", "forms.gle", "customform.jp", "e-starbox.com", "membercard.jp")

PROMPT = """{domain}の抽選販売の告知です。この抽選の「応募の受付締切」の日時を読み取ってください。
画像（告知画像）にだけ書かれていることが多いので、画像の文字を隅々まで読んでください。
「受付期間」「応募期間」「抽選期間」「申込期間」「〇/〇(〇)〜〇/〇(〇)」「〇日〇時まで」などの書き方があります。期間が「A〜B」なら B が締切です。

ルール:
- 受付締切（応募期間・申込期間・受付期間の終わり）だけ。当選発表日・購入期間・発売日・引き換え期間は締切ではない\n- ただし締切が書かれておらず「当選発表〇/〇」「結果発表〇/〇」だけが書かれている時は、発表日の 00:00 を end にし、evidence に「発表日から推定」と書く（発表の時点で受付は終わっているため）\n- 「〆」「締め」「〜〇/〇」「〇/〇まで」「〇日〇時迄」なども締切の書き方
- 年が書かれていなければ、投稿日（{posted}）を基準に補う。時刻が無ければ 23:59
- 書かれていなければ null（推測しない）
- 今日は {today}

出力は次のJSONだけ: {{"end": "2026-11-02T23:59:00+09:00 または null", "start": "受付開始 or null", "evidence": "根拠の文言を20字以内"}}

店舗: {store}
商品: {product}
--- 告知の本文 ---
{text}
"""


def _image_block(u):
    """画像はダウンロードしてAIに直接渡す（URLだとXの画像が読めないことがある）"""
    import base64
    try:
        r = requests.get(u + ("&" if "?" in u else "?") + "name=large" if "pbs.twimg.com" in u and "name=" not in u else u,
                         timeout=20, headers={"User-Agent": "Mozilla/5.0"})
        ct = r.headers.get("content-type", "").split(";")[0]
        if r.status_code == 200 and ct in ("image/jpeg", "image/png", "image/gif", "image/webp") and len(r.content) < 4_500_000:
            return {"type": "image", "_ok": True,
                    "source": {"type": "base64", "media_type": ct, "data": base64.b64encode(r.content).decode()}}
    except Exception as e:
        log(f"締切の調査: 画像の取得失敗 {u[:60]} {e}")
    return {"type": "image", "source": {"type": "url", "url": u}}


def _ask(text, images, it, posted):
    key = os.environ.get("ANTHROPIC_API_KEY")
    content = [_image_block(u) for u in images[:4]]
    got = sum(1 for c in content if c.pop("_ok", False))
    content.append({"type": "text", "text": PROMPT.format(domain=DOMAIN_WORD,
        posted=posted or now().date().isoformat(), today=now().date().isoformat(),
        store=it.get("store"), product=it.get("product"), text=text[:6000])})
    r = requests.post(API_URL, timeout=90, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
    }, json={"model": VISION_MODEL, "max_tokens": 500, "messages": [{"role": "user", "content": content}]})
    if r.status_code == 404 or (r.status_code == 400 and "model" in r.text):
        r = requests.post(API_URL, timeout=90, headers={  # モデル名が使えない時はふだんのモデルで
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json",
        }, json={"model": MODEL, "max_tokens": 500, "messages": [{"role": "user", "content": content}]})
    if r.status_code >= 400 and images:
        res = _ask(text, [], it, posted)  # 画像が読めない時は本文だけで
        res["_img"] = f"画像を送れず({r.status_code})"
        return res
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API エラー {r.status_code}: {r.text[:200]}")
    raw = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        res = json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        res = {}
    res["_img"] = f"画像{got}/{len(images[:4])}枚読込"
    return res


def _tweet_id(url):
    m = re.search(r"(?:x|twitter)\.com/[^/]+/status/(\d+)", url or "")
    return m.group(1) if m else None


def _x_lookup(ids, settings, client=None):
    """ポストの本文・画像・リンクをまとめて取得。{id: (本文, 画像URL[], リンク[], 投稿日)}"""
    from fetch_x import budget_left, _spend
    if not ids:
        return {}
    if client is None:
        if not os.environ.get("X_BEARER_TOKEN"):
            return {}
        import tweepy
        client = tweepy.Client(bearer_token=os.environ["X_BEARER_TOKEN"])
    ids = ids[:max(0, min(100, budget_left(settings) - 20))]  # ふだんの収集の分を残す
    if not ids:
        log("締切の調査: Xの読み取り上限のためスキップ")
        return {}
    res = client.get_tweets(ids=ids, expansions=["attachments.media_keys"],
                            tweet_fields=["created_at", "entities", "attachments"],
                            media_fields=["url", "type", "preview_image_url"])
    tweets = res.data or []
    _spend(len(tweets))
    media = {m.media_key: (m.url or m.preview_image_url) for m in (res.includes or {}).get("media", [])}
    out = {}
    for t in tweets:
        keys = ((t.attachments or {}).get("media_keys") or [])
        imgs = [media[k] for k in keys if media.get(k)]
        links = [e.get("expanded_url") for e in (t.entities or {}).get("urls", []) if e.get("expanded_url")]
        out[str(t.id)] = (t.text or "", imgs, links, t.created_at.date().isoformat() if t.created_at else None)
    return out


LAST_ERR = {}


def _page_text(url, fetcher):
    try:
        t = html_to_text(fetcher(url), url)[:5000]
        if not t.strip():
            LAST_ERR[url] = "応募ページの中身が空"
        return t
    except Exception as e:
        LAST_ERR[url] = f"応募ページを読めず（{str(e)[:40]}）"
        log(f"締切の調査: ページ取得失敗 {url[:60]} {e}")
        return ""


def fill_deadlines(settings, ask=None, fetcher=get, x_client=None, limit=None):
    """締切の無い受付中の抽選を調べて end を埋める。戻り値: 埋めた件数"""
    if ask is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return 0
        ask = _ask
    limit = limit or settings.get("deadline_checks_per_run", 80)
    lots = load_json("lotteries.json", {})
    todo = []
    for it in lots.values():
        if it.get("status") not in ACTIVE or it.get("end"):
            continue
        t = parse_dt(it.get("deadline_checked_at"))
        if t and (now() - t).total_seconds() < 24 * 3600 and it.get("deadline_v") == 5:
            continue
        url = it.get("url") or ""
        # 応募先のページ（お店のブログ・通販の告知ページなども）は全部読む。Amazon（締切のない招待）・LINEの友だち追加などは除く
        if _tweet_id(url) or (url.startswith("http") and not re.search(r"amazon|amzn|lin\.ee|line\.me|myca\.dmm", url + " " + (it.get("store") or ""), re.I)):
            todo.append(it)
    todo = todo[:limit]
    if not todo:
        return 0

    # 応募ページを先に読む。読めなかった（ボット対策で断られた等）抽選は、お店の告知ポスト（x_post）から読む
    pages = {}
    for it in todo:
        if not _tweet_id(it["url"]):
            pages[it["url"]] = _page_text(it["url"], fetcher)
            if not pages[it["url"]] and _tweet_id(it.get("x_post")):
                it["_via_post"] = it["x_post"]
    tweets = {}
    try:
        tweets = _x_lookup(list({_tweet_id(i.get("_via_post") or i["url"]) for i in todo if _tweet_id(i.get("_via_post") or i["url"])}), settings, x_client)
    except Exception as e:
        log(f"締切の調査: X取得失敗 {e}")

    filled = 0
    for it in todo:
        tid = _tweet_id(it.pop("_via_post", None) or it["url"])
        text, imgs, posted, src = "", [], None, ""
        if tid:
            if tid not in tweets:
                continue  # 取れなかった（削除・上限）→ 次回また
            text, imgs, links, posted = tweets[tid]
            src = "Xの告知"
            for u in links:  # ポストに応募ページのリンクがあれば、その本文も読む
                if any(h in u for h in PAGE_HOSTS):
                    page = _page_text(u, fetcher)
                    if page:
                        text += "\n\n--- 応募ページ（" + u + "）---\n" + page
                        src = "Xの告知と応募ページ"
                    if "livepocket.jp" in u and not it.get("apply_url"):
                        it["apply_url"] = u
                    break
        else:
            text, src = pages.get(it["url"]) or "", "応募ページ"
        it["deadline_checked_at"] = now().isoformat()
        it["deadline_v"] = 5
        if not text and not imgs:
            it["deadline_note"] = LAST_ERR.get(it.get("url") or "", "読める内容なし")
            continue
        try:
            r = ask(text, imgs, it, posted)
        except Exception as e:
            log(f"締切の調査: AI失敗 {e}")
            continue
        it["deadline_note"] = (r.get("_img") or ("画像なし" if not imgs else "")) + "・" + ((r.get("evidence") or "締切の記載なし")[:30])
        end = parse_dt(r.get("end"))
        found = parse_dt(it.get("found_at"))
        if end and (not found or end > found.replace(year=found.year - 1)):
            it["end"] = end.isoformat()
            if r.get("start") and not it.get("start"):
                it["start"] = r["start"]
            it["end_from"] = f"{src}（{(r.get('evidence') or '')[:20]}）"
            filled += 1
            log(f"締切の調査: {it.get('store')} → {it['end']}  {it['end_from']}")
    # 同じ告知（同じポスト・同じ応募ページ）から出た抽選は、締切も同じ
    by_url = {}
    for it in lots.values():
        if it.get("end") and it.get("end_from") and it.get("url"):
            by_url.setdefault(it["url"], it)
    for it in lots.values():
        src = by_url.get(it.get("url") or "")
        if it.get("status") in ACTIVE and not it.get("end") and src:
            it["end"] = src["end"]
            it["end_from"] = "同じ告知の別の商品から"
            filled += 1
    save_json("lotteries.json", lots)
    log(f"締切の調査: {len(todo)}件を調べて {filled}件の締切が分かった")
    return filled
