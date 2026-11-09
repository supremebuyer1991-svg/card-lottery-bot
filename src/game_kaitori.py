"""ゲーム・ホビー入荷速報：買取店（kaitori-search.app に載っている店）の新品の買取価格をまとめて、いちばん高い店を出す

・お店と「ゲームの買取価格の一覧ページ」は config/game/kaitori_stores.yaml
・日本の買取店はGitHub（海外）のサーバーからだと断られることが多いので、Cloudflareの中継（jpfetch）経由で読む
・ページの作りが店ごとに違うので、本文をAI（安いモデル）に渡して「商品名・JAN・新品の買取価格」を抜き出す
・1回の実行で kaitori_stores_per_run 店まで（実行時間を5分に収めるため）。各店は1日1回
・state/game/kaitori_multi.json {店: {"at": 日時, "items": [[商品名, JAN, 価格]]}}
・サイトには「最高買取 ○円（店名・定価比 +○%）」
"""
import json
import os
import re

import requests
import yaml

from common import ROOT, load_json, save_json, now, parse_dt, log

STATE = "kaitori_multi.json"
MODEL = os.environ.get("CLAUDE_MODEL", "claude-haiku-5-5")
PROMPT = """次は日本の買取店の買取価格のページの本文です。ゲーム機・ゲーム周辺機器（コントローラー等）・ゲームソフト・ホビー（プラモデル・フィギュア等）の
「新品（未開封）」の買取価格だけを、JSONの配列で返してください。スマホ・家電・中古・開封品・減額の条件の行は入れない。
形式：[{{"name":"商品名（型番も）","jan":"JANコード or null","price":買取価格の数字（円）}}]
該当が無ければ []。JSON以外は書かない。

本文：
{text}"""


def stores():
    p = ROOT / "config" / "game" / "kaitori_stores.yaml"
    if not p.exists():
        return []
    return [s for s in (yaml.safe_load(p.read_text(encoding="utf-8")) or {}).get("stores", []) if s.get("enabled", True) and s.get("urls")]


def _ai(text):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY が未設定")
    r = requests.post("https://api.anthropic.com/v1/messages", timeout=90, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": MODEL, "max_tokens": 16000, "messages": [{"role": "user", "content": PROMPT.format(text=text[:36000])}]})
    if r.status_code >= 400:
        raise RuntimeError(f"Claude API {r.status_code}: {r.text[:200]}")
    raw = "".join(b.get("text", "") for b in r.json().get("content", []))
    out = []
    objs = []
    for mo in re.finditer(r"\{[^{}]*\}", raw):   # 1件ずつ読む（返事が途中で切れても、そこまでは使う）
        try:
            objs.append(json.loads(mo.group(0)))
        except Exception:
            pass
    if not objs:
        log(f"  買取価格のAIの返事（先頭）: {raw[:120]!r}")
    for x in objs:
        try:
            p = int(str(x.get("price")).replace(",", "").replace("円", ""))
        except Exception:
            continue
        if x.get("name") and 300 <= p <= 2_000_000:
            out.append([str(x["name"])[:120], (str(x.get("jan") or "") or None), p])
    return out


def update(settings, fetch=None, ai=None):
    """古い（1日以上前の）店から順に、1回 kaitori_stores_per_run 店まで読み直す"""
    sts = stores()
    if not sts:
        return {}
    st = load_json(STATE, {})
    t = now()
    if fetch is None:
        import jpfetch
        fetch = jpfetch.get
    ai = ai or _ai
    from fetch import html_to_text
    todo = sorted([s for s in sts if not (st.get(s["name"]) and parse_dt(st[s["name"]]["at"])
                                          and (t - parse_dt(st[s["name"]]["at"])).total_seconds() < 20 * 3600)],
                  key=lambda s: (st.get(s["name"]) or {}).get("at", ""))
    from common import job_elapsed
    for s in todo[:int(settings.get("kaitori_stores_per_run", 2))]:
        if job_elapsed() > float(settings.get("kaitori_until_sec", 230)):   # 実行開始から230秒をすぎたら次の回に（5分以内に収める）
            log("買取価格：時間の上限なので、残りの店は次の回に回します")
            break
        items = []
        try:
            import game_souba
            if s.get("parser") in game_souba.PARSERS:   # 決まった形の店（ルデヤ・モバイル一番・ケータイゴッド・トゥインクル・SY・TOJO）はAIを使わずに読む
                # 検索の言葉が多い店は、1回に kaitori_urls_per_run ずつ数回に分けて読む（続きは cur に覚える。1周したら「読んだ日時」を更新）
                parse = getattr(game_souba, game_souba.PARSERS[s["parser"]])
                rec = st.get(s["name"]) or {}
                urls = s["urls"]
                cur = int(rec.get("cur") or 0) if int(rec.get("cur") or 0) < len(urls) else 0
                acc = {(x[1] or x[0]): x for x in (rec.get("acc") or [])} if cur else {}
                old = {(x[1] or x[0]): x for x in (rec.get("items") or [])}
                done = cur
                for u in urls[cur:cur + int(settings.get("kaitori_urls_per_run", 35))]:
                    if job_elapsed() > float(settings.get("kaitori_until_sec", 230)):
                        break
                    try:
                        for x in parse(html_to_text(fetch(u), u)):
                            acc[x[1] or x[0]] = list(x)   # 違う言葉の検索で同じ商品が出たら1つに
                            old[x[1] or x[0]] = list(x)
                    except Exception as e:
                        log(f"  買取価格：{s['name']} 1ページ失敗 {str(e)[:80]}")
                    done += 1
                lap = done >= len(urls)
                st[s["name"]] = {"at": t.isoformat() if lap else rec.get("at", ""), "cur": 0 if lap else done,
                                 "acc": [] if lap else list(acc.values()), "items": list((acc if lap else old).values())[:2000]}
                log(f"買取価格：{s['name']} {len(st[s['name']]['items'])}件（{done}/{len(urls)}ページ）")
                continue
            pages = [html_to_text(fetch(u), u) for u in s["urls"][:3]]
            items += ai("\n\n=====\n\n".join(p[:12000] for p in pages))   # ページをまとめて1回のAIに渡す（時間と費用を減らす）
            st[s["name"]] = {"at": t.isoformat(), "items": items[:400]}
            log(f"買取価格：{s['name']} {len(items)}件")
        except Exception as e:
            st[s["name"]] = {"at": t.isoformat(), "items": (st.get(s["name"]) or {}).get("items", []), "error": str(e)[:120]}
            log(f"買取価格：{s['name']} 取得失敗 {str(e)[:100]}")
    save_json(STATE, st)
    return st


def best_for(it, st=None):
    """その商品の、全店でいちばん高い新品の買取価格 → (価格, 店名) or None。JANが合えばそれ、なければ商品名で照合"""
    import official_link as ol
    st = st if st is not None else load_json(STATE, {})
    jan = str(it.get("jan") or "")
    prod = it.get("product") or ""
    best = None
    for store, rec in st.items():
        if not isinstance(rec, dict):
            continue
        for name, j, price in rec.get("items", []):
            ok = (jan and j and jan == j) or min(ol._score(prod, name), ol._score(name, prod)) >= 0.75
            if ok and (best is None or price > best[0]):
                best = (price, store)
    return best


def label(it, best):
    price, store = best
    m = re.search(r"([\d,]{4,})", str(it.get("price") or ""))
    text = f"最高買取 {price:,}円（{store}"
    if m:
        teika = int(m.group(1).replace(",", ""))
        r = price / teika
        text += f"・定価比 {'+' if r >= 1 else ''}{round((r - 1) * 100)}%"
        text += "）" + ("・プレ値" if r >= 1 else "")
    else:
        text += "）"
    return text
