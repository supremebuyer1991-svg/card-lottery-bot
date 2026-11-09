"""ゲーム・ホビー入荷速報：中身の少ない商品ページから順に「解説」の文を足す（11/9 ユーザーの指示）

・前の回の測定（game_volume → state/game/content_volume.json）で「そのページだけの文字数」が少ない商品ページから順に、
  1回 aitext_per_run 件まで、AI（安いモデル）にそのページのデータだけを渡して解説文を作ってもらう（数件を同時に頼んで時間を短く）
・データに無い事実（性能の数字・発売日など）は書かせない。転売をすすめる言い方もしない
・state/game/ai_text.json {キー: {"at": 日時, "text": 文}}。同じページは aitext_refresh_days 日たったら作り直す（価格の動きが変わるため）
・キー：買取相場のページは JAN、発売予定のページは "new:" + JAN
"""
import json
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from html import escape

import requests

from common import load_json, save_json, now, parse_dt, log, job_elapsed

STATE = "ai_text.json"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
PROMPT = """あなたはゲーム機・ホビーの価格情報サイトの編集者です。次の商品データ「だけ」を使って、この商品ページに載せる解説を日本語で書いてください。

ルール：
・データに無い事実（性能・仕様の数字、発売日、同梱物、売れ行き、在庫状況など）は書かない。推測は「〜とみられます」とも書かない
・データにある数字は正確に使う。転売・投資をすすめる言い方はしない（「儲かる」「狙い目」などは使わない）
・見出しを3つ立てる（行頭に「## 」）。例：「## どんな商品？」「## 買取相場の動き」「## 買うとき・売るときのポイント」（発売前の商品は「## 発売前に知っておきたいこと」など、データに合う見出しにする）
・全体で600〜900文字。です・ます調。箇条書きは使わず、短い段落で
・最後に余計な挨拶や注意書きは付けない
・「データ」「このページ」「情報がありません」「記録がない」など、材料の有無についての話は書かない。分からない項目には一切ふれず、分かっていることだけで自然な文章にする
・英語の単語を混ぜない（商品名・ブランド名は除く）

商品データ：
{data}"""


def _ai(data):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY が未設定")
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=60, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 8000, "messages": [{"role": "user", "content": PROMPT.format(data=json.dumps(data, ensure_ascii=False, indent=1))}]})
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API {r.status_code}: {r.text[:160]}")
    js = r.json()
    text = "".join(b.get("text", "") for b in js.get("content", []) if b.get("type") == "text").strip()
    if not text:
        log(f"  解説：返事が空（stop_reason={js.get('stop_reason')}・{[b.get('type') for b in js.get('content', [])]}）")
    text = re.sub(r"^#\s.*\n", "", text)   # 先頭の大見出し（# …）は外す
    if not (300 <= len(text) <= 4000 and "## " in text) or re.search(r"データ|このページ|情報がありません|記録がな", text):
        log(f"  解説：使わない返事（{len(text)}文字）{text[:60]!r}")
        return ""
    return text


def _premium_data(x):
    hist = x.get("hist") or {}
    vals = list(hist.values())
    d = {"商品名": x["name"], "店での別の呼び方": [n for n in x.get("names", []) if n != x["name"]][:5], "JANコード": x["jan"],
         "メーカー": x.get("maker") or "", "発売日": x.get("sales_date") or "", "対応機種": x.get("hardware") or "",
         "定価（税込・円）": x.get("teika") or "不明", "新品の最高買取価格（円）": x["max"], "最高買取の店": x["store"],
         "買取店ごとの価格（円）": dict(list(x.get("prices") or [])[:10]),
         "1週間前の最高買取（円）": x.get("w1") or "記録なし", "1か月前の最高買取（円）": x.get("m1") or "記録なし",
         "記録した期間の最高値・最安値（円）": [max(vals), min(vals)] if vals else "記録なし", "記録の日数": len(vals),
         "楽天ブックスの商品説明（抜粋）": re.sub(r"\s+", " ", x.get("caption") or "")[:600]}
    if x.get("teika"):
        d["定価との差（円）"] = x["max"] - x["teika"]
    return d


def _new_data(jan, x):
    return {"商品名": x.get("title"), "JANコード": jan, "機種": x.get("hardware"), "メーカー": x.get("maker"), "発売日": x.get("sales_date"),
            "定価（楽天ブックスの販売価格・円）": x.get("price") or "不明", "楽天ブックスの状況": __import__("game_upcoming").AVAIL.get(x.get("avail"), ""),
            "買取相場": "発売前のため予測不能", "楽天ブックスの商品説明（抜粋）": re.sub(r"\s+", " ", x.get("caption") or "")[:700]}


def update(settings, ai=None):
    """少ないページから順に解説を作る（1回 aitext_per_run 件まで・時間の上限つき）"""
    if not (ai or os.environ.get("ANTHROPIC_API_KEY")):
        return {}
    ai = ai or _ai
    st = load_json(STATE, {})
    vol = (load_json("content_volume.json", {}) or {}).get("pages") or {}
    target = int(settings.get("content_target_chars", 1500))
    t = now()
    old = (t - timedelta(days=float(settings.get("aitext_refresh_days", 30)))).isoformat()
    import game_premium
    import game_upcoming
    cat = {x["jan"]: x for x in game_premium.catalog(settings)}
    up = (load_json(game_upcoming.STATE, {}) or {}).get("items") or {}
    cands = []
    for path, (total, uniq) in vol.items():
        m = re.fullmatch(r"(premium|new)/(\d{8,13})/", path)
        if not m or uniq >= target + 600:   # 解説を足しても目標を大きく超えているページは後回しにしない＝対象外
            continue
        key = m.group(2) if m.group(1) == "premium" else "new:" + m.group(2)
        rec = st.get(key)
        if rec and rec.get("at", "") > old:
            continue
        if m.group(1) == "premium" and m.group(2) in cat:
            x = cat[m.group(2)]
            # 定価以上で売れる商品・買取価格の高い商品を先に（検索されやすい）、その中は中身の少ない順
            cands.append(((x.get("ratio") or 0) < 1, uniq, -x["max"], key, _premium_data(x)))
        elif m.group(1) == "new" and m.group(2) in up:
            cands.append((True, uniq, 0, key, _new_data(m.group(2), up[m.group(2)])))
    cands.sort(key=lambda c: c[:3])
    todo = []
    for c in cands[:int(settings.get("aitext_per_run", 12))]:
        todo.append(c)
    if not todo:
        return st
    if job_elapsed() > float(settings.get("aitext_until_sec", 215)):
        log("解説：時間の上限なので次の回に")
        return st
    made = 0
    with ThreadPoolExecutor(max_workers=int(settings.get("aitext_parallel", 4))) as ex:
        futs = {ex.submit(ai, c[4]): c for c in todo}
        for f, c in futs.items():
            try:
                text = f.result(timeout=90)
            except Exception as e:
                log(f"  解説：{c[3]} 失敗 {str(e)[:80]}")
                continue
            if text:
                st[c[3]] = {"at": t.isoformat(), "text": text}
                made += 1
    save_json(STATE, st)
    log(f"解説：{made}件つくった（候補 {len(cands)}件・作成済み {len(st)}件）")
    return st


_cache = {}


def html_for(key):
    """作った解説 → ページに入れるHTML（無ければ空）"""
    if "st" not in _cache:
        _cache["st"] = load_json(STATE, {}) or {}
    rec = _cache["st"].get(key)
    if not rec or not rec.get("text"):
        return ""
    out = []
    for block in re.split(r"\n\s*\n|\n(?=## )", rec["text"].strip()):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            head, _, rest = block.partition("\n")
            out.append(f"<h2>{escape(head[3:].strip())}</h2>")
            if rest.strip():
                out.append(f"<p>{escape(rest.strip())}</p>")
        else:
            out.append(f"<p>{escape(block)}</p>")
    d = parse_dt(rec.get("at"))
    return ('<div class="pm-ai">' + "".join(out) + f'<p class="note">この解説は、このページのデータ（買取価格・定価・商品情報）をもとに自動で作成しています'
            + (f"（{d.month}/{d.day}時点）" if d else "") + "。</p></div>")
