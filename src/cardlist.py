"""弾ページの「収録カードの相場（RR以上）」（11/11）

・Cloudflare の Worker（rakuten-watch の /cards）が集めたスニダンの相場を、サイトを作る前に1回読んで state/card_lists.json にまとめる
・GitHub の時間はほぼ使わない（読むだけ・数秒）
・カードの画像は使わない（カードの絵は権利があるため）。名前・番号・レアリティ・相場・動きだけ
"""
import re
from datetime import datetime, timedelta

import requests

from common import load_json, save_json, log, now

MERCARI_AFID = "1350793153"
URL = "https://rakuten-watch.supreme-buyer-1991.workers.dev/cards"
SHOW = 15  # 最初に見せる枚数（残りは「すべて見る」で開く）
RANK = {"MUR": 0, "UR": 1, "FUR": 1, "HR": 1, "SAR": 2, "CSR": 2, "SSR": 2, "SR": 3, "AR": 4, "CHR": 5, "S": 5, "RRR": 6, "RR": 6,
        "SEC-P": 0, "SEC": 1, "SR-P": 2, "L-P": 2, "SP": 2, "SR": 3, "L": 4}


def _ago(pts, d0, days):
    """d0 の days 日前（前後3日まで）の値"""
    t = (datetime.fromisoformat(d0) - timedelta(days=days)).date().isoformat()
    cand = [(d, v) for d, v in pts if d <= t]
    if cand and (datetime.fromisoformat(t) - datetime.fromisoformat(cand[-1][0])).days <= 3:
        return cand[-1][1]
    return None


def update(settings=None):
    try:  # 11/11：Worker は弾ごとに分けて持つ。目次（/cards）を読んで、カードのある弾だけ /cards?set=キー で読む
        idx = requests.get(URL, timeout=30).json()
    except Exception as e:
        log(f"収録カード: 読めなかった {e}")
        return
    out = {}
    for key, ix in (idx.get("sets") or {}).items():
        if not ix.get("priced"):
            continue
        try:
            s = requests.get(URL, params={"set": key}, timeout=30).json()
        except Exception as e:
            log(f"収録カード: {key} 読めなかった {e}")
            continue
        rows = []
        for c in (s.get("cards") or {}).values():
            pts = sorted((c.get("h") or {}).items())
            if not pts:
                rows.append({"id": c["id"], "n": c["n"], "r": c["r"], "no": c.get("no", ""), "p": None})
                continue
            d0, p = pts[-1]
            rows.append({"id": c["id"], "n": c["n"], "r": c["r"], "no": c.get("no", ""), "p": p, "d": d0,
                         "w": _ago(pts, d0, 7), "m": _ago(pts, d0, 30), "k": sum(1 for d, _ in pts if d >= _cut(d0, 30))})
        rows.sort(key=lambda x: (-(x["p"] or 0), RANK.get(x["r"], 9), x["no"]))
        out[key] = {"rows": rows, "at": now().isoformat()}
    if out:
        save_json("card_lists.json", out)
        try:
            photos(settings or {}, out)
        except Exception as e:
            log(f"収録カード（楽天の写真）: スキップ {e}")
        log("収録カード: " + "・".join(f"{k.split('|')[1]} {sum(1 for r in v['rows'] if r['p'])}/{len(v['rows'])}枚" for k, v in out.items()))


def photos(settings, lists, budget=25):
    """11/11：カードの写真は楽天市場の商品の写真（楽天のアフィリエイトの商品画像。写真は楽天の商品ページへのリンクにする）
    ・カード名と番号（080/076 など）が両方合う商品だけ。写真は文字・ロゴの入っていない「カード1枚だけ」のもの（cardphoto.py）。なければ写真なし
    ・14日に1回見直す。1回の実行で最大 budget 件（1件約1秒）"""
    import os
    import time
    if not (os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY")):
        return
    data = load_json("card_photos.json", {})
    old = (now().date() - timedelta(days=14)).isoformat()
    n = got = 0
    for v in lists.values():
        for r in v["rows"]:  # 高い順なので、目立つカードから先に付く
            k = str(r["id"])
            if (data.get(k) or {}).get("fetched", "") > old:
                continue
            if n >= budget:
                break
            n += 1
            try:
                data[k] = _photo(settings, r)
                got += bool(data[k].get("image"))
                if not data[k].get("image"):  # 楽天にカードだけの写真がないときは TCGplayer（日本版）の写真を控えておく
                    t = tcg_find(r.get("no") or "")
                    if t:
                        data[k]["tcg"] = t
            except Exception as e:
                log(f"収録カード（楽天の写真）: {r['n']} 失敗 {e}")
                if "401" in str(e) or "403" in str(e):
                    break
            time.sleep(1.1)
    if n:
        save_json("card_photos.json", data)
        log(f"収録カード（楽天の写真）: {n}件調べて写真{got}件")


NG_ITEM = re.compile(r"オリパ|英語版|韓国|中国|まとめ|セット売|ランダム|福袋|スリーブ|ローダー|PSA|BGS|ARS|CGC|鑑定|プロモ未開封|BOX")


def _photo(settings, r):
    """楽天で「カード名＋番号」が両方合う商品を探し、その写真からカード1枚だけの写真（文字なし）を選ぶ（cardphoto.check）"""
    import os
    import rakuten
    import cardphoto
    num = (re.search(r"\d{3}/\d{3}|[A-Z]{2,4}\d{0,2}-\d{3}", r.get("no") or "") or [None])[0] or ""
    q = f'{r["n"]} {num}'.strip()
    aff = (os.environ.get("RAKUTEN_AFFILIATE_ID") or settings.get("rakuten_affiliate_id") or "").strip()
    day = now().date().isoformat()
    if not num:
        return {"image": "", "url": rakuten.search_link(q, aff), "search": True, "fetched": day}
    items = rakuten.search(q, dict(settings, _genre=None, _sort="standard"))
    nb, nn = rakuten._norm(r["n"]), rakuten._norm(num)
    def ok(it):
        nm = it.get("itemName") or ""
        n_ = rakuten._norm(nm)
        if nb not in n_ or nn not in n_ or NG_ITEM.search(nm):
            return False
        if "ミラー" in nm and "ミラー" not in r["n"]:  # マスターボールミラーなど、ちがう仕様のカード
            return False
        return True
    it, img = cardphoto.pick(items, ok)
    if it:
        return {"image": img, "url": rakuten.item_link(it.get("itemUrl") or it.get("affiliateUrl"), aff), "fetched": day}
    return {"image": "", "url": rakuten.search_link(q, aff), "search": True, "fetched": day}


_TCG = {}


def tcg_find(no):
    """「M6 080/076」→ TCGplayer の日本版ポケカ（tcgcsv.com のカテゴリ85）の同じ弾・同じ番号の商品 {id, img, url}
    ・弾は TCGplayer の略号（m6・M5・m6a など）と型番の頭（M6 など）が同じもの。番号は「080/076」がぴったり同じもの"""
    m = re.match(r"([A-Za-z0-9]+)\s+(\d{3}/\d{3})", no or "")
    if not m:
        return None
    code, num = m[1].lower(), m[2]
    if "groups" not in _TCG:
        _TCG["groups"] = {g.get("abbreviation", "").lower(): g["groupId"]
                          for g in requests.get("https://tcgcsv.com/tcgplayer/85/groups", timeout=30).json().get("results", [])}
    gid = _TCG["groups"].get(code)
    if not gid:
        return None
    if gid not in _TCG:
        idx = {}
        for p in requests.get(f"https://tcgcsv.com/tcgplayer/85/{gid}/products", timeout=30).json().get("results", []):
            n_ = next((e["value"] for e in p.get("extendedData") or [] if e.get("name") == "Number"), "")
            if n_ and p.get("imageUrl"):
                idx.setdefault(n_, []).append(p)
        _TCG[gid] = idx
    ps = _TCG[gid].get(num) or []
    if len(ps) != 1:  # 同じ番号で何種類もある（ミラー違いなど）ときは使わない
        return None
    p = ps[0]
    return {"id": p["productId"], "img": p["imageUrl"], "url": p.get("url") or f"https://www.tcgplayer.com/product/{p['productId']}"}


def _tcg_on():
    from common import load_settings
    st = load_settings()
    return bool(st.get("tcgplayer_photos")), (st.get("tcgplayer_aff") or "").strip()


def _cut(d0, days):
    return (datetime.fromisoformat(d0) - timedelta(days=days)).date().isoformat()


def mercari(r):
    """メルカリの検索ページ（販売中だけ）。カード名＋番号（「080/076」のように弾のマークを除いた部分）で探す"""
    import urllib.parse
    no = (re.search(r"[A-Z]*\d+/\d+|[A-Z]{2,4}\d{0,2}-\d{3}", r.get("no") or "") or [None])[0] or ""
    q = f"{r['n']} {no}".strip()
    # 11/11：メルカリアンバサダーのID（afid）。リンクから24時間以内に買われると販売価格の2%がメルカリポイントで入る
    # 形はアンバサダーの「リンク生成」で作ったものと同じ（search?afid=…&keyword=…）。販売中だけに絞る status は最後
    return "https://jp.mercari.com/search?afid=" + MERCARI_AFID + "&amp;keyword=" + urllib.parse.quote(q, safe="") + "&amp;status=on_sale"


def rows_of(game, series):
    return (load_json("card_lists.json", {}).get(f"{game}|{series}") or {}).get("rows") or []


def html(game, series, esc):
    """弾ページに入れる表。相場の分かるカードが5枚未満なら出さない"""
    rows = [r for r in rows_of(game, series) if r.get("p")]
    if len(rows) < 5:
        return ""
    def pct(a, b):
        if not a or not b:
            return ""
        v = (a - b) / b * 100
        cls = "up" if v > 0 else "down" if v < 0 else ""
        return f'<span class="{cls}">{"+" if v > 0 else ""}{v:.0f}%</span>'
    last = max(r["d"] for r in rows)
    ph = load_json("card_photos.json", {})
    tcg_on, tcg_aff = _tcg_on()
    used_tcg = []
    def img(r):
        x = ph.get(str(r["id"])) or {}
        alt = f'{esc(r["n"])} {esc(r["r"])} {esc(r.get("no") or "")}'
        if x.get("image") and x.get("url"):  # 1. 楽天のカードだけの写真
            return (f'<a href="{esc(x["url"])}" target="_blank" rel="nofollow sponsored noopener">'
                    f'<img src="{esc(x["image"])}" alt="{alt}" loading="lazy" width="48" height="48"></a>')
        t = x.get("tcg")
        if tcg_on and t and tcg_aff:  # 2. なければ TCGplayer（アフィリエイトの承認後に settings の tcgplayer_photos を true に）
            used_tcg.append(1)
            href = tcg_aff.replace("{url}", __import__("urllib.parse").parse.quote(t["url"], safe=""))
            return (f'<a href="{esc(href)}" target="_blank" rel="nofollow sponsored noopener">'
                    f'<img src="{esc(t["img"])}" alt="{alt}" loading="lazy" width="48" height="48"></a>')
        return '<span class="noimg" aria-hidden="true"></span>'
    def rk(r):
        x = ph.get(str(r["id"])) or {}
        return (f'<a class="rk" href="{esc(x["url"])}" target="_blank" rel="nofollow sponsored noopener">{"楽天で探す" if x.get("search") else "楽天で見る"}</a>'
                if x.get("url") else "")
    trs = "".join(
        f'<tr{" class=\"mo\"" if n_ >= SHOW else ""}><td class="ci">{img(r)}</td><td class="cr r-{esc(r["r"])}">{esc(r["r"])}</td><td class="cn"><a href="https://snkrdunk.com/apparels/{r["id"]}" rel="nofollow noopener" target="_blank">'
        f'{esc(r["n"])}</a></td><td class="cno">{esc(r["no"])}</td><td class="num cp">¥{r["p"]:,}'
        + ('<small class="few">取引少</small>' if (r.get("k") or 0) < 3 else "") + '</td>'
        f'<td class="num cw" data-l="7日">{pct(r["p"], r.get("w")) or "−"}</td><td class="num cm" data-l="30日">{pct(r["p"], r.get("m")) or "−"}</td>'
        f'<td class="mer"><a href="{mercari(r)}" rel="nofollow sponsored noopener" target="_blank">メルカリで探す</a>{rk(r)}</td></tr>'
        for n_, r in enumerate(rows))
    has_ph = any((ph.get(str(r["id"])) or {}).get("image") for r in rows)
    rars = sorted({r["r"] for r in rows}, key=lambda x: RANK.get(x, 9))
    md = f"{int(last[5:7])}/{int(last[8:10])}"
    return (f'<section class="sinfo scards" aria-label="収録カードの相場"><h2>{esc(series)}の収録カードの相場（{"・".join(esc(x) for x in rars)}）</h2>'
            f'<p class="note">スニダンの取引の値段（未鑑定・状態Aの1枚、{md}時点の最新の取引日の平均）。高い順。「取引少」は30日の取引が少なく、値段がぶれやすいカードです。'
            f'{"型番は「弾のマーク 番号/収録数」です。" if game == "pokemon" else ""}名前を押すとスニダンの商品ページ、「メルカリで探す」「楽天で見る」でそのカードの出品・商品を開きます。</p>'
            f'<div class="tbl"><table><thead><tr><th></th><th>レア</th><th>カード</th><th>型番</th><th>相場</th><th>7日</th><th>30日</th><th>買う</th></tr></thead><tbody>{trs}</tbody></table></div>'
            + (f'<button type="button" class="cmore" onclick="this.closest(\'.scards\').classList.add(\'open\')">残り{len(rows) - SHOW}枚もすべて見る ▼</button>' if len(rows) > SHOW else '') +
            f'<p class="note">※値段は取引のあった日の値段で、これからの値段を約束するものではありません。' + ('写真は楽天市場' + ('・TCGplayer' if used_tcg else '') + 'の商品の写真です。' if has_ph or used_tcg else '') + 'メルカリ・楽天市場' + ('・TCGplayer' if used_tcg else '') + 'へのリンクは広告（PR）です。</p></section>')
