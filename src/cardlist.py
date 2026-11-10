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
RANK = {"MUR": 0, "UR": 1, "FUR": 1, "SAR": 2, "SR": 3, "AR": 4, "CHR": 5, "RR": 6}


def _ago(pts, d0, days):
    """d0 の days 日前（前後3日まで）の値"""
    t = (datetime.fromisoformat(d0) - timedelta(days=days)).date().isoformat()
    cand = [(d, v) for d, v in pts if d <= t]
    if cand and (datetime.fromisoformat(t) - datetime.fromisoformat(cand[-1][0])).days <= 3:
        return cand[-1][1]
    return None


def update():
    try:
        j = requests.get(URL, timeout=30).json()
    except Exception as e:
        log(f"収録カード: 読めなかった {e}")
        return
    out = {}
    for key, s in (j.get("sets") or {}).items():
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
        log("収録カード: " + "・".join(f"{k.split('|')[1]} {sum(1 for r in v['rows'] if r['p'])}/{len(v['rows'])}枚" for k, v in out.items()))


def _cut(d0, days):
    return (datetime.fromisoformat(d0) - timedelta(days=days)).date().isoformat()


def mercari(r):
    """メルカリの検索ページ（販売中だけ）。カード名＋番号（「080/076」のように弾のマークを除いた部分）で探す"""
    import urllib.parse
    no = (re.search(r"[A-Z]*\d+/\d+|[A-Z]{2,4}\d{0,2}-\d{3}", r.get("no") or "") or [None])[0] or ""
    q = f"{r['n']} {no}".strip()
    # 11/11：メルカリアンバサダーのID（afid）。リンクから24時間以内に買われると販売価格の2%がメルカリポイントで入る
    return "https://jp.mercari.com/search?status=on_sale&amp;keyword=" + urllib.parse.quote(q, safe="") + "&amp;afid=" + MERCARI_AFID


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
    trs = "".join(
        f'<tr><td class="cr r-{esc(r["r"])}">{esc(r["r"])}</td><td><a href="https://snkrdunk.com/apparels/{r["id"]}" rel="nofollow noopener" target="_blank">'
        f'{esc(r["n"])}</a></td><td class="cno">{esc(r["no"])}</td><td class="num">¥{r["p"]:,}</td><td class="num">{pct(r["p"], r.get("w"))}</td>'
        f'<td class="num">{pct(r["p"], r.get("m"))}</td><td class="num">{"少" if (r.get("k") or 0) < 3 else ""}</td>'
        f'<td class="mer"><a href="{mercari(r)}" rel="nofollow noopener" target="_blank">探す</a></td></tr>'
        for r in rows)
    rars = sorted({r["r"] for r in rows}, key=lambda x: RANK.get(x, 9))
    md = f"{int(last[5:7])}/{int(last[8:10])}"
    return (f'<section class="sinfo scards" aria-label="収録カードの相場"><h2>{esc(series)}の収録カードの相場（{"・".join(esc(x) for x in rars)}）</h2>'
            f'<p class="note">スニダンの取引の値段（未鑑定・状態Aの1枚、{md}時点の最新の取引日の平均）。高い順。「少」は30日の取引が少なく、値段がぶれやすいカードです。'
            f'型番は「弾のマーク 番号/収録数」です。名前を押すとスニダンの商品ページ、「探す」を押すとメルカリでそのカードの検索結果を開きます。</p>'
            f'<div class="tbl"><table><thead><tr><th>レア</th><th>カード</th><th>型番</th><th>相場</th><th>7日</th><th>30日</th><th></th><th>メルカリ</th></tr></thead><tbody>{trs}</tbody></table></div>'
            f'<p class="note">※値段は取引のあった日の値段で、これからの値段を約束するものではありません。</p></section>')
