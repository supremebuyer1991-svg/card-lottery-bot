"""応募先のページ（通販の商品ページ・Googleフォーム・LivePocketなど）を1日1回見て、
販売・受付が終わっていたら抽選を終了にする

・「販売終了」「受付終了」「回答を受け付けていません」などの言葉がある時だけAIに読ませる
  （サイトのメニューに「販売終了品を含む」などがあるだけで消さないように、AIが判断する）
・Xのポストは対象外（ポストは消えないので、締切の読み取りと投稿日で判断している）
"""
import json
import os
import re

import requests

from common import load_json, save_json, now, parse_dt, log, GENERIC_STORE_RE, site_name
from extract import API_URL, MODEL
from fetch import get, html_to_text
from address import find_address

ACTIVE = ("new", "pending", "approved", "posted", "listed")
END_WORDS = re.compile(
    r"販売終了|受付終了|受付は終了|受付を終了|予約受付終了|予約受付は終了|応募受付は終了|応募は締め切|締め切りました|"
    r"回答を受け付けていません|販売期間外|受付期間外|このイベントは終了|SOLD\s*OUT|完売|在庫切れ|品切れ|"
    r"お取り扱いできません|販売を終了|抽選受付は終了|エントリー受付は終了", re.I)
SKIP_HOSTS = ("x.com", "twitter.com", "t.co", "amazon.co.jp", "amzn.to", "link.amazon", "lin.ee")

PROMPT = """トレカの抽選販売・予約販売の応募ページの本文です。
このページの「{product}」の抽選・販売の受付は、今も受付中ですか？ 終わっていますか？

- ページのメニューや一覧にある「販売終了品」「在庫切れ商品を表示」などの言葉は関係ない。この商品・この抽選の状態だけを見る
- はっきり終わっている（販売終了・受付終了・完売・フォームが回答を受け付けていない）時だけ ended
- 分からない時は unknown

出力は次のJSONだけ: {{"status": "open|ended|unknown", "evidence": "根拠の文言を20字以内"}}

--- ページ本文 ---
{text}
"""


def _ask(text, it):
    r = requests.post(API_URL, timeout=60, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json",
    }, json={"model": MODEL, "max_tokens": 200, "messages": [{"role": "user", "content": PROMPT.format(
        product=(it.get("series") or it.get("product") or "")[:60], text=text[:5000])}]})
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API エラー {r.status_code}")
    raw = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0)) if m else {}


DETAIL_PROMPT = """トレカの抽選販売の応募ページの本文です。「{store}」の「{product}」の抽選について、書かれていることだけを読み取ってください。

- conditions: 応募・購入の条件を、ページの文をそのまま写さず自分の言葉で120字以内に（会員登録・アプリ・本人確認書類・1人いくつまで・代理購入・価格など）
- announce: 当選発表の日（例「11/3(火)〜11/4(水)」）。書かれていなければ null
- buy: 購入・受け取りの期間（例「11/6(金)〜11/8(日)」）。書かれていなければ null
- method: 応募のしかた（例「Web抽選（LivePocket）→ 当選したら店頭で購入」）
- id_check: 購入時に本人確認書類が要るなら true、要らないとはっきり書いてあれば false、書かれていなければ null
- member: 会員カードが要るなら "card"、会員登録・アカウント・アプリ会員が要るなら "account"、不要とはっきり書いてあれば "none"、分からなければ null
- 書かれていないことは推測しない

出力は次のJSONだけ: {{"conditions": "...", "announce": null, "buy": null, "method": null, "id_check": null, "member": null}}

--- ページ本文 ---
{text}
"""


def _ask_details(text, it):
    r = requests.post(API_URL, timeout=60, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json",
    }, json={"model": MODEL, "max_tokens": 600, "messages": [{"role": "user", "content": DETAIL_PROMPT.format(
        store=it.get("store") or "", product=(it.get("series") or it.get("product") or "")[:60], text=text[:6000])}]})
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API エラー {r.status_code}")
    raw = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0)) if m else {}


def _needs_details(it):
    """Xの短いポストから拾った抽選などで、条件・発表日などが空のもの"""
    return not it.get("details_checked") and not it.get("manual") and (
        not it.get("conditions") or (not it.get("announce") and it.get("id_check") is None))


def fill_details(it, text, ask_details):
    """応募ページから、空いている欄（条件・発表日・購入期間・本人確認・会員）だけを埋める"""
    it["details_checked"] = True
    try:
        r = ask_details(text, it)
    except Exception as e:
        log(f"応募ページの確認: 詳細の読み取り失敗 {e}")
        return False
    got = []
    for f in ("conditions", "announce", "buy", "method"):
        v = r.get(f)
        if isinstance(v, str) and v.strip() and v.strip().lower() != "null" and not it.get(f):
            it[f] = v.strip()[:200]
            got.append(f)
    if r.get("id_check") in (True, False) and it.get("id_check") is None:
        it["id_check"] = r["id_check"]
        got.append("id_check")
    if r.get("member") in ("card", "account", "none") and not it.get("member"):
        it["member"] = r["member"]
        got.append("member")
    tags = list(it.get("tags") or [])
    for cond, tg in ((it.get("id_check") is True, "本人確認"), (it.get("member") in ("card", "account"), "会員")):
        if cond and tg not in tags:
            tags.append(tg)
    it["tags"] = tags
    if got:
        log(f"応募ページの確認: 詳細 {it.get('store')} {','.join(got)}")
    return bool(got)


def _tid(u):
    m = re.search(r"(?:x|twitter)\.com/[^/]+/status/(\d+)", u or "")
    return m.group(1) if m else None


def _ask_post(text, images, it):
    """お店の告知ポスト（本文＋画像）から、条件・本人確認などを読む（画像のポスターに書いてあることが多い）"""
    from deadline import _image_block, VISION_MODEL
    content = [_image_block(u) for u in images[:4]]
    for c in content:
        c.pop("_ok", None)
    content.append({"type": "text", "text": DETAIL_PROMPT.format(
        store=it.get("store") or "", product=(it.get("series") or it.get("product") or "")[:60],
        text="（お店のXの告知。画像の文字もよく読むこと）\n" + text[:3000])})
    for model in (VISION_MODEL, MODEL):
        r = requests.post(API_URL, timeout=90, headers={
            "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json",
        }, json={"model": model, "max_tokens": 600, "messages": [{"role": "user", "content": content}]})
        if r.status_code < 400:
            break
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API エラー {r.status_code}")
    raw = "".join(b.get("text", "") for b in r.json().get("content", []))
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0)) if m else {}


def fill_from_posts(settings, lots, ask=None, x_client=None, limit=None):
    """応募ページが読めない抽選（LivePocketなどはボットに中身を返さない）は、お店のXの告知（本文＋画像）から
    本人確認・会員・条件を埋める。1件につき1回だけ・Xの読み取り上限に数える"""
    if ask is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return 0
        ask = _ask_post
    limit = limit or settings.get("post_detail_checks_per_run", 10)
    todo = [it for it in lots.values() if it.get("status") in ACTIVE and it.get("page_err") and not it.get("post_checked")
            and (_tid(it.get("url")) or _tid(it.get("x_post"))) and (_needs_details(it) or it.get("id_check") is None)][:limit]
    if not todo:
        return 0
    from deadline import _x_lookup
    try:
        tweets = _x_lookup(list({_tid(i.get("x_post")) or _tid(i.get("url")) for i in todo}), settings, x_client)
    except Exception as e:
        log(f"告知ポストの確認: X取得失敗 {e}")
        return 0
    n = 0
    for it in todo:
        tw = tweets.get(_tid(it.get("x_post")) or _tid(it.get("url")))
        if not tw:
            continue  # 取れなかった（上限・削除）→ 次回また
        it["post_checked"] = True
        text, imgs = tw[0], tw[1]
        it.pop("details_checked", None)
        if fill_details(it, text, lambda t_, i_: ask(t_, imgs, i_)):
            n += 1
    if todo:
        log(f"告知ポストの確認: {len(todo)}件を見て {n}件の条件などが分かった")
    return n


def check_pages(settings, ask=None, fetcher=get, limit=None, ask_details=None):
    """戻り値: 終了にした件数"""
    if ask is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return 0
        ask = _ask
    if ask_details is None and os.environ.get("ANTHROPIC_API_KEY"):
        ask_details = _ask_details
    limit = limit or settings.get("page_checks_per_run", 40)
    lots = load_json("lotteries.json", {})
    todo = []
    for it in lots.values():
        if it.get("status") not in ACTIVE:
            continue
        url = it.get("apply_url") or it.get("url") or ""
        if not url.startswith("http") or any(h in url for h in SKIP_HOSTS):
            continue
        t = parse_dt(it.get("page_checked_at"))
        need_addr = it.get("channel") == "store" and not it.get("address") and not it.get("address_checked")
        need_det = bool(ask_details) and _needs_details(it)
        need_name = bool(GENERIC_STORE_RE.search(it.get("store") or "")) and not it.get("name_checked")
        if t and (now() - t).total_seconds() < 20 * 3600 and not need_addr and not need_det and not need_name:
            continue
        if t and it.get("page_err") and (now() - t).total_seconds() < 6 * 3600:
            continue  # 読めなかったページは6時間あける（毎回同じページで枠を使い切らないように）
        todo.append((it, url))
    pages, names = {}, {}
    closed = 0
    for it, url in todo[:limit]:
        it["page_checked_at"] = now().isoformat()
        if url not in pages:
            try:
                raw = fetcher(url)
                if "livepocket.jp/e/" in url:  # ついでにお店のページを覚える（追加のアクセスなし）
                    try:
                        import lpshops
                        lpshops.record(url, raw, it.get("store") or "")
                    except Exception:
                        pass
                names[url] = site_name(raw)
                pages[url] = html_to_text(raw, url)
            except Exception as e:
                pages[url] = ""
                it["page_err"] = str(e)[:120]  # 読めなかった理由を残す（サイトに断られた・時間切れなど）
                log(f"応募ページの確認: 取得失敗 {url[:60]} {e}")
        text = pages[url]
        if text:
            it.pop("page_err", None)
        elif url in pages and not it.get("page_err"):
            it["page_err"] = "中身が空"
        if text and GENERIC_STORE_RE.search(it.get("store") or ""):  # 「その他のストア」→ 応募ページの名前を店名に
            it["name_checked"] = True
            if names.get(url):
                log(f"応募ページの確認: 店名 {it.get('store')} → {names[url]}")
                it["store"] = names[url]
        if text and it.get("channel") == "store" and not it.get("address"):  # 店頭抽選はお店の住所も読む
            a = find_address(text, it.get("area"))
            if a:
                it["address"] = a
                log(f"応募ページの確認: 住所 {it.get('store')} {a}")
            it["address_checked"] = True
        if text and ask_details and _needs_details(it):  # 空いている条件などを応募ページから埋める（1つの抽選につき1回）
            fill_details(it, text, ask_details)
        if not text or not END_WORDS.search(text):
            continue
        try:
            r = ask(text, it)
        except Exception as e:
            log(f"応募ページの確認: AI失敗 {e}")
            continue
        if r.get("status") == "ended":
            it["status"] = "closed" if it["status"] in ("posted", "listed") else "expired"
            it["closed_at"] = now().isoformat()
            it["closed_reason"] = f"応募ページで受付終了（{(r.get('evidence') or '')[:20]}）"
            closed += 1
            log(f"応募ページの確認: 終了 {it.get('store')} {url[:60]} {r.get('evidence')}")
    try:
        fill_from_posts(settings, lots)  # 応募ページが読めなかった抽選は、お店のXの告知から
    except Exception as e:
        log(f"告知ポストの確認: スキップ {e}")
    save_json("lotteries.json", lots)
    if todo:
        log(f"応募ページの確認: {min(len(todo), limit)}件を見て {closed}件を終了に")
    return closed
