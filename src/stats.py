"""/stats/ 掲載データの集計（11/12）

ねらい：「トレカ抽選ナビ」という同じ名前のサイトがほかにあり、名前で検索すると負けている（11/12）。
相手は集計ページ（/stats/）で外から引用されている。こちらは掲載数が3倍以上あるので、その数字を毎日更新の集計として出し、
ニュース・ブログ・AIの検索から「トレカ抽選ナビ（tcg-chusen.com）の集計」として引用してもらう。

使うデータ：state/lottery_pages.json（これまでに載せた抽選すべて）と、いま受付中の一覧（items）。
数字はすべて自動で集計した結果。推測の数字は入れない。
"""
import re
from collections import Counter
from datetime import datetime

from common import load_json, now

WEEK = "月火水木金土日"
GAME = {"pokemon": "ポケモンカード", "onepiece": "ONE PIECEカード", "dragonball": "フュージョンワールド"}


def _bar_table(rows, unit="件", top=None, link=None, esc=lambda x: x, rank=True):
    rows = rows[:top] if top else rows
    if not rows:
        return ""
    mx = max(v for _, v in rows) or 1
    tr = "".join(
        f'<tr><td class="rk">{i + 1 if rank else ""}</td><td>{(f"<a href={chr(34)}{link(k)}{chr(34)}>{esc(k)}</a>" if link and link(k) else esc(k))}</td>'
        f'<td class="bar"><span style="width:{max(2, round(v / mx * 100))}%"></span></td><td class="num">{v:,}{unit}</td></tr>'
        for i, (k, v) in enumerate(rows))
    return f'<div class="tbl"><table class="stbl">{tr}</table></div>'


def _pct(a, b):
    return f"{a / b * 100:.0f}%" if b else "−"


def build(items, chain_of, chain_name, chain_link, pref_link, esc):
    """→ (本文HTML, FAQ, 説明文, 見出しの数字)"""
    import trends  # 11/14：弾・お店のページの「抽選の動き」と同じ数え方（重複・却下をのぞく）にそろえる
    allv = list(trends._all())
    t = now()
    first = min((d.get("found_at") or d.get("start") or "9999")[:10] for d in allv) if allv else t.date().isoformat()
    n_all = len(allv)
    stores_all = len({re.sub(r"\s+", "", d["store"]) for d in allv})
    series_all = len({(d.get("game"), d.get("series")) for d in allv if d.get("series")})
    act = list(items)
    n_act = len(act)
    on = sum(1 for i in act if i.get("channel") == "online")
    st = n_act - on
    g_act = Counter(i.get("game") for i in act)
    g_all = Counter(d.get("game") for d in allv)
    no_id = sum(1 for i in act if i.get("id_check") is False)
    no_mem = sum(1 for i in act if (i.get("member") in (None, "", "none", False)) and "会員" not in (i.get("tags") or []))
    # お店（チェーン）別：これまでの累計
    ch = Counter()
    for d in allv:
        c = chain_of(d["store"])
        if c:
            ch[c] += 1
    ch_rows = [(chain_name(c), n) for c, n in ch.most_common(15)]
    name2slug = {chain_name(c): c for c in ch}
    # 都道府県別（店頭・いま受付中）
    pf = Counter(i.get("area") for i in act if i.get("channel") == "store" and i.get("area"))
    pf_rows = pf.most_common(15)
    # 弾別（これまでの累計）
    se = Counter(f'{d.get("series")}（{ {"pokemon": "ポケカ", "onepiece": "ワンピ", "dragonball": "FW"}.get(d.get("game"), "")}）'
                 for d in allv if d.get("series"))
    se_rows = se.most_common(12)
    # 締切の曜日・時刻（これまでの累計。締切が分かるものだけ）
    wd, hr = Counter(), Counter()
    for d in allv:
        e = d.get("end")
        try:
            dt = datetime.fromisoformat(e)
        except Exception:
            continue
        wd[WEEK[dt.weekday()]] += 1
        hr[dt.hour if not (dt.hour == 0 and dt.minute == 0) else 24] += 1
    n_end = sum(wd.values())
    wd_rows = [(f"{w}曜", wd[w]) for w in WEEK]
    hr_b = Counter()
    for h, n in hr.items():
        hr_b["〜12時" if h < 12 else "12〜18時" if h < 18 else "18〜21時" if h < 21 else "21〜23時台" if h < 24 else "0:00（日付の変わり目）"] += n
    hr_rows = [(k, hr_b[k]) for k in ("〜12時", "12〜18時", "18〜21時", "21〜23時台", "0:00（日付の変わり目）") if hr_b[k]]
    # 1週間ごとに見つけた数
    wk = load_json("weekly.json", {})
    wk_rows = [(f"{k[5:7].lstrip('0')}/{k[8:10].lstrip('0')}の週", len(v)) for k, v in sorted(wk.items()) if isinstance(v, dict)]
    md = f"{t.month}/{t.day}"
    top_pf = pf_rows[0] if pf_rows else None
    top_ch = ch_rows[0] if ch_rows else None
    lead = (f"トレカ抽選ナビ（tcg-chusen.com）が{int(first[5:7])}月{int(first[8:10])}日から自動で集めて掲載した、"
            f"ポケモンカード・ONE PIECEカードなどの抽選販売{n_all:,}件（{stores_all:,}店・{series_all}商品）の集計です。"
            f"{md}時点で受付中の抽選は{n_act}件で、そのうち店頭抽選が{st}件（{_pct(st, n_act)}）、ネット抽選が{on}件でした。")
    head = (f'<div class="stat-cards">'
            f'<div><b>{n_all:,}</b><span>これまでに掲載した抽選</span></div>'
            f'<div><b>{n_act:,}</b><span>いま受付中（{md}）</span></div>'
            f'<div><b>{stores_all:,}</b><span>販売元のお店</span></div>'
            f'<div><b>{_pct(st, n_act)}</b><span>店頭抽選の割合</span></div></div>')
    sec = []
    sec.append("<h2>いま受付中の抽選の内訳</h2>"
               + _bar_table([("店頭抽選（店頭受取）", st), ("ネット抽選（発送）", on)], esc=esc, rank=False)
               + _bar_table([(GAME.get(g, g), n) for g, n in g_act.most_common()], esc=esc)
               + f"<p>本人確認がいらない抽選は{no_id}件（{_pct(no_id, n_act)}）、会員登録がいらない抽選は{no_mem}件（{_pct(no_mem, n_act)}）です。"
               f'条件で絞り込んだ一覧は<a href="/pokeka/no-id/">本人確認なし</a>のページから見られます。</p>')
    sec.append("<h2>抽選が多いお店（これまでの累計）</h2>" + _bar_table(ch_rows, link=lambda k: chain_link(name2slug.get(k)), esc=esc))
    sec.append(f"<h2>店頭抽選が多い都道府県（{md}時点で受付中）</h2>" + _bar_table(pf_rows, link=pref_link, esc=esc))
    sec.append("<h2>抽選が多かった弾・商品（これまでの累計）</h2>" + _bar_table(se_rows, esc=esc))
    if n_end:
        sec.append(f"<h2>締切の曜日（これまでの累計・締切が分かる{n_end:,}件）</h2>" + _bar_table(wd_rows, esc=esc, rank=False)
                   + "<h2>締切の時刻</h2>" + _bar_table(hr_rows, esc=esc, rank=False))
    if wk_rows:
        sec.append("<h2>1週間ごとに新しく見つかった抽選</h2>" + _bar_table(wk_rows, esc=esc, rank=False))
    gall = "・".join(f"{GAME.get(g, g)}{n:,}件" for g, n in g_all.most_common())
    sec.append("<h2>集計のしかた・引用について</h2>"
               f"<p>トレカ抽選ナビが、お店の公式サイト・公式SNS・応募ページなどから1日6回自動で集めた抽選販売の情報を集計しています（これまでの内訳：{esc(gall)}）。"
               "同じ抽選を別の情報元から見つけたときは1件にまとめています。すべての抽選を網羅するものではありません。</p>"
               "<p>数字は毎日自動で更新されます。記事・動画・SNSで使うときは「トレカ抽選ナビ（tcg-chusen.com）調べ」と出典を書き、このページにリンクしてください。</p>")
    faq = [
        (f"いま受付中のトレカの抽選は何件ありますか？", f"{md}時点で{n_act}件です（店頭抽選{st}件・ネット抽選{on}件）。"),
        ("トレカの抽選はネットと店頭どちらが多いですか？", f"{md}時点で受付中の抽選の{_pct(st, n_act)}が店頭抽選（店頭受取）です。"),
    ]
    if top_ch:
        faq.append(("抽選がいちばん多いお店はどこですか？", f"これまでに掲載した抽選では{top_ch[0]}がいちばん多く、{top_ch[1]}件です。"))
    if top_pf:
        faq.append(("店頭抽選がいちばん多い都道府県はどこですか？", f"{md}時点で受付中の店頭抽選は{top_pf[0]}が{top_pf[1]}件でいちばん多いです。"))
    body = '<div class="guide stats">' + f"<p>{esc(lead)}</p>" + head + "".join(sec) + "</div>"
    return body, faq, lead, (n_all, n_act)
