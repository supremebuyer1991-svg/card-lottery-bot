"""ゲーム・ホビー入荷速報：載せる前に、AIが読み取った抽選・予約・販売の情報が元の記事と合っているかをもう一度確かめる（11/10 ユーザーの指示「精度上げて」）

きっかけ（11/10）：
・ちいかわクリスマスマーケット：記事にない「通販で11/24 11時から先着販売」を作っていた（11時はイベントの開場時刻）
・ポケセンのハドウシーカー：何日も前から受付中の抽選を新着として速報した

やること：
・まだ確かめていない受付中の項目を、1回 verify_per_run 件まで、元の記事（source_url → url）を読み直して、
  AI（安いモデル）に「お店・商品・種類（抽選/予約/先着/再販/発売）・受付開始・締切・受け取り（通販/店頭）が本文にはっきり書かれているか」を聞く
・合っていれば verified=True。違っていれば直せるところは直し（AIが本文から正しい値を出せた時だけ）、
  直せない・そもそも販売の情報でないものは verified=False（サイトに出さない・投稿しない）
・本文が読めない時は確かめずに残す（次の回にもう一度）。手で入れたもの（manual）は確かめない
・Xへの投稿（API速報・予約投稿）は verified=True のものだけ
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor

import requests

from common import load_json, save_json, now, log, job_elapsed

MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
ACTIVE = ("approved", "listed", "posted")
FIELDS = ("store", "product", "kind", "start", "end", "channel", "price")
PROMPT = """あなたはゲーム機・ホビーの抽選・予約・販売情報サイトの校正係です。下の「読み取った情報」が「元の記事」に本当に書かれているかを、1項目ずつ厳しく確かめてください。

確かめること：
1. その記事が「商品を買う・応募する機会」（抽選販売・予約受付・先着販売・再販・発売）の情報か。イベントの開催・入場チケット・会場だけの販売・ニュースの紹介だけなら false
2. store（売る・受け付けるお店）、product（商品）が記事に書かれているか
3. kind：lottery=抽選、preorder=予約受付、first_come=先着販売、restock=再販・再入荷、release=発売日の情報、invite=招待販売。記事と合っているか
4. start（受付・販売の開始日時）・end（締切。発売の情報なら発売日）が記事の日時と合っているか。記事に無い日時を作っていないか（イベントの開場時刻などを販売開始と取り違えていないか）
5. channel：online=通販で発送、store=店頭で受け取り・購入。記事と合っているか

答えはJSONだけ：
{{"is_sale": true/false, "ok": true/false, "wrong": ["合っていない項目名"], "fix": {{"項目名": "記事から分かる正しい値（日時は 2026-11-24T11:00:00+09:00 の形。記事に無ければ null）"}}, "reason": "短い理由（日本語）"}}

読み取った情報：
{item}

元の記事（{url}）：
{text}"""


def _ai(item, url, text):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY が未設定")
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 4000, "messages": [{"role": "user", "content": PROMPT.format(
            item=json.dumps(item, ensure_ascii=False, indent=1), url=url, text=text[:14000])}]})
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API {r.status_code}: {r.text[:160]}")
    raw = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    m = re.search(r"\{.*\}", raw, re.S)
    return json.loads(m.group(0)) if m else None


def _text(url, settings, fetcher=None):
    from fetch import html_to_text
    if fetcher is None:
        from urllib.parse import urlparse
        import fetch as _f
        h = urlparse(url).hostname or ""
        jp = settings.get("via_jp_hosts") or []
        if any(h == x or h.endswith("." + x) for x in jp) and os.environ.get("JPFETCH_SEED"):
            import jpfetch
            fetcher = jpfetch.get
        else:
            fetcher = _f.get
    return html_to_text(fetcher(url), url)


def verify(settings, ai=None, fetcher=None):
    """受付中でまだ確かめていない項目を確かめる。戻り値：確かめた件数"""
    if not (ai or os.environ.get("ANTHROPIC_API_KEY")):
        return 0
    ai = ai or _ai
    lots = load_json("lotteries.json", {})
    todo = [(k, it) for k, it in lots.items() if it.get("status") in ACTIVE and "verified" not in it and not it.get("manual")
            and (it.get("source_url") or it.get("url"))]
    todo.sort(key=lambda kv: kv[1].get("found_at") or "", reverse=True)   # 新しく見つけたものから
    todo = todo[:int(settings.get("verify_per_run", 6))]
    if not todo or job_elapsed() > float(settings.get("verify_until_sec", 240)):
        return 0

    def one(kv):
        k, it = kv
        url = it.get("source_url") or it.get("url")
        if "news.google." in url and it.get("url") and "news.google." not in it["url"]:
            url = it["url"]
        try:
            text = _text(url, settings, fetcher)
        except Exception as e:
            return k, None, f"本文が読めない {str(e)[:60]}"
        if len(text) < 200:
            return k, None, "本文が短すぎる"
        try:
            res = ai({f: it.get(f) for f in FIELDS}, url, text)
        except Exception as e:
            return k, None, f"AIの失敗 {str(e)[:60]}"
        return k, res, ""

    n = 0
    with ThreadPoolExecutor(max_workers=int(settings.get("verify_parallel", 4))) as ex:
        for k, res, err in ex.map(one, todo):
            it = lots[k]
            if res is None:
                log(f"  確認：{it.get('store')} {(it.get('product') or '')[:30]} … 保留（{err}）")
                continue
            n += 1
            it["verified_at"] = now().isoformat()
            if not res.get("is_sale", True):
                it["verified"] = False
                it["verify_note"] = "販売・応募の情報ではない：" + str(res.get("reason") or "")[:120]
            elif res.get("ok"):
                it["verified"] = True
            else:
                fix = {f: v for f, v in (res.get("fix") or {}).items() if f in FIELDS and v not in (None, "")}
                wrong = [w for w in (res.get("wrong") or []) if w in FIELDS]
                if wrong and all(w in fix for w in wrong):   # 違っていた項目を全部、記事から直せた
                    for f, v in fix.items():
                        it.setdefault("before_verify", {})[f] = it.get(f)
                        it[f] = v
                    it["verified"] = True
                    it["verify_note"] = "記事に合わせて直した：" + "・".join(wrong)
                else:
                    it["verified"] = False
                    it["verify_note"] = ("記事と合わない：" + "・".join(wrong) + " " + str(res.get("reason") or ""))[:160]
            log(f"  確認：{it.get('store')} {(it.get('product') or '')[:30]} → {'OK' if it['verified'] else 'NG'} {it.get('verify_note', '')[:60]}")
    save_json("lotteries.json", lots)
    if n:
        log(f"確認：{n}件（記事と合わない・販売の情報でないものはサイトに出さない）")
    return n
