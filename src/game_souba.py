"""ゲーム・ホビー入荷速報：スニダンの相場（トレカ抽選ナビの相場と同じ読み方）

・対象は config/game/models.yaml の series_souba に書いた機種・モデルだけ（スニダンの商品番号 snkr・定価 teika）
・1日1回（souba_hour 時以降の最初の実行）。1件ずつ間をあけて読む。断られたらその日はあきらめる
・state/game/souba.json に {"<カテゴリ>|<モデル>": {"price": 直近の取引の平均, "date": その日, "avg7": 7日平均, "teika": 定価}} を残す
・サイトには「スニダン相場 ○円（定価比 +○%）」と、定価比からの目安（プレ値の目安）を出す。予想ではなく、目安と書く
"""
import time

import yaml

from common import ROOT, load_json, save_json, now, log

STATE = "souba.json"


def cfg():
    y = yaml.safe_load((ROOT / "config" / "game" / "models.yaml").read_text(encoding="utf-8")) or {}
    return y.get("series_souba") or {}


def update(settings, sess=None, sleep=time.sleep, daily=None):
    """daily(sess, snkr_id) → {日付: 値段}（テストでは偽物を渡す）"""
    c = cfg()
    if not c:
        return {}
    st = load_json(STATE, {})
    t = now()
    if t.hour < int(settings.get("souba_hour", 7)) or st.get("_checked", "")[:10] == t.date().isoformat():
        return st
    import souba
    if sess is None:
        import requests
        sess = requests.Session()
        sess.headers.update({"User-Agent": souba.UA, "Accept-Language": "ja"})
    daily = daily or souba._snkr_daily
    n = 0
    for game, models in c.items():
        for name, v in (models or {}).items():
            if not v or not v.get("snkr"):
                continue
            try:
                d = daily(sess, int(v["snkr"]))
            except Exception as e:
                log(f"相場（ゲーム）: {name} 取得失敗 {e}")
                if "403" in str(e) or "429" in str(e):
                    st["_checked"] = t.isoformat()
                    save_json(STATE, st)
                    return st
                continue
            from datetime import timedelta
            cut = (t.date() - timedelta(days=int(settings.get("souba_max_age_days", 30)))).isoformat()
            days = [k for k in sorted(d) if k >= cut]   # 古い取引（1か月より前）しかないものは出さない
            st.pop(f"{game}|{name}", None)
            if days:
                last7 = [d[k] for k in days if k >= (t.date() - timedelta(days=7)).isoformat()] or [d[k] for k in days[-3:]]
                st[f"{game}|{name}"] = {"price": d[days[-1]], "date": days[-1], "avg7": round(sum(last7) / len(last7)),
                                        "teika": v.get("teika"), "snkr": v["snkr"]}
                n += 1
            sleep(1.5)
    st["_checked"] = t.isoformat()
    save_json(STATE, st)
    log(f"相場（ゲーム）: {n}件を更新")
    return st


def label(rec):
    """{"text": "スニダン相場 59,800円（定価比 +0%）", "hint": "定価前後"} か None"""
    if not rec or not rec.get("price"):
        return None
    p = int(rec.get("avg7") or rec["price"])
    text = f"スニダン相場 {p:,}円"
    hint = ""
    if rec.get("teika"):
        r = p / int(rec["teika"])
        text += f"（定価比 {'+' if r >= 1 else ''}{round((r - 1) * 100)}%）"
        hint = "プレ値 高め" if r >= 1.3 else "プレ値 やや高め" if r >= 1.1 else "定価前後" if r >= 0.95 else "定価より安い"
    return {"text": text, "hint": hint}


def for_item(it, st=None):
    st = st if st is not None else load_json(STATE, {})
    return label(st.get(f"{it.get('game')}|{it.get('series')}"))


# ---- 買取ルデヤの新品の買取価格（スニダンに無い商品の目安。買取価格が定価を超える＝相場は定価より上）----
KAITORI = "kaitori.json"   # state/game/kaitori.json {検索語: {"items": [[名前, JAN, 買取価格]], "at": 日時}}


def parse_rudeya(text):
    """買取ルデヤの検索結果（本文テキスト）→ [(商品名, JAN, 買取価格)]（新品だけ）"""
    import re
    out = []
    text = re.sub(r"\s+", " ", text or "")   # 改行をならす（ページの本文は行ごとに分かれている）
    for m in re.finditer(r"(?:^|\s)新品 (.+?) JAN: ?(\d{8,13}).*?買取価格 ([\d,]+) 円", text):
        out.append((m.group(1).strip(), m.group(2), int(m.group(3).replace(",", ""))))
    return out


def parse_ichiban(text):
    """モバイル一番の検索結果（本文テキスト）→ [(商品名, JAN, 買取価格)]（新品だけ。「来店+○円」は足さない＝郵送の価格）"""
    import re
    out = []
    text = re.sub(r"\s+", " ", text or "")
    for m in re.finditer(r"(?:強 化 )?(.+?) JAN: ?(\d{8,13}) (?:来店\+\d+ )?新品 (?:商品買取選択項目 来店 \+[\d,]+円 確定 )?([\d,]+) ?円", text):
        name = re.sub(r"^.*?(?:更新日:\S+ |円 )", "", m.group(1)).replace("強 化 ", "").strip()
        out.append((name, m.group(2), int(m.group(3).replace(",", ""))))
    return out


def parse_god(text):
    """ケータイゴッドの買取価格一覧（「商品名 JAN 価格円 査定」の並び）→ [(商品名, JAN, 買取価格)]"""
    import re
    out = []
    text = re.sub(r"\s+", " ", text or "")
    for chunk in text.split(" 査定 "):
        m = re.search(r"(?:自動査定 )?([^円]{4,160}?) ?(\d{13})? ?([\d,]{3,})円$", chunk.strip())
        if m:
            name = re.sub(r"^.*自動査定 ", "", m.group(1)).replace("【ゲーム機本体】", "").strip()
            out.append((name, m.group(2), int(m.group(3).replace(",", ""))))
    return out


def parse_twinkle(text):
    """トゥインクルモバイルの買取価格一覧（「商品名 JANコード: JAN … 新品 価格 円」）→ [(商品名, JAN, 買取価格)]"""
    import re
    out = []
    text = re.sub(r"\s+", " ", text or "")
    for chunk in re.split(r" 円 ", text + " "):
        m = re.search(r"(?:数量 )?([^円]{4,160}?) JANコード: ?(\d{8,13}) .*?新品 ([\d,]{3,})$", chunk.strip())
        if m:
            name = re.sub(r"^.*新品買取額 数量 ", "", m.group(1)).strip()
            out.append((name, m.group(2), int(m.group(3).replace(",", ""))))
    return out


PARSERS = {"rudeya": "parse_rudeya", "ichiban": "parse_ichiban", "god": "parse_god", "twinkle": "parse_twinkle"}


def _q(product):
    """買取ルデヤで探す言葉（商品名の最初の数語。カッコ書き・受付の言葉は外す）"""
    import re
    import unicodedata
    t = unicodedata.normalize("NFKC", product or "")
    t = re.sub(r"[（(【\[].*?[）)】\]]", " ", t)
    t = re.sub(r"抽選|予約|販売|受付|再販|再入荷|先着|発売|の?情報", " ", t)
    words = [w for w in re.split(r"[\s・]+", t) if w]
    out = []
    for w in words:
        if len(" ".join(out + [w])) > 30:
            break
        out.append(w)
    return " ".join(out[:4])


def _match(product, name):
    import official_link as ol
    return min(ol._score(product, name), ol._score(name, product))


def kaitori_update(settings, items, fetch=None, sleep=time.sleep):
    """サイトに載っている商品（items）を買取ルデヤで検索して、新品の買取価格を記録する（1回 kaitori_per_run 件まで・24時間に1回）"""
    from urllib.parse import quote
    import game_affi
    from fetch import html_to_text
    cache = load_json(KAITORI, {})
    t = now()
    left = int(settings.get("kaitori_per_run", 6))
    if fetch is None:
        from fetch import get as fetch
    import game_xpost as gx
    for it in sorted(items, key=lambda i: not gx.is_game(i)):   # ゲームを先に
        q = _q(it.get("product"))
        if not q or left <= 0:
            continue
        c = cache.get(q)
        if c and (t - __import__("common").parse_dt(c["at"])).total_seconds() < 24 * 3600:
            continue
        left -= 1
        try:
            text = html_to_text(fetch(f"https://kaitori-rudeya.com/search/index/{quote(q)}"))
            cache[q] = {"items": parse_rudeya(text)[:20], "at": t.isoformat()}
        except Exception as e:
            log(f"買取価格: {q} 取得失敗 {e}")
            cache[q] = {"items": [], "at": t.isoformat()}
        sleep(1.5)
    save_json(KAITORI, cache)
    return cache


def kaitori_for(it, cache=None):
    """その商品の新品の買取価格（合うものが無ければ None）"""
    import game_affi
    cache = cache if cache is not None else load_json(KAITORI, {})
    q = _q(it.get("product"))
    best = None
    for name, jan, price in (cache.get(q) or {}).get("items", []):
        sc = _match(it.get("product") or "", name)
        if sc >= 0.7 and (best is None or sc > best[0]):
            best = (sc, price)
    return best[1] if best else None


def kaitori_label(it, price):
    import re
    teika = None
    m = re.search(r"([\d,]{4,})", str(it.get("price") or ""))
    if m:
        teika = int(m.group(1).replace(",", ""))
    text = f"買取 {price:,}円"
    if teika:
        r = price / teika
        text += f"（定価比 {'+' if r >= 1 else ''}{round((r - 1) * 100)}%）"
        if r >= 1:
            text += "・プレ値"
    return text
