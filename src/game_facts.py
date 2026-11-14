"""ゲーム・ホビー入荷速報：商品ページ（/premium/<JAN>/）に、メーカー公式ページなどから取った商品の事実を足す（11/14）

11/14 ユーザー「商品の説明をどっかからもってきて自分の言葉に直してのせるのは？」「もうやっていこや」。
・1回 product_facts_per_run 件まで、AI（Claude API のウェブ検索・ページ読み取りの機能つき）に、商品名とJANから
  メーカー公式ページ（無ければ大手のお店の商品ページ）を探して読んでもらい、仕様・同梱物・発売日などの事実を
  最大8つ、元の文を写さず短い自分の言葉で書いてもらう。出典のURLも返してもらう
・出典のURLが、実際に検索・読み取りした結果に無いもの（AIが作ったURL）は使わない。メルカリなどのフリマは検索しない
・情報集めの間に裏で同時に動かす（start() → 解説の前に wait()）。GitHub の時間を延ばさない。1件ずつ state に保存
・state/game/product_facts.json {JAN: {"at", "facts": [...], "src", "src_title", "name"}}。見つからなかったものは "facts": [] で
  product_facts_retry_days 日たったら探し直す。見つかったものは product_facts_refresh_days 日で取り直す
"""
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from html import escape

import requests

from common import load_json, save_json, now, parse_dt, log

STATE = "product_facts.json"
BLOCK = ["mercari.com", "jp.mercari.com", "auctions.yahoo.co.jp", "paypayfleamarket.yahoo.co.jp", "fril.jp", "rakuma.rakuten.co.jp",
         "game-nyuka.com", "tcg-chusen.com"]
PROMPT = """日本で売られている次の商品について、メーカーの公式ページ（無ければ大手のお店の商品ページ）を検索して読み、商品の事実を集めてください。

商品名：{name}
JANコード：{jan}
（参考：買取店での呼び方 {names}）

ルール：
・まず「JANコード」や「商品名＋公式」で検索し、この商品（色・型番・セット内容まで同じもの）のページを見つける。別の商品・別の色・中古のページは使わない
・ページに「はっきり書かれている」事実だけを、最大8つ。例：発売日、メーカー希望小売価格、セット内容・同梱物、大きさ・重さ、対応機種、主な機能・仕様の数字、対象年齢、シリーズの中での位置づけ
・元の文をそのまま写さず、短い自分の言葉で（1つ70文字まで）。数字・型番・固有名詞はページのとおり正確に
・推測・一般論・宣伝の言葉（「大人気」「おすすめ」など）は書かない。価格の相場・在庫・転売のことは書かない
・この商品のページが見つからない・自信がないときは found を false にする

答えは最後にJSONだけ：
{{"found": true/false, "src": "事実を取ったページのURL", "src_title": "そのページの題名", "official": true/false（メーカー公式か）, "facts": ["…", "…"]}}"""


def _call(name, jan, names, settings):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY が未設定")
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": int(settings.get("product_facts_searches", 3)),
              "blocked_domains": BLOCK, "user_location": {"type": "approximate", "country": "JP", "timezone": "Asia/Tokyo"}},
             {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 2, "blocked_domains": BLOCK, "max_content_tokens": 12000}]
    msgs = [{"role": "user", "content": PROMPT.format(name=name, jan=jan, names="・".join(names[:4]))}]
    model = settings.get("product_facts_model") or os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
    seen_urls, text = set(), ""
    for _ in range(3):   # 検索が長いと pause_turn で止まるので続けさせる（最大3回）
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=90, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": 3000, "tools": tools, "messages": msgs})
        if r.status_code >= 400:
            raise RuntimeError(f"Claude API {r.status_code}: {r.text[:200]}")
        js = r.json()
        for b in js.get("content", []):
            if b.get("type") in ("web_search_tool_result", "web_fetch_tool_result"):
                c = b.get("content")
                for x in (c if isinstance(c, list) else [c] if isinstance(c, dict) else []):
                    if isinstance(x, dict) and x.get("url"):
                        seen_urls.add(x["url"])
            if b.get("type") == "text":
                text += b.get("text", "")
        if js.get("stop_reason") != "pause_turn":
            break
        msgs = msgs + [{"role": "assistant", "content": js["content"]}]
    m = re.search(r"\{[^{}]*\"found\"[\s\S]*\}", text)
    if not m:
        return None
    try:
        res = json.loads(m.group(0))
    except Exception:
        return None
    return res, seen_urls


def _norm_url(u):
    return re.sub(r"[?#].*$", "", (u or "").strip()).rstrip("/").lower()


def check(res, seen_urls):
    """AIの答えを使ってよいか → (facts, src, title, official) か None"""
    if not res or not res.get("found"):
        return None
    src = res.get("src") or ""
    if not src.startswith("http") or _norm_url(src) not in {_norm_url(u) for u in seen_urls}:   # 実際に見たページだけ
        return None
    if any(d in src for d in BLOCK):
        return None
    facts = [re.sub(r"\s+", " ", str(f)).strip()[:90] for f in (res.get("facts") or []) if isinstance(f, str) and f.strip()]
    facts = [f for f in facts if not re.search(r"大人気|おすすめ|オススメ|お得|狙い目|転売|プレ値|相場", f)][:8]
    if len(facts) < 2:
        return None
    return facts, src, str(res.get("src_title") or "")[:80], bool(res.get("official"))


_th = {}
_lock = threading.Lock()


def update(settings, call=None):
    """事実がまだ無い商品から順に取る（1件ずつ保存）。戻り値：取れた件数"""
    if not (call or os.environ.get("ANTHROPIC_API_KEY")) or not settings.get("product_facts_per_run", 0):
        return 0
    call = call or (lambda n, j, ns: _call(n, j, ns, settings))
    st = load_json(STATE, {})
    t = now()
    retry = (t - timedelta(days=float(settings.get("product_facts_retry_days", 14)))).isoformat()
    refresh = (t - timedelta(days=float(settings.get("product_facts_refresh_days", 120)))).isoformat()
    import game_premium
    cands = []
    for x in game_premium.catalog(settings):   # 定価以上で売れる商品・買取価格の高い商品から（検索されやすい）
        rec = st.get(x["jan"])
        if rec and rec.get("at", "") > (refresh if rec.get("facts") else retry):
            continue
        cands.append(x)
    todo = cands[:int(settings["product_facts_per_run"])]
    if not todo:
        return 0
    got = [0]

    def one(x):
        try:
            out = call(x["name"], x["jan"], x.get("names") or [])
        except Exception as e:
            log(f"  商品の事実：{x['name'][:30]} 失敗 {str(e)[:100]}")
            return
        ok = check(*out) if out else None
        with _lock:
            cur = load_json(STATE, {})
            if ok:
                facts, src, title, official = ok
                cur[x["jan"]] = {"at": now().isoformat(), "facts": facts, "src": src, "src_title": title, "official": official, "name": x["name"]}
                got[0] += 1
            else:
                cur[x["jan"]] = {"at": now().isoformat(), "facts": [], "name": x["name"]}
            save_json(STATE, cur)
        log(f"  商品の事実：{x['name'][:30]} → {len(ok[0]) if ok else 0}件" + (f"（{ok[1][:60]}）" if ok else ""))

    with ThreadPoolExecutor(max_workers=int(settings.get("product_facts_parallel", 4))) as ex:
        list(ex.map(one, todo))
    log(f"商品の事実：{got[0]}件取れた（候補 {len(cands)}件）")
    return got[0]


def start(settings):
    """情報集めの間に裏で動かす（GitHub の時間を延ばさない）"""
    if _th.get("t") or not settings.get("product_facts_per_run", 0):
        return
    th = threading.Thread(target=lambda: _safe(settings), daemon=True)
    _th["t"] = th
    th.start()


def _safe(settings):
    try:
        update(settings)
    except Exception as e:
        log(f"商品の事実: スキップ {e}")


def wait(timeout):
    th = _th.get("t")
    if th:
        th.join(max(0.0, timeout))
        if th.is_alive():
            log("商品の事実：まだ終わっていないので、終わった分だけ使います（残りは次の回）")


_cache = {}


def get(jan):
    if "st" not in _cache:
        _cache["st"] = load_json(STATE, {}) or {}
    rec = _cache["st"].get(jan) or {}
    return rec if rec.get("facts") else None


def html_for(jan, name):
    """商品ページに入れる欄（無ければ空）"""
    rec = get(jan)
    if not rec:
        return ""
    from urllib.parse import urlparse
    host = urlparse(rec["src"]).netloc
    who = "メーカー公式" if rec.get("official") else escape(host)
    return (f'<section class="pm-facts"><h2>{escape(name)}の商品の特徴</h2><ul>' + "".join(f"<li>{escape(f)}</li>" for f in rec["facts"]) + "</ul>"
            f'<p class="note">出典：<a href="{escape(rec["src"])}" target="_blank" rel="nofollow noopener">{who}（{escape(rec.get("src_title") or host)}）</a>'
            "の内容を要約しています。くわしい仕様は出典のページでご確認ください。</p></section>")
