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

from common import load_json, save_json, now, parse_dt, log
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


def check_pages(settings, ask=None, fetcher=get, limit=None):
    """戻り値: 終了にした件数"""
    if ask is None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return 0
        ask = _ask
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
        if t and (now() - t).total_seconds() < 20 * 3600 and not need_addr:
            continue
        todo.append((it, url))
    pages = {}
    closed = 0
    for it, url in todo[:limit]:
        it["page_checked_at"] = now().isoformat()
        if url not in pages:
            try:
                pages[url] = html_to_text(fetcher(url), url)
            except Exception as e:
                pages[url] = ""
                log(f"応募ページの確認: 取得失敗 {url[:60]} {e}")
        text = pages[url]
        if text and it.get("channel") == "store" and not it.get("address"):  # 店頭抽選はお店の住所も読む
            a = find_address(text, it.get("area"))
            if a:
                it["address"] = a
                log(f"応募ページの確認: 住所 {it.get('store')} {a}")
            it["address_checked"] = True
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
    save_json("lotteries.json", lots)
    if todo:
        log(f"応募ページの確認: {min(len(todo), limit)}件を見て {closed}件を終了に")
    return closed
