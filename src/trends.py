"""お店・弾のページの下に出す「抽選の傾向」（11/14）

・これまでに掲載した抽選（state/lottery_pages.json）から、うちだけが持っている数字をまとめる
・ページの上は今までどおり「受付中の抽選の一覧」。傾向は一覧のあと（よくある質問の手前）に、たたんだ形（<details>）で出す（ユーザー希望：目立つところには入れない）
・数字はすべて自動の集計。5件未満のときは出さない
"""
import re
from collections import Counter
from datetime import datetime, date

from common import load_json

WEEK = "月火水木金土日"
GS = {"pokemon": "ポケカ", "onepiece": "ワンピースカード", "dragonball": "フュージョンワールド"}
_CACHE = {}


def _all():
    if "v" not in _CACHE:
        lp = load_json("lottery_pages.json", {})
        _CACHE["v"] = [v.get("d") or {} for v in lp.values() if isinstance(v, dict) and (v.get("d") or {}).get("store")]
    return _CACHE["v"]


def _pct(a, b):
    return f"{round(a / b * 100)}%" if b else "−"


def _method(m):
    m = m or ""
    if re.search(r"店頭", m):
        return "店頭で応募"
    if re.search(r"X|SNS", m):
        return "X・SNSで応募"
    if re.search(r"LivePocket|ライヴポケット", m, re.I):
        return "LivePocketで応募"
    if m:
        return "Web・アプリで応募"
    return ""


def _announce_days(d):
    """締切から当選発表までの日数（発表日が分かるものだけ）"""
    a, e = d.get("announce") or "", d.get("end") or ""
    try:
        ed = datetime.fromisoformat(e).date()
    except Exception:
        return None
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", a) or None
    if m:
        ad = date(int(m[1]), int(m[2]), int(m[3]))
    else:
        m = re.search(r"(\d{1,2})[/月](\d{1,2})", a)
        if not m:
            return None
        ad = date(ed.year + (1 if int(m[1]) < ed.month - 6 else 0), int(m[1]), int(m[2]))
    n = (ad - ed).days
    return n if 0 <= n <= 30 else None


def _rows(rows, esc, unit="件"):
    mx = max([v for _, v in rows] or [1]) or 1
    return ('<div class="tbl"><table class="stbl">' + "".join(
        f'<tr><td>{esc(k)}</td><td class="bar"><span style="width:{max(3, round(v / mx * 100))}%"></span></td><td class="num">{v:,}{unit}</td></tr>'
        for k, v in rows) + "</table></div>")


def _common(ds, esc, who):
    n = len(ds)
    on = sum(1 for d in ds if d.get("channel") == "online")
    st = n - on
    lines = []
    games = Counter(d.get("game") for d in ds)
    lines.append(f"<li>これまでに掲載した{who}の抽選は<b>{n:,}件</b>（" + "・".join(f"{GS.get(g, g)}{c:,}件" for g, c in games.most_common()) + "）。</li>")
    lines.append(f"<li>店頭で受け取る抽選が<b>{_pct(st, n)}</b>、自宅に届くネット抽選が{_pct(on, n)}。</li>")
    idk = [d.get("id_check") for d in ds if d.get("id_check") is not None]
    if len(idk) >= 5:
        lines.append(f"<li>本人確認がいる抽選は<b>{_pct(sum(1 for x in idk if x), len(idk))}</b>（条件が分かる{len(idk)}件のうち）。</li>")
    mem = [d.get("member") for d in ds if d.get("member")]
    if len(mem) >= 5:
        need = sum(1 for x in mem if x in ("account", "card"))
        card = sum(1 for x in mem if x == "card")
        lines.append(f"<li>会員登録・会員カードがいる抽選は<b>{_pct(need, len(mem))}</b>" + (f"（会員カード・アプリ会員証は{_pct(card, len(mem))}）" if card else "") + "。</li>")
    wd, hb = Counter(), Counter()
    for d in ds:
        try:
            dt = datetime.fromisoformat(d.get("end") or "")
        except Exception:
            continue
        wd[WEEK[dt.weekday()]] += 1
        h = dt.hour
        hb["夜21〜23時台" if 21 <= h else "夕方〜夜（18〜20時台）" if 18 <= h else "日中（12〜17時台）" if 12 <= h else "0:00・午前"] += 1
    ne = sum(wd.values())
    if ne >= 5:
        w1, c1 = wd.most_common(1)[0]
        h1, hc = hb.most_common(1)[0]
        lines.append(f"<li>締切がいちばん多い曜日は<b>{w1}曜日</b>（{_pct(c1, ne)}）、時間は<b>{h1}</b>（{_pct(hc, ne)}）。</li>")
    days = [x for x in (_announce_days(d) for d in ds) if x is not None]
    if len(days) >= 3:
        days.sort()
        med = days[len(days) // 2]
        lines.append(f"<li>締切から当選発表までは、だいたい<b>{med}日</b>（発表日が分かる{len(days)}件の真ん中の値）。</li>")
    meth = Counter(x for x in (_method(d.get("method")) for d in ds) if x)
    return lines, meth, wd, ne


def chain_html(chain_of, slug, name, esc, game=None):
    ds = [d for d in _all() if chain_of(d["store"]) == slug and (not game or d.get("game") == game)]
    if len(ds) < 5:
        return ""
    who = name + (f"の{GS.get(game, '')}" if game else "")
    lines, meth, wd, ne = _common(ds, esc, who)
    se = Counter(d.get("series") for d in ds if d.get("series"))
    if se:
        lines.append("<li>抽選が多かった商品：" + "、".join(f"「{esc(s)}」{c}件" for s, c in se.most_common(3)) + "。</li>")
    stores = len({re.sub(r"\s+", "", d["store"]) for d in ds})
    if stores >= 2:
        lines.append(f"<li>抽選があった店舗は<b>{stores}店</b>。</li>")
    body = "<ul>" + "".join(lines) + "</ul>"
    if meth:
        body += "<h3>応募のしかた</h3>" + _rows(meth.most_common(4), esc)
    if ne >= 10:
        body += "<h3>締切の曜日</h3>" + _rows([(f"{w}曜", wd[w]) for w in WEEK], esc)
    return (f'<section class="sinfo trend"><details><summary><h2>📊 {esc(who)}の抽選の傾向（これまでの{len(ds):,}件から）</h2></summary>'
            + body + '<p class="note">トレカ抽選ナビが自動で集めて掲載した抽選の集計です（<a href="/stats/">集計データ</a>）。すべての抽選を網羅するものではありません。</p></details></section>')


def series_html(chain_of, chain_name, g, x, esc):
    ds = [d for d in _all() if d.get("game") == g and (d.get("series") == x or x in (d.get("sers") or []))]
    if len(ds) < 5:
        return ""
    lines, meth, wd, ne = _common(ds, esc, f"「{x}」")
    ch = Counter(chain_name(c) for c in (chain_of(d["store"]) for d in ds) if c)
    body = "<ul>" + "".join(lines) + "</ul>"
    if ch:
        body += "<h3>抽選が多かったお店</h3>" + _rows(ch.most_common(5), esc)
    wk = Counter()
    for d in ds:
        try:
            dt = datetime.fromisoformat(d.get("found_at") or "")
        except Exception:
            continue
        mon = dt.date().toordinal() - dt.weekday()
        wk[mon] += 1
    if len(wk) >= 2:
        body += "<h3>1週間ごとに見つかった抽選</h3>" + _rows(
            [(f"{date.fromordinal(k).month}/{date.fromordinal(k).day}の週", v) for k, v in sorted(wk.items())][-8:], esc)
    return (f'<section class="sinfo trend"><details><summary><h2>📊 「{esc(x)}」の抽選の動き（これまでの{len(ds):,}件から）</h2></summary>'
            + body + '<p class="note">トレカ抽選ナビが自動で集めて掲載した抽選の集計です（<a href="/stats/">集計データ</a>）。すべての抽選を網羅するものではありません。</p></details></section>')
